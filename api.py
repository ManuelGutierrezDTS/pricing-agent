# api.py
"""
FastAPI Wrapper for Pricing Agent
Exposes pricing analysis as REST API endpoints
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import sys
import json
from datetime import datetime
import numpy as np
import pandas as pd

# Import pricing agent modules
from config import PATH_CONFIG
from modules.data.unity_catalog import check_and_refresh_unity
from modules.analysis.integrated import run_integrated_analysis
from modules.utils.vooma_logger import get_vooma_logger
from modules.ai.ai_rec import get_ai_recommendation_engine

# Initialize FastAPI
app = FastAPI(
    title="DTS Pricing Agent API",
    description="Advanced freight pricing analysis and validation system",
    version="3.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variable para Unity Catalog (cargado una vez)
unity_df = None


# ==========================================================================================
# HELPER FUNCTIONS
# ==========================================================================================

def convert_numpy_types(obj):
    """Recursively convert numpy types to Python native types for JSON serialization"""
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    else:
        return obj


# ==========================================================================================
# PYDANTIC MODELS
# ==========================================================================================

class Stop(BaseModel):
    """Stop model for pickup/delivery locations"""
    type: str = Field(..., description="PICKUP or DROP")
    zip: str = Field(..., description="ZIP code (5 digits)")

class PricingRequest(BaseModel):
    """Request model for pricing analysis"""
    proposed_price: float = Field(..., description="Proposed customer price", gt=0)
    carrier_cost: str | float = Field(default="auto", description="Carrier cost or 'auto' for automatic calculation")
    stops: List[Stop] = Field(..., description="List of stops (at least 2: 1 PICKUP + 1 DROP)", min_length=2)
    customer_name: str = Field(..., description="Customer name")
    equipment_type: str = Field(..., description="Equipment type (e.g., FLATBED, VAN, REEFER, HOTSHOT)")
    pickup_date: Optional[str] = Field(None, description="Pickup date (YYYY-MM-DD) - optional")
    delivery_date: Optional[str] = Field(None, description="Delivery date (YYYY-MM-DD) - optional")
    weight: Optional[float] = Field(None, description="Load weight in lbs - optional")
    quote_id: Optional[str] = Field(None, description="Vooma quote ID - optional")

    class Config:
        json_schema_extra = {
            "example": {
                "quote_id": "VOOMA-12345",
                "proposed_price": 1500,
                "carrier_cost": "auto",
                "stops": [
                    {"type": "PICKUP", "zip": "60160"},
                    {"type": "DROP", "zip": "53703"}
                ],
                "customer_name": "SureBuilt",
                "equipment_type": "HOTSHOT",
                "pickup_date": "2025-01-15",
                "delivery_date": "2025-01-17",
                "weight": 6036
            }
        }

class PricingResponse(BaseModel):
    """Response model for pricing analysis"""
    success: bool
    timestamp: str
    analysis_results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_seconds: Optional[float] = None


class VoomaSimplifiedResponse(BaseModel):
    """Simplified response for Vooma integration"""
    quote_id: str
    evaluation: Dict[str, Any]
    pricing: Dict[str, Any]
    recommendation: str
    execution_time_seconds: float


class AIRecommendationRequest(BaseModel):
    """Request model for AI recommendation"""
    validation_result: Dict[str, Any] = Field(..., description="Full pricing analysis results from /api/v1/analyze")
    context_prompt: Optional[str] = Field(
        "We're running out to Christmas season",
        description="Editable business context for the recommendation"
    )
    max_lines: Optional[int] = Field(4, description="Maximum lines for recommendation", ge=1, le=10)

    class Config:
        json_schema_extra = {
            "example": {
                "validation_result": {
                    "final_rating": "POOR",
                    "combined_confidence": 85,
                    "suggested_price": 1162.00,
                    "negotiation_range": {
                        "proposed_price": 1500.00,
                        "carrier_cost": 1025.00
                    },
                    "prc_validation": {
                        "rating": "POOR",
                        "recommendation": "Pricing far outside historical ranges",
                        "proposed_margin_pct": 31.67,
                        "flags": ["margin_high_warning", "Above 75th percentile"]
                    }
                },
                "context_prompt": "Christmas season, customer is loyal, prioritize closing",
                "max_lines": 4
            }
        }


class AIRecommendationResponse(BaseModel):
    """Response model for AI recommendation"""
    success: bool
    recommendation: str
    context_used: str
    execution_time_seconds: float


# ==========================================================================================
# STARTUP/SHUTDOWN EVENTS
# ==========================================================================================

@app.on_event("startup")
async def startup_event():
    """Load Unity Catalog on startup"""
    global unity_df
    try:
        print("🔄 Loading Unity Catalog on startup...")
        unity_df = check_and_refresh_unity()
        print(f"✅ Unity Catalog loaded: {len(unity_df)} records")
    except Exception as e:
        print(f"❌ Error loading Unity Catalog on startup: {e}")
        unity_df = None

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 Shutting down Pricing Agent API...")


# ==========================================================================================
# ENDPOINTS
# ==========================================================================================

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "DTS Pricing Agent API",
        "version": "3.2.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "/api/v1/analyze",
            "vooma_analyze": "/api/v1/vooma/analyze",
            "ai_recommendation": "/api/v1/ai-recommendation",
            "ai_recommendation_structured": "/api/v1/ai-recommendation/structured",
            "docs": "/docs",
            "redoc": "/redoc"
        },
        "unity_catalog_loaded": unity_df is not None,
        "unity_records": len(unity_df) if unity_df is not None else 0
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "unity_catalog_loaded": unity_df is not None,
        "unity_records": len(unity_df) if unity_df is not None else 0
    }

@app.post("/api/v1/analyze", response_model=PricingResponse)
async def analyze_pricing(request: PricingRequest):
    """
    Analyze freight pricing and provide recommendations
    
    This endpoint processes a pricing request through the complete pricing engine:
    - Validates against historical data (Unity Catalog)
    - Queries external APIs (DAT, GreenScreens)
    - Calculates negotiation ranges
    - Provides accept/reject recommendation
    
    Returns detailed analysis with confidence scores and suggested actions.
    
    NOTE: This endpoint does NOT log executions to CSV. Use /api/v1/vooma/analyze for logging.
    """
    start_time = datetime.utcnow()
    
    try:
        # Check if Unity Catalog is loaded
        if unity_df is None:
            raise HTTPException(
                status_code=503,
                detail="Unity Catalog not loaded. Service unavailable."
            )
        
        # Convert request to config format
        analysis_config = {
            "proposed_price": request.proposed_price,
            "carrier_cost": request.carrier_cost,
            "stops": [{"type": s.type, "zip": s.zip} for s in request.stops],
            "customer_name": request.customer_name,
            "equipment_type": request.equipment_type,
            "pickup_date": request.pickup_date,
            "delivery_date": request.delivery_date,
            "weight": request.weight,
        }
        
        # Run integrated analysis
        results = run_integrated_analysis(unity_df, analysis_config)
        
        # 🔧 FIX: Convert numpy types to Python native types
        results = convert_numpy_types(results)
        
        # Check for errors in results
        if "error" in results:
            raise HTTPException(
                status_code=400,
                detail=f"Analysis error: {results['error']}"
            )
        
        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        
        # ❌ NO LOGGING FOR THIS ENDPOINT - Only /api/v1/vooma/analyze logs to CSV
        
        # Return response
        return PricingResponse(
            success=True,
            timestamp=datetime.utcnow().isoformat(),
            analysis_results=results,
            execution_time_seconds=round(execution_time, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in analyze_pricing: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.post("/api/v1/vooma/analyze", response_model=VoomaSimplifiedResponse)
async def vooma_analyze_pricing(request: PricingRequest):
    """
    Vooma-specific endpoint with simplified response
    
    This endpoint is designed for Vooma integration and returns a simplified response
    with only the essential information needed for the UI:
    - Rating and action (APPROVE/REJECT/REVIEW)
    - Recommended pricing
    - Brief recommendation text
    
    ✅ LOGS EVERY EXECUTION to CSV in Azure Blob Storage (voomalogsdts/pricing-logs/vooma_pricing_history.csv)
    """
    start_time = datetime.utcnow()
    
    try:
        # Require quote_id for Vooma endpoint
        if not request.quote_id:
            raise HTTPException(
                status_code=400,
                detail="quote_id is required for Vooma endpoint"
            )
        
        # Check if Unity Catalog is loaded
        if unity_df is None:
            raise HTTPException(
                status_code=503,
                detail="Unity Catalog not loaded. Service unavailable."
            )
        
        # Convert request to config format
        analysis_config = {
            "proposed_price": request.proposed_price,
            "carrier_cost": request.carrier_cost,
            "stops": [{"type": s.type, "zip": s.zip} for s in request.stops],
            "customer_name": request.customer_name,
            "equipment_type": request.equipment_type,
            "pickup_date": request.pickup_date,
            "delivery_date": request.delivery_date,
            "weight": request.weight,
        }
        
        # Run integrated analysis
        results = run_integrated_analysis(unity_df, analysis_config)
        
        # Convert numpy types
        results = convert_numpy_types(results)
        
        # Check for errors
        if "error" in results:
            raise HTTPException(
                status_code=400,
                detail=f"Analysis error: {results['error']}"
            )
        
        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Determine action based on rating and confidence
        final_rating = results.get("final_rating", "NO_DATA")
        combined_confidence = results.get("combined_confidence", 0)
        
        if final_rating == "NO_DATA" or combined_confidence < 30:
            action = "REVIEW"
        elif final_rating in ["EXCELLENT", "GOOD"]:
            action = "APPROVE"
        elif final_rating == "ACCEPTABLE" and combined_confidence >= 60:
            action = "REVIEW"
        else:
            action = "REJECT"
        
        # Build simplified response
        simplified_response = VoomaSimplifiedResponse(
            quote_id=request.quote_id,
            evaluation={
                "rating": final_rating,
                "action": action,
                "confidence": combined_confidence
            },
            pricing={
                "proposed_price": request.proposed_price,
                "recommended_price": results.get("suggested_price"),
                "carrier_cost": results.get("negotiation_range", {}).get("carrier_cost"),
                "proposed_margin_pct": results.get("prc_validation", {}).get("proposed_margin_pct"),
                "suggested_margin_pct": results.get("suggested_margin_pct")
            },
            recommendation=results.get("prc_validation", {}).get("recommendation", "No recommendation available"),
            execution_time_seconds=round(execution_time, 2)
        )
        
        # ✅ LOG TO CSV - This is the ONLY endpoint that logs
        try:
            logger = get_vooma_logger()
            logger.log_execution(
                quote_id=request.quote_id,
                request_data=request.dict(),
                analysis_results=results,
                execution_time=execution_time,
                user="vooma_user"
            )
            print(f"✅ Logged Vooma execution: {request.quote_id}")
        except Exception as log_error:
            print(f"⚠️ Warning: Could not log execution: {log_error}")
        
        return simplified_response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in vooma_analyze_pricing: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.post("/api/v1/ai-recommendation", response_model=AIRecommendationResponse)
async def get_ai_recommendation(request: AIRecommendationRequest):
    """
    Generate AI-powered sales recommendation based on pricing analysis
    
    This endpoint takes the full pricing analysis result from /api/v1/analyze and generates
    a concise, sales-oriented recommendation using OpenAI GPT.
    
    The context_prompt is fully editable to reflect current business conditions:
    - "Christmas season, customer is loyal, prioritize closing"
    - "End of quarter push, need to close deals"
    - "Tight margin month, need profitability"
    - "Customer is price-sensitive, competitor quoted lower"
    
    Returns a 4-line actionable sales recommendation.
    """
    start_time = datetime.utcnow()
    
    try:
        # Get AI engine
        ai_engine = get_ai_recommendation_engine()
        
        # Generate recommendation
        recommendation = ai_engine.generate_recommendation(
            validation_result=request.validation_result,
            context_prompt=request.context_prompt,
            max_lines=request.max_lines
        )
        
        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        
        return AIRecommendationResponse(
            success=True,
            recommendation=recommendation,
            context_used=request.context_prompt,
            execution_time_seconds=round(execution_time, 2)
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {str(e)}. Please ensure OPENAI_API_KEY is set."
        )
    except Exception as e:
        print(f"❌ Error generating AI recommendation: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendation: {str(e)}"
        )


@app.post("/api/v1/ai-recommendation/structured")
async def get_ai_recommendation_structured(request: AIRecommendationRequest):
    """
    Generate structured AI recommendation with additional metadata
    
    Returns a more detailed response including:
    - AI-generated recommendation text
    - Confidence level (HIGH/MEDIUM/LOW)
    - Key factors affecting the recommendation
    - Suggested action (APPROVE/ADJUST_PRICE/REVIEW)
    - Business context used
    
    This endpoint provides more comprehensive information for decision-making.
    """
    start_time = datetime.utcnow()
    
    try:
        # Get AI engine
        ai_engine = get_ai_recommendation_engine()
        
        # Generate structured recommendation
        result = ai_engine.generate_recommendation_structured(
            validation_result=request.validation_result,
            context_prompt=request.context_prompt
        )
        
        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "success": True,
            "recommendation": result["recommendation"],
            "confidence_level": result["confidence_level"],
            "key_factors": result["key_factors"],
            "suggested_action": result["suggested_action"],
            "context_used": request.context_prompt,
            "execution_time_seconds": round(execution_time, 2)
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {str(e)}. Please ensure OPENAI_API_KEY is set."
        )
    except Exception as e:
        print(f"❌ Error generating AI recommendation: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendation: {str(e)}"
        )


@app.get("/api/v1/unity/refresh")
async def refresh_unity(background_tasks: BackgroundTasks):
    """
    Refresh Unity Catalog data
    
    This endpoint triggers a background refresh of the Unity Catalog
    from Azure Blob Storage or local file.
    """
    def refresh_task():
        global unity_df
        try:
            print("🔄 Refreshing Unity Catalog...")
            unity_df = check_and_refresh_unity()
            print(f"✅ Unity Catalog refreshed: {len(unity_df)} records")
        except Exception as e:
            print(f"❌ Error refreshing Unity Catalog: {e}")
    
    background_tasks.add_task(refresh_task)
    
    return {
        "message": "Unity Catalog refresh started in background",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/config")
async def get_configuration():
    """
    Get current configuration (non-sensitive data only)
    
    Returns configuration parameters without exposing API keys or secrets.
    """
    from config import (
        HOTSHOT_CONFIG,
        MULTISTOP_CONFIG,
        NEGOTIATION_CONFIG,
        PRC_CONFIG,
        RATING_THRESHOLDS
    )
    
    # Return only non-sensitive config
    safe_multistop = MULTISTOP_CONFIG.copy()
    safe_multistop.pop("google_api_key", None)
    
    return {
        "hotshot_config": HOTSHOT_CONFIG,
        "multistop_config": safe_multistop,
        "negotiation_config": NEGOTIATION_CONFIG,
        "prc_config": PRC_CONFIG,
        "rating_thresholds": RATING_THRESHOLDS,
    }


# ==========================================================================================
# ERROR HANDLERS
# ==========================================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return {
        "error": "Not Found",
        "message": f"The requested endpoint does not exist: {request.url.path}",
        "available_endpoints": ["/", "/health", "/api/v1/analyze", "/api/v1/vooma/analyze", "/api/v1/ai-recommendation", "/docs"]
    }

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors"""
    return {
        "error": "Internal Server Error",
        "message": "An unexpected error occurred. Please check logs.",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
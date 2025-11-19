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

# Import pricing agent modules
from config import PATH_CONFIG
from modules.data.unity_catalog import check_and_refresh_unity
from modules.analysis.integrated import run_integrated_analysis

# Initialize FastAPI
app = FastAPI(
    title="DTS Pricing Agent API",
    description="Advanced freight pricing analysis and validation system",
    version="3.0.0",
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
    stops: List[Stop] = Field(..., description="List of stops (at least 2: 1 PICKUP + 1 DROP)", min_items=2)
    customer_name: str = Field(..., description="Customer name")
    equipment_type: str = Field(..., description="Equipment type (e.g., FLATBED, VAN, REEFER, HOTSHOT)")
    pickup_date: Optional[str] = Field(None, description="Pickup date (YYYY-MM-DD) - optional")
    delivery_date: Optional[str] = Field(None, description="Delivery date (YYYY-MM-DD) - optional")
    weight: Optional[float] = Field(None, description="Load weight in lbs - optional")

    class Config:
        json_schema_extra = {
            "example": {
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
        "version": "3.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "/api/v1/analyze",
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
        
        # Check for errors in results
        if "error" in results:
            raise HTTPException(
                status_code=400,
                detail=f"Analysis error: {results['error']}"
            )
        
        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        
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
        "available_endpoints": ["/", "/health", "/api/v1/analyze", "/docs"]
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
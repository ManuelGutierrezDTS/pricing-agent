# modules/ai/ai_rec.py
"""
AI Recommendation Module
Generates sales-oriented recommendations using OpenAI GPT based on pricing analysis
"""

import os
from openai import OpenAI
from typing import Dict, Any, Optional


class AIRecommendationEngine:
    """OpenAI-powered recommendation engine for pricing decisions"""
    
    def __init__(self):
        """Initialize OpenAI client"""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Default to gpt-4o-mini for speed/cost
    
    
    def _build_analysis_summary(self, validation_result: Dict[str, Any]) -> str:
        """Build a concise summary of the pricing analysis for the prompt"""
        
        # Extract key metrics
        rating = validation_result.get("final_rating", "UNKNOWN")
        confidence = validation_result.get("combined_confidence", 0)
        proposed_price = validation_result.get("negotiation_range", {}).get("proposed_price", 0)
        suggested_price = validation_result.get("suggested_price", 0)
        carrier_cost = validation_result.get("negotiation_range", {}).get("carrier_cost", 0)
        
        # PRC validation
        prc = validation_result.get("prc_validation", {})
        prc_rating = prc.get("rating", "UNKNOWN")
        prc_recommendation = prc.get("recommendation", "No recommendation")
        proposed_margin = prc.get("proposed_margin_pct", 0)
        
        # Build summary
        summary = f"""
PRICING ANALYSIS SUMMARY:
- Overall Rating: {rating}
- Confidence: {confidence}%
- Proposed Price: ${proposed_price:,.2f}
- Suggested Price: ${suggested_price:,.2f}
- Carrier Cost: ${carrier_cost:,.2f}
- Proposed Margin: {proposed_margin:.1f}%
- PRC Rating: {prc_rating}
- Recommendation: {prc_recommendation}
"""
        
        # Add flags if present
        flags = prc.get("flags", [])
        if flags:
            summary += f"\n- Warning Flags: {', '.join(flags)}"
        
        return summary.strip()
    
    
    def generate_recommendation(
        self,
        validation_result: Dict[str, Any],
        context_prompt: Optional[str] = None,
        max_lines: int = 4
    ) -> str:
        """
        Generate AI-powered sales recommendation
        
        Args:
            validation_result: Full pricing analysis results
            context_prompt: Editable context (e.g., "Christmas season", "End of quarter")
            max_lines: Maximum number of lines for the recommendation
        
        Returns:
            AI-generated sales recommendation
        """
        
        # Default context if not provided
        if not context_prompt:
            context_prompt = "We're running out to Christmas season"
        
        # Build analysis summary
        analysis_summary = self._build_analysis_summary(validation_result)
        
        # Build the full prompt
        system_prompt = """You are a sales advisor for a freight logistics company. 
Your job is to provide concise, actionable sales recommendations based on pricing analysis results.
Your recommendations should be:
- Sales-oriented (focused on winning deals while maintaining margins)
- Concise (maximum 4 lines)
- Action-oriented (what to do with the final price)
- Considerate of the business context provided"""
        
        user_prompt = f"""{analysis_summary}

BUSINESS CONTEXT: {context_prompt}

Based on the pricing analysis above and the business context, provide a SHORT and CONCISE sales recommendation.
Focus on what action to take with the final price.
Maximum {max_lines} lines.
Be direct and actionable."""
        
        try:
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            # Extract recommendation
            recommendation = response.choices[0].message.content.strip()
            
            return recommendation
            
        except Exception as e:
            print(f"❌ Error calling OpenAI API: {e}")
            return f"Error generating AI recommendation: {str(e)}"
    
    
    def generate_recommendation_structured(
        self,
        validation_result: Dict[str, Any],
        context_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate structured recommendation with additional metadata
        
        Returns:
            {
                "recommendation": str,
                "confidence_level": str,
                "key_factors": list,
                "suggested_action": str
            }
        """
        
        # Get basic recommendation
        basic_rec = self.generate_recommendation(validation_result, context_prompt)
        
        # Extract confidence level from analysis
        confidence = validation_result.get("combined_confidence", 0)
        if confidence >= 80:
            confidence_level = "HIGH"
        elif confidence >= 60:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "LOW"
        
        # Extract key factors
        prc = validation_result.get("prc_validation", {})
        flags = prc.get("flags", [])
        rating = validation_result.get("final_rating", "UNKNOWN")
        
        # Determine suggested action
        if rating in ["EXCELLENT", "GOOD"]:
            suggested_action = "APPROVE"
        elif rating == "ACCEPTABLE":
            suggested_action = "REVIEW"
        else:
            suggested_action = "ADJUST_PRICE"
        
        return {
            "recommendation": basic_rec,
            "confidence_level": confidence_level,
            "key_factors": flags if flags else ["No major concerns"],
            "suggested_action": suggested_action
        }


# Singleton instance
_ai_engine = None

def get_ai_recommendation_engine() -> AIRecommendationEngine:
    """Get singleton instance of AIRecommendationEngine"""
    global _ai_engine
    if _ai_engine is None:
        _ai_engine = AIRecommendationEngine()
    return _ai_engine
# modules/utils/vooma_logger.py
"""
Vooma Logger - Saves pricing analysis executions to Azure Blob CSV
For future ML training and auditing
"""

import pandas as pd
from datetime import datetime
from azure.storage.blob import BlobServiceClient
import io
import os


class VoomaLogger:
    """Logger for Vooma pricing executions"""
    
    def __init__(self):
        """Initialize Azure Blob connection for Vooma logs ONLY"""
        # USE ONLY VOOMA STORAGE - NO FALLBACK TO DATABRICKS
        self.account_name = os.getenv("VOOMA_STORAGE_ACCOUNT", "voomalogsdts")
        self.account_key = os.getenv("VOOMA_STORAGE_KEY", "")
        self.container_name = os.getenv("VOOMA_STORAGE_CONTAINER", "pricing-logs")
        self.blob_name = "vooma_pricing_history.csv"
        
        # Connection string
        self.connection_string = f"DefaultEndpointsProtocol=https;AccountName={self.account_name};AccountKey={self.account_key};EndpointSuffix=core.windows.net"
        
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
            self.container_client = self.blob_service_client.get_container_client(self.container_name)
            self.blob_client = self.container_client.get_blob_client(self.blob_name)
        except Exception as e:
            print(f"⚠️ Warning: Could not connect to Azure Blob: {e}")
            self.blob_client = None
    
    
    def _download_existing_csv(self) -> pd.DataFrame:
        """Download existing CSV from blob, or return empty DataFrame"""
        try:
            if self.blob_client and self.blob_client.exists():
                download_stream = self.blob_client.download_blob()
                csv_data = download_stream.readall()
                df = pd.read_csv(io.BytesIO(csv_data))
                print(f"📥 Downloaded existing CSV: {len(df)} records")
                return df
            else:
                print("📝 No existing CSV found, creating new")
                return pd.DataFrame()
        except Exception as e:
            print(f"⚠️ Error downloading CSV: {e}")
            return pd.DataFrame()
    
    
    def _upload_csv(self, df: pd.DataFrame):
        """Upload DataFrame to blob as CSV"""
        try:
            if self.blob_client is None:
                print("⚠️ Blob client not available, skipping upload")
                return False
            
            # Convert DataFrame to CSV bytes
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_bytes = csv_buffer.getvalue().encode('utf-8')
            
            # Upload with overwrite
            self.blob_client.upload_blob(csv_bytes, overwrite=True)
            print(f"📤 Uploaded CSV: {len(df)} records")
            return True
        except Exception as e:
            print(f"❌ Error uploading CSV: {e}")
            return False
    
    
    def log_execution(
        self,
        quote_id: str,
        request_data: dict,
        analysis_results: dict,
        execution_time: float,
        user: str = "vooma_user"
    ):
        """
        Log a pricing execution to CSV
        
        Args:
            quote_id: Vooma quote ID
            request_data: Original request payload
            analysis_results: Full analysis results from pricing agent
            execution_time: Execution time in seconds
            user: User who made the request (default: vooma_user)
        """
        try:
            # Download existing CSV
            df = self._download_existing_csv()
            
            # Prepare new row
            # Determine if multistop (more than 2 stops = 1 PICKUP + multiple DROPs)
            total_stops = len(request_data.get("stops", []))
            is_multistop = total_stops > 2
            
            new_row = {
                # Metadata
                "timestamp": datetime.utcnow().isoformat(),
                "quote_id": quote_id,
                "user": user,
                "execution_time_seconds": execution_time,
                
                # Input data
                "proposed_price": request_data.get("proposed_price"),
                "carrier_cost_input": request_data.get("carrier_cost"),
                "customer_name": request_data.get("customer_name"),
                "equipment_type": request_data.get("equipment_type"),
                "weight": request_data.get("weight"),
                "pickup_date": request_data.get("pickup_date"),
                "delivery_date": request_data.get("delivery_date"),
                
                # Stops
                "origin_zip": request_data.get("stops", [{}])[0].get("zip") if request_data.get("stops") else None,
                "destination_zip": request_data.get("stops", [{}])[-1].get("zip") if len(request_data.get("stops", [])) > 1 else None,
                "total_stops": total_stops,
                "is_multistop": is_multistop,
                
                # Analysis results
                "final_rating": analysis_results.get("final_rating"),
                "combined_confidence": analysis_results.get("combined_confidence"),
                "suggested_price": analysis_results.get("suggested_price"),
                "carrier_cost_calculated": analysis_results.get("negotiation_range", {}).get("carrier_cost"),
                "proposed_margin_pct": analysis_results.get("prc_validation", {}).get("proposed_margin_pct"),
                "suggested_margin_pct": analysis_results.get("suggested_margin_pct"),
                
                # PRC validation
                "prc_rating": analysis_results.get("prc_validation", {}).get("rating"),
                "prc_confidence": analysis_results.get("prc_validation", {}).get("confidence_score"),
                "prc_recommendation": analysis_results.get("prc_validation", {}).get("recommendation"),
                
                # Historical data
                "hist_confidence": analysis_results.get("id_analysis", {}).get("HistConfidence"),
                "records_analyzed_lane": analysis_results.get("id_analysis", {}).get("RecordsAnalyzed_Lane"),
                "records_analyzed_zip3": analysis_results.get("id_analysis", {}).get("RecordsAnalyzed_Zip3"),
                
                # Market data
                "dat_rate_usd": analysis_results.get("dat_api_data", {}).get("rates_mci", {}).get("rateUsd"),
                "dat_forecast_usd": analysis_results.get("dat_api_data", {}).get("rates_mci", {}).get("total_forecastUSD"),
                "gs_target_rate": analysis_results.get("greenscreens_api_data", {}).get("RateForecast", {}).get("total_targetBuyRate"),
                
                # Flags
                "has_flags": len(analysis_results.get("prc_validation", {}).get("flags", [])) > 0,
                "flags": ", ".join(analysis_results.get("prc_validation", {}).get("flags", [])),
            }
            
            # Append new row
            new_df = pd.DataFrame([new_row])
            df = pd.concat([df, new_df], ignore_index=True)
            
            # Upload to blob
            success = self._upload_csv(df)
            
            if success:
                print(f"✅ Logged execution for quote_id: {quote_id}")
            else:
                print(f"⚠️ Could not log execution for quote_id: {quote_id}")
            
            return success
            
        except Exception as e:
            print(f"❌ Error logging execution: {e}")
            import traceback
            traceback.print_exc()
            return False


# Singleton instance
_vooma_logger = None

def get_vooma_logger() -> VoomaLogger:
    """Get singleton instance of VoomaLogger"""
    global _vooma_logger
    if _vooma_logger is None:
        _vooma_logger = VoomaLogger()
    return _vooma_logger
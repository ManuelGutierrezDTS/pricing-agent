# modules/apis/greenscreens_api.py
"""
GreenScreens AI API Integration
Maneja autenticación y consultas a GreenScreens API
"""

import requests
import time
from typing import Optional, Dict
from datetime import datetime
from config import (
    GS_CLIENT_ID, GS_CLIENT_SECRET, GS_AUTH_URL,
    API_RETRY_CONFIG
)
from modules.logic.equipment import map_equipment_for_api


def get_greenscreens_token() -> Optional[str]:
    """Get GreenScreens auth token"""
    try:
        headers = {"content-type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": GS_CLIENT_ID,
            "client_secret": GS_CLIENT_SECRET,
        }
        resp = requests.post(GS_AUTH_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:
        print(f"❌ Error getting GreenScreens token: {e}")
        return None


def fetch_greenscreens_rates(token: str, pickup_date: str, origin_city: str, 
                             origin_state: str, dest_city: str, dest_state: str, 
                             equipment: str) -> Optional[Dict]:
    """Fetch rates from GreenScreens API"""
    
    mapped_equipment = map_equipment_for_api(equipment)
    
    base_payload = {
        "pickupDateTime": pickup_date,
        "transportType": mapped_equipment,
        "stops": [
            {"order": 0, "country": "US", "city": origin_city, "state": origin_state},
            {"order": 1, "country": "US", "city": dest_city, "state": dest_state},
        ],
        "commodity": "General",
        "tag": "GreenScreensLane",
        "currency": "USD",
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    forecast_url = "https://api.greenscreens.ai/v3/prediction/rates"
    network_url = "https://api.greenscreens.ai/v3/prediction/network-rates"
    
    result = {}
    
    # Forecast API
    try:
        r = requests.post(forecast_url, json=base_payload, headers=headers, timeout=45)
        r.raise_for_status()
        data = r.json()
        
        distance = data.get("distance", 0) or 0
        low = data.get("lowBuyRate", 0) or 0
        high = data.get("highBuyRate", 0) or 0
        start = data.get("startBuyRate", 0) or 0
        target = data.get("targetBuyRate", 0) or 0
        
        result["RateForecast"] = {
            "source": "forecast",
            "confidenceLevel": data.get("confidenceLevel"),
            "distance": distance,
            "fuelRate": data.get("fuelRate", 0) or 0,
            "rate_lowBuyRate": low,
            "rate_highBuyRate": high,
            "rate_startBuyRate": start,
            "rate_targetBuyRate": target,
            "total_lowBuyRate": round(low * distance, 2),
            "total_highBuyRate": round(high * distance, 2),
            "total_startBuyRate": round(start * distance, 2),
            "total_targetBuyRate": round(target * distance, 2),
        }
        
        print(f"   ✅ GreenScreens forecast - Target: ${target}/mile")
        
    except Exception as e:
        print(f"   ⚠️ GreenScreens forecast failed: {e}")
    
    # Network API
    try:
        r = requests.post(network_url, json=base_payload, headers=headers, timeout=45)
        r.raise_for_status()
        data = r.json()
        
        distance = data.get("distance", 0) or 0
        low = data.get("lowBuyRate", 0) or 0
        high = data.get("highBuyRate", 0) or 0
        start = data.get("startBuyRate", 0) or 0
        target = data.get("targetBuyRate", 0) or 0
        
        result["RateNetwork"] = {
            "source": "network",
            "confidenceLevel": data.get("confidenceLevel"),
            "distance": distance,
            "fuelRate": data.get("fuelRate", 0) or 0,
            "rate_lowBuyRate": low,
            "rate_highBuyRate": high,
            "rate_startBuyRate": start,
            "rate_targetBuyRate": target,
            "total_lowBuyRate": round(low * distance, 2),
            "total_highBuyRate": round(high * distance, 2),
            "total_startBuyRate": round(start * distance, 2),
            "total_targetBuyRate": round(target * distance, 2),
        }
        
        print(f"   ✅ GreenScreens network - Target: ${target}/mile")
        
    except Exception as e:
        print(f"   ⚠️ GreenScreens network failed: {e}")
    
    return result if result else None


def get_greenscreens_data_with_retry(pickup_date, origin_city: str, origin_state: str,
                                     dest_city: str, dest_state: str, 
                                     equipment: str) -> Optional[Dict]:
    """Get GreenScreens data with retry logic"""
    
    print(f"\n🔍 Fetching GreenScreens data: {origin_city}, {origin_state} → {dest_city}, {dest_state}")
    
    if isinstance(pickup_date, datetime):
        pickup_iso = pickup_date.strftime("%Y-%m-%dT00:00:00Z")
    else:
        pickup_iso = pickup_date
    
    for attempt in range(API_RETRY_CONFIG["max_retries"] + 1):
        if attempt > 0:
            print(f"   🔄 Retry attempt {attempt}/{API_RETRY_CONFIG['max_retries']}")
            time.sleep(API_RETRY_CONFIG["retry_delay_seconds"])
        
        try:
            token = get_greenscreens_token()
            if not token:
                continue
            
            result = fetch_greenscreens_rates(
                token, pickup_iso, origin_city, origin_state, dest_city, dest_state, equipment
            )
            
            if result:
                return result
            
        except Exception as e:
            print(f"   ❌ GreenScreens API attempt {attempt + 1} failed: {e}")
            if attempt == API_RETRY_CONFIG["max_retries"]:
                print(f"   ❌ GreenScreens API failed after {attempt + 1} attempts")
                return None
    
    return None
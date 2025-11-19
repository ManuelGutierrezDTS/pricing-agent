# modules/apis/dat_api.py
"""
DAT API Integration
Maneja autenticación y consultas a DAT Load Board API
CORREGIDO: Fuel surcharge incluido en total rates
"""

import requests
import time
from typing import Optional, Dict
from config import (
    DAT_ORG_USERNAME, DAT_ORG_PASSWORD, DAT_USER_EMAIL,
    DAT_ORG_TOKEN_URL, DAT_USER_TOKEN_URL, 
    DAT_RATE_LOOKUP_URL, DAT_FORECAST_URL,
    API_RETRY_CONFIG
)
from modules.logic.equipment import map_equipment_for_api


def get_dat_org_token() -> Optional[str]:
    """Get DAT organization token"""
    try:
        payload = {
            "username": DAT_ORG_USERNAME,
            "password": DAT_ORG_PASSWORD
        }
        r = requests.post(DAT_ORG_TOKEN_URL, json=payload, timeout=30)
        r.raise_for_status()
        token = r.json()
        return token["accessToken"]
    except Exception as e:
        print(f"❌ Error getting DAT org token: {e}")
        return None


def get_dat_user_token(org_token: str) -> Optional[str]:
    """Get DAT user token"""
    try:
        headers = {
            "Authorization": f"Bearer {org_token}",
            "Content-Type": "application/json"
        }
        payload = {"username": DAT_USER_EMAIL}
        r = requests.post(DAT_USER_TOKEN_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        token = r.json()
        return token["accessToken"]
    except Exception as e:
        print(f"❌ Error getting DAT user token: {e}")
        return None


def fetch_dat_rate(user_token: str, o_city: str, o_state: str, 
                   d_city: str, d_state: str, equipment: str) -> Optional[Dict]:
    """Fetch rate data from DAT API"""
    
    dat_equipment = map_equipment_for_api(equipment)
    
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    }
    
    # Try multiple escalation modes
    for mode in ["minimum", "fallback", "strict"]:
        escalation = {
            "minimum": {
                "escalationType": "MINIMUM_AREA_TYPE_AND_MINIMUM_TIME_FRAME",
                "minimumTimeFrame": "7_DAYS",
                "minimumAreaType": "MARKET_AREA"
            },
            "fallback": {
                "escalationType": "BEST_FIT"
            },
            "strict": {
                "escalationType": "SPECIFIC_AREA_TYPE_AND_SPECIFIC_TIME_FRAME",
                "specificTimeFrame": "7_DAYS",
                "specificAreaType": "MARKET_AREA"
            },
        }[mode]
        
        payload = [{
            "origin": {"city": o_city, "stateOrProvince": o_state},
            "destination": {"city": d_city, "stateOrProvince": d_state},
            "rateType": "SPOT",
            "equipment": dat_equipment,
            "includeMyRate": False,
            "targetEscalation": escalation,
            "rateTimePeriod": {"rateTense": "CURRENT"},
        }]
        
        try:
            r = requests.post(DAT_RATE_LOOKUP_URL, headers=headers, json=payload, timeout=45)
            r.raise_for_status()
            
            response_data = r.json()
            
            if "rateResponses" not in response_data:
                continue
            
            res = response_data["rateResponses"][0].get("response", {})
            
            if not res or "rate" not in res or "perTrip" not in res["rate"]:
                continue
            
            rate = res["rate"]
            mileage = rate["mileage"]
            per_trip = rate["perTrip"]
            
            # Calculate fuel surcharge
            fuel_per_mile = rate.get("averageFuelSurchargePerMileUsd")
            if not fuel_per_mile and rate.get("averageFuelSurchargePerTripUsd") and mileage:
                fuel_per_mile = rate["averageFuelSurchargePerTripUsd"] / mileage
            fuel_per_mile = round(fuel_per_mile if fuel_per_mile is not None else 0.37, 2)
            
            # 🆕 CALCULAR FUEL TOTAL
            fuel_total = round(fuel_per_mile * mileage, 2)
            
            # 🆕 INCLUIR FUEL EN LOS TOTALES
            linehaul_rate = round(per_trip["rateUsd"], 2)
            linehaul_high = round(per_trip["highUsd"], 2)
            linehaul_low = round(per_trip["lowUsd"], 2)
            
            total_with_fuel = round(linehaul_rate + fuel_total, 2)
            high_with_fuel = round(linehaul_high + fuel_total, 2)
            low_with_fuel = round(linehaul_low + fuel_total, 2)
            
            print(f"   ✅ DAT rate found ({mode}) - Linehaul: ${linehaul_rate}, Fuel: ${fuel_total}, Total: ${total_with_fuel}, Miles: {mileage}")
            
            return {
                "rates_mci": {
                    # Per-mile rates (linehaul only, sin fuel)
                    "rateUsd": round(per_trip["rateUsd"] / mileage, 2),
                    "highUsd": round(per_trip["highUsd"] / mileage, 2),
                    "lowUsd": round(per_trip["lowUsd"] / mileage, 2),
                    
                    # Mileage and fuel
                    "mileage": mileage,
                    "fuel_per_mile": fuel_per_mile,
                    "fuel_totalUSD": fuel_total,
                    
                    # 🆕 TOTAL RATES (LINEHAUL + FUEL)
                    "linehaul_forecastUSD": linehaul_rate,
                    "linehaul_mae_highUSD": linehaul_high,
                    "linehaul_mae_lowUSD": linehaul_low,
                    
                    "total_forecastUSD": total_with_fuel,      # ✅ CON FUEL
                    "total_mae_highUSD": high_with_fuel,       # ✅ CON FUEL
                    "total_mae_lowUSD": low_with_fuel,         # ✅ CON FUEL
                    
                    # Metadata
                    "reports": rate.get("reports"),
                    "companies": rate.get("companies"),
                    "source": mode,
                }
            }
            
        except Exception as e:
            print(f"   ⚠️ DAT rate {mode} mode failed: {e}")
            continue
    
    return None


def fetch_dat_forecast(user_token: str, o_city: str, o_state: str,
                       d_city: str, d_state: str, equipment: str, 
                       miles: float, fuel_per_mile: float) -> Optional[Dict]:
    """Fetch 8-day forecast from DAT API"""
    
    dat_equipment = map_equipment_for_api(equipment)
    
    headers = {"Authorization": f"Bearer {user_token}"}
    
    payload = {
        "origin": {"city": o_city, "stateProv": o_state},
        "destination": {"city": d_city, "stateProv": d_state},
        "equipmentCategory": dat_equipment,
        "forecastPeriod": "8DAYS",
    }
    
    try:
        r = requests.post(DAT_FORECAST_URL, headers=headers, json=payload, timeout=45)
        r.raise_for_status()
        
        response_data = r.json()
        forecasts = response_data.get("forecasts", {})
        
        if "perMile" not in forecasts or len(forecasts["perMile"]) < 8:
            return None
        
        f = forecasts["perMile"][7]
        
        # Per-mile rates (linehaul only)
        forecastUSD = round(f["forecastUSD"], 2)
        mae_high = round(f["mae"]["highUSD"], 2)
        mae_low = round(f["mae"]["lowUSD"], 2)
        
        # 🆕 CALCULAR FUEL TOTAL
        fuel_total = round(fuel_per_mile * miles, 2)
        
        # 🆕 CALCULAR TOTALES (LINEHAUL + FUEL)
        linehaul_total = round(forecastUSD * miles, 2)
        linehaul_high = round(mae_high * miles, 2)
        linehaul_low = round(mae_low * miles, 2)
        
        total_with_fuel = round(linehaul_total + fuel_total, 2)
        high_with_fuel = round(linehaul_high + fuel_total, 2)
        low_with_fuel = round(linehaul_low + fuel_total, 2)
        
        print(f"   ✅ DAT forecast found - 8-day rate: ${forecastUSD}/mile, Total with fuel: ${total_with_fuel}")
        
        return {
            "forecast": {
                "forecastDate": f["forecastDate"],
                
                # Per-mile rates (linehaul only)
                "forecastUSD": forecastUSD,
                "mae_highUSD": mae_high,
                "mae_lowUSD": mae_low,
                
                # Fuel
                "fuel_per_mile": fuel_per_mile,
                "fuel_totalUSD": fuel_total,
                
                # 🆕 TOTAL RATES (LINEHAUL + FUEL)
                "linehaul_forecastUSD": linehaul_total,
                "linehaul_mae_highUSD": linehaul_high,
                "linehaul_mae_lowUSD": linehaul_low,
                
                "total_forecastUSD": total_with_fuel,          # ✅ CON FUEL
                "total_mae_highUSD": high_with_fuel,           # ✅ CON FUEL
                "total_mae_lowUSD": low_with_fuel,             # ✅ CON FUEL
            }
        }
        
    except Exception as e:
        print(f"   ⚠️ DAT forecast failed: {e}")
        return None


def get_dat_data_with_retry(o_city: str, o_state: str, d_city: str, 
                            d_state: str, equipment: str, miles: float) -> Optional[Dict]:
    """Get DAT data with retry logic"""
    
    print(f"\n🔍 Fetching DAT data: {o_city}, {o_state} → {d_city}, {d_state} ({equipment})")
    
    for attempt in range(API_RETRY_CONFIG["max_retries"] + 1):
        if attempt > 0:
            print(f"   🔄 Retry attempt {attempt}/{API_RETRY_CONFIG['max_retries']}")
            time.sleep(API_RETRY_CONFIG["retry_delay_seconds"])
        
        try:
            org_token = get_dat_org_token()
            if not org_token:
                continue
            
            user_token = get_dat_user_token(org_token)
            if not user_token:
                continue
            
            rate_data = fetch_dat_rate(user_token, o_city, o_state, d_city, d_state, equipment)
            if not rate_data:
                continue
            
            fuel_per_mile = rate_data["rates_mci"]["fuel_per_mile"]
            forecast_data = fetch_dat_forecast(
                user_token, o_city, o_state, d_city, d_state, equipment, miles, fuel_per_mile
            )
            
            result = rate_data.copy()
            if forecast_data:
                result.update(forecast_data)
            
            return result
            
        except Exception as e:
            print(f"   ❌ DAT API attempt {attempt + 1} failed: {e}")
            if attempt == API_RETRY_CONFIG["max_retries"]:
                print(f"   ❌ DAT API failed after {attempt + 1} attempts")
                return None
    
    return None
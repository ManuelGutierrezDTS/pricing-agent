# modules/apis/google_maps_api.py
"""
Google Maps API Integration
Cálculo de rutas y distancias reales para multistop
"""

import requests
from typing import List, Dict, Optional
from config import GOOGLE_MAPS_API_KEY, GOOGLE_ROUTES_BASE_URL


def calculate_google_miles(stops: List[Dict]) -> Optional[float]:
    """
    Calcula millas reales usando Google Routes API
    stops: Lista de dicts con 'city', 'state', 'zip'
    """
    if not GOOGLE_MAPS_API_KEY:
        print("⚠️ No hay GOOGLE_MAPS_API_KEY configurado")
        return None
    
    if len(stops) < 2:
        return None
    
    # Construir lista de ubicaciones con direcciones completas
    locations = []
    for stop in stops:
        city = stop.get("city", "").strip()
        state = stop.get("state", "").strip()
        zip_code = stop.get("zip", "").strip()
        
        if not zip_code:
            print(f"⚠️ Stop sin ZIP code: {stop}")
            return None
        
        # Formato completo: "City, ST ZIP"
        if city and state:
            address = f"{city}, {state} {zip_code}"
        else:
            # Fallback a solo ZIP si no hay city/state
            address = zip_code
        
        locations.append(address)
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.distanceMeters"
    }
    
    request_body = {
        "origin": {"address": locations[0]},
        "destination": {"address": locations[-1]},
        "travelMode": "DRIVE",
    }
    
    # Agregar paradas intermedias
    if len(locations) > 2:
        request_body["intermediates"] = [{"address": loc} for loc in locations[1:-1]]
    
    try:
        print(f"   🗺️  Calculando millas con Google Maps:")
        print(f"       Origin: {locations[0]}")
        if len(locations) > 2:
            print(f"       Intermediates: {len(locations) - 2} stops")
        print(f"       Destination: {locations[-1]}")
        
        response = requests.post(GOOGLE_ROUTES_BASE_URL, json=request_body, headers=headers, timeout=45)
        
        if response.status_code != 200:
            print(f"   ❌ Google Maps API error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return None
        
        data = response.json()
        
        if "routes" not in data or len(data["routes"]) == 0:
            print(f"   ❌ No routes found in response")
            print(f"   Response keys: {list(data.keys())}")
            return None
        
        # Calcular distancia total en millas
        total_distance_meters = data["routes"][0].get("distanceMeters", 0)
        total_distance_miles = round(total_distance_meters / 1609.344)
        
        print(f"   ✅ Google Miles: {total_distance_miles}")
        return total_distance_miles
        
    except Exception as e:
        print(f"   ❌ Error calculando Google Miles: {e}")
        import traceback
        traceback.print_exc()
        return None
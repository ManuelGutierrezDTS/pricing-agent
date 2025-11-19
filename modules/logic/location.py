# modules/logic/location.py
"""
Location handling and ZIP code resolution
Resolución de ubicaciones usando pgeocode
"""

from typing import Dict, Tuple
import pgeocode
import pandas as pd

# Inicializar pgeocode
nomi = pgeocode.Nominatim('us')


def resolve_location(stop_data: Dict) -> Tuple[str, str, str]:
    """
    Resuelve ubicación desde stop_data (flexible)
    Retorna: (city, state, zip)
    
    Acepta:
    - Solo ZIP: {"zip": "81050"}
    - Completo: {"city": "La Junta", "state": "CO", "zip": "81050"}
    """
    zip_code = stop_data.get("zip", "").strip()
    
    # Si ya tiene city y state, usar eso
    if stop_data.get("city") and stop_data.get("state"):
        return (
            stop_data["city"].strip(),
            stop_data["state"].strip().upper(),
            zip_code
        )
    
    # Si solo tiene ZIP, resolver con pgeocode
    if zip_code:
        try:
            location = nomi.query_postal_code(zip_code)
            
            if location is not None and not pd.isna(location.place_name):
                # pgeocode retorna state_code (ej: "CO")
                city = location.place_name
                state = location.state_code
                
                if city and state:
                    return (
                        str(city).title(),  # Title case para city
                        str(state).upper(),  # Upper case para state
                        zip_code
                    )
        except Exception as e:
            print(f"   ⚠️ Error resolving ZIP {zip_code}: {e}")
    
    raise ValueError(f"No se pudo resolver ZIP code: {zip_code}")
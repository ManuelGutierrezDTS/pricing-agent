# modules/logic/hotshot.py
"""
Hotshot logic handler
Maneja ajustes de precios basados en peso
HOTSHOT se busca como FLATBED en APIs
Pesado (≥10000 lbs): +10%
Liviano (<10000 lbs): -20%
"""

from typing import Tuple
from config import HOTSHOT_CONFIG


def handle_hotshot(equipment: str, weight: float) -> Tuple[str, float, bool]:
    """
    Maneja lógica de Hotshot (case-insensitive)
    Retorna: (api_equipment, adjustment_multiplier, is_hotshot)
    """
    if not HOTSHOT_CONFIG["enabled"] or weight <= 0:
        return equipment, 1.0, False
    
    # Normalizar equipment (case-insensitive, remove spaces)
    equipment_normalized = equipment.upper().replace(" ", "").strip()
    
    # Detectar HOTSHOT
    if "HOTSHOT" not in equipment_normalized:
        return equipment, 1.0, False
    
    # Es HOTSHOT
    is_hotshot = True
    threshold = HOTSHOT_CONFIG["weight_threshold"]  # 10000
    
    # Mapear a FLATBED para APIs
    api_equipment = HOTSHOT_CONFIG["map_to_equipment"]  # "FLATBED"
    
    # Determinar adjustment basado en peso
    if weight >= threshold:
        # Pesado (≥10000 lbs): +10%
        adjustment = 0.80
        print(f"   🔥 HOTSHOT DETECTED (HEAVY):")
        print(f"      Weight: {weight:,.0f} lbs (≥{threshold:,})")
        print(f"      API equipment: {api_equipment}")
        print(f"      Adjustment: -20%")
    else:
        # Liviano (<10000 lbs): -20%
        adjustment = 0.65
        print(f"   🔥 HOTSHOT DETECTED (LIGHT):")
        print(f"      Weight: {weight:,.0f} lbs (<{threshold:,})")
        print(f"      API equipment: {api_equipment}")
        print(f"      Adjustment: -35%")
    
    return api_equipment, adjustment, is_hotshot
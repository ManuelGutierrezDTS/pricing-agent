# modules/logic/equipment.py
"""
Equipment handling logic
Manejo de tipos de equipo, normalización, y multi-equipment
"""

from typing import List
from modules.utils.helpers import normalize_text


def normalize_equipment(equipment_str: str) -> str:
    """
    Normaliza y estandariza el equipment type (UPPERCASE)
    VAN, Van, van → VAN
    Van OR Reefer, VAN OR REEFER → REEFER/VAN (sorted)
    """
    equipment_upper = normalize_text(equipment_str)
    equipment_upper = equipment_upper.replace(" OR ", "/")
    
    if "/" in equipment_upper:
        parts = [p.strip() for p in equipment_upper.split("/")]
        parts.sort()
        return "/".join(parts)
    
    return equipment_upper


def is_multi_equipment(equipment_str: str) -> bool:
    """Detecta si es multi-equipment"""
    normalized = normalize_equipment(equipment_str)
    return "/" in normalized


def split_equipment(equipment_str: str) -> List[str]:
    """Separa multi-equipment en lista"""
    normalized = normalize_equipment(equipment_str)
    if "/" in normalized:
        return normalized.split("/")
    return [normalized]


def map_equipment_for_api(equipment: str) -> str:
    """Mapea equipment type para APIs (DAT/GS) - siempre UPPERCASE"""
    equipment_upper = normalize_text(equipment)
    
    mapping = {
        "VAN": "VAN",
        "DRY VAN": "VAN",
        "STRAIGHT VAN": "VAN",
        "REEFER": "REEFER",
        "FLATBED": "FLATBED",
    }
    
    # Buscar match exacto o parcial
    for key, value in mapping.items():
        if key in equipment_upper:
            return value
    
    return "VAN"  # default
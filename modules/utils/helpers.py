# modules/utils/helpers.py
"""
Funciones auxiliares y helpers generales
"""

def safe_float(value, default=0.0):
    """Safely convert a value to float"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Safely convert a value to int"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def round_to_nearest_5(value):
    """Redondea al múltiplo de 5 más cercano"""
    if value is None:
        return 0
    return round(float(value) / 5) * 5


def normalize_text(text: str) -> str:
    """Normaliza texto a uppercase para comparaciones case-insensitive"""
    if not text:
        return ""
    return str(text).strip().upper()


def contains_word(text: str, word: str) -> bool:
    """Verifica si text contiene word (case-insensitive)"""
    if not text or not word:
        return False
    return normalize_text(word) in normalize_text(text)
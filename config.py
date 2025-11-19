# config.py
"""
Configuración centralizada del Pricing Agent
Todas las configuraciones y parámetros del sistema
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ==========================================================================================
# SINGLE ANALYSIS CONFIGURATION
# ==========================================================================================
SINGLE_ANALYSIS = {
    "proposed_price": 1500,
    "carrier_cost": "auto",
    
    "stops": [
        {"type": "PICKUP", "zip": "60160"},
        # Para multistop, agregar más DROP stops:
         {"type": "DROP", "zip": "53703"},
        # {"type": "DROP", "zip": "17011"},
        # {"type": "DROP", "zip": "27545"},
        # {"type": "DROP", "zip": "27529"},
        # {"type": "DROP", "zip": "28348"},
        # {"type": "DROP", "zip": "28001"},
        # {"type": "DROP", "zip": "28027"},
        # {"type": "DROP", "zip": "28205"},
        # {"type": "DROP", "zip": "29732"}
    ],
    
    "customer_name": "SureBuilt",
    "equipment_type": "HOTSHOT",
    "pickup_date": None,
    "delivery_date": None,
    "weight": 6036,
}

# ==========================================================================================
# HOTSHOT CONFIGURATION
# ==========================================================================================
HOTSHOT_CONFIG = {
    "enabled": True,
    "weight_operator": ">",
    "weight_threshold": 10000,
    "map_to_equipment": "FLATBED",
    "heavy_adjustment": -0.10,
    "light_adjustment": 0.10,
}

# ==========================================================================================
# MULTISTOP CONFIGURATION
# ==========================================================================================
MULTISTOP_CONFIG = {
    "google_api_key": os.getenv("GOOGLE_MAPS_API_KEY") or "AIzaSyDWnxUDq9qjCXTQt38OLi6a2l1svGt-owM",
    "variable_stop_charge": 100,
    "variable_stop_charge_fabuwood": 150,
    "layover_rate": 200,
    "layover_rate_fabuwood": 125,
    "extra_stops_bonus_divisor": 4,
    "extra_stops_bonus_multiplier": 150,
    "extra_stops_bonus_multiplier_fabuwood": 100,
    "markup": 0.02,
}

# ==========================================================================================
# API CREDENTIALS
# ==========================================================================================
# DAT API
DAT_ORG_USERNAME = os.getenv("DAT_ORG_USERNAME")
DAT_ORG_PASSWORD = os.getenv("DAT_ORG_PASSWORD")
DAT_USER_EMAIL = os.getenv("DAT_USER_EMAIL")
DAT_ORG_TOKEN_URL = os.getenv("DAT_ORG_TOKEN_URL")
DAT_USER_TOKEN_URL = os.getenv("DAT_USER_TOKEN_URL")
DAT_RATE_LOOKUP_URL = os.getenv("DAT_RATE_LOOKUP_URL")
DAT_FORECAST_URL = os.getenv("DAT_FORECAST_URL")

# GreenScreens API
GS_CLIENT_ID = os.getenv("GS_CLIENT_ID")
GS_CLIENT_SECRET = os.getenv("GS_CLIENT_SECRET")
GS_AUTH_URL = os.getenv("GS_AUTH_URL")

# Google Maps API
GOOGLE_MAPS_API_KEY = MULTISTOP_CONFIG["google_api_key"]
GOOGLE_ROUTES_BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

# ==========================================================================================
# NEGOTIATION RANGE CONFIGURATION
# ==========================================================================================
NEGOTIATION_CONFIG = {
    "enable_auto_cost": True,
    "transit_days_default": 2,
    "capacity_sensitivity": 0.15,
    "confidence_weight": 0.25,
    "weekend_penalty": 50,
    "long_haul_threshold": 700,
    "short_haul_threshold": 200,
    "minimum_margin_buffer": 100,
}

# ==========================================================================================
# AZURE BLOB STORAGE CONFIGURATION
# ==========================================================================================
AZURE_CONFIG = {
    "account_name": os.getenv("AZ_BLOB_ACCOUNT") or "databricksdts",
    "container": os.getenv("AZ_BLOB_CONTAINER") or "databrickscontainer",
    "blob_name": os.getenv("AZ_BLOB_FILE") or "UnityCatalog_Tables.xlsx",
    "account_key": os.getenv("AZ_BLOB_KEY") or "",
}

# ==========================================================================================
# LOCAL PATH CONFIGURATION
# ==========================================================================================
PATH_CONFIG = {
    "unity_csv_path": "unity/UnityCatalog_Tables.csv",
    "unity_xlsx_path": "unity/UnityCatalog_Tables.xlsx",
    "results_output": "validation_results.json",
    "auto_refresh_hours": 24,
}

# ==========================================================================================
# ID ANALYSIS CONFIGURATION
# ==========================================================================================
ID_CONFIG = {
    "months_lookback": 3,
    "fallback_to_year": True,
    "min_records_confidence": 3,
    "equipment_match": "contains",
    "stop_type_filter": "UNIQUE STOP",
}

# ==========================================================================================
# PRC VALIDATION CONFIGURATION
# ==========================================================================================
PRC_CONFIG = {
    "min_loads_for_match": 3,
    "enable_zip4_fallback": True,
    "enable_zip3_fallback": True,
    "debug_mode": False,
    "minimum_margin_pct": 5.0,
    "maximum_margin_pct": 35.0,      # 🆕 Margen máximo aceptable (industria)
    "target_margin_pct": 16.0,       # 🆕 Margen objetivo típico
    "warning_margin_high": 30.0,     # 🆕 Warning si supera este margen
}

# ==========================================================================================
# RATING THRESHOLDS CONFIGURATION
# ==========================================================================================
RATING_THRESHOLDS = {
    "excellent": {"min": -5, "max": 5},
    "good": {"min": -10, "max": 10},
    "acceptable": {"min": -15, "max": 15},
    "risky": {"min": -25, "max": 25},
    "poor": {"min": -100, "max": 100}
}

# ==========================================================================================
# API RETRY CONFIGURATION
# ==========================================================================================
API_RETRY_CONFIG = {
    "retry_delay_seconds": 5,
    "max_retries": 1,
}
# modules/analysis/id_analysis.py
"""
Internal Data Analysis (ID)
Análisis de datos históricos internos de Unity Catalog
INCLUYE CUSTOMER PRICING HISTÓRICO
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from config import ID_CONFIG
from modules.utils.helpers import normalize_text


def calculate_hist_confidence_id(carrier_costs_df, pod_df, general_median, median_3zip):
    """Calculate confidence score for ID analysis"""
    
    lane_records = len(carrier_costs_df) if not carrier_costs_df.empty else 0
    zip3_records = len(pod_df) if not pod_df.empty else 0
    
    volume_score = min(40, (lane_records * 2) + (zip3_records * 0.5))
    
    consistency_score = 35
    if not carrier_costs_df.empty and len(carrier_costs_df) > 1:
        std_dev = carrier_costs_df['CarrierFreightCost'].std()
        mean_cost = carrier_costs_df['CarrierFreightCost'].mean()
        if mean_cost > 0:
            cv = std_dev / mean_cost
            consistency_score = max(0, 35 - (cv * 50))
    
    data_quality_score = 0
    if general_median and median_3zip:
        if general_median > 0 and median_3zip > 0:
            diff_pct = abs(general_median - median_3zip) / general_median * 100
            if diff_pct < 20:
                data_quality_score = 25
            elif diff_pct < 40:
                data_quality_score = 15
            else:
                data_quality_score = 5
    
    total_score = volume_score + consistency_score + data_quality_score
    return min(100, int(total_score))


def run_internal_data_analysis(
    unity_df: pd.DataFrame,
    origin_zip: str,
    destination_zip: str,
    equipment_type: Optional[str] = None,
    pickup_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """Run ID-style analysis on internal data"""
    
    if pickup_date is None:
        pickup_date = datetime.now()
    
    # Normalizar equipment (UPPERCASE)
    equipment_keyword = normalize_text(equipment_type) if equipment_type else ""
    
    df_shipment = unity_df.copy()
    
    required_cols = ['Origin_Zip', 'Destination_Zip', 'CarrierFreightCost', 'CarrierName']
    missing = [c for c in required_cols if c not in df_shipment.columns]
    if missing:
        return {
            "error": f"Missing columns: {missing}",
            "RecordsAnalyzed_Lane": 0,
            "HistConfidence": 0
        }
    
    # 🆕 Verificar si existe CustomerFreightCost
    has_customer_pricing = 'CustomerFreightCost' in df_shipment.columns
    
    if 'PickupDate' in df_shipment.columns:
        df_shipment['PickupDate'] = pd.to_datetime(df_shipment['PickupDate'], errors='coerce')
    else:
        df_shipment['PickupDate'] = pickup_date
    
    if 'Equipment' in df_shipment.columns:
        df_shipment['Equipment_Norm'] = df_shipment['Equipment'].apply(normalize_text)
    else:
        df_shipment['Equipment_Norm'] = ""
    
    df_shipment['Origin_Zip3'] = df_shipment['Origin_Zip'].astype(str).str[:3]
    df_shipment['Origin_Zip4'] = df_shipment['Origin_Zip'].astype(str).str[:4]
    df_shipment['Destination_Zip3'] = df_shipment['Destination_Zip'].astype(str).str[:3]
    df_shipment['Destination_Zip4'] = df_shipment['Destination_Zip'].astype(str).str[:4]
    
    if 'Stop_Type' in df_shipment.columns:
        df_shipment['Stop_Type_Norm'] = df_shipment['Stop_Type'].apply(normalize_text)
    else:
        df_shipment['Stop_Type_Norm'] = "UNIQUE STOP"
    
    df_shipment["PodToPod"] = df_shipment["Origin_Zip3"] + "-" + df_shipment["Destination_Zip3"]
    
    three_months_ago = pickup_date - timedelta(days=90)
    
    origin_zip4 = origin_zip[:4]
    destination_zip4 = destination_zip[:4]
    
    filtered_df = df_shipment[
        (df_shipment['PickupDate'] >= three_months_ago) &
        (df_shipment['Origin_Zip4'] == origin_zip4) &
        (df_shipment['Destination_Zip4'] == destination_zip4) &
        (pd.to_numeric(df_shipment['CarrierFreightCost'], errors='coerce') > 0)
    ].copy()
    
    if equipment_keyword and ID_CONFIG["equipment_match"] == "contains":
        filtered_df = filtered_df[
            filtered_df['Equipment_Norm'].str.contains(equipment_keyword, na=False, regex=False)
        ]
    elif equipment_keyword and ID_CONFIG["equipment_match"] == "exact":
        filtered_df = filtered_df[filtered_df['Equipment_Norm'] == equipment_keyword]
    
    if ID_CONFIG["stop_type_filter"]:
        filtered_df = filtered_df[
            filtered_df['Stop_Type_Norm'] == normalize_text(ID_CONFIG["stop_type_filter"])
        ]
    
    if filtered_df.empty and ID_CONFIG["fallback_to_year"]:
        current_year = pickup_date.year
        filtered_df = df_shipment[
            (df_shipment['PickupDate'].dt.year == current_year) &
            (df_shipment['Origin_Zip4'] == origin_zip4) &
            (df_shipment['Destination_Zip4'] == destination_zip4) &
            (pd.to_numeric(df_shipment['CarrierFreightCost'], errors='coerce') > 0)
        ].copy()
        
        if equipment_keyword and ID_CONFIG["equipment_match"] == "contains":
            filtered_df = filtered_df[
                filtered_df['Equipment_Norm'].str.contains(equipment_keyword, na=False, regex=False)
            ]
    
    best_carrier_name = None
    best_carrier_rate = None
    general_median = None
    
    # 🆕 Variables para Customer Pricing
    customer_median_price = None
    customer_average_price = None
    historical_margin_pct = None
    historical_markup = None
    
    if not filtered_df.empty:
        carrier_costs_df = filtered_df[['ClientLoadId', 'CarrierName', 'CarrierFreightCost', 'PickupDate']].drop_duplicates() if 'ClientLoadId' in filtered_df.columns else filtered_df[['CarrierName', 'CarrierFreightCost', 'PickupDate']].drop_duplicates()
        carrier_costs_df['CarrierFreightCost'] = pd.to_numeric(carrier_costs_df['CarrierFreightCost'], errors='coerce')
        
        if not carrier_costs_df.empty:
            carrier_avg = carrier_costs_df.groupby('CarrierName', as_index=False)['CarrierFreightCost'].mean()
            if not carrier_avg.empty:
                best_carrier_row = carrier_avg.loc[carrier_avg['CarrierFreightCost'].idxmin()]
                best_carrier_name = best_carrier_row['CarrierName']
                best_carrier_rate = round(float(best_carrier_row['CarrierFreightCost']), 2)
            general_median = round(float(carrier_costs_df['CarrierFreightCost'].median()), 2)
        
        # 🆕 CALCULAR CUSTOMER PRICING HISTÓRICO
        if has_customer_pricing:
            customer_df = filtered_df[
                (pd.to_numeric(filtered_df['CustomerFreightCost'], errors='coerce') > 0) &
                (pd.to_numeric(filtered_df['CarrierFreightCost'], errors='coerce') > 0)
            ].copy()
            
            if not customer_df.empty:
                customer_df['CustomerFreightCost'] = pd.to_numeric(customer_df['CustomerFreightCost'], errors='coerce')
                customer_df['CarrierFreightCost'] = pd.to_numeric(customer_df['CarrierFreightCost'], errors='coerce')
                
                # Calcular métricas de customer pricing
                customer_median_price = round(float(customer_df['CustomerFreightCost'].median()), 2)
                customer_average_price = round(float(customer_df['CustomerFreightCost'].mean()), 2)
                
                # Calcular markup y margin históricos
                customer_df['Markup'] = customer_df['CustomerFreightCost'] / customer_df['CarrierFreightCost']
                customer_df['MarginPct'] = ((customer_df['CustomerFreightCost'] - customer_df['CarrierFreightCost']) / customer_df['CustomerFreightCost']) * 100
                
                historical_markup = round(float(customer_df['Markup'].median()), 3)
                historical_margin_pct = round(float(customer_df['MarginPct'].median()), 2)
    else:
        carrier_costs_df = pd.DataFrame()
    
    origin_zip3 = origin_zip[:3]
    destination_zip3 = destination_zip[:3]
    pod_to_pod = f"{origin_zip3}-{destination_zip3}"
    
    pod_df = df_shipment[
        (df_shipment["PodToPod"] == pod_to_pod) &
        (df_shipment["PickupDate"] >= three_months_ago) &
        (pd.to_numeric(df_shipment["CarrierFreightCost"], errors='coerce') > 0)
    ].copy()
    
    if equipment_keyword and ID_CONFIG["equipment_match"] == "contains":
        pod_df = pod_df[
            pod_df['Equipment_Norm'].str.contains(equipment_keyword, na=False, regex=False)
        ]
    
    if ID_CONFIG["stop_type_filter"]:
        pod_df = pod_df[
            pod_df['Stop_Type_Norm'] == normalize_text(ID_CONFIG["stop_type_filter"])
        ]
    
    median_3zip = None
    start_rate = None
    start_rate_carrier = None
    start_rate_load_id = None
    
    if not pod_df.empty:
        pod_df["CarrierFreightCost"] = pd.to_numeric(pod_df["CarrierFreightCost"], errors='coerce')
        median_3zip = round(float(pod_df["CarrierFreightCost"].median()), 2)
        
        q1 = pod_df["CarrierFreightCost"].quantile(0.25)
        q3 = pod_df["CarrierFreightCost"].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        filtered_rates = pod_df[
            (pod_df["CarrierFreightCost"] >= lower_bound) & 
            (pod_df["CarrierFreightCost"] <= upper_bound)
        ]
        
        if not filtered_rates.empty:
            start_row = filtered_rates.loc[filtered_rates["CarrierFreightCost"].idxmin()]
            start_rate = round(float(start_row["CarrierFreightCost"]), 2)
            start_rate_carrier = start_row.get("CarrierName")
            if 'ClientLoadId' in start_row:
                start_rate_load_id = start_row.get("ClientLoadId")
    
    hist_confidence = calculate_hist_confidence_id(
        carrier_costs_df, pod_df, general_median, median_3zip
    )
    
    return {
        "RecommendedCarrier": str(best_carrier_name) if best_carrier_name else None,
        "BestCarrierAverageRate": best_carrier_rate,
        "LaneMedianRate": general_median,
        "Zip3MedianLaneRate": median_3zip,
        "Zip3StartRate": start_rate,
        "Zip3StartRateCarrier": str(start_rate_carrier) if start_rate_carrier else None,
        "Zip3StartRateLoadId": str(start_rate_load_id) if start_rate_load_id else None,
        "PodToPod": pod_to_pod,
        "ZIP4_Lane": f"{origin_zip4}-{destination_zip4}",
        "RecordsAnalyzed_Lane": len(carrier_costs_df) if not carrier_costs_df.empty else 0,
        "RecordsAnalyzed_Zip3": len(pod_df) if not pod_df.empty else 0,
        "HistConfidence": hist_confidence,
        "EquipmentKeyword": equipment_keyword if equipment_keyword else "ALL",
        # 🆕 CUSTOMER PRICING HISTÓRICO
        "CustomerMedianPrice": customer_median_price,
        "CustomerAveragePrice": customer_average_price,
        "HistoricalMarginPct": historical_margin_pct,
        "HistoricalMarkup": historical_markup,
    }
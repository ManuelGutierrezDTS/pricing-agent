# modules/analysis/prc.py
"""
PRC (Pricing Validator)
Valida precios propuestos contra datos históricos
CON MARGEN DINÁMICO POR CUSTOMER Y JERARQUÍA: Lane+Customer > Customer > Industry
APLICA JERARQUÍA TAMBIÉN EN VALIDACIÓN DE MARGEN MÁXIMO
SOPORTA MULTISTOP OUTLIERS
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from config import PRC_CONFIG, RATING_THRESHOLDS


@dataclass
class LaneHistorical:
    """Historical data found for the lane"""
    match_level: str
    lane_identifier: str
    customer: str
    avg_markup: float
    median_markup: float
    std_markup: float
    avg_margin_pct: float
    median_margin_pct: float
    std_margin_pct: float
    confidence_score: float
    total_loads: int
    recent_loads: int
    min_markup: float
    max_markup: float
    p25_markup: float
    p75_markup: float
    min_margin_pct: float
    max_margin_pct: float
    p25_margin_pct: float
    p75_margin_pct: float


def _calculate_confidence_score(df: pd.DataFrame, match_level: str, recent_loads: int) -> float:
    """Calculate confidence score based on data quality"""
    score = 0.0
    
    # Volume (40%)
    volume_score = min(40, len(df) * 2)
    score += volume_score
    
    # Match level (30%)
    if match_level == "exact":
        score += 30
    elif match_level == "zip4":
        score += 20
    else:
        score += 10
    
    # Recency (20%)
    if len(df) > 0:
        recency_score = min(20, (recent_loads / len(df)) * 20)
        score += recency_score
    
    # Consistency (10%)
    if len(df) > 1 and 'Markup' in df.columns:
        cv = df['Markup'].std() / df['Markup'].mean() if df['Markup'].mean() > 0 else 1
        consistency_score = max(0, 10 - (cv * 20))
        score += consistency_score
    else:
        score += 5
    
    return min(100, round(score, 2))


def _calculate_historical_stats(df: pd.DataFrame, match_level: str, 
                                lane_identifier: str, customer: str) -> LaneHistorical:
    """Calculate historical statistics from filtered dataframe"""
    
    df['CarrierFreightCost'] = pd.to_numeric(df['CarrierFreightCost'], errors='coerce')
    df['CustomerFreightCost'] = pd.to_numeric(df['CustomerFreightCost'], errors='coerce')
    
    df = df[
        (df['CarrierFreightCost'] > 0) & 
        (df['CustomerFreightCost'] > 0) &
        (df['CustomerFreightCost'] >= df['CarrierFreightCost'])
    ].copy()
    
    df['Markup'] = df['CustomerFreightCost'] / df['CarrierFreightCost']
    df['MarginDollars'] = df['CustomerFreightCost'] - df['CarrierFreightCost']
    df['MarginPct'] = (df['MarginDollars'] / df['CustomerFreightCost']) * 100
    
    if 'PickupDate' in df.columns:
        df['PickupDate'] = pd.to_datetime(df['PickupDate'], errors='coerce')
        recent_cutoff = datetime.now() - timedelta(days=90)
        recent_df = df[df['PickupDate'] >= recent_cutoff]
        recent_loads = len(recent_df)
    else:
        recent_loads = 0
    
    stats = LaneHistorical(
        match_level=match_level,
        lane_identifier=lane_identifier,
        customer=customer,
        avg_markup=df['Markup'].mean(),
        median_markup=df['Markup'].median(),
        std_markup=df['Markup'].std(),
        min_markup=df['Markup'].min(),
        max_markup=df['Markup'].max(),
        p25_markup=df['Markup'].quantile(0.25),
        p75_markup=df['Markup'].quantile(0.75),
        avg_margin_pct=df['MarginPct'].mean(),
        median_margin_pct=df['MarginPct'].median(),
        std_margin_pct=df['MarginPct'].std(),
        min_margin_pct=df['MarginPct'].min(),
        max_margin_pct=df['MarginPct'].max(),
        p25_margin_pct=df['MarginPct'].quantile(0.25),
        p75_margin_pct=df['MarginPct'].quantile(0.75),
        total_loads=len(df),
        recent_loads=recent_loads,
        confidence_score=_calculate_confidence_score(df, match_level, recent_loads)
    )
    
    return stats


def calculate_customer_historical_margin(
    unity_df: pd.DataFrame,
    customer_name: str,
    debug: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Calcula el margen histórico promedio del customer
    Usado cuando NO hay datos de la lane específica
    """
    
    if not customer_name or customer_name == "":
        if debug:
            print("DEBUG: No customer name provided for margin calculation")
        return None
    
    def normalize_name(name):
        import re
        if pd.isna(name):
            return ""
        name = str(name).lower()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    # Verificar columnas necesarias
    required_cols = ['CompanyName', 'CarrierFreightCost', 'CustomerFreightCost']
    if not all(col in unity_df.columns for col in required_cols):
        if debug:
            print(f"DEBUG: Missing columns for customer margin calc")
        return None
    
    # Filtrar por customer
    target_normalized = normalize_name(customer_name)
    customer_df = unity_df[
        unity_df['CompanyName'].apply(normalize_name) == target_normalized
    ].copy()
    
    if len(customer_df) == 0:
        if debug:
            print(f"DEBUG: No loads found for customer: {customer_name}")
        return None
    
    # Filtrar por Status
    if 'Status' in customer_df.columns:
        customer_df = customer_df[
            customer_df['Status'].isin(['Delivered', 'Completed'])
        ]
    
    # Filtrar últimos 3 meses
    if 'PickupDate' in customer_df.columns:
        customer_df['PickupDate'] = pd.to_datetime(customer_df['PickupDate'], errors='coerce')
        three_months_ago = datetime.now() - timedelta(days=90)
        customer_df = customer_df[customer_df['PickupDate'] >= three_months_ago]
    
    # Convertir a numeric y filtrar válidos
    customer_df['CarrierFreightCost'] = pd.to_numeric(customer_df['CarrierFreightCost'], errors='coerce')
    customer_df['CustomerFreightCost'] = pd.to_numeric(customer_df['CustomerFreightCost'], errors='coerce')
    
    customer_df = customer_df[
        (customer_df['CarrierFreightCost'] > 0) &
        (customer_df['CustomerFreightCost'] > 0) &
        (customer_df['CustomerFreightCost'] >= customer_df['CarrierFreightCost'])
    ].copy()
    
    if len(customer_df) < 3:  # Mínimo 3 loads
        if debug:
            print(f"DEBUG: Insufficient customer loads: {len(customer_df)} < 3")
        return None
    
    # Calcular métricas
    customer_df['MarginPct'] = ((customer_df['CustomerFreightCost'] - customer_df['CarrierFreightCost']) / customer_df['CustomerFreightCost']) * 100
    customer_df['Markup'] = customer_df['CustomerFreightCost'] / customer_df['CarrierFreightCost']
    
    result = {
        'customer_name': customer_name,
        'total_loads': len(customer_df),
        'median_margin_pct': customer_df['MarginPct'].median(),
        'avg_margin_pct': customer_df['MarginPct'].mean(),
        'median_markup': customer_df['Markup'].median(),
        'avg_markup': customer_df['Markup'].mean(),
        'min_margin_pct': customer_df['MarginPct'].min(),
        'max_margin_pct': customer_df['MarginPct'].max(),
        'std_margin_pct': customer_df['MarginPct'].std()
    }
    
    if debug:
        print(f"\n🎯 CUSTOMER HISTORICAL MARGIN:")
        print(f"   Customer: {customer_name}")
        print(f"   Loads analyzed: {result['total_loads']}")
        print(f"   Median Margin: {result['median_margin_pct']:.2f}%")
        print(f"   Avg Margin: {result['avg_margin_pct']:.2f}%")
        print(f"   Median Markup: {result['median_markup']:.3f}x")
    
    return result


def find_lane_historical(
    unity_df: pd.DataFrame,
    origin_zip: str,
    destination_zip: str,
    customer_name: Optional[str] = None,
    debug: bool = False
) -> Optional[LaneHistorical]:
    """Search historical data with hierarchical fallback"""
    
    if debug:
        print(f"\nDEBUG: Searching Origin: {origin_zip}, Destination: {destination_zip}")
        if customer_name:
            print(f"DEBUG: Customer: {customer_name}")
    
    origin_zip = str(origin_zip).strip().zfill(5)[:5]
    destination_zip = str(destination_zip).strip().zfill(5)[:5]
    
    required_cols = ['Origin_Zip', 'Destination_Zip', 'CarrierFreightCost', 'CustomerFreightCost']
    missing_cols = [col for col in required_cols if col not in unity_df.columns]
    
    if missing_cols:
        if debug:
            print(f"DEBUG: Missing columns: {missing_cols}")
        return None
    
    def normalize_name(name):
        import re
        if pd.isna(name):
            return ""
        name = str(name).lower()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    # LEVEL 1: Exact lane
    df = unity_df[
        (unity_df['Origin_Zip'].astype(str).str.strip().str.zfill(5) == origin_zip) &
        (unity_df['Destination_Zip'].astype(str).str.strip().str.zfill(5) == destination_zip)
    ].copy()
    
    if customer_name and 'CompanyName' in df.columns:
        target_normalized = normalize_name(customer_name)
        df = df[df['CompanyName'].apply(normalize_name) == target_normalized]
    
    if len(df) >= PRC_CONFIG["min_loads_for_match"]:
        return _calculate_historical_stats(df, "exact", f"{origin_zip}-{destination_zip}", customer_name or "ALL")
    
    # LEVEL 2: ZIP4
    if PRC_CONFIG["enable_zip4_fallback"]:
        origin_zip4 = origin_zip[:4]
        destination_zip4 = destination_zip[:4]
        
        df = unity_df[
            (unity_df['Origin_Zip'].astype(str).str.strip().str[:4] == origin_zip4) &
            (unity_df['Destination_Zip'].astype(str).str.strip().str[:4] == destination_zip4)
        ].copy()
        
        if customer_name and 'CompanyName' in df.columns:
            target_normalized = normalize_name(customer_name)
            df = df[df['CompanyName'].apply(normalize_name) == target_normalized]
        
        if len(df) >= PRC_CONFIG["min_loads_for_match"]:
            return _calculate_historical_stats(df, "zip4", f"{origin_zip4}-{destination_zip4}", customer_name or "ALL")
    
    # LEVEL 3: ZIP3
    if PRC_CONFIG["enable_zip3_fallback"]:
        origin_zip3 = origin_zip[:3]
        destination_zip3 = destination_zip[:3]
        
        df = unity_df[
            (unity_df['Origin_Zip'].astype(str).str.strip().str[:3] == origin_zip3) &
            (unity_df['Destination_Zip'].astype(str).str.strip().str[:3] == destination_zip3)
        ].copy()
        
        if customer_name and 'CompanyName' in df.columns:
            target_normalized = normalize_name(customer_name)
            df = df[df['CompanyName'].apply(normalize_name) == target_normalized]
        
        if len(df) >= PRC_CONFIG["min_loads_for_match"]:
            return _calculate_historical_stats(df, "zip3", f"{origin_zip3}-{destination_zip3}", customer_name or "ALL")
    
    return None


def validate_customer_pricing(
    unity_df: pd.DataFrame,
    proposed_customer_price: float,
    carrier_cost: float,
    origin_zip: str,
    destination_zip: str,
    customer_name: Optional[str] = None,
    debug: bool = False,
    multistop_outlier: Optional[Dict] = None
) -> Dict[str, Any]:
    """Main validation function"""
    
    proposed_markup = proposed_customer_price / carrier_cost
    proposed_margin_dollars = proposed_customer_price - carrier_cost
    proposed_margin_pct = (proposed_margin_dollars / proposed_customer_price) * 100
    
    historical = find_lane_historical(
        unity_df=unity_df,
        origin_zip=origin_zip,
        destination_zip=destination_zip,
        customer_name=customer_name,
        debug=debug
    )
    
    result = {
        "proposed_customer_price": proposed_customer_price,
        "carrier_cost": carrier_cost,
        "proposed_markup": proposed_markup,
        "proposed_margin_dollars": proposed_margin_dollars,
        "proposed_margin_pct": proposed_margin_pct,
        "origin_zip": origin_zip,
        "destination_zip": destination_zip,
        "customer_name": customer_name,
        "historical": None,
        "comparison": None,
        "rating": "NO_DATA",
        "confidence_score": 0,
        "recommendation": "No historical data available",
        "flags": []
    }
    
    # ===== VALIDACIÓN 1: MARGEN MÁXIMO DE INDUSTRIA =====
    MAXIMUM_MARGIN_PCT = PRC_CONFIG.get("maximum_margin_pct", 35.0)
    WARNING_MARGIN_HIGH = PRC_CONFIG.get("warning_margin_high", 30.0)
    
    if proposed_margin_pct > MAXIMUM_MARGIN_PCT:
        result["rating"] = "POOR"
        result["recommendation"] = f"REJECT. Margin too high ({proposed_margin_pct:.1f}% > {MAXIMUM_MARGIN_PCT}% industry max)."
        result["flags"].append("margin_above_industry_max")
        result["confidence_score"] = 100
        
        # APLICAR JERARQUÍA TAMBIÉN EN MARGEN MÁXIMO
        
        # PRIORIDAD 1: Lane+Customer específico
        if historical and historical.customer and historical.customer != "ALL":
            suggested_price = carrier_cost * historical.median_markup
            result["industry_suggested_price"] = round(suggested_price, 2)
            if debug:
                print(f"   Using lane+customer markup: {historical.median_markup:.3f}x")
        else:
            # PRIORIDAD 2: Customer global margin
            customer_margin_data = calculate_customer_historical_margin(unity_df, customer_name, debug)
            
            if customer_margin_data and customer_margin_data['total_loads'] >= 5:
                target_margin = customer_margin_data['median_margin_pct'] / 100
                suggested_price = carrier_cost / (1 - target_margin)
                result["industry_suggested_price"] = round(suggested_price, 2)
                result["customer_historical_margin"] = customer_margin_data
                if debug:
                    print(f"   Using customer historical margin: {customer_margin_data['median_margin_pct']:.2f}%")
            else:
                # PRIORIDAD 3: Industry default
                target_margin = PRC_CONFIG.get("target_margin_pct", 16.0) / 100
                suggested_price = carrier_cost / (1 - target_margin)
                result["industry_suggested_price"] = round(suggested_price, 2)
                if debug:
                    print(f"   Using default margin: {PRC_CONFIG.get('target_margin_pct', 16.0):.0f}%")
        
        return result
    
    elif proposed_margin_pct > WARNING_MARGIN_HIGH:
        result["flags"].append(f"margin_high_warning (>{WARNING_MARGIN_HIGH}%)")
    
    # ===== SI NO HAY LANE DATA =====
    if not historical:
        result["flags"].append("No historical data found")
        
        # CASO ESPECIAL: Multistop Outlier
        if multistop_outlier and multistop_outlier.get("detected"):
            lane_markup = multistop_outlier.get("lane_markup", 1.20)
            suggested_price = carrier_cost * lane_markup
            result["industry_suggested_price"] = round(suggested_price, 2)
            result["multistop_outlier"] = multistop_outlier
            result["recommendation"] = f"Multistop outlier detected. Using lane markup {lane_markup:.3f}x → ${suggested_price:,.2f} (based on {multistop_outlier.get('records')} historical loads)"
            
            if debug:
                print(f"\n   🎯 MULTISTOP OUTLIER pricing:")
                print(f"      Lane carrier cost: ${multistop_outlier.get('lane_carrier_cost'):,.2f}")
                print(f"      Lane customer price: ${multistop_outlier.get('customer_median_price'):,.2f}")
                print(f"      Lane markup: {lane_markup:.3f}x")
                print(f"      Suggested price: ${suggested_price:,.2f}")
            
            return result
        
        # Intentar usar margen histórico del customer
        customer_margin_data = calculate_customer_historical_margin(unity_df, customer_name, debug)
        
        if customer_margin_data and customer_margin_data['total_loads'] >= 5:
            # Hay suficientes datos del customer
            target_margin = customer_margin_data['median_margin_pct'] / 100
            suggested_price = carrier_cost / (1 - target_margin)
            result["industry_suggested_price"] = round(suggested_price, 2)
            result["customer_historical_margin"] = customer_margin_data
            result["recommendation"] = f"No lane data. Customer historical suggests ~${suggested_price:,.2f} ({customer_margin_data['median_margin_pct']:.1f}% margin based on {customer_margin_data['total_loads']} loads)"
        else:
            # Fallback a margen default
            target_margin = PRC_CONFIG.get("target_margin_pct", 16.0) / 100
            suggested_price = carrier_cost / (1 - target_margin)
            result["industry_suggested_price"] = round(suggested_price, 2)
            result["recommendation"] = f"No historical data. Industry standard suggests ~${suggested_price:,.2f} ({PRC_CONFIG.get('target_margin_pct', 16.0):.0f}% margin)"
        
        return result
    
    # ===== SI HAY LANE DATA (normal flow) =====
    result["historical"] = {
        "match_level": historical.match_level,
        "lane_identifier": historical.lane_identifier,
        "customer": historical.customer,
        "median_markup": historical.median_markup,
        "avg_markup": historical.avg_markup,
        "median_margin_pct": historical.median_margin_pct,
        "avg_margin_pct": historical.avg_margin_pct,
        "markup_range": f"{historical.min_markup:.3f} - {historical.max_markup:.3f}",
        "margin_range": f"{historical.min_margin_pct:.1f}% - {historical.max_margin_pct:.1f}%",
        "total_loads": historical.total_loads,
        "recent_loads": historical.recent_loads,
        "confidence_score": historical.confidence_score
    }
    
    result["confidence_score"] = historical.confidence_score
    
    # JERARQUÍA DE PRICING: Lane+Customer > Customer Global > Industry
    
    # PRIORIDAD 1: Lane + Customer específico
    if historical.customer and historical.customer != "ALL":
        # Tenemos data de esta lane CON este customer específico
        suggested_price = carrier_cost * historical.median_markup
        result["industry_suggested_price"] = round(suggested_price, 2)
        
        if debug:
            print(f"\n   💎 LANE+CUSTOMER specific pricing:")
            print(f"      Using lane markup: {historical.median_markup:.3f}x")
            print(f"      Suggested price: ${suggested_price:,.2f}")
    
    # PRIORIDAD 2: Lane sin customer específico → usar customer global
    else:
        customer_margin_data = calculate_customer_historical_margin(unity_df, customer_name, debug)
        
        if customer_margin_data and customer_margin_data['total_loads'] >= 5:
            # Usar customer global margin
            target_margin = customer_margin_data['median_margin_pct'] / 100
            suggested_price = carrier_cost / (1 - target_margin)
            result["industry_suggested_price"] = round(suggested_price, 2)
            result["customer_historical_margin"] = customer_margin_data
            
            if debug:
                print(f"\n   📊 CUSTOMER global pricing:")
                print(f"      Using customer margin: {customer_margin_data['median_margin_pct']:.1f}%")
                print(f"      Suggested price: ${suggested_price:,.2f}")
        else:
            # PRIORIDAD 3: Sin customer data → usar lane markup
            suggested_price = carrier_cost * historical.median_markup
            result["industry_suggested_price"] = round(suggested_price, 2)
            
            if debug:
                print(f"\n   ⚠️ LANE-ONLY pricing (no customer data):")
                print(f"      Using lane markup: {historical.median_markup:.3f}x")
                print(f"      Suggested price: ${suggested_price:,.2f}")
    
    markup_diff = proposed_markup - historical.median_markup
    markup_diff_pct = (markup_diff / historical.median_markup) * 100
    margin_diff_pct = proposed_margin_pct - historical.median_margin_pct
    
    within_historical_range = (
        historical.min_markup <= proposed_markup <= historical.max_markup
    )
    
    within_iqr = (
        historical.p25_markup <= proposed_markup <= historical.p75_markup
    )
    
    result["comparison"] = {
        "markup_diff": markup_diff,
        "markup_diff_pct": markup_diff_pct,
        "margin_diff_pct": margin_diff_pct,
        "within_historical_range": within_historical_range,
        "within_iqr": within_iqr
    }
    
    MINIMUM_MARGIN_PCT = PRC_CONFIG.get("minimum_margin_pct", 5.0)
    
    if proposed_margin_pct < MINIMUM_MARGIN_PCT:
        result["rating"] = "POOR"
        result["recommendation"] = f"REJECT. Margin below minimum (<{MINIMUM_MARGIN_PCT}%)."
        result["flags"].append("margin_below_minimum")
    else:
        deviation_pct = abs(markup_diff_pct)
        
        if deviation_pct <= RATING_THRESHOLDS["excellent"]["max"]:
            result["rating"] = "EXCELLENT"
            result["recommendation"] = "Pricing aligned with historical median"
        elif deviation_pct <= RATING_THRESHOLDS["good"]["max"]:
            result["rating"] = "GOOD"
            result["recommendation"] = "Pricing within acceptable range"
        elif deviation_pct <= RATING_THRESHOLDS["acceptable"]["max"]:
            result["rating"] = "ACCEPTABLE"
            result["recommendation"] = "Pricing reasonable but could be optimized"
        elif deviation_pct <= RATING_THRESHOLDS["risky"]["max"]:
            result["rating"] = "RISKY"
            result["recommendation"] = "Pricing deviates significantly"
        else:
            result["rating"] = "POOR"
            result["recommendation"] = "Pricing far outside historical ranges"
    
    if proposed_markup < historical.p25_markup:
        result["flags"].append("Below 25th percentile")
    elif proposed_markup > historical.p75_markup:
        result["flags"].append("Above 75th percentile")
    
    if not within_historical_range:
        result["flags"].append("Outside historical range")
    
    if historical.match_level != "exact":
        result["flags"].append(f"Using {historical.match_level.upper()} match")
    
    if historical.recent_loads < 3:
        result["flags"].append("Limited recent data")
    
    return result
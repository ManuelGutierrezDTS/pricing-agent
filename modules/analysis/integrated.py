# modules/analysis/integrated.py
"""
Integrated Analysis Module
Orquesta todos los componentes del Pricing Agent
CON SUGGESTED PRICE CONSISTENTE Y OUTLIER DETECTION EN MULTISTOP
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd

from config import (
    PRC_CONFIG, SINGLE_ANALYSIS, PATH_CONFIG
)
from modules.utils.helpers import safe_float, safe_int, round_to_nearest_5
from modules.logic.location import resolve_location
from modules.logic.equipment import normalize_equipment, is_multi_equipment
from modules.logic.hotshot import handle_hotshot
from modules.logic.multistop import is_multistop, calculate_multistop_negotiation_range
from modules.logic.multi_equipment import handle_multi_equipment
from modules.apis.dat_api import get_dat_data_with_retry
from modules.apis.gs_api import get_greenscreens_data_with_retry
from modules.apis.google_maps_api import calculate_google_miles
from modules.analysis.id_analysis import run_internal_data_analysis
from modules.analysis.prc import validate_customer_pricing
from modules.analysis.negotiation import calculate_negotiation_range


def run_integrated_analysis(
    unity_df: pd.DataFrame,
    analysis_config: Dict
) -> Dict[str, Any]:
    """Run complete integrated analysis"""
    
    print("\n" + "="*70)
    print("🔍 RUNNING INTEGRATED PRICING ANALYSIS")
    print("="*70)
    
    # Parse configuration
    stops = analysis_config["stops"]
    equipment = normalize_equipment(analysis_config["equipment_type"])
    weight = analysis_config.get("weight", 0)
    proposed_price = analysis_config["proposed_price"]
    carrier_cost_input = analysis_config["carrier_cost"]
    customer_name = analysis_config.get("customer_name", "")
    
    # Parse dates
    pickup_date = analysis_config.get("pickup_date")
    if pickup_date:
        if isinstance(pickup_date, str):
            pickup_date = datetime.strptime(pickup_date, "%Y-%m-%d")
    else:
        pickup_date = datetime.now()
    
    delivery_date = analysis_config.get("delivery_date")
    if delivery_date:
        if isinstance(delivery_date, str):
            delivery_date = datetime.strptime(delivery_date, "%Y-%m-%d")
    else:
        delivery_date = pickup_date + timedelta(days=2)
    
    # Resolve locations from stops
    print("\n📍 Resolving locations...")
    resolved_stops = []
    for stop in stops:
        city, state, zip_code = resolve_location(stop)
        resolved_stops.append({
            "type": stop["type"].upper(),
            "city": city,
            "state": state,
            "zip": zip_code
        })
        print(f"   {stop['type']}: {city}, {state} {zip_code}")
    
    # Detectar multistop
    is_multi = is_multistop(resolved_stops)
    
    pickup_stop = next(s for s in resolved_stops if s["type"] == "PICKUP")
    drop_stops = [s for s in resolved_stops if s["type"] == "DROP"]
    last_drop = drop_stops[-1]
    
    origin_city = pickup_stop["city"]
    origin_state = pickup_stop["state"]
    origin_zip = pickup_stop["zip"]
    
    dest_city = last_drop["city"]
    dest_state = last_drop["state"]
    dest_zip = last_drop["zip"]
    
    # Handle Hotshot
    hotshot_adjustment = 1.0
    original_equipment = equipment
    is_hotshot = False
    
    if weight > 0:
        api_equipment, hotshot_adjustment, is_hotshot = handle_hotshot(equipment, weight)
        
        if is_hotshot:
            # Usar api_equipment (FLATBED) para llamadas API
            equipment = api_equipment
    
    # Handle Multi-Equipment
    dat_data = None
    if is_multi_equipment(equipment):
        equipment, dat_data = handle_multi_equipment(
            origin_city, origin_state, dest_city, dest_state, equipment, 0
        )
    
    # Calcular millas
    google_miles = None
    dat_miles = None
    
    if is_multi:
        print(f"\n🗺️  MULTISTOP DETECTED: {len(drop_stops)} drop stops")
        google_miles = calculate_google_miles(resolved_stops)
        if not google_miles:
            print("   ⚠️ Google Miles calculation failed, cannot proceed with multistop")
            return {"error": "Google Miles calculation failed for multistop"}
    
    # Get DAT data (si no se obtuvo en multi-equipment)
    if not dat_data:
        estimated_miles = google_miles if google_miles else 500
        dat_data = get_dat_data_with_retry(
            origin_city, origin_state, dest_city, dest_state, equipment, estimated_miles
        )
    
    if not dat_data or not dat_data.get("rates_mci"):
        print("   ⚠️ DAT data not available")
        dat_miles = google_miles if google_miles else 500
    else:
        dat_miles = dat_data["rates_mci"].get("mileage", 500)
    
    miles = google_miles if google_miles else dat_miles
    
    # Get GreenScreens data
    gs_data = get_greenscreens_data_with_retry(
        pickup_date, origin_city, origin_state, dest_city, dest_state, equipment
    )
    
    # Run ID analysis
    print("\n📊 Running Internal Data Analysis (ID)...")
    print("-"*40)
    internal_data = run_internal_data_analysis(
        unity_df=unity_df,
        origin_zip=origin_zip,
        destination_zip=dest_zip,
        equipment_type=equipment,
        pickup_date=pickup_date
    )
    
    # Display ID results - CARRIER COSTS
    print("🚚 CARRIER COSTS (What we pay):")
    if internal_data.get("RecommendedCarrier"):
        print(f"   ✅ Recommended Carrier: {internal_data['RecommendedCarrier']}")
        print(f"      Best Rate: ${safe_float(internal_data.get('BestCarrierAverageRate')):.2f}")
    else:
        print("   ⚠️ No recommended carrier found")
    
    print(f"   Lane Median: ${safe_float(internal_data.get('LaneMedianRate')):.2f}")
    print(f"   ZIP3 Median: ${safe_float(internal_data.get('Zip3MedianLaneRate')):.2f}")
    
    # Display ID results - CUSTOMER PRICING
    if internal_data.get("CustomerMedianPrice"):
        print(f"\n💵 CUSTOMER PRICING (What we charged):")
        print(f"   Customer Median: ${safe_float(internal_data.get('CustomerMedianPrice')):.2f}")
        print(f"   Customer Average: ${safe_float(internal_data.get('CustomerAveragePrice')):.2f}")
        if internal_data.get("HistoricalMarginPct"):
            print(f"   Historical Margin: {safe_float(internal_data.get('HistoricalMarginPct')):.1f}%")
        if internal_data.get("HistoricalMarkup"):
            print(f"   Historical Markup: {safe_float(internal_data.get('HistoricalMarkup')):.3f}x")
    else:
        print(f"\n💵 CUSTOMER PRICING: No historical customer pricing data available")
    
    print(f"\n📊 DATA QUALITY:")
    print(f"   Records: Lane={safe_int(internal_data.get('RecordsAnalyzed_Lane'))}, ZIP3={safe_int(internal_data.get('RecordsAnalyzed_Zip3'))}")
    print(f"   Confidence: {safe_float(internal_data.get('HistConfidence'))}%")
    
    # Calculate carrier cost if "auto"
    target_rate = None
    max_buy = None
    outlier_info = None
    
    if carrier_cost_input == "auto":
        print("\n💰 Calculating Carrier Cost (auto mode)...")
        
        if is_multi and google_miles and dat_miles:
            # Multistop - CAPTURAR outlier_info
            target_rate, max_buy, outlier_info = calculate_multistop_negotiation_range(
                google_miles=google_miles,
                dat_miles=dat_miles,
                stops_count=len(drop_stops),
                customer_name=customer_name,
                dat_data=dat_data or {},
                hotshot_adjustment=hotshot_adjustment,
                internal_data=internal_data,
                greenscreens_data=gs_data
            )
        else:
            # Single-stop
            target_rate, max_buy = calculate_negotiation_range(
                miles=miles,
                pickup_date=pickup_date,
                delivery_date=delivery_date,
                dat_data=dat_data or {},
                greenscreens_data=gs_data or {},
                internal_data=internal_data
            )
            
            # Aplicar hotshot adjustment si existe
            if hotshot_adjustment != 1.0:
                target_rate = round_to_nearest_5(target_rate * hotshot_adjustment)
                max_buy = round_to_nearest_5(max_buy * hotshot_adjustment)
        
        if target_rate and max_buy:
            carrier_cost = (target_rate + max_buy) / 2
            print(f"   Target Rate: ${target_rate}")
            print(f"   Max Buy: ${max_buy}")
            print(f"   Carrier Cost (midpoint): ${carrier_cost:.2f}")
        else:
            print("   ⚠️ Could not calculate negotiation range")
            carrier_cost = None
    else:
        carrier_cost = float(carrier_cost_input)
        print(f"\n💰 Using fixed Carrier Cost: ${carrier_cost}")
    
    if not carrier_cost or carrier_cost <= 0:
        return {
            "error": "Could not determine carrier cost",
            "dat_data": dat_data,
            "greenscreens_data": gs_data,
            "internal_data": internal_data
        }
    
    # Run PRC validation - PASAR outlier_info
    print("\n📊 Running Price Validation (PRC)...")
    print("-"*40)
    prc_result = validate_customer_pricing(
        unity_df=unity_df,
        proposed_customer_price=proposed_price,
        carrier_cost=carrier_cost,
        origin_zip=origin_zip,
        destination_zip=dest_zip,
        customer_name=customer_name,
        debug=PRC_CONFIG["debug_mode"],
        multistop_outlier=outlier_info
    )
    
    print(f"✅ PRC Rating: {prc_result['rating']}")
    print(f"   Confidence: {prc_result['confidence_score']}/100")
    print(f"   Proposed Margin: ${prc_result['proposed_margin_dollars']:.2f} ({prc_result['proposed_margin_pct']:.2f}%)")
    print(f"   Proposed Markup: {prc_result['proposed_markup']:.3f}x")
    
    if prc_result.get('historical'):
        hist = prc_result['historical']
        print(f"   Historical - Level: {hist['match_level']}, Median Markup: {hist['median_markup']:.3f}x")
    
    # Mostrar precio sugerido e info del customer
    if prc_result.get('industry_suggested_price'):
        print(f"\n💡 SUGGESTED PRICING:")
        print(f"   Suggested Price: ${prc_result['industry_suggested_price']:,.2f}")
        
        # Si hay customer historical margin, mostrarlo
        if prc_result.get('customer_historical_margin'):
            chm = prc_result['customer_historical_margin']
            print(f"   Based on: Customer historical margin")
            print(f"   Customer: {chm['customer_name']}")
            print(f"   Loads analyzed: {chm['total_loads']}")
            print(f"   Median margin: {chm['median_margin_pct']:.1f}%")
            print(f"   Median markup: {chm['median_markup']:.3f}x")
        elif prc_result.get('multistop_outlier'):
            print(f"   Based on: Multistop outlier - lane historical markup")
        else:
            print(f"   Based on: Industry standard ({PRC_CONFIG.get('target_margin_pct', 16.0):.0f}% margin)")
    
    # Build results
    results = {
        "timestamp": datetime.now().isoformat(),
        "load_type": "MULTISTOP" if is_multi else "SINGLE-STOP",
        "inputs": {
            "proposed_price": proposed_price,
            "carrier_cost": carrier_cost,
            "origin": f"{origin_city}, {origin_state} {origin_zip}",
            "destination": f"{dest_city}, {dest_state} {dest_zip}",
            "stops": resolved_stops,
            "customer_name": customer_name,
            "equipment_type": equipment,
            "original_equipment": original_equipment,
            "weight": weight,
            "pickup_date": pickup_date.isoformat() if pickup_date else None,
            "delivery_date": delivery_date.isoformat() if delivery_date else None,
        },
        "mileage": {
            "google_miles": google_miles,
            "dat_miles": dat_miles,
            "miles_used": miles
        },
        "negotiation_range": {
            "target_rate": target_rate,
            "max_buy": max_buy,
            "carrier_cost": carrier_cost,
            "hotshot_adjustment": hotshot_adjustment,
            "method": "multistop" if is_multi else "singlestop"
        },
        "prc_validation": prc_result,
        "id_analysis": internal_data,
        "dat_api_data": dat_data,
        "greenscreens_api_data": gs_data,
    }
    
    # Guardar outlier info si existe
    if outlier_info:
        results["multistop_outlier"] = outlier_info
    
    # Combined recommendation
    print("\n" + "="*70)
    print("🎯 GENERATING FINAL RECOMMENDATION")
    print("="*70)
    
    prc_confidence = prc_result.get("confidence_score", 0)
    id_confidence = internal_data.get("HistConfidence", 0)
    combined_confidence = int((prc_confidence * 0.6) + (id_confidence * 0.4))
    
    results["combined_confidence"] = combined_confidence
    
    # NUEVA LÓGICA: Priorizar industry_suggested_price de PRC
    final_suggested = None
    
    # PRIORIDAD 1: Usar industry_suggested_price de PRC (es el más inteligente)
    if prc_result.get("industry_suggested_price"):
        final_suggested = prc_result["industry_suggested_price"]
        print(f"\n💡 Using PRC suggested price: ${final_suggested:,.2f}")
        
    # PRIORIDAD 2: Si no hay PRC suggestion, calcular con customer historical margin
    elif prc_result.get("customer_historical_margin"):
        chm = prc_result["customer_historical_margin"]
        median_markup = chm.get("median_markup", 1.20)
        final_suggested = carrier_cost * median_markup
        print(f"\n💡 Using customer historical markup ({median_markup:.3f}x): ${final_suggested:,.2f}")
        
    # PRIORIDAD 3: Usar industry standard margin
    else:
        target_margin = PRC_CONFIG.get("target_margin_pct", 16.0) / 100
        final_suggested = carrier_cost / (1 - target_margin)
        print(f"\n💡 Using industry standard margin ({target_margin*100:.0f}%): ${final_suggested:,.2f}")
    
    # Verificar margen mínimo
    MINIMUM_MARGIN_PCT = PRC_CONFIG.get("minimum_margin_pct", 5.0)
    min_price_for_margin = carrier_cost / (1 - MINIMUM_MARGIN_PCT/100)
    
    if final_suggested < min_price_for_margin:
        print(f"   ⚠️ Adjusting to meet minimum margin ({MINIMUM_MARGIN_PCT}%)")
        final_suggested = min_price_for_margin
        results["price_adjusted_for_min_margin"] = True
    else:
        results["price_adjusted_for_min_margin"] = False
    
    results["suggested_price"] = round(final_suggested, 2)
    results["suggested_margin_pct"] = ((final_suggested - carrier_cost) / final_suggested) * 100
    
    # Final rating
    proposed_margin_pct = ((proposed_price - carrier_cost) / proposed_price) * 100
    
    if proposed_margin_pct < MINIMUM_MARGIN_PCT:
        final_rating = "POOR"
        results["margin_flag"] = "below_minimum"
    else:
        final_rating = prc_result["rating"]
        if final_rating in ["RISKY", "POOR"] and combined_confidence < 50:
            final_rating = "NEEDS_REVIEW"
        elif final_rating == "ACCEPTABLE" and combined_confidence > 80:
            final_rating = "GOOD"
    
    results["final_rating"] = final_rating
    
    # Print summary
    print(f"\n🏆 FINAL RATING: {final_rating}")
    print(f"📊 COMBINED CONFIDENCE: {combined_confidence}%")
    print(f"\n💰 SUGGESTED PRICE: ${results['suggested_price']:,.2f}")
    print(f"   Suggested Margin: {results['suggested_margin_pct']:.2f}%")
    
    diff = results['suggested_price'] - proposed_price
    diff_pct = (diff / proposed_price) * 100 if proposed_price > 0 else 0
    
    print(f"\n📊 COMPARISON:")
    print(f"   Proposed Price: ${proposed_price:,.2f}")
    print(f"   Suggested Price: ${results['suggested_price']:,.2f}")
    print(f"   Difference: ${diff:+.2f} ({diff_pct:+.1f}%)")
    
    if abs(diff) > 50:
        if diff > 0:
            print("   ⬆️ Recommendation: Consider increasing price")
        else:
            print("   ⬇️ Recommendation: Consider reducing price")
    else:
        print("   ✅ Proposed price is within acceptable range")
    
    if prc_result.get("recommendation"):
        print(f"\n📋 PRC RECOMMENDATION: {prc_result['recommendation']}")
    
    if proposed_margin_pct < MINIMUM_MARGIN_PCT:
        print(f"\n🚨 CRITICAL: Margin ({proposed_margin_pct:.2f}%) below minimum ({MINIMUM_MARGIN_PCT}%)")
        print(f"   Minimum acceptable price: ${min_price_for_margin:.2f}")
    
    if prc_result.get("flags"):
        print("\n⚠️ FLAGS:")
        for flag in prc_result["flags"]:
            print(f"   • {flag}")
    
    return results
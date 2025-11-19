# modules/logic/multistop.py
"""
Multistop logic handler
Detección de multistop y cálculo de negotiation range
CON INTEGRACIÓN DE HISTORICAL DATA, LAYOVER INTELIGENTE, LÓGICA DIFERENCIADA Y OUTLIER DETECTION
RETORNA OUTLIER INFO PARA PRC
"""

from typing import List, Dict, Tuple, Optional
import numpy as np
from modules.utils.helpers import normalize_text, round_to_nearest_5, contains_word
from config import MULTISTOP_CONFIG


def is_multistop(stops: List[Dict]) -> bool:
    """Detecta si hay múltiples DROP stops"""
    drop_count = sum(1 for s in stops if normalize_text(s.get("type", "")) == "DROP")
    return drop_count > 1


def calculate_multistop_negotiation_range(
    google_miles: float,
    dat_miles: float,
    stops_count: int,
    customer_name: str,
    dat_data: Dict,
    hotshot_adjustment: float = 1.0,
    internal_data: Optional[Dict] = None,
    greenscreens_data: Optional[Dict] = None
) -> Tuple[Optional[float], Optional[float], Optional[Dict]]:
    """
    Calcula targetRate y maxBuy para cargas multistop
    LÓGICA COMPLETA:
    - Detecta outliers (negociaciones excepcionales)
    - Usa historical data cuando existe
    - Layover inteligente (solo si >1.5 días)
    - Stop charges diferenciados: Fabuwood vs Non-Fabuwood
    
    Returns:
        (target_rate, max_buy, outlier_info)
    """
    
    print(f"\n   🗺️  MULTISTOP Calculation:")
    print(f"     Google Miles (real): {google_miles}")
    print(f"     DAT Miles (origin→last drop): {dat_miles}")
    print(f"     Stops Count: {stops_count}")
    print(f"     Customer: {customer_name}")
    
    # Identificar tipo de customer
    is_fabuwood = contains_word(customer_name or "", "fabuwood")
    
    # Variable para outlier info
    outlier_info = None
    
    # PASO 0: Evaluar si hay historical data
    has_lane_data = False
    lane_median = None
    lane_confidence = 0
    records = 0
    
    if internal_data:
        lane_median = internal_data.get("LaneMedianRate")
        lane_confidence = internal_data.get("HistConfidence", 0)
        records = internal_data.get("RecordsAnalyzed_Lane", 0)
        
        # Threshold más estricto: confidence >= 40% Y al menos 3 records
        if lane_median and lane_median > 0 and lane_confidence >= 40 and records >= 3:
            has_lane_data = True
            print(f"     📊 Lane Historical: ${lane_median:,.2f} (confidence {lane_confidence}%, {records} records)")
    
    # 🆕 PASO 0.5: DETECTAR OUTLIERS EXCEPCIONALES
    outlier_detected = False
    
    if internal_data and lane_median and lane_median > 0 and records >= 1:
        # Construir lista de market rates
        market_rates = []
        
        # DAT rates
        if dat_data and dat_data.get("rates_mci"):
            mci = dat_data["rates_mci"]
            if mci.get("total_forecastUSD"):
                market_rates.append(mci["total_forecastUSD"])
            if mci.get("total_mae_highUSD"):
                market_rates.append(mci["total_mae_highUSD"])
            if mci.get("total_mae_lowUSD"):
                market_rates.append(mci["total_mae_lowUSD"])
        
        # GreenScreens rates
        if greenscreens_data and greenscreens_data.get("RateForecast"):
            rf = greenscreens_data["RateForecast"]
            if rf.get("total_targetBuyRate"):
                market_rates.append(rf["total_targetBuyRate"])
            if rf.get("total_highBuyRate"):
                market_rates.append(rf["total_highBuyRate"])
            if rf.get("total_lowBuyRate"):
                market_rates.append(rf["total_lowBuyRate"])
        
        if market_rates:
            market_median = np.median([r for r in market_rates if r > 0])
            
            if market_median > 0:
                # Calcular desviación: ¿qué tan bajo está el historical vs market?
                deviation = (market_median - lane_median) / market_median
                
                # 🎯 OUTLIER: Si lane median es ≥30% más bajo que market
                if deviation >= 0.30:
                    outlier_detected = True
                    
                    # 🆕 CONSTRUIR OUTLIER INFO
                    outlier_info = {
                        "detected": True,
                        "lane_carrier_cost": lane_median,
                        "market_median": market_median,
                        "deviation_pct": deviation * 100,
                        "records": records,
                        "customer_median_price": internal_data.get("CustomerMedianPrice"),
                        "customer_average_price": internal_data.get("CustomerAveragePrice"),
                        "lane_markup": internal_data.get("HistoricalMarkup", 1.20),
                        "lane_margin_pct": internal_data.get("HistoricalMarginPct", 15.0)
                    }
                    
                    print(f"\n     🎯 EXCEPTIONAL NEGOTIATION DETECTED (OUTLIER):")
                    print(f"        Lane Median: ${lane_median:,.2f}")
                    print(f"        Market Median: ${market_median:,.2f}")
                    print(f"        Deviation: {deviation*100:.1f}% below market")
                    print(f"        Records: {records} (recent)")
                    print(f"     ✅ Using OUTLIER-BASED pricing (trust exceptional negotiation)")
    
    # Obtener DAT average rate
    dat_average = None
    try:
        rates_mci = dat_data.get("rates_mci", {})
        dat_average = rates_mci.get("total_forecastUSD")
    except:
        pass
    
    if not dat_average or dat_average <= 0:
        print(f"     ❌ No DAT average rate available")
        return None, None, None
    
    if dat_miles <= 0 or google_miles <= 0:
        print(f"     ❌ Invalid miles data")
        return None, None, None
    
    # Calcular diferencia de millas
    miles_diff = google_miles - dat_miles
    miles_diff_pct = (miles_diff / dat_miles) * 100 if dat_miles > 0 else 0
    
    print(f"     Miles difference: {miles_diff:.0f} miles ({miles_diff_pct:+.1f}%)")
    
    # 🆕 DECISIÓN 1: OUTLIER (prioridad máxima)
    if outlier_detected:
        # ========== MÉTODO 0: OUTLIER - CONFIAR EN NEGOCIACIÓN EXCEPCIONAL ==========
        base_cost = lane_median
        
        # Solo ajustar por stops extra (MUY conservador)
        extra_stops = stops_count - 1
        
        # Para outliers, usar stop charge MÍNIMO (asumimos negociación incluyó complejidad)
        stop_charge = 50  # Fijo, no importa complejidad
        total_stop_charge = extra_stops * stop_charge
        
        # NO layover para outliers (asumimos fue negociación agresiva todo incluido)
        layover_rate = 0
        
        print(f"     📊 OUTLIER Calculation breakdown:")
        print(f"        Historical base: ${base_cost:,.2f}")
        print(f"        Stop charges: +${total_stop_charge} (conservative)")
        print(f"        Layover: $0 (included in negotiation)")
        
        total_cost = base_cost + total_stop_charge
        total_cost = round_to_nearest_5(total_cost * hotshot_adjustment)
        
        print(f"        Total: ${total_cost:,.2f}")
        
        # Spread MUY estrecho (confiamos en la negociación)
        target_rate = round_to_nearest_5(total_cost * 0.95)
        max_buy = round_to_nearest_5(total_cost * 1.05)
        
        print(f"     Target Rate: ${target_rate:,.2f}")
        print(f"     Max Buy: ${max_buy:,.2f}")
        print(f"     Spread: ${max_buy - target_rate:.2f} (10% - tight for outlier)")
    
    # DECISIÓN 2: ¿Usar historical o calcular desde cero?
    elif has_lane_data:
        # ========== MÉTODO 1: USAR HISTORICAL COMO BASE ==========
        print(f"     ✅ Using HISTORICAL-BASED pricing")
        
        base_cost = lane_median
        
        # Calcular cargo incremental por stops adicionales
        extra_stops = stops_count - 1
        
        # LÓGICA DIFERENCIADA: Fabuwood vs Non-Fabuwood
        if is_fabuwood:
            # FABUWOOD: Muchas paradas, alta complejidad
            print(f"     🏢 Customer type: FABUWOOD (high complexity rates)")
            if miles_diff_pct < 20:
                stop_charge = 150
                complexity = "LOW"
            elif miles_diff_pct < 40:
                stop_charge = 200
                complexity = "MEDIUM"
            else:
                stop_charge = 250
                complexity = "HIGH"
        else:
            # NON-FABUWOOD: Pocas paradas, complejidad moderada
            print(f"     🏢 Customer type: STANDARD (conservative rates)")
            if miles_diff_pct < 20:
                stop_charge = 50
                complexity = "LOW"
            elif miles_diff_pct < 40:
                stop_charge = 75
                complexity = "MEDIUM"
            else:
                stop_charge = 100
                complexity = "HIGH"
        
        print(f"     Route complexity: {complexity} (stop charge: ${stop_charge} per extra stop)")
        
        total_stop_charge = extra_stops * stop_charge
        
        # LAYOVER INTELIGENTE
        days_google = google_miles / 500
        
        layover_rate_per_day = (
            MULTISTOP_CONFIG["layover_rate_fabuwood"] if is_fabuwood 
            else MULTISTOP_CONFIG["layover_rate"]
        )
        
        if days_google > 1.5:
            layover_count = int(days_google) - 1
            layover_rate = layover_count * layover_rate_per_day
            print(f"     Layover: {days_google:.1f} days total → {layover_count} layover day(s) × ${layover_rate_per_day} = ${layover_rate}")
        else:
            layover_rate = 0
            print(f"     Layover: {days_google:.1f} days total → No layover charge (same-day or 1-day trip)")
        
        print(f"     Stop charge: {extra_stops} extra stops × ${stop_charge} = ${total_stop_charge}")
        
        # Total cost = base + incremental
        total_cost = base_cost + total_stop_charge + layover_rate
        total_cost = round_to_nearest_5(total_cost * hotshot_adjustment)
        
        # Spread más estrecho porque tenemos datos históricos
        spread_pct = 0.05
        target_rate = round_to_nearest_5(total_cost * 0.98)
        max_buy = round_to_nearest_5(total_cost * 1.03)
        
        print(f"     📊 Calculation breakdown:")
        print(f"        Historical base: ${base_cost:,.2f}")
        print(f"        Stop charges: +${total_stop_charge}")
        if layover_rate > 0:
            print(f"        Layover: +${layover_rate}")
        print(f"        Total: ${total_cost:,.2f}")
        print(f"     Target Rate: ${target_rate:,.2f}")
        print(f"     Max Buy: ${max_buy:,.2f}")
        print(f"     Spread: ${max_buy - target_rate:.2f} ({spread_pct*100:.0f}%)")
        
    else:
        # ========== MÉTODO 2: CÁLCULO DESDE CERO (MARKET-BASED) ==========
        print(f"     📊 Using MARKET-BASED pricing (no reliable historical)")
        
        # LAYOVER INTELIGENTE
        days_google = google_miles / 500
        
        if is_fabuwood:
            variable_stops = MULTISTOP_CONFIG["variable_stop_charge_fabuwood"]
            layover_rate_per_day = MULTISTOP_CONFIG["layover_rate_fabuwood"]
            increase_per_stop = round(
                (stops_count / MULTISTOP_CONFIG["extra_stops_bonus_divisor"]) * 
                MULTISTOP_CONFIG["extra_stops_bonus_multiplier_fabuwood"], 
                2
            ) if stops_count > 4 else 0
            print(f"     🏢 Customer type: FABUWOOD (special rates)")
        else:
            # NON-FABUWOOD: Usar stop charges más conservadores
            base_stop_charge = 75
            
            if miles_diff_pct < 20:
                variable_stops = base_stop_charge * 0.67  # ~$50
            elif miles_diff_pct < 40:
                variable_stops = base_stop_charge  # $75
            else:
                variable_stops = base_stop_charge * 1.33  # ~$100
            
            layover_rate_per_day = MULTISTOP_CONFIG["layover_rate"]
            increase_per_stop = 0
            print(f"     🏢 Customer type: STANDARD (conservative rates)")
        
        # Layover inteligente
        if days_google > 1.5:
            layover_count = int(days_google) - 1
            layover_rate = layover_count * layover_rate_per_day
            print(f"     Layover: {days_google:.1f} days total → {layover_count} layover day(s) × ${layover_rate_per_day} = ${layover_rate}")
        else:
            layover_rate = 0
            print(f"     Layover: {days_google:.1f} days total → No layover charge")
        
        total_stops_charge = stops_count * variable_stops
        
        print(f"     Stops charge: {stops_count} × ${variable_stops:.0f} = ${total_stops_charge:.0f}")
        if increase_per_stop > 0:
            print(f"     Extra stops bonus: ${increase_per_stop}")
        
        # Calcular RPM y mileage charge
        rpm = dat_average / dat_miles
        mileage_charge = rpm * google_miles
        
        print(f"     RPM: ${rpm:.2f}/mile")
        print(f"     Mileage charge: {google_miles:.0f} miles × ${rpm:.2f} = ${mileage_charge:.2f}")
        
        # Calcular total cost
        if miles_diff >= 0:
            total_cost = round_to_nearest_5(
                mileage_charge + total_stops_charge + increase_per_stop + layover_rate
            )
        else:
            total_cost = round_to_nearest_5(
                dat_average + total_stops_charge + increase_per_stop + layover_rate
            )
        
        # Aplicar hotshot adjustment si existe
        total_cost = round_to_nearest_5(total_cost * hotshot_adjustment)
        
        # Aplicar markup
        markup = MULTISTOP_CONFIG["markup"]
        final_rate = round_to_nearest_5(total_cost * (1 + markup))
        
        # Determinar target y maxBuy
        target_rate = total_cost
        max_buy = final_rate
        
        print(f"     Total Cost (target): ${total_cost}")
        print(f"     Final Rate (maxBuy): ${max_buy}")
        print(f"     Markup: ${max_buy - target_rate} ({markup*100:.0f}%)")
    
    if target_rate <= 0 or max_buy <= 0:
        return None, None, None
    
    if max_buy <= target_rate:
        max_buy = round_to_nearest_5(target_rate * 1.10)
    
    return float(target_rate), float(max_buy), outlier_info
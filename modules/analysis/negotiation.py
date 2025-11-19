# modules/analysis/negotiation.py
"""
Negotiation Range Calculator
Calcula target_rate y max_buy basado en múltiples fuentes de datos
CON PRIORIZACIÓN INTELIGENTE DEL HISTÓRICO INTERNO Y DAT FORECAST
THRESHOLD AJUSTADO: 40% + RECORDS COMBINADOS (Lane + ZIP3)
STRONG HISTORICAL: No market cushion cuando confidence ≥90%
"""

import numpy as np
from datetime import datetime
from typing import Dict, Optional, Tuple
from config import NEGOTIATION_CONFIG
from modules.utils.helpers import round_to_nearest_5


def calculate_negotiation_range(
    miles: float,
    pickup_date: Optional[datetime] = None,
    delivery_date: Optional[datetime] = None,
    dat_data: Optional[Dict] = None,
    greenscreens_data: Optional[Dict] = None,
    internal_data: Optional[Dict] = None,
    config: Optional[Dict] = None
) -> Tuple[float, float]:
    """
    Calculate target_rate and max_buy based on API data and internal historical data
    NUEVA LÓGICA: Prioriza histórico interno cuando hay alta confianza
    INCLUYE: DAT Forecast (8-day) para mejor precisión
    """
    
    if config is None:
        config = NEGOTIATION_CONFIG
    
    transit_days = config["transit_days_default"]
    if pickup_date and delivery_date:
        try:
            delta = delivery_date - pickup_date
            transit_days = max(1, delta.days)
        except:
            pass
    
    pickup_weekday = None
    if pickup_date:
        try:
            pickup_weekday = pickup_date.weekday()
        except:
            pickup_weekday = datetime.now().weekday()
    else:
        pickup_weekday = datetime.now().weekday()
    
    # Extract rates from DAT (INCLUYENDO FORECAST)
    dat_rates = []
    if dat_data and dat_data.get("rates_mci"):
        mci = dat_data["rates_mci"]
        if mci.get("total_forecastUSD"):
            dat_rates.append(mci["total_forecastUSD"])
        if mci.get("total_mae_highUSD"):
            dat_rates.append(mci["total_mae_highUSD"])
        if mci.get("total_mae_lowUSD"):
            dat_rates.append(mci["total_mae_lowUSD"])
    
    # INCLUIR DAT FORECAST (8-day) - MÁS IMPORTANTE
    if dat_data and dat_data.get("forecast"):
        forecast = dat_data["forecast"]
        if forecast.get("total_forecastUSD"):
            dat_rates.append(forecast["total_forecastUSD"])
            print(f"      📈 Including DAT 8-day forecast: ${forecast['total_forecastUSD']:,.2f}")
        # También incluir high/low del forecast
        if forecast.get("total_mae_highUSD"):
            dat_rates.append(forecast["total_mae_highUSD"])
        if forecast.get("total_mae_lowUSD"):
            dat_rates.append(forecast["total_mae_lowUSD"])
    
    gs_rates = []
    if greenscreens_data and greenscreens_data.get("RateForecast"):
        rf = greenscreens_data["RateForecast"]
        if rf.get("total_targetBuyRate"):
            gs_rates.append(rf["total_targetBuyRate"])
        if rf.get("total_highBuyRate"):
            gs_rates.append(rf["total_highBuyRate"])
        if rf.get("total_lowBuyRate"):
            gs_rates.append(rf["total_lowBuyRate"])
    
    # NUEVA LÓGICA: Evaluar calidad del histórico interno
    internal_confidence = internal_data.get("HistConfidence", 0) if internal_data else 0
    
    # USAR RECORDS COMBINADOS (Lane + ZIP3)
    lane_records = internal_data.get("RecordsAnalyzed_Lane", 0) if internal_data else 0
    zip3_records = internal_data.get("RecordsAnalyzed_Zip3", 0) if internal_data else 0
    internal_records = lane_records + zip3_records
    
    lane_median = internal_data.get("LaneMedianRate") if internal_data else None
    best_carrier_rate = internal_data.get("BestCarrierAverageRate") if internal_data else None
    
    # THRESHOLD DE CONFIDENCE AJUSTADO: 40% (más inclusivo)
    INTERNAL_CONFIDENCE_THRESHOLD = 40
    
    # REQUISITOS DE RECORDS AJUSTADOS (más realistas)
    # Determinar si el histórico es confiable
    has_strong_historical = (
        internal_confidence >= 80 and 
        internal_records >= 8 and
        lane_median and 
        lane_median > 0
    )
    
    has_good_historical = (
        internal_confidence >= 60 and 
        internal_records >= 3 and
        lane_median and 
        lane_median > 0
    )
    
    # Nuevo nivel: MODERATE (50-59% confidence)
    has_moderate_historical = (
        internal_confidence >= 50 and
        internal_confidence < 60 and
        internal_records >= 2 and
        lane_median and
        lane_median > 0
    )
    
    has_acceptable_historical = (
        internal_confidence >= INTERNAL_CONFIDENCE_THRESHOLD and 
        internal_confidence < 50 and
        internal_records >= 1 and
        lane_median and 
        lane_median > 0
    )
    
    # Calcular mediana de APIs (para comparación)
    api_rates = dat_rates + gs_rates
    api_median = np.median(api_rates) if api_rates else None
    
    # DECISIÓN INTELIGENTE DE PRICING
    if has_strong_historical:
        # CASO 1: Histórico EXCELENTE (Confidence ≥80%, Records ≥8)
        print(f"\n   💎 STRONG HISTORICAL DATA DETECTED:")
        print(f"      Confidence: {internal_confidence}%, Records: {internal_records} (Lane={lane_records}, ZIP3={zip3_records})")
        print(f"      Using historical base: ${lane_median:,.2f}")
        
        base_rate = lane_median
        
        # 🆕 NUEVA LÓGICA: Con confidence MUY alta (≥90%) y muchos records (≥20), NO ajustar
        if internal_confidence >= 90 and internal_records >= 20:
            adjustment = 1.0
            print(f"      No market adjustment: Excellent data quality (conf≥90%, rec≥20)")
        
        # 🆕 Con confidence alta (≥85%) y buenos records (≥15), solo ajustar si market MUY alto
        elif internal_confidence >= 85 and internal_records >= 15:
            if api_median:
                market_trend = (api_median - lane_median) / lane_median
                print(f"      Market trend: {market_trend*100:+.1f}% vs historical")
                
                if market_trend > 0.20:  # Mercado >20% más alto
                    adjustment = 1.05  # +5% cushion
                    print(f"      Applying +5% cushion (market significantly higher)")
                else:
                    adjustment = 1.0
                    print(f"      No adjustment: Market within reasonable range")
            else:
                adjustment = 1.0
        
        # Para confidence 80-84%, aplicar lógica moderada
        else:
            if api_median:
                market_trend = (api_median - lane_median) / lane_median
                print(f"      Market trend: {market_trend*100:+.1f}% vs historical")
                
                # Solo ajustar si market está significativamente más alto
                if market_trend > 0.15:  # Mercado >15% más alto
                    adjustment = 1.03  # +3% cushion
                    print(f"      Applying +3% market cushion")
                elif market_trend > 0.10:  # Mercado 10-15% más alto
                    adjustment = 1.02  # +2% cushion
                    print(f"      Applying +2% market cushion")
                else:
                    adjustment = 1.0  # Sin ajuste
                    print(f"      No market adjustment needed")
            else:
                adjustment = 1.0
        
        target_rate = base_rate * adjustment
        max_buy = base_rate * adjustment * 1.05  # 5% spread
        
    elif has_good_historical:
        # CASO 2: Histórico BUENO (Confidence 60-79%, Records ≥3)
        print(f"\n   ✅ GOOD HISTORICAL DATA:")
        print(f"      Confidence: {internal_confidence}%, Records: {internal_records} (Lane={lane_records}, ZIP3={zip3_records})")
        print(f"      Blending: 70% historical, 30% market")
        
        if api_median:
            base_rate = (lane_median * 0.7) + (api_median * 0.3)
            print(f"      Historical: ${lane_median:,.2f}")
            print(f"      Market: ${api_median:,.2f}")
            print(f"      Blended: ${base_rate:,.2f}")
        else:
            base_rate = lane_median
        
        target_rate = base_rate * 0.97
        max_buy = base_rate * 1.08
        
    elif has_moderate_historical:
        # CASO 3: Histórico MODERADO (Confidence 50-59%, Records ≥2)
        print(f"\n   ⚠️ MODERATE HISTORICAL DATA:")
        print(f"      Confidence: {internal_confidence}%, Records: {internal_records} (Lane={lane_records}, ZIP3={zip3_records})")
        print(f"      Blending: 60% historical, 40% market")
        
        if api_median:
            base_rate = (lane_median * 0.6) + (api_median * 0.4)
            print(f"      Historical: ${lane_median:,.2f}")
            print(f"      Market: ${api_median:,.2f}")
            print(f"      Blended: ${base_rate:,.2f}")
        else:
            base_rate = lane_median
        
        target_rate = base_rate * 0.96
        max_buy = base_rate * 1.09
        
    elif has_acceptable_historical:
        # CASO 4: Histórico ACEPTABLE (Confidence 40-49%, Records ≥1)
        print(f"\n   ⚠️ ACCEPTABLE HISTORICAL DATA:")
        print(f"      Confidence: {internal_confidence}%, Records: {internal_records} (Lane={lane_records}, ZIP3={zip3_records})")
        print(f"      Blending: 50% historical, 50% market")
        
        if api_median:
            base_rate = (lane_median * 0.5) + (api_median * 0.5)
            print(f"      Historical: ${lane_median:,.2f}")
            print(f"      Market: ${api_median:,.2f}")
            print(f"      Blended: ${base_rate:,.2f}")
        else:
            base_rate = lane_median
        
        target_rate = base_rate * 0.95
        max_buy = base_rate * 1.10
        
    else:
        # CASO 5: Sin histórico confiable → usar solo mercado
        print(f"\n   📊 MARKET-BASED PRICING (weak/no historical data)")
        if internal_confidence > 0:
            print(f"      Historical: Confidence {internal_confidence}%, Records {internal_records} (insufficient)")
        
        # NO incluir internal rates si confidence < threshold
        all_rates = api_rates.copy()
        
        # NO agregar best_carrier_rate si no alcanza threshold
        # (evita que 1 dato histórico distorsione la mediana de APIs)
        
        if not all_rates:
            print(f"      No market data available, using fallback: ${miles * 2.50:.2f}")
            base_rate = miles * 2.50
            target_rate = base_rate
            max_buy = base_rate * 1.15
        else:
            print(f"      Market rates considered: {len(all_rates)} data points")
            median_rate = np.median(all_rates)
            print(f"      Market median: ${median_rate:,.2f}")
            
            gs_confidence = 50
            if greenscreens_data and greenscreens_data.get("RateForecast"):
                gs_confidence = greenscreens_data["RateForecast"].get("confidenceLevel", 50)
            
            combined_confidence = (gs_confidence * 0.4 + internal_confidence * 0.6) / 100
            
            target_rate = median_rate
            max_buy = median_rate * 1.10
            
            # Distance adjustment
            if miles > config["long_haul_threshold"]:
                adjustment = 0.98
            elif miles < config["short_haul_threshold"]:
                adjustment = 1.05
            else:
                adjustment = 1.0
            
            target_rate *= adjustment
            max_buy *= adjustment
            
            # Transit time adjustment
            if transit_days <= 1:
                target_rate *= 1.08
                max_buy *= 1.10
            elif transit_days > 3:
                target_rate *= 0.97
                max_buy *= 0.95
            
            # Weekend adjustment
            if pickup_weekday in [5, 6]:
                target_rate += config["weekend_penalty"]
                max_buy += config["weekend_penalty"]
            
            # Capacity adjustment
            if dat_data and dat_data.get("rates_mci"):
                companies = dat_data["rates_mci"].get("companies", 0)
                if companies < 5:
                    capacity_adj = 1 + config["capacity_sensitivity"]
                    target_rate *= capacity_adj
                    max_buy *= capacity_adj
                elif companies > 20:
                    capacity_adj = 1 - (config["capacity_sensitivity"] * 0.5)
                    target_rate *= capacity_adj
                    max_buy *= capacity_adj
            
            # Confidence adjustment
            if combined_confidence < 0.5:
                max_buy *= 1.05
            elif combined_confidence > 0.8:
                max_buy *= 0.98
            
            min_buffer = config["minimum_margin_buffer"]
            if (max_buy - target_rate) < min_buffer:
                max_buy = target_rate + min_buffer
    
    # Redondear a múltiplos de 5
    target_rate = round_to_nearest_5(target_rate)
    max_buy = round_to_nearest_5(max_buy)
    
    if max_buy <= target_rate:
        max_buy = target_rate + 50
    
    return float(target_rate), float(max_buy)


def calculate_carrier_cost_from_range(
    miles: float,
    pickup_date: Optional[datetime] = None,
    delivery_date: Optional[datetime] = None,
    dat_data: Optional[Dict] = None,
    greenscreens_data: Optional[Dict] = None,
    internal_data: Optional[Dict] = None
) -> Tuple[float, float, float]:
    """Calculate carrier cost as midpoint between target_rate and max_buy"""
    target_rate, max_buy = calculate_negotiation_range(
        miles=miles,
        pickup_date=pickup_date,
        delivery_date=delivery_date,
        dat_data=dat_data,
        greenscreens_data=greenscreens_data,
        internal_data=internal_data
    )
    
    carrier_cost = (target_rate + max_buy) / 2
    
    return float(carrier_cost), float(target_rate), float(max_buy)
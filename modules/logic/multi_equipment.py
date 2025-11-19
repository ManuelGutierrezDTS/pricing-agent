# modules/logic/multi_equipment.py
"""
Multi-Equipment handler
Compara precios de múltiples tipos de equipo y selecciona el más barato
"""

from typing import Tuple, Optional, Dict
from modules.logic.equipment import is_multi_equipment, split_equipment
from modules.apis.dat_api import get_dat_data_with_retry


def handle_multi_equipment(
    origin_city: str, 
    origin_state: str, 
    dest_city: str, 
    dest_state: str, 
    equipment_str: str, 
    miles: float
) -> Tuple[str, Optional[Dict]]:
    """
    Compara precios de múltiples equipment types y elige el más barato
    Retorna: (equipment_ganador, dat_data_ganador)
    """
    if not is_multi_equipment(equipment_str):
        return equipment_str, None
    
    equipments = split_equipment(equipment_str)
    print(f"\n🔄 Comparando precios para multi-equipment: {equipments}")
    
    results = {}
    
    for equip in equipments:
        print(f"\n   📊 Consultando {equip}...")
        dat_data = get_dat_data_with_retry(origin_city, origin_state, dest_city, dest_state, equip, miles)
        
        if dat_data and dat_data.get("rates_mci"):
            rate = dat_data["rates_mci"].get("total_forecastUSD")
            if rate:
                results[equip] = {"rate": rate, "data": dat_data}
                print(f"      ✅ {equip}: ${rate}")
            else:
                print(f"      ⚠️ {equip}: Sin rate válido")
        else:
            print(f"      ❌ {equip}: Sin datos")
    
    if not results:
        print(f"\n   ⚠️ No se obtuvieron rates para ningún equipment, usando {equipments[0]} por defecto")
        return equipments[0], None
    
    # Seleccionar el más barato
    winner = min(results.items(), key=lambda x: x[1]["rate"])
    winner_equipment = winner[0]
    winner_rate = winner[1]["rate"]
    winner_data = winner[1]["data"]
    
    print(f"\n   🏆 GANADOR: {winner_equipment} (${winner_rate})")
    
    return winner_equipment, winner_data
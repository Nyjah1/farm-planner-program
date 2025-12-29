from typing import Optional, Tuple, Dict, Any
from .models import CropModel, FieldModel, SoilType


def _safe_yield_for_soil(crop, soil: SoilType) -> float:
    """
    Atgriež ražu (t/ha) ar fallback loģiku.
    
    Returns:
        yield_t_ha (float)
    """
    yield_t_ha, _ = _safe_yield_for_soil_with_fallback(crop, soil)
    return yield_t_ha


def _safe_yield_for_soil_with_fallback(crop, soil: SoilType) -> Tuple[float, bool]:
    """
    Atgriež ražu (t/ha) un fallback statusu.
    
    Returns:
        Tuple (yield_t_ha, fallback_used)
    """
    # 1) precīzs match
    if soil in crop.yield_t_ha:
        return crop.yield_t_ha[soil], False

    # 2) fallback: ja nav šī augsne, ņem vidējo ražību no pieejamajām
    values = list(crop.yield_t_ha.values())
    if values:
        avg_yield = sum(values) / len(values)
        return avg_yield, True

    # 3) galējais fallback
    return 0.0, True


def profit_eur_detailed(
    field: FieldModel, 
    crop: CropModel, 
    price_info: Tuple[float, str, str]
) -> Dict[str, Any]:
    """
    Aprēķina peļņu eiro ar detalizētu breakdown.
    
    Formula:
    - revenue_per_ha = yield_t_ha * price_eur_t
    - profit_per_ha = revenue_per_ha - cost_eur_ha - rent_eur_ha
    - total_profit = profit_per_ha * field.area_ha
    
    Args:
        field: Lauka modelis
        crop: Kultūras modelis
        price_info: Tuple (price_eur_t, source_label, confidence)
    
    Returns:
        Dict ar:
        - profit: float (kopējā peļņa EUR)
        - profit_per_ha: float (peļņa uz ha EUR/ha)
        - revenue_per_ha: float (ieņēmumi uz ha EUR/ha)
        - revenue_total: float (kopējie ieņēmumi EUR)
        - cost_per_ha: float (izmaksas uz ha EUR/ha)
        - cost_total: float (kopējās izmaksas EUR)
        - rent_per_ha: float (noma uz ha EUR/ha)
        - rent_total: float (kopējā noma EUR)
        - yield_t_ha: float (raža t/ha)
        - price_eur_t: float (cena EUR/t)
        - fallback_used: bool (vai izmantots fallback ražai)
        - warning: Optional[str] (brīdinājuma teksts, ja ir)
    """
    # Pārbauda, vai kultūra ir tirgus kultūra
    is_market = getattr(crop, "is_market_crop", True)
    
    # Iegūst ražu un fallback statusu
    yield_t_ha, fallback_used = _safe_yield_for_soil_with_fallback(crop, field.soil)
    
    # Iegūst cenu
    price_eur_t, _source_label, _confidence = price_info
    
    # Iegūst izmaksas un nomu
    rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
    cost_eur_ha = crop.cost_eur_ha
    
    # Drošības pārbaudes
    warning = None
    if yield_t_ha <= 0 or price_eur_t <= 0:
        if yield_t_ha <= 0:
            warning = f"Raža nav definēta vai ir 0 (t/ha). Peļņa nav aprēķināma."
        elif price_eur_t <= 0:
            warning = f"Cena nav definēta vai ir 0 (EUR/t). Peļņa nav aprēķināma."
        
        return {
            "profit": 0.0,
            "profit_per_ha": 0.0,
            "revenue_per_ha": 0.0,
            "revenue_total": 0.0,
            "cost_per_ha": cost_eur_ha,
            "cost_total": cost_eur_ha * field.area_ha,
            "rent_per_ha": rent_eur_ha,
            "rent_total": rent_eur_ha * field.area_ha,
            "yield_t_ha": yield_t_ha,
            "price_eur_t": price_eur_t,
            "fallback_used": fallback_used,
            "warning": warning
        }
    
    # Aprēķina ieņēmumus (tikai tirgus kultūrām)
    if not is_market:
        # Segkultūra/zālāji: nav tiešu ieņēmumu
        revenue_per_ha = 0.0
        revenue_total = 0.0
    else:
        # Tirgus kultūra: revenue = yield_t_ha * price_eur_t (uz ha)
        revenue_per_ha = yield_t_ha * price_eur_t
        revenue_total = revenue_per_ha * field.area_ha
    
    # Aprēķina izmaksas
    cost_total = cost_eur_ha * field.area_ha
    rent_total = rent_eur_ha * field.area_ha
    
    # Aprēķina peļņu
    # profit_per_ha = revenue_per_ha - cost_eur_ha - rent_eur_ha
    profit_per_ha = revenue_per_ha - cost_eur_ha - rent_eur_ha
    # total_profit = profit_per_ha * field.area_ha
    total_profit = profit_per_ha * field.area_ha
    
    # Sanity check: iespējamas vienību kļūdas
    if profit_per_ha > 5000 or revenue_per_ha > 10000:
        if warning is None:
            warning = "Iespējamas vienību kļūdas (t/ha vs kg/ha vai EUR/t vs EUR/kg). Pārbaudiet, vai raža ir tonnās uz hektāru (t/ha) un cena eiro uz tonnu (EUR/t)."
        else:
            warning += " Iespējamas vienību kļūdas (t/ha vs kg/ha vai EUR/t vs EUR/kg)."
    
    return {
        "profit": total_profit,
        "profit_per_ha": profit_per_ha,
        "revenue_per_ha": revenue_per_ha,
        "revenue_total": revenue_total,
        "cost_per_ha": cost_eur_ha,
        "cost_total": cost_total,
        "rent_per_ha": rent_eur_ha,
        "rent_total": rent_total,
        "yield_t_ha": yield_t_ha,
        "price_eur_t": price_eur_t,
        "fallback_used": fallback_used,
        "warning": warning,
        "units": {
            "yield": "t/ha",
            "price": "EUR/t"
        }
    }


def profit_eur(field: FieldModel, crop: CropModel, price_info: Tuple[float, str, str]) -> float:
    """
    Aprēķina peļņu eiro (atpakaļsaderības wrapper).
    
    Formula:
    - revenue_per_ha = yield_t_ha * price_eur_t
    - profit_per_ha = revenue_per_ha - cost_eur_ha - rent_eur_ha
    - total_profit = profit_per_ha * field.area_ha
    
    Args:
        field: Lauka modelis
        crop: Kultūras modelis
        price_info: Tuple (price_eur_t, source_label, confidence)
    
    Returns:
        Peļņa eiro (kopējā)
    """
    result = profit_eur_detailed(field, crop, price_info)
    return result["profit"]


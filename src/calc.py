"""
Peļņas un ieņēmumu aprēķinu modulis.
"""
from dataclasses import dataclass
from typing import Optional, Tuple
from .models import FieldModel, CropModel


@dataclass
class ProfitCalculationResult:
    """
    Peļņas aprēķina rezultāts.
    """
    revenue_per_ha: float
    revenue_total: float
    cost_per_ha: float
    cost_total: float
    profit_per_ha: float
    profit_total: float
    yield_fallback_used: bool = False
    yield_fallback_warning: Optional[str] = None


def calculate_profit(
    field: FieldModel,
    crop: CropModel,
    rent_eur_ha: float = 0.0
) -> Optional[ProfitCalculationResult]:
    """
    Aprēķina peļņu un ieņēmumus laukam ar konkrētu kultūru.
    
    Formulas:
    - revenue_per_ha = yield_t_ha * price_eur_t
    - cost_per_ha = cost_eur_ha + rent_eur_ha
    - profit_per_ha = revenue_per_ha - cost_per_ha
    - total = per_ha * field.area_ha
    
    Noteikumi:
    - Ja price_eur_t is None -> izmanto 0.0 (neatgriež None)
    - Ja yield_t_ha nav atrodams konkrētai augsnei -> izmanto fallback (vidējo vai 0)
    
    Args:
        field: Lauka modelis (satur area_ha un soil)
        crop: Kultūras modelis (satur yield_t_ha, price_eur_t, cost_eur_ha)
        rent_eur_ha: Nomas maksa uz hektāru (noklusējuma: 0.0)
    
    Returns:
        ProfitCalculationResult ar visiem aprēķinātajiem rādītājiem vai None, ja nav iespējams aprēķināt
    """
    # Iegūst ražu ar fallback loģiku
    yield_t_ha = 0.0
    yield_fallback_used = False
    yield_fallback_warning = None
    
    if isinstance(crop.yield_t_ha, dict):
        # 1) Precīzs match
        if field.soil in crop.yield_t_ha and crop.yield_t_ha[field.soil] is not None:
            yield_t_ha = float(crop.yield_t_ha[field.soil])
            if yield_t_ha <= 0:
                yield_t_ha = 0.0
        else:
            # 2) Fallback: ja nav šī augsne, ņem vidējo ražību no pieejamajām
            values = [v for v in crop.yield_t_ha.values() if v is not None and v > 0]
            if values:
                yield_t_ha = sum(values) / len(values)
                yield_fallback_used = True
                yield_fallback_warning = "Nav ražas datu šai augsnei (izmantots vidējais)."
            else:
                # 3) Galējais fallback - nav nevienas ražas vērtības
                yield_t_ha = 0.0
                yield_fallback_used = True
                yield_fallback_warning = "Nav ražas datu šai augsnei (izmantots vidējais)."
    
    # Iegūst vērtības (izmanto 0.0, ja nav cenas vai izmaksu)
    area_ha = float(field.area_ha)
    price_eur_t = float(crop.price_eur_t) if crop.price_eur_t is not None and crop.price_eur_t > 0 else 0.0
    cost_eur_ha = float(crop.cost_eur_ha) if crop.cost_eur_ha and crop.cost_eur_ha > 0 else 0.0
    rent_eur_ha = float(rent_eur_ha)
    
    # Aprēķina ieņēmumus
    revenue_per_ha = yield_t_ha * price_eur_t
    revenue_total = revenue_per_ha * area_ha
    
    # Aprēķina izmaksas
    cost_per_ha = cost_eur_ha + rent_eur_ha
    cost_total = cost_per_ha * area_ha
    
    # Aprēķina peļņu
    profit_per_ha = revenue_per_ha - cost_per_ha
    profit_total = profit_per_ha * area_ha
    
    return ProfitCalculationResult(
        revenue_per_ha=revenue_per_ha,
        revenue_total=revenue_total,
        cost_per_ha=cost_per_ha,
        cost_total=cost_total,
        profit_per_ha=profit_per_ha,
        profit_total=profit_total,
        yield_fallback_used=yield_fallback_used,
        yield_fallback_warning=yield_fallback_warning
    )


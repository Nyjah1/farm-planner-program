from typing import List

from .models import CropModel, SoilType


def validate_crop_numbers(crop: CropModel, field_soil: SoilType) -> List[str]:
    """
    Validē kultūras skaitliskos datus un atgriež brīdinājumu sarakstu.
    
    Args:
        crop: Kultūras modelis
        field_soil: Lauka augsnes veids
    
    Returns:
        Saraksts ar brīdinājumu kodiem: "yield_too_high", "price_too_high", "cost_too_high"
    """
    warnings = []
    
    # Pārbauda ražu (tikai graudiem/rapsim/pākšaugiem)
    if isinstance(crop.yield_t_ha, dict) and field_soil in crop.yield_t_ha:
        yield_value = crop.yield_t_ha[field_soil]
        
        # Noteikt, vai kultūra ir graudiem/rapsim/pākšaugiem
        is_grain_or_rapeseed_or_legume = (
            crop.group == "Graudaugi" or
            crop.group == "Eļļaugi" or  # Rapsis
            crop.group == "Pākšaugi"
        )
        
        if is_grain_or_rapeseed_or_legume and yield_value > 20:
            warnings.append("yield_too_high")
    
    # Pārbauda cenu
    if crop.price_eur_t is not None and crop.price_eur_t > 1200:
        warnings.append("price_too_high")
    
    # Pārbauda izmaksas
    if crop.cost_eur_ha > 3000:
        warnings.append("cost_too_high")
    
    return warnings


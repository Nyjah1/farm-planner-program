from typing import Dict


def default_volatility_pct(crop_group: str) -> float:
    """
    Atgriež tipisko cenu svārstību procentuāli pēc kultūras grupas.
    
    Args:
        crop_group: Kultūras grupa (piem., "Graudaugi", "Pākšaugi", "Eļļaugi", "Sakņaugi", "Dārzeņi")
    
    Returns:
        Tipiska svārstība procentos (piem., 5.0 nozīmē ±5%)
    """
    group_lower = crop_group.lower()
    
    if "graud" in group_lower:
        return 5.0
    elif "dārzeņ" in group_lower or "sakņ" in group_lower:
        return 10.0
    elif "eļļ" in group_lower:
        return 7.0
    elif "pākš" in group_lower:
        return 6.0
    else:
        # Noklusējums citām grupām
        return 5.0


def price_scenarios(base_prices: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """
    Izveido 5 cenu scenārijus ar dažādām izmaiņām.
    
    Scenāriji:
    - minus20: -20% cenu izmaiņa
    - minus10: -10% cenu izmaiņa
    - base: 0% (bāzes cenas)
    - plus10: +10% cenu izmaiņa
    - plus20: +20% cenu izmaiņa
    
    Args:
        base_prices: Bāzes cenas vārdnīca (kultūras nosaukums -> cena eiro/t)
    
    Returns:
        Vārdnīca ar scenārijiem, kur katrs scenārijs ir vārdnīca ar kultūru cenām
    """
    scenarios = {}
    
    # -20% scenārijs
    scenarios["minus20"] = {
        crop: price * 0.8 for crop, price in base_prices.items()
    }
    
    # -10% scenārijs
    scenarios["minus10"] = {
        crop: price * 0.9 for crop, price in base_prices.items()
    }
    
    # Bāzes scenārijs (0%)
    scenarios["base"] = base_prices.copy()
    
    # +10% scenārijs
    scenarios["plus10"] = {
        crop: price * 1.1 for crop, price in base_prices.items()
    }
    
    # +20% scenārijs
    scenarios["plus20"] = {
        crop: price * 1.2 for crop, price in base_prices.items()
    }
    
    return scenarios


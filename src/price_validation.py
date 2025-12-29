"""
Cenu validācijas modulis.

Pārbauda, vai cenas ir saprātīgā diapazonā atkarībā no kultūras grupas.
"""
import json
from pathlib import Path
from typing import Dict, Optional, Any
from functools import lru_cache


def validate_price(crop_name: str, price_eur_t: float) -> Dict[str, Any]:
    """
    Validē cenu atkarībā no kultūras grupas.
    
    Args:
        crop_name: Kultūras nosaukums
        price_eur_t: Cena eiro uz tonnu
        
    Returns:
        Dict ar:
        - valid: bool - vai cena ir saprātīgā diapazonā
        - adjusted_price: float | None - koriģētā cena (vienmēr None)
        - note: str | None - piezīme, ja cena nav derīga
    """
    # Iegūst kultūras grupu no kataloga
    crop_group = _get_crop_group(crop_name)
    
    if crop_group is None:
        # Ja kultūra nav atrasta, atgriež valid = True (nav validācijas)
        return {
            "valid": True,
            "adjusted_price": None,
            "note": None
        }
    
    # Nosaka cenu diapazonu atkarībā no grupas
    price_range = _get_price_range_for_group(crop_group)
    
    if price_range is None:
        # Ja grupai nav definēts diapazons, atgriež valid = True
        return {
            "valid": True,
            "adjusted_price": None,
            "note": None
        }
    
    min_price, max_price = price_range
    
    # Pārbauda, vai cena ir diapazonā
    if min_price <= price_eur_t <= max_price:
        return {
            "valid": True,
            "adjusted_price": None,
            "note": None
        }
    else:
        return {
            "valid": False,
            "adjusted_price": None,
            "note": "Cena ārpus saprātīga diapazona"
        }


@lru_cache(maxsize=1)
def _get_crop_group(crop_name: str) -> Optional[str]:
    """
    Iegūst kultūras grupu no crops.json faila.
    
    Args:
        crop_name: Kultūras nosaukums
        
    Returns:
        Grupas nosaukums vai None, ja kultūra nav atrasta
    """
    try:
        crops_file = Path("data/crops.json")
        if not crops_file.exists():
            return None
        
        with crops_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            return None
        
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("name") == crop_name:
                return item.get("group")
    except Exception:
        pass
    return None


def _get_price_range_for_group(group: str) -> Optional[tuple]:
    """
    Atgriež cenu diapazonu (min, max) atkarībā no grupas.
    
    Args:
        group: Kultūras grupas nosaukums
        
    Returns:
        Tuple ar (min_price, max_price) vai None, ja grupai nav definēts diapazons
    """
    ranges = {
        "Graudaugi": (80, 500),
        "Eļļaugi": (200, 900),
        "Pākšaugi": (150, 800),
        "Dārzeņi": (50, 300),
    }
    
    return ranges.get(group)


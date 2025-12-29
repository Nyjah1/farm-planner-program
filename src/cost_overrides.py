"""
Izmaksu override modulis - ļauj pārrakstīt kultūru izmaksas bez crops.json rediģēšanas.
"""
import csv
import json
from pathlib import Path
from typing import Dict, Optional


def load_cost_overrides(csv_path: str = "data/costs_overrides.csv") -> Dict[str, float]:
    """
    Ielādē izmaksu overrides no CSV faila.
    
    Args:
        csv_path: Ceļš uz costs_overrides.csv
    
    Returns:
        Dict ar kultūras nosaukumu -> cost_eur_ha
    """
    overrides: Dict[str, float] = {}
    csv_path_obj = Path(csv_path)
    
    if not csv_path_obj.exists():
        return overrides
    
    try:
        with csv_path_obj.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                crop_name = (row.get("crop_name") or "").strip()
                cost_raw = (row.get("cost_eur_ha") or "").strip()
                
                if not crop_name:
                    continue
                
                try:
                    cost_value = float(cost_raw)
                    if cost_value > 0:
                        overrides[crop_name] = cost_value
                except (TypeError, ValueError):
                    continue
    except Exception as e:
        print(f"[WARN] Neizdevās ielādēt cost overrides: {e}")
    
    return overrides


def save_cost_override(crop_name: str, cost_eur_ha: float, csv_path: str = "data/costs_overrides.csv") -> bool:
    """
    Saglabā vai atjauno izmaksu override.
    
    Args:
        crop_name: Kultūras nosaukums
        cost_eur_ha: Izmaksas EUR/ha
        csv_path: Ceļš uz costs_overrides.csv
    
    Returns:
        True, ja izdevās saglabāt
    """
    csv_path_obj = Path(csv_path)
    csv_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # Ielādē esošos overrides
    existing_overrides = load_cost_overrides(csv_path)
    
    # Atjauno vai pievieno jaunu
    existing_overrides[crop_name] = cost_eur_ha
    
    # Saglabā visus overrides
    try:
        with csv_path_obj.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["crop_name", "cost_eur_ha"])
            writer.writeheader()
            for name, cost in sorted(existing_overrides.items()):
                writer.writerow({
                    "crop_name": name,
                    "cost_eur_ha": f"{cost:.2f}"
                })
        return True
    except Exception as e:
        print(f"[ERROR] Neizdevās saglabāt cost override: {e}")
        return False


def apply_overrides_to_catalog(crops_dict: Dict[str, "CropModel"]) -> Dict[str, "CropModel"]:
    """
    Piemēro izmaksu overrides kultūru katalogam.
    
    Args:
        crops_dict: Oriģinālais kultūru vārdnīca
    
    Returns:
        Jauna vārdnīca ar atjaunotām izmaksām
    """
    from .models import CropModel
    
    overrides = load_cost_overrides()
    if not overrides:
        return crops_dict
    
    updated_dict = {}
    for name, crop in crops_dict.items():
        if name in overrides:
            # Izveido jaunu CropModel ar atjaunotām izmaksām
            updated_crop = CropModel(
                name=crop.name,
                group=crop.group,
                sow_months=crop.sow_months,
                yield_t_ha=crop.yield_t_ha,
                cost_eur_ha=overrides[name],
                price_eur_t=crop.price_eur_t,
                is_market_crop=crop.is_market_crop
            )
            updated_dict[name] = updated_crop
        else:
            updated_dict[name] = crop
    
    return updated_dict


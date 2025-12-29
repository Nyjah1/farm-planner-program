"""
Kultūru pārvaldības modulis - saglabāšana un dzēšana no crops.json un crops_user.json.
"""
import json
from pathlib import Path
from typing import Dict, Optional
from .models import CropModel, SoilType


def save_crop_to_json(crop: CropModel, crops_file: str = "data/crops.json") -> bool:
    """
    Saglabā vai atjauno kultūru crops.json failā.
    
    Args:
        crop: CropModel objekts
        crops_file: Ceļš uz crops.json failu
    
    Returns:
        True, ja saglabāšana veiksmīga, citādi False
    """
    try:
        crops_path = Path(crops_file)
        
        # Ielādē esošo katalogu
        if crops_path.exists():
            with open(crops_path, 'r', encoding='utf-8') as f:
                crops_data = json.load(f)
        else:
            crops_data = []
        
        # Konvertē yield_t_ha no SoilType enum uz string kodu
        yield_dict = {}
        for soil_type, yield_value in crop.yield_t_ha.items():
            yield_dict[soil_type.code] = yield_value
        
        # Sagatavo kultūras datus JSON formātā
        crop_data = {
            "name": crop.name,
            "group": crop.group,
            "sow_months": crop.sow_months,
            "yield_t_ha": yield_dict,
            "cost_eur_ha": crop.cost_eur_ha,
            "price_eur_t": crop.price_eur_t,
            "is_market_crop": crop.is_market_crop,
            "ph_range": list(crop.ph_range) if crop.ph_range else None
        }
        
        # Meklē, vai kultūra jau eksistē
        crop_index = None
        for i, existing_crop in enumerate(crops_data):
            if existing_crop.get("name") == crop.name:
                crop_index = i
                break
        
        # Atjauno vai pievieno
        if crop_index is not None:
            crops_data[crop_index] = crop_data
        else:
            crops_data.append(crop_data)
        
        # Saglabā atpakaļ uz failu
        with open(crops_path, 'w', encoding='utf-8') as f:
            json.dump(crops_data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[ERROR] Neizdevās saglabāt kultūru: {e}")
        return False


def add_or_update_user_crop(crop: CropModel, crops_user_file: str = "data/crops_user.json") -> bool:
    """
    Pievieno vai atjauno kultūru crops_user.json failā.
    
    Args:
        crop: CropModel objekts
        crops_user_file: Ceļš uz crops_user.json failu
    
    Returns:
        True, ja saglabāšana veiksmīga, citādi False
    """
    try:
        crops_path = Path(crops_user_file)
        
        # Ielādē esošo katalogu
        if crops_path.exists():
            with open(crops_path, 'r', encoding='utf-8') as f:
                crops_data = json.load(f)
        else:
            crops_data = []
        
        # Konvertē yield_t_ha no SoilType enum uz string kodu
        # crops_user.json izmanto jaunos kodus ("mālaina", "kūdra")
        yield_dict = {}
        for soil_type, yield_value in crop.yield_t_ha.items():
            yield_dict[soil_type.code] = yield_value
        
        # Sagatavo kultūras datus JSON formātā
        crop_data = {
            "name": crop.name,
            "group": crop.group,
            "sow_months": crop.sow_months,
            "yield_t_ha": yield_dict,
            "cost_eur_ha": crop.cost_eur_ha,
            "price_eur_t": crop.price_eur_t,
            "ph_range": list(crop.ph_range) if crop.ph_range else None
        }
        
        # Meklē, vai kultūra jau eksistē
        crop_index = None
        for i, existing_crop in enumerate(crops_data):
            if existing_crop.get("name") == crop.name:
                crop_index = i
                break
        
        # Atjauno vai pievieno
        if crop_index is not None:
            crops_data[crop_index] = crop_data
        else:
            crops_data.append(crop_data)
        
        # Saglabā atpakaļ uz failu
        crops_path.parent.mkdir(parents=True, exist_ok=True)
        with open(crops_path, 'w', encoding='utf-8') as f:
            json.dump(crops_data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[ERROR] Neizdevās saglabāt kultūru: {e}")
        return False


def delete_user_crop(crop_name: str, crops_user_file: str = "data/crops_user.json") -> bool:
    """
    Dzēš kultūru no crops_user.json faila.
    
    Args:
        crop_name: Kultūras nosaukums
        crops_user_file: Ceļš uz crops_user.json failu
    
    Returns:
        True, ja dzēšana veiksmīga, citādi False
    """
    try:
        crops_path = Path(crops_user_file)
        
        if not crops_path.exists():
            return False
        
        # Ielādē esošo katalogu
        with open(crops_path, 'r', encoding='utf-8') as f:
            crops_data = json.load(f)
        
        # Atrod un dzēš kultūru
        crops_data = [c for c in crops_data if c.get("name") != crop_name]
        
        # Saglabā atpakaļ uz failu
        with open(crops_path, 'w', encoding='utf-8') as f:
            json.dump(crops_data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[ERROR] Neizdevās dzēst kultūru: {e}")
        return False


def delete_crop_from_json(crop_name: str, crops_file: str = "data/crops.json") -> bool:
    """
    Dzēš kultūru no crops.json faila.
    
    Args:
        crop_name: Kultūras nosaukums
        crops_file: Ceļš uz crops.json failu
    
    Returns:
        True, ja dzēšana veiksmīga, citādi False
    """
    try:
        crops_path = Path(crops_file)
        
        if not crops_path.exists():
            return False
        
        # Ielādē esošo katalogu
        with open(crops_path, 'r', encoding='utf-8') as f:
            crops_data = json.load(f)
        
        # Atrod un dzēš kultūru
        crops_data = [c for c in crops_data if c.get("name") != crop_name]
        
        # Saglabā atpakaļ uz failu
        with open(crops_path, 'w', encoding='utf-8') as f:
            json.dump(crops_data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[ERROR] Neizdevās dzēst kultūru: {e}")
        return False


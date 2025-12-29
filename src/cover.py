import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .models import CoverCropModel, SoilType


def load_cover_catalog(cover_crops_file: str = "data/cover_crops.json") -> Dict[str, CoverCropModel]:
    """
    Ielādē starpkultūru katalogu no JSON faila.
    
    Args:
        cover_crops_file: Ceļš uz cover_crops.json failu
    
    Returns:
        Dict ar starpkultūras nosaukumu -> CoverCropModel
    """
    cover_crops_path = Path(cover_crops_file)
    
    if not cover_crops_path.exists():
        logging.warning(f"Starpkultūru katalogs nav atrasts: {cover_crops_file}")
        return {}
    
    try:
        with open(cover_crops_path, 'r', encoding='utf-8') as f:
            cover_crops_data = json.load(f)
    except json.JSONDecodeError as e:
        error_msg = (
            f"cover_crops.json nav derīgs JSON. "
            f"Fails: {cover_crops_file}, rinda: {e.lineno}, kolonna: {e.colno}"
        )
        logging.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Neizdevās ielādēt starpkultūru katalogu: {str(e)}"
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    cover_crops_dict = {}
    
    for cover_crop_data in cover_crops_data:
        cover_crop = CoverCropModel(
            name=cover_crop_data['name'],
            sow_months=cover_crop_data.get('sow_months', []),
            benefits=cover_crop_data.get('benefits', []),
            cost_eur_ha=cover_crop_data.get('cost_eur_ha', 0.0),
            allowed_after_groups=cover_crop_data.get('allowed_after_groups', [])
        )
        cover_crops_dict[cover_crop.name] = cover_crop
    
    logging.info(f"Ielādētas {len(cover_crops_dict)} starpkultūras")
    return cover_crops_dict


def recommend_cover_crop(
    main_crop_group: str,
    sow_month: int,
    field_soil: SoilType
) -> Optional[CoverCropModel]:
    """
    Ieteic starpkultūru, pamatojoties uz galvenās kultūras grupu, sēšanas mēnesi un augsnes veidu.
    
    Args:
        main_crop_group: Galvenās kultūras grupa (piem., "Graudaugi", "Eļļaugi")
        sow_month: Sēšanas mēnesis (1-12)
        field_soil: Lauka augsnes veids
    
    Returns:
        CoverCropModel vai None, ja nav piemērotu starpkultūru
    """
    cover_crops_dict = load_cover_catalog()
    
    if not cover_crops_dict:
        return None
    
    # Filtrē starpkultūras pēc kritērijiem
    suitable_covers = []
    
    for cover_crop in cover_crops_dict.values():
        # Pārbauda, vai starpkultūra ir atļauta pēc galvenās kultūras grupas
        if main_crop_group not in cover_crop.allowed_after_groups:
            continue
        
        # Pārbauda, vai sēšanas mēnesis sakrīt
        if sow_month not in cover_crop.sow_months:
            continue
        
        # Visas pārbaudes izietas
        suitable_covers.append(cover_crop)
    
    # Ja nav piemērotu starpkultūru, atgriež None
    if not suitable_covers:
        return None
    
    # Atgriež pirmo piemēroto starpkultūru
    # Varētu arī izvēlēties pēc izmaksām vai citiem kritērijiem
    return suitable_covers[0]


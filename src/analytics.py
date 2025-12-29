"""
Analītikas funkcijas lauku un sējumu datu analīzei.
"""
from typing import Dict, List
from .models import FieldModel, PlantingRecord


def crop_area_by_year(storage, year: int, user_id: int) -> List[Dict[str, float]]:
    """
    Aprēķina platību (ha) pa kultūrām izvēlētam gadam.
    
    Args:
        storage: Storage instance ar list_fields() un list_plantings() metodēm
        year: Gads, par kuru aprēķināt platības
        user_id: Lietotāja ID, lai filtrētu datus
    
    Returns:
        Saraksts ar vārdnīcām:
        [
            {"crop": "Kvieši", "area_ha": 15.5},
            {"crop": "Mieži", "area_ha": 10.2},
            ...
        ]
        Sakārtots alfabētiski pēc kultūras nosaukuma.
        
    Loģika:
    - Paņem visus laukus no storage.list_fields(user_id)
    - Paņem visus sējumu ierakstus no storage.list_plantings(user_id)
    - Katram laukam atrod kultūru konkrētajā gadā (pēc field_id un year)
    - Ja vienam laukam gadā ir vairāki ieraksti, ņem pēdējo (pēc pievienošanas secības)
    - Saskaita lauku platības pa crop
    - Laukus, kam nav ieraksta tajā gadā, neliek rezultātā
    """
    # 1) Iegūst visus laukus
    fields = storage.list_fields(user_id)
    fields_dict = {field.id: field for field in fields}
    
    # 2) Iegūst visus sējumu ierakstus
    all_plantings = storage.list_plantings(user_id)
    
    # 3) Filtrē ierakstus pēc gada
    plantings_for_year = [
        p for p in all_plantings
        if p.year == year
    ]
    
    # 4) Katram laukam atrod kultūru (ja ir vairāki ieraksti, ņem pēdējo)
    # Izveido dict: field_id -> crop (pēdējais ieraksts)
    field_to_crop: Dict[int, str] = {}
    
    # Sakārto pēc pievienošanas secības (pēdējais ieraksts pārraksta iepriekšējo)
    for planting in plantings_for_year:
        field_to_crop[planting.field_id] = planting.crop
    
    # 5) Saskaita platības pa kultūrām
    crop_areas: Dict[str, float] = {}
    
    for field_id, crop in field_to_crop.items():
        if field_id in fields_dict:
            field = fields_dict[field_id]
            area_ha = field.area_ha
            
            # Pievieno platību kultūrai
            if crop in crop_areas:
                crop_areas[crop] += area_ha
            else:
                crop_areas[crop] = area_ha
    
    # 6) Konvertē uz sarakstu ar vārdnīcām un sakārto alfabētiski
    result = [
        {"crop": crop, "area_ha": round(area, 2)}
        for crop, area in sorted(crop_areas.items())
    ]
    
    return result


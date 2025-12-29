from typing import List

from .models import PlantingRecord


def get_allowed_crops(
    planting_history: List[PlantingRecord],
    available_crops: List[str],
    target_year: int,
    field_id: int
) -> List[str]:
    """
    Atgriež atļautās kultūras pēc sējumu vēstures noteikumiem.
    
    Noteikumi:
    - To pašu kultūru nedrīkst 2 gadus pēc kārtas
    - Rapsi nedrīkst, ja tas bijis pēdējo 3 gadu laikā
    
    Args:
        planting_history: Visi sējumu vēstures ieraksti
        available_crops: Pieejamo kultūru nosaukumu saraksts
        target_year: Gads, kurā plāno sēt
        field_id: Lauka ID, kuram pārbauda noteikumus
    
    Returns:
        Atļauto kultūru nosaukumu saraksts
    """
    # Filtrē pēc lauka ID un sakārto pēc gada
    field_history = [
        p for p in planting_history
        if p.field_id == field_id
    ]
    field_history.sort(key=lambda x: x.year, reverse=True)
    
    # Ignorē kultūras, kas nav pieejamas katalogā (aizsardzība pret KeyError)
    valid_crops_set = set(available_crops)
    field_history = [
        p for p in field_history
        if p.crop in valid_crops_set
    ]
    
    # Noteikums 1: To pašu kultūru nedrīkst 2 gadus pēc kārtas
    # Pārbauda pēdējos 2 gadus (target_year - 1 un target_year - 2)
    forbidden_crops = set()
    for record in field_history:
        if record.year >= target_year - 1:
            forbidden_crops.add(record.crop)
    
    # Noteikums 2: Rapsi nedrīkst, ja tas bijis pēdējo 3 gadu laikā
    # Pārbauda visus rapsu variantus
    rapeseed_variants = ["Rapsis", "Rapsis (ziemas)", "Rapsis (vasaras)"]
    rapeseed_years = [
        record.year for record in field_history
        if record.crop in rapeseed_variants and record.year >= target_year - 3
    ]
    if rapeseed_years:
        # Aizliedz visus rapsu variantus
        for variant in rapeseed_variants:
            if variant in available_crops:
                forbidden_crops.add(variant)
    
    # Atgriež kultūras, kas nav aizliegtas
    allowed = [crop for crop in available_crops if crop not in forbidden_crops]
    return allowed


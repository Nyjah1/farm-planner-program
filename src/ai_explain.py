from typing import List, Dict
from src.models import FieldModel, PlantingRecord


def explain_recommendation(
    field: FieldModel,
    history: List[PlantingRecord],
    base_result: Dict,
    scenario_result: Dict
) -> str:
    """
    Ģenerē cilvēkam saprotamu skaidrojumu bez ārēja AI.
    Teksts balstās tikai uz aprēķinātajiem datiem.
    """

    if base_result.get("best_crop") is None:
        return (
            "Šim laukam šobrīd nevar sniegt ieteikumu. "
            "Pēc sējumu vēstures noteikumiem visas kultūras ir ierobežotas."
        )

    best_crop = base_result["best_crop"]
    profit = base_result["best_profit"]
    profit_per_ha = profit / field.area_ha if field.area_ha > 0 else 0

    # Vēstures kopsavilkums
    if history:
        last_crop = max(history, key=lambda x: x.year).crop
        history_text = f"Pēdējā sētā kultūra bija **{last_crop}**, tāpēc tika ievērota augu maiņa."
    else:
        history_text = "Šim laukam nav iepriekšējas sējumu vēstures."

    # Stabilitāte
    stability = scenario_result.get("stability", 0)
    if stability == 5:
        stability_text = "Ieteikums ir ļoti stabils – tas nemainās pat pie cenu svārstībām."
    elif stability >= 3:
        stability_text = "Ieteikums ir vidēji stabils – pie lielām cenu izmaiņām izvēle var mainīties."
    else:
        stability_text = "Ieteikums ir jutīgs pret cenu izmaiņām – ieteicams sekot tirgus cenām."

    # Galīgais teksts
    explanation = (
        f"Ieteicamā kultūra šim laukam ir **{best_crop}**.\n\n"
        f"Prognozētā peļņa ir **{profit:.2f} EUR**, kas atbilst aptuveni "
        f"**{profit_per_ha:.2f} EUR/ha**.\n\n"
        f"{history_text}\n\n"
        f"{stability_text}"
    )

    return explanation


def explain_multi_year_plan(field: FieldModel, plan_result: Dict) -> str:
    """
    Ģenerē skaidrojumu daudzgadu plānam.
    
    Args:
        field: Lauka modelis
        plan_result: Plāna rezultāts no plan_for_years
    
    Returns:
        Skaidrojums latviešu valodā
    """
    plan = plan_result.get("plan", [])
    total_profit = plan_result.get("total_profit", 0.0)
    avg_profit_per_ha = plan_result.get("avg_profit_per_ha", 0.0)
    years = plan_result.get("years", 3)
    
    if not plan:
        return "Plāns nav pieejams."
    
    # Sākuma daļa
    sentences = [
        f"Laukam '{field.name}' ir izveidots {years} gadu plāns, "
        f"katru gadu ievērojot augu maiņu un rotācijas noteikumus."
    ]
    
    # Kultūru secība
    crop_sequence = []
    missing_years = []
    
    for entry in plan:
        year = entry.get("year")
        crop = entry.get("crop")
        
        if crop:
            crop_sequence.append(f"{year} {crop}")
        else:
            missing_years.append(year)
    
    if crop_sequence:
        sequence_text = " -> ".join(crop_sequence)
        sentences.append(f"Kultūru secība: {sequence_text}.")
    
    # Kopējā peļņa un vidējā
    sentences.append(
        f"Kopējā prognozētā peļņa {years} gados ir **{total_profit:.2f} EUR**, "
        f"kas atbilst vidēji **{avg_profit_per_ha:.2f} EUR/ha** gadā."
    )
    
    # Ierobežojumi
    if missing_years:
        years_list = ", ".join(map(str, missing_years))
        sentences.append(
            f"Piezīme: {years_list}. gadā nav iespējams ieteikt kultūru "
            f"pēc sējumu vēstures noteikumiem (visas kultūras ir ierobežotas)."
        )
    
    return " ".join(sentences)

"""
CLI aplikācija Farm Planner.
Šis fails ir tikai CLI versijai un NEDRĪKST tikt importēts Streamlit vidē.

IMPORTANT: This file should NEVER be imported by Streamlit or run in Streamlit Cloud.
It contains input() calls that will block Streamlit execution.
"""
import sys

# Prevent execution in Streamlit environment
if 'streamlit' in sys.modules:
    raise RuntimeError(
        "cli_app.py cannot be imported in Streamlit environment. "
        "Use app.py or ui_app.py for Streamlit."
    )

from datetime import datetime

from src.ai_explain import explain_recommendation
from src.models import FieldModel, PlantingRecord, SoilType
from src.planner import load_catalog, recommend_for_field, recommend_with_scenarios
from src.storage import Storage


def main_cli():
    """Galvenā CLI izvēlne."""
    storage = Storage()
    
    # CLI versijai izveidojam demo lietotāju vai izmantojam pirmo lietotāju
    # Pārbauda, vai ir lietotāji
    from src.db import get_db_cursor, _get_placeholder
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        if not row:
            print("Nav lietotāju! Vispirms izveidojiet lietotāju caur Streamlit UI.")
            return
        user_id = row[0]
    
    while True:
        print("\n=== Farm Planner ===")
        print("1) Pievienot lauku")
        print("2) Parādīt laukus")
        print("3) Pievienot sējumu vēsturi")
        print("4) Parādīt sējumu vēsturi pēc field_id")
        print("5) Ieteikt ko sēt nākamajam gadam")
        print("0) Iziet")
        
        choice = input("\nIzvēlieties opciju: ").strip()
        
        if choice == "0":
            print("Uz redzēšanos!")
            break
        elif choice == "1":
            add_field(storage, user_id)
        elif choice == "2":
            list_fields(storage, user_id)
        elif choice == "3":
            add_planting(storage, user_id)
        elif choice == "4":
            list_plantings_by_field(storage, user_id)
        elif choice == "5":
            recommend_crop_for_field(storage, user_id)
        else:
            print("Nepareiza izvēle! Lūdzu, izvēlieties no 0-5.")


def add_field(storage: Storage, user_id: int):
    """Pievieno jaunu lauku."""
    try:
        name = input("Lauka nosaukums: ").strip()
        if not name:
            print("Kļūda: Nosaukums nevar būt tukšs!")
            return
        
        area_str = input("Platība (ha): ").strip()
        try:
            area_ha = float(area_str)
        except ValueError:
            print("Kļūda: Platībai jābūt skaitlim!")
            return
        
        print("Augsnes veids: 1) smilts, 2) mals, 3) kudra")
        soil_choice = input("Izvēlieties (1-3): ").strip()
        soil_map = {"1": SoilType.SMILTS, "2": SoilType.MALS, "3": SoilType.KUDRA}
        
        if soil_choice not in soil_map:
            print("Kļūda: Nepareiza augsnes veida izvēle!")
            return
        
        field = FieldModel(id=0, name=name, area_ha=area_ha, soil=soil_map[soil_choice], owner_user_id=user_id)
        result = storage.add_field(field, user_id)
        print(f"Lauks pievienots ar ID: {result.id}")
    except Exception as e:
        print(f"Kļūda: {e}")


def list_fields(storage: Storage, user_id: int):
    """Parāda visus laukus."""
    try:
        fields = storage.list_fields(user_id)
        if not fields:
            print("Nav pievienotu lauku.")
            return
        
        print("\nLauki:")
        print("-" * 60)
        for field in fields:
            print(f"ID: {field.id} | Nosaukums: {field.name} | "
                  f"Platība: {field.area_ha} ha | Augsne: {field.soil.label}")
    except Exception as e:
        print(f"Kļūda: {e}")


def add_planting(storage: Storage, user_id: int):
    """Pievieno sējumu vēsturi."""
    try:
        field_id_str = input("Lauka ID: ").strip()
        try:
            field_id = int(field_id_str)
        except ValueError:
            print("Kļūda: Lauka ID jābūt skaitlim!")
            return
        
        year_str = input("Gads: ").strip()
        try:
            year = int(year_str)
        except ValueError:
            print("Kļūda: Gads jābūt skaitlim!")
            return
        
        crop = input("Kultūras nosaukums: ").strip()
        if not crop:
            print("Kļūda: Kultūras nosaukums nevar būt tukšs!")
            return
        
        planting = PlantingRecord(field_id=field_id, year=year, crop=crop, owner_user_id=user_id)
        storage.add_planting(planting, user_id)
        print("Sējuma vēsture pievienota!")
    except Exception as e:
        print(f"Kļūda: {e}")


def list_plantings_by_field(storage: Storage, user_id: int):
    """Parāda sējumu vēsturi pēc lauka ID."""
    try:
        field_id_str = input("Lauka ID: ").strip()
        try:
            field_id = int(field_id_str)
        except ValueError:
            print("Kļūda: Lauka ID jābūt skaitlim!")
            return
        
        all_plantings = storage.list_plantings(user_id)
        filtered = [p for p in all_plantings if p.field_id == field_id]
        
        if not filtered:
            print(f"Nav sējumu vēstures laukam ar ID: {field_id}")
            return
        
        print(f"\nSējumu vēsture laukam ID {field_id}:")
        print("-" * 60)
        for planting in filtered:
            print(f"Gads: {planting.year} | Kultūra: {planting.crop}")
    except Exception as e:
        print(f"Kļūda: {e}")


def recommend_crop_for_field(storage: Storage, user_id: int):
    """Ieteic ko sēt nākamajam gadam pēc lauka ID."""
    try:
        # Ielādē kultūru katalogu
        crops_dict = load_catalog()
        
        # Iegūst lauka ID
        field_id_str = input("Lauka ID: ").strip()
        try:
            field_id = int(field_id_str)
        except ValueError:
            print("Kļūda: Lauka ID jābūt skaitlim!")
            return
        
        # Iegūst lauku no DB
        fields = storage.list_fields(user_id)
        field = next((f for f in fields if f.id == field_id), None)
        if not field:
            print(f"Kļūda: Lauks ar ID {field_id} nav atrasts!")
            return
        
        # Iegūst visu sējumu vēsturi
        history = storage.list_plantings(user_id)
        
        # Pārbauda, vai ir vēsture
        field_history = [p for p in history if p.field_id == field_id]
        
        # Nosaka nākamo gadu
        next_year = datetime.now().year + 1
        
        # Iegūst ieteikumu ar scenārijiem
        scenario_result = recommend_with_scenarios(
            field=field,
            history=history,
            crops_dict=crops_dict,
            target_year=next_year
        )
        
        # Izdrukā rezultātu
        print(f"\n=== Ieteikums laukam '{field.name}' (ID: {field.id}) ===")
        print(f"Plānotais gads: {next_year}")
        print("-" * 60)
        
        # Iegūst bāzes scenārija rezultātu
        base_result = scenario_result['scenario_results'].get('base')
        
        if not base_result or base_result['best_crop'] is None:
            if not field_history:
                print("Nav sējumu vēstures šim laukam.")
                print("Lai iegūtu ieteikumus, pievienojiet sējumu vēsturi (opcija 3).")
            else:
                print(f"Nav atļautu kultūru pēc sējumu vēstures noteikumiem.")
                print(f"Pamatojums: {base_result['explanation'] if base_result else 'Nav pieejamu kultūru'}")
            return
        
        # Izdrukā galveno ieteikumu
        print(f"\nIeteicamā kultūra: {base_result['best_crop']}")
        profit_eur = base_result['best_profit']
        profit_per_ha = profit_eur / field.area_ha if field.area_ha > 0 else 0
        print(f"Paredzamā peļņa: {profit_eur:.2f} EUR ({profit_per_ha:.2f} EUR/ha)")
        print(f"Sēšanas mēneši: {', '.join(map(str, base_result['sow_months']))}")
        print(f"Pamatojums: {base_result['explanation']}")
        
        # Parāda TOP-3 alternatīvas
        if base_result['top3']:
            print("\nTOP-3 alternatīvas:")
            print("-" * 60)
            for i, item in enumerate(base_result['top3'], 1):
                marker = "★" if i == 1 else " "
                alt_profit_per_ha = item['profit'] / field.area_ha if field.area_ha > 0 else 0
                print(f"{marker} {i}. {item['name']}")
                print(f"   Peļņa: {item['profit']:.2f} EUR ({alt_profit_per_ha:.2f} EUR/ha)")
        
        # Parāda scenāriju stabilitāti
        stability = scenario_result['stability']
        stable_crop = scenario_result.get('stable_crop')
        total_scenarios = 5
        
        print(f"\nScenāriju stabilitāte:")
        if stable_crop and stable_crop != base_result['best_crop']:
            print(f"  Piezīme: Stabilākā izvēle visos scenārijos ir '{stable_crop}'")
            print(f"  (atšķiras no bāzes scenārija ieteikuma '{base_result['best_crop']}')")
        
        if stability == total_scenarios:
            print(f"  Ieteikums nemainās visos {total_scenarios} scenārijos (stabilā izvēle)")
        elif stability >= 3:
            print(f"  Ieteikums nemainās {stability}/{total_scenarios} scenārijos (relatīvi stabila izvēle)")
        else:
            print(f"  Ieteikums nemainās tikai {stability}/{total_scenarios} scenārijos (nestabila izvēle)")
            print(f"  Uzmanību: ieteikums var mainīties atkarībā no cenu izmaiņām!")
        
        # Piemērs: AI skaidrojums (opcionāli)
        # explanation_data = {
        #     'best_crop': base_result['best_crop'],
        #     'best_profit': base_result['best_profit'],
        #     'sow_months': base_result['sow_months'],
        #     'top3': base_result['top3'],
        #     'stability': stability,
        #     'field': field
        # }
        # ai_explanation = explain_recommendation(explanation_data)
        # print(f"\n=== Detalizēts skaidrojums ===")
        # print(ai_explanation)
        
    except FileNotFoundError:
        print("Kļūda: Nav atrasts crops.json fails!")
    except Exception as e:
        print(f"Kļūda: {e}")


if __name__ == "__main__":
    # CLI versija - tikai, ja fails tiek palaists tieši
    # Streamlit NEDRĪKST importēt šo failu
    main_cli()


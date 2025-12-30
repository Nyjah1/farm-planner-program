import sys
import io
import os

# Iestatīt UTF-8 kodējumu Windows sistēmām
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from pathlib import Path
import pandas as pd
from urllib.parse import quote
from typing import Optional, Dict
import re
import plotly.express as px

from src.models import CropModel, FieldModel, PlantingRecord, SoilType
from src.planner import load_catalog, plan_for_years, plan_for_years_lookahead, recommend_for_field, recommend_with_scenarios, get_last_price_update, get_price_meta, get_catalog_validation_result, recommend_for_all_fields_with_limits
from src.storage import Storage
from src.market_prices import get_price_history
from src.scenarios import default_volatility_pct
from src.prices import load_prices_with_fallback, load_prices_csv
from src.price_provider import get_price_for_crop
from src.profit import _safe_yield_for_soil, profit_eur_detailed
from src.analytics import crop_area_by_year
from src.auth import login, register, logout
import json

# Konfigurācija - JĀBŪT PIRMAJAI Streamlit komandai
st.set_page_config(
    page_title="Farm Planner",
    page_icon=None,
    layout="wide"
)

# Inicializācijas pārbaude (tikai servera logā)
if 'debug_shown' not in st.session_state:
    st.session_state.debug_shown = True
    print("Aplikācija sākas...")

# Inicializē Storage (izmantojot session state, lai nav katru reizi jauns)
if 'storage' not in st.session_state:
    try:
        st.session_state.storage = Storage()
    except Exception as e:
        st.error(f"Kļūda inicializējot sistēmu: {e}")
        import traceback
        print(f"Kļūda inicializējot sistēmu: {e}")
        print(traceback.format_exc())
        st.stop()

# Definē storage tikai pēc inicializācijas
if 'storage' in st.session_state:
    storage = st.session_state.storage
else:
    storage = None


def _show_price_source_info():
    """
    Parāda cenu avota informāciju (EC agridata vai lokālais katalogs).
    """
    last_update = get_last_price_update()
    if last_update:
        st.caption(f"**Cenas:** EC Agri-food Data Portal, atjaunots: {last_update}")
    else:
        st.caption("**Cenas:** lokālais katalogs (crops.json)")


def _show_price_source_for_crop(crop_name: str):
    """
    Parāda cenu avotu konkrētai kultūrai.
    """
    try:
        prices_fallback = load_prices_with_fallback()
        price_info = prices_fallback.get(crop_name, {})
        
        if not price_info or price_info.get("price_eur_t") is None or price_info.get("price_eur_t") == 0:
            st.caption("Nav cenas")
            return
        
        source_type = price_info.get("source_type", "manual")
        
        if source_type == "market":
            st.caption("Tirgus cena")
        elif source_type == "proxy":
            st.caption("Aprēķināta cena")
        elif source_type == "manual":
            st.caption("Lietotāja ievadīta cena")
        else:
            st.caption("Nav cenas")
    except Exception:
        # Fallback, ja neizdodas ielādēt
        st.caption("Nav cenas")


def _get_price_source_text(crop_name: str, crops_dict: Optional[Dict] = None) -> str:
    """
    Atgriež cilvēkam saprotamu cenu avota tekstu.
    
    Args:
        crop_name: Kultūras nosaukums
        crops_dict: Optional kultūru vārdnīca (ja nav, mēģina ielādēt)
    
    Returns:
        Avota teksts vai tukšs strings "", ja nav cenas
    """
    try:
        # Pārbauda, vai kultūrai vispār ir cena
        if crops_dict is None:
            try:
                crops_dict = load_catalog()
            except Exception:
                pass
        
        if crops_dict and crop_name in crops_dict:
            crop = crops_dict[crop_name]
            if crop.price_eur_t is None:
                return ""  # Nav avota, ja nav cenas
        
        # Vispirms mēģina no price_meta (kas satur CSP informāciju)
        price_meta_dict = get_price_meta()
        meta = price_meta_dict.get(crop_name, {})
        source_type = meta.get("source_type")
        
        if source_type == "csp":
            return "CSP LAC020"
        
        # Citādi mēģina no prices_fallback
        prices_fallback = load_prices_with_fallback()
        price_info = prices_fallback.get(crop_name, {})
        
        if not price_info or price_info.get("price_eur_t") is None or price_info.get("price_eur_t") == 0:
            return ""  # Nav avota, ja nav cenas
        
        source_type = price_info.get("source_type", "manual")
        
        if source_type == "market":
            return "Tirgus cena"
        elif source_type == "proxy":
            return "Aprēķināta cena"
        elif source_type == "manual":
            return "Lietotāja ievadīta cena"
        elif source_type == "csp":
            return "CSP LAC020"
        else:
            return ""  # Nav avota, ja nav cenas
    except Exception:
        return ""  # Nav avota, ja nav cenas


def _price_badge(crop_name: str) -> str:
    """
    Atgriež vienkāršu tekstu par cenu avotu (cilvēkam saprotamu).
    """
    return _get_price_source_text(crop_name)


def _agro_badge():
    """Badge agrovides / zālāju kultūrām."""
    return "Agrovides kultūra"


def load_price_volatility() -> Dict[str, Dict[str, int]]:
    """
    Ielādē cenu svārstību datus no price_volatility.json.
    """
    volatility_path = Path("data/price_volatility.json")
    if not volatility_path.exists():
        return {}
    
    try:
        with open(volatility_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def get_price_change_for_scenario(scenario: str, crop_group: str) -> int:
    """
    Atgriež cenu izmaiņu procentus scenārijam un kultūras grupai.
    
    Args:
        scenario: "Pesimistisks", "Bāzes", vai "Optimistisks"
        crop_group: Kultūras grupa (piem., "Graudaugi", "Eļļaugi")
    
    Returns:
        Cenu izmaiņa procentos
    """
    if scenario == "Bāzes":
        return 0
    
    volatility_data = load_price_volatility()
    group_data = volatility_data.get(crop_group, {})
    
    if scenario == "Pesimistisks":
        return group_data.get("min", -10)
    elif scenario == "Optimistisks":
        return group_data.get("max", 10)
    
    return 0


def normalize_block_code(block_code: str) -> Optional[str]:
    """
    Normalizē bloka kodu: strip(), aizvieto vairākas atstarpes ar vienu,
    un pārvērš 10 ciparus bez domuzīmes uz formātu ar domuzīmi.
    
    Args:
        block_code: Oriģinālais bloka kods
    
    Returns:
        Normalizēts bloka kods vai None, ja tukšs
    """
    if not block_code:
        return None
    # Noņem atstarpes un normalizē
    normalized = re.sub(r'\s+', '', block_code.strip())
    if not normalized:
        return None
    
    # Ja ir tieši 10 cipari bez domuzīmes, pievieno domuzīmi
    if re.match(r'^\d{10}$', normalized):
        normalized = f"{normalized[:5]}-{normalized[5:]}"
    
    return normalized


def safe_filename(text: str) -> str:
    """
    Normalizē tekstu, lai to varētu izmantot kā faila nosaukumu.
    
    Args:
        text: Oriģinālais teksts
    
    Returns:
        Normalizēts faila nosaukums
    """
    # Latviešu garumzīmju normalizācija
    char_map = {
        'ā': 'a', 'ē': 'e', 'ī': 'i', 'ū': 'u',
        'č': 'c', 'š': 's', 'ž': 'z',
        'ģ': 'g', 'ķ': 'k', 'ļ': 'l', 'ņ': 'n',
        'Ā': 'A', 'Ē': 'E', 'Ī': 'I', 'Ū': 'U',
        'Č': 'C', 'Š': 'S', 'Ž': 'Z',
        'Ģ': 'G', 'Ķ': 'K', 'Ļ': 'L', 'Ņ': 'N'
    }
    
    # Normalizē garumzīmes
    normalized = text
    for lat_char, eng_char in char_map.items():
        normalized = normalized.replace(lat_char, eng_char)
    
    # Pārveido uz lowercase
    normalized = normalized.lower()
    
    # Atstarpes uz _
    normalized = normalized.replace(' ', '_')
    
    # Noņem citus nepareizos simbolus (atstāj tikai burtus, ciparus, _ un -)
    import re
    normalized = re.sub(r'[^a-z0-9_-]', '', normalized)
    
    return normalized


def load_demo_data():
    """Ielādē demo datus, ja DB ir tukšs."""
    if "user" not in st.session_state:
        st.error("Nav ielogojies")
        return
    
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta")
        return
    
    storage = st.session_state.storage
    user_id = st.session_state["user"]
    fields = storage.list_fields(user_id)
    plantings = storage.list_plantings(user_id)

    if len(fields) > 0 or len(plantings) > 0:
        st.info("Dati jau eksistē. Demo datus nevar ielādēt.")
        return

    # Demo lauki ar konkrētiem LAD bloku kodiem
    demo_fields_data = [
        {"block_code": "59276-37098", "area_ha": 10.71, "soil": SoilType.MALS, "name": "Ziemeļu lauks"},
        {"block_code": "59240-37102", "area_ha": 7.01, "soil": SoilType.SMILTS, "name": "Dienvidu lauks"},
        {"block_code": "59286-37066", "area_ha": 7.22, "soil": SoilType.KUDRA, "name": "Rietumu lauks"},
        {"block_code": "59340-37036", "area_ha": 12.04, "soil": SoilType.MITRA, "name": "Austrumu lauks"},
        {"block_code": "59340-37062", "area_ha": 4.19, "soil": SoilType.MALS, "name": "Centrālais lauks"},
    ]

    # Izveido laukus
    user_id = st.session_state["user"]
    created_fields = []
    for field_data in demo_fields_data:
        field = FieldModel(
            id=0,
            name=field_data["name"],
            area_ha=field_data["area_ha"],
            soil=field_data["soil"],
            owner_user_id=user_id,
            block_code=field_data["block_code"],
            rent_eur_ha=0.0
        )
        result = storage.add_field(field, user_id)
        created_fields.append(result)

    # Demo sējumu vēsture (4 ieraksti katram laukam: current_year-4 līdz current_year-1)
    current_year = datetime.now().year
    
    # Reālistiskas rotācijas katram laukam (dažādas, lai nav identiskas)
    # Izmanto tikai kultūras, kas eksistē crops.json
    rotation_patterns = [
        ["Kvieši", "Rapsis (vasaras)", "Mieži", "Zirņi"],  # Lauks 1
        ["Mieži", "Kvieši", "Auzas", "Pupas"],              # Lauks 2
        ["Auzas", "Zirņi", "Kvieši", "Mieži"],              # Lauks 3
        ["Rapsis (vasaras)", "Mieži", "Pupas", "Kvieši"],   # Lauks 4
        ["Kvieši", "Auzas", "Rapsis (vasaras)", "Zirņi"],  # Lauks 5
    ]

    demo_plantings = []
    for idx, field in enumerate(created_fields):
        rotation = rotation_patterns[idx % len(rotation_patterns)]
        for year_offset in range(4):
            year = current_year - 4 + year_offset
            crop = rotation[year_offset % len(rotation)]
            demo_plantings.append(
                PlantingRecord(field_id=field.id, year=year, crop=crop, owner_user_id=user_id)
            )

    # Pievieno sējumu ierakstus
    for p in demo_plantings:
        storage.add_planting(p, user_id)

    # Parāda success ar skaitiem
    st.success(f"Ielādēti {len(created_fields)} lauki un {len(demo_plantings)} sējumu ieraksti.")


def clear_all_data():
    """Izdzēš visus datus konkrētam lietotājam."""
    try:
        if "user" not in st.session_state:
            st.error("Nav ielogojies")
            return False
        
        if 'storage' not in st.session_state:
            st.error("Sistēma nav inicializēta")
            return False
        
        storage = st.session_state.storage
        user_id = st.session_state["user"]
        if storage.clear_user_data(user_id):
            st.success("Visi dati veiksmīgi izdzēsti!")
            return True
        else:
            st.info("Nav datu, ko dzēst.")
            return False
    except Exception as e:
        st.error(f"Kļūda dzēšot datus: {e}")
        return False


def month_names(months: list[int]) -> str:
    """
    Pārvērš mēnešu numurus uz latviešu mēnešu nosaukumiem.
    
    Args:
        months: Mēnešu numuru saraksts (1-12), piem. [4, 5]
    
    Returns:
        Formatēts teksts, piem. "Aprīlis, Maijs"
    """
    month_dict = {
        1: "Janvāris",
        2: "Februāris",
        3: "Marts",
        4: "Aprīlis",
        5: "Maijs",
        6: "Jūnijs",
        7: "Jūlijs",
        8: "Augusts",
        9: "Septembris",
        10: "Oktobris",
        11: "Novembris",
        12: "Decembris"
    }
    
    month_texts = [month_dict.get(m, str(m)) for m in months]
    return ", ".join(month_texts)


def generate_report_text(
    field: FieldModel,
    planning_horizon: str,
    target_year: int,
    price_change: int,
    result_data: dict
) -> str:
    """
    Ģenerē teksta atskaiti no ieteikuma rezultāta.
    
    Args:
        field: Lauka modelis
        planning_horizon: "1 gads" vai "3 gadi"
        target_year: Plānotais gads
        price_change: Cenu izmaiņas procentos
        result_data: Ieteikuma rezultāts (base_result vai plan_result)
    
    Returns:
        Atskaites teksts
    """
    lines = []
    lines.append("=" * 60)
    lines.append("FARM PLANNER - IETEIKUMA ATSKAITE")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Lauks: {field.name} (ID: {field.id})")
    lines.append(f"Platība: {field.area_ha} ha")
    lines.append(f"Augsnes veids: {field.soil.label}")
    lines.append(f"Plānošanas horizonts: {planning_horizon}")
    lines.append(f"Plānotais gads: {target_year}")
    if price_change != 0:
        lines.append(f"Cenu izmaiņas: {price_change:+.0f}%")
    lines.append("")
    lines.append("-" * 60)
    lines.append("")
    
    if planning_horizon == "3 gadi":
        # 3 gadu plāna atskaite
        plan = result_data.get("plan", [])
        total_profit = result_data.get("total_profit", 0.0)
        avg_profit_per_ha = result_data.get("avg_profit_per_ha", 0.0)
        
        lines.append("3 GADU PLĀNS")
        lines.append("")
        
        for entry in plan:
            year = entry.get("year")
            crop = entry.get("crop")
            profit = entry.get("profit", 0.0)
            profit_per_ha = entry.get("profit_per_ha", 0.0)
            sow_months = entry.get("sow_months", [])
            explanation = entry.get("explanation", "")
            
            lines.append(f"Gads: {year}")
            if crop:
                lines.append(f"  Kultūra: {crop}")
                lines.append(f"  Peļņa: {profit:.2f} EUR ({profit_per_ha:.2f} EUR/ha)")
                if sow_months:
                    sow_months_str = month_names(sow_months)
                    lines.append(f"  Sēšanas mēneši: {sow_months_str}")
            else:
                lines.append(f"  Kultūra: Nav ieteikuma")
                if explanation:
                    lines.append(f"  Piezīme: {explanation}")
            lines.append("")
        
        lines.append("-" * 60)
        lines.append("")
        lines.append(f"Kopējā peļņa (3 gadi): {total_profit:.2f} EUR")
        lines.append(f"Vidējā peļņa (uz ha): {avg_profit_per_ha:.2f} EUR/ha")
    else:
        # 1 gada ieteikuma atskaite
        best_crop = result_data.get("best_crop")
        best_profit = result_data.get("best_profit", 0.0)
        sow_months = result_data.get("sow_months", [])
        top3 = result_data.get("top3", [])
        explanation = result_data.get("explanation", "")
        stability = result_data.get("stability", 0)
        
        if best_crop:
            lines.append("IETEIKUMS")
            lines.append("")
            lines.append(f"Ieteicamā kultūra: {best_crop}")
            profit_per_ha = best_profit / field.area_ha if field.area_ha > 0 else 0
            lines.append(f"Prognozētā peļņa: {best_profit:.2f} EUR ({profit_per_ha:.2f} EUR/ha)")
            
            if sow_months:
                sow_months_str = month_names(sow_months)
                lines.append(f"Sēšanas mēneši: {sow_months_str}")
            
            if explanation:
                lines.append(f"Pamatojums: {explanation}")
            
            lines.append("")
            
            if top3:
                lines.append("TOP-3 alternatīvas:")
                for i, item in enumerate(top3, 1):
                    alt_profit_per_ha = item['profit'] / field.area_ha if field.area_ha > 0 else 0
                    line = f"  {i}. {item['name']}: {item['profit']:.2f} EUR ({alt_profit_per_ha:.2f} EUR/ha)"
                    if item.get('ph_note'):
                        line += f" - {item['ph_note']}"
                    lines.append(line)
                lines.append("")
            
            if stability > 0:
                lines.append(f"Scenāriju stabilitāte: {stability}/5 scenāriji")
        else:
            lines.append("Nav ieteikuma")
            if explanation:
                lines.append(f"Piezīme: {explanation}")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"Ģenerēts: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def show_dashboard_section():
    """Sadaļa: Dashboard."""
    st.title("Dashboard")
    st.caption("Sistēmas pārskats")
    
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta")
        return
    
    storage = st.session_state.storage
    
    # Iegūst datus
    user_id = st.session_state["user"]
    fields = storage.list_fields(user_id)
    all_plantings = storage.list_plantings(user_id)
    
    # Aprēķina statistiku
    total_fields = len(fields)
    total_hectares = sum(f.area_ha for f in fields)
    total_plantings = len(all_plantings)
    
    # Parāda metrikas
    if total_fields > 0 or total_plantings > 0:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Lauku skaits", total_fields)
        
        with col2:
            st.metric("Kopējā platība", f"{total_hectares:.2f} ha")
        
        with col3:
            st.metric("Sējumu ieraksti", total_plantings)
        
        # Potenciālā peļņa
        if fields:
            est_profit = sum(f.area_ha * 300 for f in fields)  # demo
            st.metric("Potenciālā peļņa sezonā", f"{est_profit:,.0f} EUR")
        
        # Īss skaidrojums
        st.markdown("### Sistēmas apraksts")
        st.write(
            "Farm Planner ir vienkārša lēmumu atbalsta sistēma, "
            "kas palīdz izvēlēties optimālas kultūras sēšanai, "
            "balstoties uz augsni, sējumu vēsturi, ražību un cenām."
        )
        
        # Ātrais ceļš
        st.markdown("### Darba uzsākšana")
        st.write("""
        1. Pievienojiet laukus sadaļā **Lauki**
        2. Ievadiet sējumu vēsturi
        3. Dodieties uz sadaļu **Ieteikumi**, lai saņemtu plānu
        """)
        
        st.divider()
        st.subheader("Peļņas prognoze (3 gadi)")
        st.caption("Prognoze balstīta uz cenu bāzes scenāriju")

        # ielādē katalogu
        try:
            crops_dict = load_catalog()
            # Saglabā last_price_update session_state
            st.session_state.last_price_update = get_last_price_update()
        except Exception as e:
            st.error(f"Nevar ielādēt kultūru katalogu: {e}")
            return
        
        # Datu validācija
        validation_result = get_catalog_validation_result()
        if validation_result:
            with st.expander("Datu validācija", expanded=False):
                missing_yield_by_soil = validation_result.get('missing_yield_by_soil', {})
                crops_without_yield = validation_result.get('crops_without_yield', [])
                
                # Pārbauda, vai ir problēmas
                has_issues = False
                for soil_type, missing_crops in missing_yield_by_soil.items():
                    if missing_crops:
                        has_issues = True
                        break
                
                if crops_without_yield:
                    has_issues = True
                
                if has_issues:
                    # Parāda statistiku pa augsnēm
                    st.markdown("#### Trūkstošie yield dati pa augsnēm")
                    validation_data = []
                    for soil_type in SoilType:
                        missing_crops = missing_yield_by_soil.get(soil_type, [])
                        count = len(missing_crops)
                        validation_data.append({
                            "Augsne": soil_type.label,
                            "Kultūru skaits bez yield datu": count
                        })
                    st.dataframe(validation_data, use_container_width=True, hide_index=True)
                    
                    # Parāda brīdinājumu, ja ir problēmas
                    total_missing = sum(len(missing_crops) for missing_crops in missing_yield_by_soil.values())
                    if total_missing > 0:
                        st.warning(f"Daudzām kultūrām nav ražas datu šai augsnei, ieteikumi būs ierobežoti.")
                    
                    # Parāda kultūras bez jebkāda yield datu
                    if crops_without_yield:
                        st.markdown("#### Kultūras bez jebkāda yield datu")
                        st.caption(", ".join(crops_without_yield))
                else:
                    st.success("Visi yield dati ir kārtībā.")
        
        user_id = st.session_state["user"]
        fields = storage.list_fields(user_id)
        if not fields:
            st.info("Nav lauku datu, lai veidotu prognozi.")
            return

        current_year = datetime.now().year
        start_year = current_year + 1
        years = [start_year, start_year + 1, start_year + 2]
        
        # Vēsturiskie gadi (pēdējie 3 gadi pirms start_year)
        historical_years = [start_year - 3, start_year - 2, start_year - 1]

        # dropdown: visi lauki / viens lauks
        options = ["Visi lauki"] + [f"{f.id} - {f.name}" for f in fields]
        selected = st.selectbox("Izvēlēties lauku", options, key="dash_field_select")

        # savāc datus (1x)
        all_plantings = storage.list_plantings(user_id)
        rows = []
        
        # Ielādē cenas
        from src.price_provider import get_price_for_crop
        from src.profit import profit_eur_detailed
        prices_csv = load_prices_csv()

        for f in fields:
            field_history = [p for p in all_plantings if p.field_id == f.id]
            
            # Aprēķina vēsturisko peļņu (ja ir dati)
            for hist_year in historical_years:
                hist_planting = next((p for p in field_history if p.year == hist_year), None)
                if hist_planting and hist_planting.crop in crops_dict:
                    crop = crops_dict[hist_planting.crop]
                    price_info = get_price_for_crop(crop, prices_csv)
                    profit_details = profit_eur_detailed(f, crop, price_info)
                    rows.append({
                        "Year": hist_year,
                        "Field": f.name,
                        "Profit": profit_details["profit"],
                        "IsHistorical": True,
                    })

            plan_result = plan_for_years(
                field=f,
                history=field_history,
                crops_dict=crops_dict,
                start_year=start_year,
                years=3,
                include_crops_without_price=False
            )

            for entry in plan_result.get("plan", []):
                rows.append({
                    "Year": int(entry["year"]),
                    "Field": f.name,
                    "Profit": float(entry.get("profit", 0.0)),
                    "IsHistorical": False,
                })

        df = pd.DataFrame(rows)

        if df.empty:
            st.info("Nav pietiekamu datu, lai uzzīmētu grafiku.")
            return

        # Visi gadi (vēsturiskie + prognozētie)
        all_years = historical_years + years
        df = df[df["Year"].isin(all_years)].copy()
        
        # Izveido YearLabel ar vizuālu atšķirību
        def format_year_label(row):
            year = row["Year"]
            is_hist = row.get("IsHistorical", False)
            if is_hist:
                return f"{year} (vēsture)"
            return str(year)
        
        df["YearLabel"] = df.apply(format_year_label, axis=1)

        # peļņa uz ha
        field_area = {f.name: float(f.area_ha) for f in fields}
        df["AreaHa"] = df["Field"].map(field_area).fillna(0)
        df["ProfitPerHa"] = df.apply(lambda r: (r["Profit"] / r["AreaHa"]) if r["AreaHa"] > 0 else 0, axis=1)

        # ja izvēlēts konkrēts lauks — filtrējam df
        if selected != "Visi lauki":
            selected_name = selected.split(" - ", 1)[1]
            df = df[df["Field"] == selected_name].copy()

        # Sakārto gada secību: vēsturiskie, tad prognozētie
        historical_df = df[df["IsHistorical"] == True].copy()
        forecast_df = df[df["IsHistorical"] == False].copy()
        
        # Sakārto vēsturiskos gadus
        if not historical_df.empty:
            historical_df = historical_df.sort_values("Year")
        # Sakārto prognozētos gadus
        if not forecast_df.empty:
            forecast_df = forecast_df.sort_values("Year")
        
        # 2 grafiki blakus
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("#### Peļņa (EUR)")
            
            # Izveido grafiku ar plotly, lai varētu kontrolēt stilu
            import plotly.graph_objects as go
            
            fig_profit = go.Figure()
            
            # Vēsturiskie gadi (gaišāka līnija)
            if not historical_df.empty:
                for field_name in historical_df["Field"].unique():
                    field_data = historical_df[historical_df["Field"] == field_name]
                    fig_profit.add_trace(go.Scatter(
                        x=field_data["YearLabel"],
                        y=field_data["Profit"],
                        name=f"{field_name} (vēsture)",
                        line=dict(color='lightgray', width=2, dash='dot'),
                        mode='lines+markers'
                    ))
            
            # Prognozētie gadi (normāla līnija)
            if not forecast_df.empty:
                for field_name in forecast_df["Field"].unique():
                    field_data = forecast_df[forecast_df["Field"] == field_name]
                    fig_profit.add_trace(go.Scatter(
                        x=field_data["YearLabel"],
                        y=field_data["Profit"],
                        name=field_name,
                        line=dict(width=2),
                        mode='lines+markers'
                    ))
            
            # Ja ir "Visi lauki", pievieno "Kopā"
            if selected == "Visi lauki":
                if not historical_df.empty:
                    hist_total = historical_df.groupby("YearLabel")["Profit"].sum()
                    fig_profit.add_trace(go.Scatter(
                        x=hist_total.index,
                        y=hist_total.values,
                        name="Kopā (vēsture)",
                        line=dict(color='gray', width=2, dash='dot'),
                        mode='lines+markers'
                    ))
                if not forecast_df.empty:
                    forecast_total = forecast_df.groupby("YearLabel")["Profit"].sum()
                    fig_profit.add_trace(go.Scatter(
                        x=forecast_total.index,
                        y=forecast_total.values,
                        name="Kopā",
                        line=dict(color='blue', width=3),
                        mode='lines+markers'
                    ))
            
            fig_profit.update_layout(
                height=320,
                xaxis_title="Gads",
                yaxis_title="Peļņa (EUR)",
                hovermode='x unified'
            )
            st.plotly_chart(fig_profit, use_container_width=True)

        with col_right:
            st.markdown("#### Peļņa (EUR/ha)")
            
            # Izveido grafiku ar plotly
            fig_ha = go.Figure()
            
            # Vēsturiskie gadi (gaišāka līnija)
            if not historical_df.empty:
                for field_name in historical_df["Field"].unique():
                    field_data = historical_df[historical_df["Field"] == field_name]
                    fig_ha.add_trace(go.Scatter(
                        x=field_data["YearLabel"],
                        y=field_data["ProfitPerHa"],
                        name=f"{field_name} (vēsture)",
                        line=dict(color='lightgray', width=2, dash='dot'),
                        mode='lines+markers',
                        showlegend=False
                    ))
            
            # Prognozētie gadi (normāla līnija)
            if not forecast_df.empty:
                for field_name in forecast_df["Field"].unique():
                    field_data = forecast_df[forecast_df["Field"] == field_name]
                    fig_ha.add_trace(go.Scatter(
                        x=field_data["YearLabel"],
                        y=field_data["ProfitPerHa"],
                        name=field_name,
                        line=dict(width=2),
                        mode='lines+markers',
                        showlegend=False
                    ))
            
            # Ja ir "Visi lauki", pievieno "Kopā"
            if selected == "Visi lauki":
                if not historical_df.empty:
                    hist_total_profit = historical_df.groupby("YearLabel")["Profit"].sum()
                    hist_total_area = historical_df.groupby("YearLabel")["AreaHa"].sum()
                    hist_avg_ha = (hist_total_profit / hist_total_area).fillna(0)
                    fig_ha.add_trace(go.Scatter(
                        x=hist_avg_ha.index,
                        y=hist_avg_ha.values,
                        name="Kopā (vēsture)",
                        line=dict(color='gray', width=2, dash='dot'),
                        mode='lines+markers',
                        showlegend=False
                    ))
                if not forecast_df.empty:
                    forecast_total_profit = forecast_df.groupby("YearLabel")["Profit"].sum()
                    forecast_total_area = forecast_df.groupby("YearLabel")["AreaHa"].sum()
                    forecast_avg_ha = (forecast_total_profit / forecast_total_area).fillna(0)
                    fig_ha.add_trace(go.Scatter(
                        x=forecast_avg_ha.index,
                        y=forecast_avg_ha.values,
                        name="Kopā",
                        line=dict(color='blue', width=3),
                        mode='lines+markers',
                        showlegend=False
                    ))
            
            fig_ha.update_layout(
                height=320,
                xaxis_title="Gads",
                yaxis_title="Peļņa (EUR/ha)",
                hovermode='x unified'
            )
            st.plotly_chart(fig_ha, use_container_width=True)
        
        # Paskaidrojums par vēsturiskajiem gadiem
        if not historical_df.empty:
            st.caption("Vēsturiskie gadi (pēdējie 3 gadi) ir parādīti ar punktētu līniju. Prognozētie gadi ir parādīti ar nepārtrauktu līniju.")

        # Pārbauda, vai 2. prognozes gadā peļņa ir zemāka (rotācijas efekts)
        if not forecast_df.empty:
            forecast_sorted = forecast_df.sort_values("Year").copy()
            if len(forecast_sorted) >= 2:
                # Aprēķina peļņu uz ha katram gadam
                if selected == "Visi lauki":
                    # Visiem laukiem kopā
                    yearly_stats = forecast_sorted.groupby("Year").agg({"Profit": "sum", "AreaHa": "sum"}).reset_index()
                    if len(yearly_stats) >= 2:
                        first_year_stats = yearly_stats.iloc[0]
                        second_year_stats = yearly_stats.iloc[1]
                        first_year_profit_ha = first_year_stats["Profit"] / first_year_stats["AreaHa"] if first_year_stats["AreaHa"] > 0 else 0
                        second_year_profit_ha = second_year_stats["Profit"] / second_year_stats["AreaHa"] if second_year_stats["AreaHa"] > 0 else 0
                        
                        if second_year_profit_ha < first_year_profit_ha:
                            st.info("Peļņa zemāka rotācijas gadā – galvenā kultūra nav atļauta pēc iepriekšējā gada. Tas ir normāli un atbilst agronomiskajai loģikai.")
                else:
                    # Vienam laukam
                    first_year_data = forecast_sorted.iloc[0]
                    second_year_data = forecast_sorted.iloc[1]
                    first_year_profit_ha = first_year_data["ProfitPerHa"]
                    second_year_profit_ha = second_year_data["ProfitPerHa"]
                    
                    if second_year_profit_ha < first_year_profit_ha:
                        st.info("Peļņa zemāka rotācijas gadā – galvenā kultūra nav atļauta pēc iepriekšējā gada. Tas ir normāli un atbilst agronomiskajai loģikai.")

        # metrikas zem grafikiem
        st.divider()
        # Tikai prognozētie gadi metrikām
        forecast_total_profit = forecast_df["Profit"].sum() if not forecast_df.empty else 0
        forecast_avg_profit_per_ha = (forecast_df["ProfitPerHa"].mean()) if not forecast_df.empty and len(forecast_df) > 0 else 0

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Kopējā peļņa (3 gadi)", f"{forecast_total_profit:,.0f} EUR")
        with m2:
            st.metric("Vidēji EUR/ha", f"{forecast_avg_profit_per_ha:,.0f} EUR/ha")
        with m3:
            st.metric("Gadu skaits", forecast_df["Year"].nunique() if not forecast_df.empty else 0)
        
        # Cenu avota informācija
        _show_price_source_info()
        
        # Analītika: Kultūru sadalījums pēc platības
        st.divider()
        st.subheader("Kultūru sadalījums pēc platības")
        
        # Iegūst unikālos gadus no sējumu vēstures
        user_id = st.session_state["user"]
        all_plantings = storage.list_plantings(user_id)
        available_years = sorted(set(p.year for p in all_plantings), reverse=True)
        
        if available_years:
            # Dropdown ar gadiem
            selected_year = st.selectbox(
                "Gads",
                options=available_years,
                index=0,  # Default: jaunākais gads (pirmais dilstošā secībā)
                key="analytics_year_select"
            )
            
            # Aprēķina platības pa kultūrām
            user_id = st.session_state["user"]
            crop_areas = crop_area_by_year(storage, selected_year, user_id)
            
            if not crop_areas:
                st.info("Nav datu izvēlētajam gadam.")
            else:
                # Aprēķina kopējo platību
                total_area = sum(item["area_ha"] for item in crop_areas)
                
                # Sagatavo datus tabulai ar procentiem
                table_data = []
                for item in crop_areas:
                    percentage = (item["area_ha"] / total_area * 100) if total_area > 0 else 0.0
                    table_data.append({
                        "Kultūra": item["crop"],
                        "Platība (ha)": f"{item['area_ha']:.2f}",
                        "Procenti": f"{percentage:.1f}%"
                    })
                
                # Parāda pie chart un tabulu blakus
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    # Pie chart ar plotly
                    df_chart = pd.DataFrame(crop_areas)
                    fig = px.pie(
                        df_chart,
                        values="area_ha",
                        names="crop",
                        title=f"Kultūru sadalījums {selected_year}. gadā"
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Tabula
                    df_table = pd.DataFrame(table_data)
                    st.dataframe(df_table, use_container_width=True, hide_index=True)
        else:
            st.info("Nav pieejamu datu sējumu vēsturē.")
    else:
        # Nav datu - draudzīgs teksts
        st.info("Laipni lūdzam Farm Planner!")
        st.write("Sāciet ar lauku pievienošanu sadaļā **Lauki**.")
        st.write("Pēc tam varat pievienot sējumu vēsturi un saņemt ieteikumus.")
        
        # Īss skaidrojums
        st.markdown("### Kas tas ir?")
        st.write(
            "Farm Planner ir vienkārša lēmumu atbalsta sistēma, "
            "kas palīdz izvēlēties kultūras sēšanai, balstoties uz "
            "augsni, sējumu vēsturi, ražību un cenām."
        )


def show_fields_section():
    """Sadaļa: Lauki."""
    st.title("Lauki")
    
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta")
        return
    
    storage = st.session_state.storage
    
    # Forma pievienot lauku
    with st.form("add_field_form", clear_on_submit=True):
        st.subheader("Pievienot jaunu lauku")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            field_name = st.text_input("Lauka nosaukums", key="field_name")
        with col2:
            area_ha = st.number_input(
                "Platība (ha)",
                min_value=0.1,
                step=0.1,
                value=0.10,
                key="area_ha"
            )
        with col3:
            soil_label = st.selectbox(
                "Augsnes veids",
                [s.label for s in SoilType],
                key="soil"
            )
        
        col4, col5 = st.columns(2)
        with col4:
            block_code = st.text_input(
                "Lauka bloka kods (LAD)",
                key="block_code",
                placeholder="piem., 1234-5678",
                help="Var ievadīt 10 ciparus bez domuzīmes (piem 5927637098) — sistēma pati pārvērtīs uz 59276-37098. Nav obligāts."
            )
        with col5:
            rent_eur_ha = st.number_input(
                "Nomas maksa (EUR/ha)",
                min_value=0.0,
                step=10.0,
                value=0.0,
                key="rent_eur_ha",
                help="Nomas maksa uz hektāru. Ja nav nomas, atstāj 0."
            )
        
        col6, col7 = st.columns(2)
        with col6:
            specify_ph = st.checkbox("Norādīt pH", key="specify_ph_add")
            ph_value = None
            if specify_ph:
                ph_value = st.number_input(
                    "pH",
                    min_value=0.0,
                    max_value=14.0,
                    step=0.1,
                    value=7.0,
                    key="ph_add",
                    help="Augsnes pH vērtība (0-14)"
                )
        
        submitted = st.form_submit_button("Pievienot lauku")
        
        if submitted:
            try:
                if not field_name:
                    st.error("Lauka nosaukums nevar būt tukšs!")
                else:
                    soil_type = SoilType.from_label(soil_label)
                    # Normalizē block_code
                    block_code_value = normalize_block_code(block_code)
                    
                    # Parāda normalizēto vērtību, ja tā atšķiras no ievadītās
                    if block_code_value and block_code_value != block_code:
                        st.info(f"Normalizēts bloka kods: `{block_code_value}`")
                    
                    user_id = st.session_state["user"]
                    field = FieldModel(
                        id=0,
                        name=field_name,
                        area_ha=area_ha,
                        soil=soil_type,
                        owner_user_id=user_id,
                        block_code=block_code_value,
                        lad_area_ha=None,
                        lad_last_edited=None,
                        lad_last_synced=None,
                        rent_eur_ha=rent_eur_ha,
                        ph=ph_value
                    )
                    result = storage.add_field(field, user_id)
                    st.success(f"Lauks '{result.name}' pievienots ar ID: {result.id}")
                    st.rerun()
            except Exception as e:
                st.error(f"Kļūda: {e}")
    
    st.divider()
    st.subheader("Pievienotie lauki")

    user_id = st.session_state["user"]
    fields = storage.list_fields(user_id)
    if not fields:
        st.info("Nav pievienotu lauku.")
        return

    # Viena selectbox izvēle
    options = ["0 - Visi lauki"] + [f"{f.id} - {f.name}" for f in fields]
    selected_option = st.selectbox("Izvēlies lauku", options, key="selected_field_id")
    
    # Parsē izvēlēto ID
    selected_field_id = int(selected_option.split(" - ")[0])
    
    # LAD karte uzreiz zem selectbox
    url = "https://karte.lad.gov.lv/"
    selected_field = None
    
    if selected_field_id == 0:
        # "Visi lauki" - default karte
        pass
    else:
        # Konkrēts lauks
        selected_field = next((f for f in fields if f.id == selected_field_id), None)
        if selected_field:
            # Detalizētā informācija
            st.markdown(f"### {selected_field.name}")
            c1, c2, c3 = st.columns(3)
            c1.metric("ID", selected_field.id)
            c2.metric("Platība", f"{selected_field.area_ha:.2f} ha")
            rent_eur_ha = getattr(selected_field, "rent_eur_ha", 0.0)
            c3.metric("Noma", f"{rent_eur_ha:.2f} EUR/ha")
            st.markdown(f"**Augsne:** {selected_field.soil.label}")
            if selected_field.block_code:
                st.markdown(f"**Bloka kods (LAD):** `{selected_field.block_code}`")
            
            # LAD informācija
            if selected_field.lad_area_ha is not None:
                st.markdown(f"**LAD platība:** {selected_field.lad_area_ha:.2f} ha")
            if selected_field.lad_last_edited:
                st.markdown(f"**Labots:** {selected_field.lad_last_edited}")
            if selected_field.lad_last_synced:
                st.markdown(f"**Pēdējā sinhronizācija:** {selected_field.lad_last_synced}")
            
            # Veido URL pēc block_code
            if selected_field.block_code:
                url = f"https://karte.lad.gov.lv/?q={quote(selected_field.block_code)}"
    
    # LAD karte
    st.subheader("LAD karte")
    components.iframe(url, height=720)

    # Rediģēšana un dzēšana (tikai ja izvēlēts konkrēts lauks)
    if selected_field_id != 0 and selected_field:
        st.divider()
        with st.expander("Rediģēt lauku"):
            with st.form("edit_field_form"):
                new_name = st.text_input("Nosaukums", value=selected_field.name)
                new_area = st.number_input("Platība (ha)", min_value=0.1, step=0.1, value=float(selected_field.area_ha))
                new_soil = st.selectbox(
                    "Augsnes veids",
                    [s.label for s in SoilType],
                    index=[s.label for s in SoilType].index(selected_field.soil.label)
                )
                new_block_code = st.text_input(
                    "Lauka bloka kods (LAD)",
                    value=selected_field.block_code or "",
                    placeholder="piem., 1234-5678",
                    help="Var ievadīt 10 ciparus bez domuzīmes (piem 5927637098) — sistēma pati pārvērtīs uz 59276-37098. Nav obligāts."
                )
                new_rent_eur_ha = st.number_input(
                    "Nomas maksa (EUR/ha)",
                    min_value=0.0,
                    step=10.0,
                    value=float(getattr(selected_field, "rent_eur_ha", 0.0)),
                    help="Nomas maksa uz hektāru. Ja nav nomas, atstāj 0."
                )
                
                specify_ph = st.checkbox("Norādīt pH", value=getattr(selected_field, "ph", None) is not None, key="specify_ph_edit")
                ph_value = None
                if specify_ph:
                    current_ph = getattr(selected_field, "ph", None)
                    ph_value = st.number_input(
                        "pH",
                        min_value=0.0,
                        max_value=14.0,
                        step=0.1,
                        value=float(current_ph) if current_ph is not None else 7.0,
                        key="ph_edit",
                        help="Augsnes pH vērtība (0-14)"
                    )

                save = st.form_submit_button("Saglabāt", use_container_width=True)

                if save:
                    soil_type = SoilType.from_label(new_soil)
                    # Normalizē block_code
                    block_code_value = normalize_block_code(new_block_code)
                    
                    # Parāda normalizēto vērtību, ja tā atšķiras no ievadītās
                    if block_code_value and block_code_value != new_block_code:
                        st.info(f"Normalizēts bloka kods: `{block_code_value}`")
                    
                    user_id = st.session_state["user"]
                    ok = storage.update_field(
                        field_id=selected_field.id,
                        user_id=user_id,
                        name=new_name.strip(),
                        area_ha=float(new_area),
                        soil=soil_type,
                        block_code=block_code_value,
                        rent_eur_ha=float(new_rent_eur_ha),
                        ph=ph_value
                    )
                    if ok:
                        st.success("Izmaiņas saglabātas.")
                        st.rerun()
                    else:
                        st.error("Neizdevās saglabāt izmaiņas.")

        with st.expander("Dzēst lauku", expanded=False):
            st.warning("Dzēšot lauku, tiks dzēsta arī tā sējumu vēsture.")
            confirm = st.checkbox("Apstiprinu dzēšanu", key="confirm_delete_field")

            if st.button("Dzēst", use_container_width=True, disabled=not confirm):
                user_id = st.session_state["user"]
                ok = storage.delete_field(selected_field.id, user_id)
                if ok:
                    st.success("Lauks izdzēsts.")
                    st.rerun()
                else:
                    st.error("Neizdevās izdzēst lauku.")


def show_history_section():
    """Sadaļa: Sējumu vēsture."""
    st.title("Sējumu vēsture")
    
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta")
        return
    
    storage = st.session_state.storage
    
    # Iegūst laukus dropdown
    user_id = st.session_state["user"]
    fields = storage.list_fields(user_id)
    
    if not fields:
        st.warning("Vispirms pievienojiet laukus sadaļā 'Lauki'.")
        return
    
    # Ielādē kultūru sarakstu
    try:
        crops_dict = load_catalog()
        crop_names = list(crops_dict.keys())
    except Exception as e:
        st.error(f"Kļūda ielādējot kultūru katalogu: {e}")
        crop_names = []
    
    # Dropdown lauka izvēlei
    field_options = {f"{f.id} - {f.name}": f.id for f in fields}
    selected_field_label = st.selectbox(
        "Izvēlieties lauku",
        options=list(field_options.keys()),
        key="history_field_select"
    )
    
    if selected_field_label:
        selected_field_id = field_options[selected_field_label]
        selected_field = next(f for f in fields if f.id == selected_field_id)
        
        st.info(f"Lauks: {selected_field.name} ({selected_field.area_ha} ha, {selected_field.soil.label})")
        
        # Forma pievienot ierakstu
        with st.form("add_planting_form", clear_on_submit=True):
            st.subheader("Pievienot sējumu vēsturi")
            col1, col2 = st.columns(2)
            
            with col1:
                year = st.number_input("Gads", min_value=2000, max_value=2100, value=datetime.now().year, key="planting_year")
            with col2:
                # Selectbox ar kultūru nosaukumiem + "Cits..." opcija
                crop_options = crop_names + ["Cits..."] if crop_names else ["Cits..."]
                selected_crop = st.selectbox("Kultūras nosaukums", options=crop_options, key="planting_crop_select")
                
                # Ja izvēlēts "Cits...", parāda text_input
                if selected_crop == "Cits...":
                    crop = st.text_input("Ievadiet kultūras nosaukumu", key="planting_crop_custom")
                else:
                    crop = selected_crop
            
            submitted = st.form_submit_button("Pievienot ierakstu")
            
            if submitted:
                try:
                    if not crop or (selected_crop == "Cits..." and not crop.strip()):
                        st.error("Kultūras nosaukums nevar būt tukšs!")
                    else:
                        user_id = st.session_state["user"]
                        planting = PlantingRecord(field_id=selected_field_id, year=year, crop=crop.strip(), owner_user_id=user_id)
                        storage.add_planting(planting, user_id)
                        st.success(f"Sējuma vēsture pievienota: {crop} ({year})")
                        st.rerun()
                except Exception as e:
                    st.error(f"Kļūda: {e}")
        
        st.divider()
        
        # Tabula ar vēsturi
        st.subheader(f"Sējumu vēsture laukam '{selected_field.name}'")
        user_id = st.session_state["user"]
        all_plantings = storage.list_plantings(user_id)
        field_history = [p for p in all_plantings if p.field_id == selected_field_id]
        
        if not field_history:
            st.info("Nav sējumu vēstures šim laukam.")
        else:
            # Sakārto pēc gada (jaunākais pirmā)
            field_history.sort(key=lambda x: x.year, reverse=True)
            
            history_data = []
            for planting in field_history:
                history_data.append({
                    "Gads": planting.year,
                    "Kultūra": planting.crop
                })
            
            st.dataframe(history_data, use_container_width=True, hide_index=True)


def show_catalog_section():
    """Sadaļa: Kultūru katalogs."""
    st.title("Kultūru katalogs")
    
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta")
        return
    
    storage = st.session_state.storage
    
    # Ielādē kultūru katalogu
    try:
        crops_dict = load_catalog()
    except FileNotFoundError:
        st.error("Nav atrasts crops.json fails!")
        return
    except Exception as e:
        st.error(f"Kļūda ielādējot katalogu: {e}")
        return
    
    # Ielādē cenas un price_meta
    try:
        prices_dict = load_prices_with_fallback()
    except Exception as e:
        st.warning(f"Neizdevās ielādēt cenas: {e}")
        prices_dict = {}
    
    # Ielādē price_meta (avotu informācija)
    try:
        price_meta = get_price_meta()
    except Exception as e:
        price_meta = {}
    
    # Ielādē favorītus
    user_id = st.session_state["user"]
    favorites = storage.get_favorites(user_id)
    favorites_set = set(favorites)
    
    # Filtri
    col1, col2 = st.columns(2)
    with col1:
        # Grupas filtra izvēle
        all_groups = sorted(set(crop.group for crop in crops_dict.values()))
        selected_group = st.selectbox(
            "Filtrēt pēc grupas",
            options=["Visas grupas"] + all_groups,
            key="catalog_group_filter"
        )
    with col2:
        # Favorītu filtrs
        show_favorites_only = st.checkbox(
            "Rādīt tikai favorītus",
            value=False,
            key="catalog_favorites_filter"
        )
    
    # Favorītu skaitītājs
    st.caption(f"Favorīti: {len(favorites)}")
    
    # Filtrē kultūras
    filtered_crops = []
    for crop_name, crop in crops_dict.items():
        # Grupas filtrs
        if selected_group != "Visas grupas" and crop.group != selected_group:
            continue
        
        # Favorītu filtrs
        if show_favorites_only and crop_name not in favorites_set:
            continue
        
        filtered_crops.append((crop_name, crop))
    
    # Sagatavo tabulas datus
    table_data = []
    for crop_name, crop in filtered_crops:
        # Iegūst cenu
        price_eur_t = crop.price_eur_t if hasattr(crop, 'price_eur_t') and crop.price_eur_t is not None else None
        
        # Formatē cenu kolonnu
        if price_eur_t is None or price_eur_t == 0:
            price_display = "— Nav tirgus cenas"
            source_name = ""  # Nav avota, ja nav cenas
        else:
            price_display = f"{price_eur_t:.2f} (bez PVN)"
            # Iegūst avotu informāciju tikai, ja ir cena
            meta = price_meta.get(crop_name, {})
            source_name = meta.get("source_name", "Lokālais katalogs")
            if meta.get("source_type") == "csp":
                source_name = "CSP LAC020"
            elif meta.get("source_type") == "market":
                source_name = "ES Agri-food Data Portal"
            elif meta.get("source_type") == "manual":
                source_name = "Lietotāja ievadīta cena"
        
        # Pārbauda, vai ir raža/izmaksas
        has_yield = len(crop.yield_t_ha) > 0
        has_cost = crop.cost_eur_ha > 0
        has_data = "Jā" if (has_yield and has_cost) else "Nē"
        
        table_data.append({
            "Nosaukums": crop_name,
            "Grupa": crop.group,
            "Cena (EUR/t)": price_display,
            "Avots": source_name,
            "Vai ir raža/izmaksas": has_data
        })
    
    # Parāda tabulu ar favorītu toggles
    if table_data:
        # Sagatavo favorītu sarakstu
        user_id = st.session_state["user"]
        current_favorites = storage.get_favorites(user_id)
        favorites_set = set(current_favorites)
        
        # Parāda tabulu ar favorītu kolonnu
        table_data_with_fav = []
        for row in table_data:
            crop_name = row["Nosaukums"]
            is_favorite = crop_name in favorites_set
            
            # Pievieno favorītu kolonnu
            row_with_fav = row.copy()
            row_with_fav["Favorīts"] = "Jā" if is_favorite else ""
            table_data_with_fav.append(row_with_fav)
        
        df = pd.DataFrame(table_data_with_fav)
        
        # Parāda tabulu
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"Rādītas {len(table_data)} kultūras no {len(crops_dict)} kopā.")
        
        # Favorītu pārvaldība - izmanto formu, lai novērstu bezgalīgu rerun ciklu
        st.divider()
        st.subheader("Favorītās kultūras")
        
        with st.form("favorites_form", clear_on_submit=False):
            st.caption("Atzīmē kultūras kā favorītus:")
            
            # Izveido kolonnas ar favorītu checkboxes
            col1, col2, col3 = st.columns(3)
            all_crop_names = sorted(crops_dict.keys())
            chunk_size = (len(all_crop_names) + 2) // 3
            chunks = [all_crop_names[i:i+chunk_size] for i in range(0, len(all_crop_names), chunk_size)]
            
            new_favorites = []
            for i, chunk in enumerate(chunks):
                with [col1, col2, col3][i % 3]:
                    for crop_name in chunk:
                        is_favorite = crop_name in favorites_set
                        checked = st.checkbox(
                            crop_name,
                            value=is_favorite,
                            key=f"fav_check_{crop_name}"
                        )
                        if checked:
                            new_favorites.append(crop_name)
            
            save_favorites = st.form_submit_button("Saglabāt favorītus", use_container_width=True)
            
            if save_favorites:
                # Pārbauda, vai tiešām ir izmaiņas
                current_favs_set = set(current_favorites)
                new_favs_set = set(new_favorites)
                
                if current_favs_set != new_favs_set:
                    user_id = st.session_state["user"]
                    if storage.set_favorites(new_favorites, user_id):
                        st.success(f"Saglabāti {len(new_favorites)} favorīti.")
                        st.rerun()
                    else:
                        st.error("Neizdevās saglabāt favorītus.")
                else:
                    st.info("Nav izmaiņu favorītos.")
        
        # Kultūras pārvaldība
        st.divider()
        st.subheader("Kultūras pārvaldība")
        
        action = st.radio(
            "Darbība",
            ["Rediģēt esošu", "Pievienot jaunu"],
            key="crop_management_action"
        )
        
        with st.form("crop_management_form"):
            if action == "Rediģēt esošu":
                # Izvēle esošai kultūrai
                crop_options = {crop_name: crop_name for crop_name, _ in filtered_crops}
                selected_crop_name = st.selectbox(
                    "Izvēlies kultūru",
                    options=list(crop_options.keys()),
                    key="edit_crop_select"
                )
                
                if selected_crop_name:
                    selected_crop = crops_dict[selected_crop_name]
                    # Iegūst esošās vērtības
                    default_name = selected_crop.name
                    default_group = selected_crop.group
                    default_sow_months = selected_crop.sow_months
                    default_cost = selected_crop.cost_eur_ha
                    default_price = selected_crop.price_eur_t
                    default_yield_smilts = selected_crop.yield_t_ha.get(SoilType.SMILTS, 0.0)
                    default_yield_mals = selected_crop.yield_t_ha.get(SoilType.MALS, 0.0)
                    default_yield_kudra = selected_crop.yield_t_ha.get(SoilType.KUDRA, 0.0)
                    default_yield_mitra = selected_crop.yield_t_ha.get(SoilType.MITRA, 0.0)
                    default_is_market = selected_crop.is_market_crop
                else:
                    default_name = ""
                    default_group = "Graudaugi"
                    default_sow_months = []
                    default_cost = 0.0
                    default_price = None
                    default_yield_smilts = 0.0
                    default_yield_mals = 0.0
                    default_yield_kudra = 0.0
                    default_yield_mitra = 0.0
                    default_is_market = True
            else:
                # Jauna kultūra
                selected_crop_name = None
                default_name = ""
                default_group = "Graudaugi"
                default_sow_months = []
                default_cost = 0.0
                default_price = None
                default_yield_smilts = 0.0
                default_yield_mals = 0.0
                default_yield_kudra = 0.0
                default_yield_mitra = 0.0
                default_is_market = True
            
            # Formas lauki
            crop_name = st.text_input(
                "Nosaukums",
                value=default_name,
                key="crop_name_input",
                disabled=bool(action == "Rediģēt esošu" and selected_crop_name)
            )
            
            all_groups = sorted(set(crop.group for crop in crops_dict.values()))
            crop_group = st.selectbox(
                "Grupa",
                options=all_groups,
                index=all_groups.index(default_group) if default_group in all_groups else 0,
                key="crop_group_select"
            )
            
            sow_months = st.multiselect(
                "Sēšanas mēneši",
                options=list(range(1, 13)),
                default=default_sow_months,
                key="crop_sow_months_multiselect",
                format_func=lambda x: ["", "Janvāris", "Februāris", "Marts", "Aprīlis", "Maijs", "Jūnijs", 
                                      "Jūlijs", "Augusts", "Septembris", "Oktobris", "Novembris", "Decembris"][x]
            )
            
            cost_eur_ha = st.number_input(
                "Izmaksas (EUR/ha)",
                min_value=0.0,
                step=10.0,
                value=float(default_cost),
                key="crop_cost_input"
            )
            
            # Cena - ja grupa ir "Dārzeņi", pēc noklusējuma None
            if crop_group == "Dārzeņi":
                price_help = "Cena par tonnu (EUR/t). Dārzeņiem parasti nav vienotas tirgus cenas."
                # Ja rediģē esošu un cena nav None, rāda to, citādi 0
                if action == "Rediģēt esošu" and default_price is not None:
                    price_default_value = float(default_price)
                else:
                    price_default_value = 0.0
                price_value = st.number_input(
                    "Cena (EUR/t) (ievadi 0, ja nav cenas)",
                    min_value=0.0,
                    step=1.0,
                    value=price_default_value,
                    key="crop_price_input",
                    help=price_help
                )
                # Ja grupa ir "Dārzeņi" un cena ir 0, iestata uz None
                price_eur_t = None if price_value == 0 else price_value
            else:
                price_default = default_price if default_price is not None else 0.0
                price_help = "Cena par tonnu (EUR/t)"
                price_value = st.number_input(
                    "Cena (EUR/t)",
                    min_value=0.0,
                    step=1.0,
                    value=float(price_default) if price_default is not None else 0.0,
                    key="crop_price_input",
                    help=price_help
                )
                price_eur_t = price_value if price_value and price_value > 0 else None
            
            st.markdown("**Raža (t/ha) pēc augsnes veida:**")
            col1, col2 = st.columns(2)
            with col1:
                yield_smilts = st.number_input(
                    "Smilšaina",
                    min_value=0.0,
                    step=0.1,
                    value=float(default_yield_smilts),
                    key="yield_smilts_input"
                )
                yield_mals = st.number_input(
                    "Mālaina",
                    min_value=0.0,
                    step=0.1,
                    value=float(default_yield_mals),
                    key="yield_mals_input"
                )
            with col2:
                yield_kudra = st.number_input(
                    "Kūdraina",
                    min_value=0.0,
                    step=0.1,
                    value=float(default_yield_kudra),
                    key="yield_kudra_input"
                )
                yield_mitra = st.number_input(
                    "Mitra",
                    min_value=0.0,
                    step=0.1,
                    value=float(default_yield_mitra),
                    key="yield_mitra_input"
                )
            
            is_market_crop = st.checkbox(
                "Tirgus kultūra",
                value=default_is_market,
                key="crop_is_market_checkbox"
            )
            
            submit_button = st.form_submit_button("Saglabāt", use_container_width=True)
            
            if submit_button:
                if not crop_name or not crop_name.strip():
                    st.error("Nosaukums nevar būt tukšs!")
                else:
                    # Sagatavo yield_t_ha
                    yield_t_ha = {}
                    if yield_smilts > 0:
                        yield_t_ha[SoilType.SMILTS] = yield_smilts
                    if yield_mals > 0:
                        yield_t_ha[SoilType.MALS] = yield_mals
                    if yield_kudra > 0:
                        yield_t_ha[SoilType.KUDRA] = yield_kudra
                    if yield_mitra > 0:
                        yield_t_ha[SoilType.MITRA] = yield_mitra
                    
                    # Izveido CropModel
                    new_crop = CropModel(
                        name=crop_name.strip(),
                        group=crop_group,
                        sow_months=sow_months,
                        yield_t_ha=yield_t_ha,
                        cost_eur_ha=cost_eur_ha,
                        price_eur_t=price_eur_t,
                        is_market_crop=is_market_crop
                    )
                    
                    # Saglabā
                    from src.crop_manager import add_or_update_user_crop
                    if add_or_update_user_crop(new_crop):
                        st.success(f"Kultūra saglabāta: {crop_name}")
                        st.rerun()
                    else:
                        st.error("Neizdevās saglabāt kultūru.")
        
        # Dzēst kultūru
        st.divider()
        st.subheader("Dzēst kultūru")
        
        with st.form("delete_crop_form"):
            delete_crop_options = {crop_name: crop_name for crop_name, _ in filtered_crops}
            selected_crop_to_delete = st.selectbox(
                "Izvēlies kultūru",
                options=list(delete_crop_options.keys()),
                key="delete_crop_select"
            )
            
            confirm_delete = st.checkbox(
                f"Apstiprini dzēšanu: {selected_crop_to_delete}",
                key="confirm_delete_crop_checkbox"
            )
            
            delete_button = st.form_submit_button("Dzēst kultūru", use_container_width=True, disabled=not confirm_delete)
            
            if delete_button and confirm_delete:
                from src.crop_manager import delete_user_crop
                if delete_user_crop(selected_crop_to_delete):
                    st.success(f"Kultūra izdzēsta: {selected_crop_to_delete}")
                    st.rerun()
                else:
                    st.error("Neizdevās dzēst kultūru.")
    else:
        st.info("Nav kultūru, kas atbilst izvēlētajiem filtriem.")


def compute_reco():
    """Aprēķina ieteikumus un saglabā session_state."""
    # Iegūst parametrus no session_state
    field_id = st.session_state.get("reco_field_id")
    selected_field_label = st.session_state.get("recommend_field_select", "")
    use_capacity_limit = st.session_state.get("use_capacity_limit", False)
    max_area_per_crop = st.session_state.get("max_area_per_crop", {})
    target_year = st.session_state.get("target_year")
    planning_horizon = st.session_state.get("planning_horizon", "1 gads")
    crop_selection = st.session_state.get("recommend_crop_selection", "Visas kultūras")
    selected_group = st.session_state.get("recommend_crop_group", "Visas grupas")
    price_scenario = st.session_state.get("price_scenario_radio", "Bāzes")
    use_lookahead = st.session_state.get("use_lookahead_checkbox", False)
    include_crops_without_price = st.session_state.get("include_crops_without_price_checkbox", False)
    include_vegetables = st.session_state.get("include_vegetables_checkbox", False)
    enable_diversification = st.session_state.get("enable_diversification_checkbox", False)
    include_cover_crops = st.session_state.get("include_cover_crops_checkbox", False)
    
    # Iegūst favorītus
    storage = st.session_state.storage
    user_id = st.session_state["user"]
    favorites = storage.get_favorites(user_id)
    favorites_set = set(favorites) if favorites else set()
    
    # Nosaka filtrus
    crop_group_filter = None if selected_group == "Visas grupas" else selected_group
    favorite_crops_filter = None
    favorites_plus_group = False
    if crop_selection == "Tikai favorīti":
        if favorites_set:
            favorite_crops_filter = favorites_set
    elif crop_selection == "Favorīti + izvēlētā grupa":
        if crop_group_filter and favorites_set:
            favorite_crops_filter = favorites_set
            favorites_plus_group = True
    
    # Pārbauda, vai izvēlēts "Visi lauki" un ir ieslēgts kapacitātes ierobežojums
    is_all_fields = selected_field_label == "Visi lauki"
    
    # Izveido params_key
    params_key = (
        field_id,
        is_all_fields,
        use_capacity_limit,
        tuple(sorted(max_area_per_crop.items())) if max_area_per_crop else None,
        target_year,
        planning_horizon,
        crop_selection,
        crop_group_filter,
        tuple(sorted(favorites_set)) if favorites_set else None,
        include_vegetables,
        include_crops_without_price,
        price_scenario,
        use_lookahead,
        enable_diversification,
        include_cover_crops
    )
    
    # Pārbauda, vai ir izmaiņas
    if st.session_state.get("reco_params_key") == params_key:
        # Nav izmaiņu, neko nerēķina
        return
    
    # Saglabā jauno params_key
    st.session_state["reco_params_key"] = params_key
    
    # Ja izvēlēts "Visi lauki" un ir ieslēgts kapacitātes ierobežojums
    if is_all_fields and use_capacity_limit:
        # Iegūst visus laukus
        fields = storage.list_fields(user_id)
        if not fields:
            st.session_state["reco_result"] = None
            st.session_state["reco_error"] = "Nav lauku"
            return
        
        # Iegūst katalogu
        try:
            crops_dict = load_catalog()
        except Exception as e:
            st.session_state["reco_result"] = None
            st.session_state["reco_error"] = f"Kļūda ielādējot katalogu: {e}"
            return
        
        # Iegūst vēsturi visiem laukiem
        all_history = storage.list_plantings(user_id)
        histories_by_field = {}
        for field in fields:
            histories_by_field[field.id] = [p for p in all_history if p.field_id == field.id]
        
        # Izsauc recommend_for_all_fields_with_limits
        try:
            results = recommend_for_all_fields_with_limits(
                fields=fields,
                histories_by_field=histories_by_field,
                crops_dict=crops_dict,
                target_year=target_year,
                max_area_per_crop=max_area_per_crop,
                use_market_prices=True,
                favorite_crops_filter=favorite_crops_filter,
                crop_group_filter=crop_group_filter,
                favorites_plus_group=favorites_plus_group,
                include_crops_without_price=include_crops_without_price,
                include_vegetables=include_vegetables
            )
            
            # Saglabā rezultātu
            st.session_state["reco_result"] = {
                "type": "all_fields_with_limits",
                "data": results
            }
            st.session_state["reco_error"] = None
        except Exception as e:
            st.session_state["reco_result"] = None
            st.session_state["reco_error"] = f"Kļūda aprēķinot ieteikumus: {e}"
            import traceback
            print(f"Kļūda: {e}")
            print(traceback.format_exc())
        return
    
    # Pārbauda, vai ir lauks (vienam laukam)
    if not field_id:
        st.session_state["reco_result"] = None
        st.session_state["reco_error"] = None
        return
    
    # Iegūst lauku
    user_id = st.session_state["user"]
    fields = storage.list_fields(user_id)
    selected_field = None
    for f in fields:
        if f.id == field_id:
            selected_field = f
            break
    
    if not selected_field:
        st.session_state["reco_result"] = None
        st.session_state["reco_error"] = "Lauks nav atrasts"
        return
    
    # Iegūst katalogu
    try:
        crops_dict = load_catalog()
    except Exception as e:
        st.session_state["reco_result"] = None
        st.session_state["reco_error"] = f"Kļūda ielādējot katalogu: {e}"
        return
    
    # Iegūst vēsturi
    user_id = st.session_state["user"]
    all_history = storage.list_plantings(user_id)
    history = [p for p in all_history if p.field_id == selected_field.id]
    
    # Iegūst rent_eur_ha no lauka (default 0.0, ja nav uzstādīts)
    rent_eur_ha = getattr(selected_field, "rent_eur_ha", 0.0) or 0.0
    
    # Izveido pagaidu crops_dict ar koriģētām cenām pēc scenārija
    working_crops_dict = crops_dict
    if price_scenario != "Bāzes":
        adjusted_crops_dict = {}
        for name, crop in crops_dict.items():
            price_change_pct = get_price_change_for_scenario(price_scenario, crop.group)
            price_multiplier = 1 + (price_change_pct / 100)
            new_price = crop.price_eur_t * price_multiplier if crop.price_eur_t is not None else None
            adjusted_crop = CropModel(
                name=crop.name,
                group=crop.group,
                sow_months=crop.sow_months,
                yield_t_ha=crop.yield_t_ha,
                cost_eur_ha=crop.cost_eur_ha,
                price_eur_t=new_price,
                is_market_crop=crop.is_market_crop,
                ph_range=crop.ph_range
            )
            adjusted_crops_dict[name] = adjusted_crop
        working_crops_dict = adjusted_crops_dict
    
    # Aprēķina ieteikumus
    try:
        if planning_horizon == "3 gadi":
            # 3 gadu plānošana
            if use_lookahead:
                plan_result = plan_for_years_lookahead(
                    field=selected_field,
                    history=history,
                    crops_dict=working_crops_dict,
                    start_year=target_year,
                    years=3,
                    candidates=3,
                    preferred_crops=None,
                    favorite_crops_filter=favorite_crops_filter,
                    crop_group_filter=crop_group_filter,
                    favorites_plus_group=(crop_selection == "Favorīti + izvēlētā grupa"),
                    include_crops_without_price=include_crops_without_price,
                    include_vegetables=include_vegetables,
                    allowed_groups=None
                )
                st.session_state["reco_result"] = {
                    "type": "plan_3y_lookahead",
                    "data": plan_result
                }
            else:
                plan_result = plan_for_years(
                    field=selected_field,
                    history=history,
                    crops_dict=working_crops_dict,
                    start_year=target_year,
                    years=3,
                    preferred_crops=None,
                    favorite_crops_filter=favorite_crops_filter,
                    crop_group_filter=crop_group_filter,
                    favorites_plus_group=(crop_selection == "Favorīti + izvēlētā grupa"),
                    include_crops_without_price=include_crops_without_price,
                    include_vegetables=include_vegetables,
                    allowed_groups=None
                )
                st.session_state["reco_result"] = {
                    "type": "plan_3y",
                    "data": plan_result
                }
        else:
            # 1 gada plānošana
            # Aprēķina ar bāzes cenām (salīdzināšanai)
            base_scenario_result = recommend_with_scenarios(
                field=selected_field,
                history=history,
                crops_dict=crops_dict,
                target_year=target_year,
                preferred_crops=None,
                favorite_crops_filter=favorite_crops_filter,
                crop_group_filter=crop_group_filter,
                favorites_plus_group=(crop_selection == "Favorīti + izvēlētā grupa"),
                include_crops_without_price=include_crops_without_price,
                include_vegetables=include_vegetables,
                allowed_groups=None,
                debug=False
            )
            
            # Aprēķina ar koriģētām cenām
            scenario_result = recommend_with_scenarios(
                field=selected_field,
                history=history,
                crops_dict=working_crops_dict,
                target_year=target_year,
                preferred_crops=None,
                favorite_crops_filter=favorite_crops_filter,
                crop_group_filter=crop_group_filter,
                favorites_plus_group=(crop_selection == "Favorīti + izvēlētā grupa"),
                include_crops_without_price=include_crops_without_price,
                include_vegetables=include_vegetables,
                allowed_groups=None,
                debug=False
            )
            base_result = scenario_result['scenario_results'].get('base')
            
            # Diversifikācijas loģika (vienkāršota versija)
            if enable_diversification and base_result and base_result.get('best_crop'):
                user_id = st.session_state["user"]
                all_fields = storage.list_fields(user_id)
                used_crops = {}
                
                for other_field in all_fields:
                    if other_field.id == selected_field.id:
                        continue
                    
                    other_history = [p for p in history if p.field_id == other_field.id]
                    try:
                        other_scenario_result = recommend_with_scenarios(
                            field=other_field,
                            history=history,
                            crops_dict=crops_dict,
                            target_year=target_year,
                            preferred_crops=None,
                            favorite_crops_filter=favorite_crops_filter,
                            crop_group_filter=crop_group_filter,
                            favorites_plus_group=(crop_selection == "Favorīti + izvēlētā grupa"),
                            include_crops_without_price=include_crops_without_price,
                            include_vegetables=include_vegetables,
                            allowed_groups=None,
                            debug=False
                        )
                        other_base_result = other_scenario_result['scenario_results'].get('base')
                        if other_base_result and other_base_result.get('best_crop'):
                            used_crops[other_field.id] = other_base_result['best_crop']
                    except Exception:
                        pass
                
                best_crop = base_result['best_crop']
                if best_crop in used_crops.values():
                    best_profit_total = base_result.get('profit_total', base_result.get('best_profit', 0.0))
                    min_profit_threshold = best_profit_total * 0.95
                    
                    top3 = base_result.get('top3', [])
                    debug_info = base_result.get('debug_info', {})
                    scored = debug_info.get('scored', [])
                    
                    all_candidates = []
                    seen_crops = set()
                    
                    for item in top3:
                        crop_name = item['name']
                        if crop_name not in seen_crops:
                            all_candidates.append({
                                'name': crop_name,
                                'profit_total': item.get('profit_total', item.get('profit', 0.0))
                            })
                            seen_crops.add(crop_name)
                    
                    for item in scored:
                        crop_name = item['crop']
                        if crop_name not in seen_crops:
                            all_candidates.append({
                                'name': crop_name,
                                'profit_total': item.get('profit_total', 0.0)
                            })
                            seen_crops.add(crop_name)
                    
                    all_candidates.sort(key=lambda x: x['profit_total'], reverse=True)
                    
                    alternative_crop = None
                    for candidate in all_candidates:
                        candidate_name = candidate['name']
                        candidate_profit = candidate['profit_total']
                        
                        if candidate_name not in used_crops.values():
                            if candidate_profit >= min_profit_threshold:
                                alternative_crop = candidate_name
                                break
                    
                    if alternative_crop and alternative_crop != best_crop:
                        for item in top3:
                            if item['name'] == alternative_crop:
                                base_result['best_crop'] = alternative_crop
                                base_result['profit_total'] = item.get('profit_total', item.get('profit', 0.0))
                                base_result['best_profit'] = item.get('profit_total', item.get('profit', 0.0))
                                base_result['profit_per_ha'] = item.get('profit_per_ha', 0.0)
                                base_result['revenue_total'] = item.get('revenue_total', 0.0)
                                base_result['revenue_per_ha'] = item.get('revenue_per_ha', 0.0)
                                base_result['cost_total'] = item.get('cost_total', 0.0)
                                base_result['cost_per_ha'] = item.get('cost_per_ha', 0.0)
                                base_result['sow_months'] = crops_dict[alternative_crop].sow_months if alternative_crop in crops_dict else []
                                base_result['risk_level'] = item.get('risk_level', 'nezināms')
                                base_result['volatility_pct'] = item.get('volatility_pct')
                                base_result['is_market_crop'] = getattr(crops_dict[alternative_crop], 'is_market_crop', True) if alternative_crop in crops_dict else True
                                base_result['diversification_applied'] = True
                                base_result['original_crop'] = best_crop
                                break
            
            st.session_state["reco_result"] = {
                "type": "recommendation_1y",
                "data": {
                    "base_result": base_result,
                    "scenario_result": scenario_result,
                    "base_scenario_result": base_scenario_result
                }
            }
        
        st.session_state["reco_error"] = None
        
        # Atjauno recommendations un indeksu
        if st.session_state["reco_result"]["type"] == "recommendation_1y":
            base_result = st.session_state["reco_result"]["data"]["base_result"]
            candidates = base_result.get('candidates', []) if base_result else []
            st.session_state.recommendations = candidates
            st.session_state.current_recommendation_index = 0
        else:
            st.session_state.recommendations = []
            st.session_state.current_recommendation_index = 0
            
    except Exception as e:
        st.session_state["reco_result"] = None
        st.session_state["reco_error"] = f"Kļūda aprēķinot ieteikumus: {e}"


def show_recommendations_section():
    """Sadaļa: Ieteikumi."""
    st.title("Ieteikumi")
    
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta")
        return
    
    storage = st.session_state.storage
    
    # Iegūst laukus
    user_id = st.session_state["user"]
    fields = storage.list_fields(user_id)
    
    if not fields:
        st.warning("Vispirms pievienojiet laukus sadaļā 'Lauki'.")
        return
    
    # Ielādē kultūru katalogu
    try:
        crops_dict = load_catalog()
        # Saglabā last_price_update session_state
        st.session_state.last_price_update = get_last_price_update()
    except FileNotFoundError:
        st.error("Nav atrasts crops.json fails!")
        return
    except Exception as e:
        st.error(f"Kļūda ielādējot katalogu: {e}")
        return
    
    # Inicializē session state
    if "reco_result" not in st.session_state:
        st.session_state["reco_result"] = None
    if "reco_error" not in st.session_state:
        st.session_state["reco_error"] = None
    if "reco_params_key" not in st.session_state:
        st.session_state["reco_params_key"] = None
    if 'recommendations' not in st.session_state:
        st.session_state.recommendations = []
    if 'current_recommendation_index' not in st.session_state:
        st.session_state.current_recommendation_index = 0
    
    # Lauka un gada izvēle
    col1, col2 = st.columns(2)
    
    with col1:
        field_options = {"Visi lauki": None}
        field_options.update({f"{f.id} - {f.name}": f for f in fields})
        selected_field_label = st.selectbox(
            "Izvēlieties lauku",
            options=list(field_options.keys()),
            key="recommend_field_select",
            on_change=compute_reco
        )
        # Saglabā field_id session_state
        if selected_field_label and selected_field_label != "Visi lauki":
            selected_field = field_options[selected_field_label]
            st.session_state["reco_field_id"] = selected_field.id
        else:
            st.session_state["reco_field_id"] = None
    
    with col2:
        current_year = datetime.now().year
        target_year = st.number_input(
            "Plānotais gads",
            min_value=current_year,
            max_value=current_year + 10,
            value=current_year + 1,
            key="target_year",
            on_change=compute_reco
        )
    
    # Plānošanas horizonta izvēle
    planning_horizon = st.radio(
        "Plānošanas horizonts",
        ["1 gads", "3 gadi"],
        horizontal=True,
        key="planning_horizon",
        on_change=compute_reco
    )
    
    # Kultūru grupas un atlases kontroles
    st.divider()
    st.markdown("### Filtrēšana")
    
    # Iegūst visas grupas no kataloga
    all_groups = sorted(set(crop.group for crop in crops_dict.values()))
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Kultūru grupas dropdown
        selected_group = st.selectbox(
            "Kultūru grupa",
            options=["Visas grupas"] + all_groups,
            key="recommend_crop_group",
            on_change=compute_reco
        )
    
    with col2:
        # Kultūru atlases radio
        crop_selection = st.radio(
            "Kultūru atlase",
            ["Visas kultūras", "Tikai favorīti", "Favorīti + izvēlētā grupa"],
            key="recommend_crop_selection",
            on_change=compute_reco
        )
    
    # Iegūst favorītus
    user_id = st.session_state["user"]
    favorites = storage.get_favorites(user_id)
    favorites_set = set(favorites) if favorites else set()
    
    # Darba kapacitātes ierobežojums (tikai, ja izvēlēts "Visi lauki")
    use_capacity_limit = False
    max_area_per_crop = {}
    
    if selected_field_label == "Visi lauki":
        st.divider()
        use_capacity_limit = st.checkbox(
            "Ierobežot platību vienai kultūrai",
            key="use_capacity_limit",
            help="Ja ieslēgts, sistēma sadala kultūras pa laukiem, lai nepārsniegtu izvēlēto maksimālo platību vienai kultūrai."
        )
        
        if use_capacity_limit:
            st.caption("Ja jauda ir ierobežota, sistēma sadala kultūras pa laukiem, lai nepārsniegtu izvēlēto maksimālo platību vienai kultūrai.")
            
            # Iegūst visas kultūras no kataloga
            all_crop_names = sorted(crops_dict.keys())
            
            # Noklusējuma vērtības
            default_limits = {
                "Kukurūza": 20.0,
                "Rapsis (vasaras)": 25.0,
                "Rapsis (ziemas)": 25.0,
                "Kartupeļi": 5.0,
                "Graudaugi": 999.0  # Vispārējs limits graudaugiem
            }
            
            # Inicializē session state ar noklusējuma vērtībām
            if "max_area_per_crop" not in st.session_state:
                st.session_state.max_area_per_crop = {}
                for crop_name in all_crop_names:
                    crop = crops_dict[crop_name]
                    # Meklē noklusējuma vērtību
                    if crop_name in default_limits:
                        st.session_state.max_area_per_crop[crop_name] = default_limits[crop_name]
                    elif crop.group == "Graudaugi":
                        st.session_state.max_area_per_crop[crop_name] = default_limits.get("Graudaugi", 999.0)
                    else:
                        st.session_state.max_area_per_crop[crop_name] = 999.0
            
            # Tabula ar max ha katrai kultūrai
            st.markdown("#### Maksimālā platība (ha) katrai kultūrai")
            
            # Grupē pēc kultūru grupām
            crops_by_group = {}
            for crop_name in all_crop_names:
                crop = crops_dict[crop_name]
                group = crop.group
                if group not in crops_by_group:
                    crops_by_group[group] = []
                crops_by_group[group].append(crop_name)
            
            # Parāda tabulu ar rediģējamiem laukiem
            for group in sorted(crops_by_group.keys()):
                st.markdown(f"**{group}**")
                group_crops = sorted(crops_by_group[group])
                
                # Izveido kolonnas (3 kolonnas)
                num_cols = 3
                for i in range(0, len(group_crops), num_cols):
                    cols = st.columns(num_cols)
                    for j, crop_name in enumerate(group_crops[i:i+num_cols]):
                        with cols[j]:
                            current_value = st.session_state.max_area_per_crop.get(crop_name, 999.0)
                            new_value = st.number_input(
                                crop_name,
                                min_value=0.0,
                                step=1.0,
                                value=float(current_value),
                                key=f"max_area_{crop_name}",
                                label_visibility="visible"
                            )
                            st.session_state.max_area_per_crop[crop_name] = new_value
            
            max_area_per_crop = st.session_state.max_area_per_crop.copy()
    
    # Nosaka filtrus
    crop_group_filter = None if selected_group == "Visas grupas" else selected_group
    favorite_crops_filter = None
    filter_info = []
    
    if crop_selection == "Tikai favorīti":
        if favorites_set:
            favorite_crops_filter = favorites_set
            filter_info.append("Atlase: tikai favorīti")
            if crop_group_filter:
                filter_info.append(f"Filtrs: {crop_group_filter}")
        else:
            st.warning("Nav izvēlētu favorītu. Dodieties uz 'Kultūru katalogs', lai pievienotu favorītus.")
            if crop_group_filter:
                filter_info.append(f"Filtrs: {crop_group_filter}")
    elif crop_selection == "Favorīti + izvēlētā grupa":
        if crop_group_filter:
            if favorites_set:
                favorite_crops_filter = favorites_set
                filter_info.append(f"Filtrs: {crop_group_filter}")
                filter_info.append("Atlase: favorīti + izvēlētā grupa")
            else:
                st.warning("Nav izvēlētu favorītu. Izmantos tikai izvēlēto grupu.")
                filter_info.append(f"Filtrs: {crop_group_filter}")
        else:
            st.warning("Izvēlieties grupu, lai izmantotu 'Favorīti + izvēlētā grupa'.")
            if favorites_set:
                favorite_crops_filter = favorites_set
                filter_info.append("Atlase: tikai favorīti")
    else:
        # "Visas kultūras"
        if crop_group_filter:
            filter_info.append(f"Filtrs: {crop_group_filter}")
    
    # Papildu iestatījumi
    price_scenario = "Bāzes"
    use_lookahead = False
    with st.expander("Papildu iestatījumi"):
        price_scenario = st.radio(
            "Scenārijs",
            ["Pesimistisks", "Bāzes", "Optimistisks"],
            index=1,  # Noklusējuma: Bāzes
            horizontal=True,
            key="price_scenario_radio",
            help="Scenārijs tiek piemērots automātiski pēc kultūras grupas",
            on_change=compute_reco
        )
        
        use_lookahead = st.checkbox(
            "Optimizēt kopējo peļņu vairākiem gadiem",
            key="use_lookahead_checkbox",
            on_change=compute_reco
        )
        
        include_crops_without_price = st.checkbox(
            "Iekļaut kultūras bez tirgus cenas",
            key="include_crops_without_price_checkbox",
            help="Iekļauj kultūras ar manuāli ievadītām cenām vai bez cenas",
            on_change=compute_reco
        )
        
        include_vegetables = st.checkbox(
            "Iekļaut dārzeņus",
            key="include_vegetables_checkbox",
            value=False,
            help="Iekļauj dārzeņus ieteikumos (pēc noklusējuma nav iekļauti)",
            on_change=compute_reco
        )
        
        enable_diversification = st.checkbox(
            "Diversifikācija",
            key="enable_diversification_checkbox",
            value=False,
            help="Ja ieslēgta, izvairās no tās pašas kultūras izvēles vairākiem laukiem tajā pašā gadā",
            on_change=compute_reco
        )
        
        include_cover_crops = st.checkbox(
            "Iekļaut starpkultūras",
            key="include_cover_crops_checkbox",
            value=False,
            help="Parāda starpkultūras ieteikumus pēc galvenās kultūras izvēles",
            on_change=compute_reco
        )

    # Cenu avota informācija tiks parādīta pie rezultātiem
    
    # Parāda info tekstu par cenām un validāciju
    st.info("Cenas tiek ņemtas no CSP (vidējās gada cenas). Ja cena ir ārpus saprātīga tirgus diapazona, kultūra netiek izmantota ieteikumos.")
    
    # Parāda info tekstu, ja dārzeņi ir izslēgti
    if not include_vegetables:
        st.info("Dārzeņi ir izslēgti no ieteikumiem. Lai tos iekļautu, atzīmē 'Iekļaut dārzeņus'.")
    
    if selected_field_label:
        # Ja nav "Visi lauki", saglabā field_id
        if selected_field_label != "Visi lauki":
            selected_field = field_options[selected_field_label]
            
            # Saglabā field_id session_state (ja vēl nav)
            if st.session_state.get("reco_field_id") != selected_field.id:
                st.session_state["reco_field_id"] = selected_field.id
        else:
            # "Visi lauki" - noņem field_id
            st.session_state["reco_field_id"] = None
        
        # Izsauc automātisko aprēķinu
        compute_reco()
        
        # Maza sekundāra poga "Pārrēķināt" (optional)
        col_refresh, _ = st.columns([1, 5])
        with col_refresh:
            if st.button("Pārrēķināt", key="recalculate_reco_btn", use_container_width=True):
                st.session_state["reco_params_key"] = None
                compute_reco()
                st.rerun()
        
        # Parāda kļūdu, ja ir
        if st.session_state.get("reco_error"):
            st.error(st.session_state["reco_error"])
        
        # Parāda rezultātu no session_state
        reco_result = st.session_state.get("reco_result")
        if reco_result:
            # Iegūst datus no session_state
            reco_type = reco_result.get("type")
            reco_data = reco_result.get("data")
            
            # "Visi lauki" ar kapacitātes ierobežojumu
            if reco_type == "all_fields_with_limits":
                st.success("Ieteikumi visiem laukiem ar kapacitātes ierobežojumu")
                
                # Sagatavo tabulu ar rezultātiem
                results_data = []
                total_profit = 0.0
                for result in reco_data:
                    field_name = result["field_name"]
                    chosen_crop = result["chosen_crop"] or "—"
                    profit = result["profit"]
                    profit_per_ha = result["profit_per_ha"]
                    warnings = result.get("warnings", [])
                    
                    results_data.append({
                        "Lauks": field_name,
                        "Kultūra": chosen_crop,
                        "Peļņa (EUR)": f"{profit:,.2f}",
                        "Peļņa (EUR/ha)": f"{profit_per_ha:,.2f}",
                        "Brīdinājumi": "; ".join(warnings) if warnings else "—"
                    })
                    total_profit += profit
                
                # Parāda tabulu
                df_results = pd.DataFrame(results_data)
                st.dataframe(df_results, use_container_width=True, hide_index=True)
                
                # Parāda kopējo peļņu
                st.metric("Kopējā peļņa", f"{total_profit:,.2f} EUR")
                
                # Parāda brīdinājumus, ja ir
                all_warnings = []
                for result in reco_data:
                    all_warnings.extend(result.get("warnings", []))
                if all_warnings:
                    st.warning("Dažas kultūras pārsniedz maksimālo platību. Lūdzu, pārskatiet brīdinājumus.")
            
            elif reco_type == "plan_3y" or reco_type == "plan_3y_lookahead":
                # 3 gadu plānošana
                plan_result = reco_data
                # Parāda rezultātus (tā pati loģika kā iepriekš)
                if reco_type == "plan_3y_lookahead":
                    st.success(f"3 gadu plāns laukam '{plan_result['field_name']}'")
                    st.info("Plāns veidots ar look-ahead metodi")
                    
                    evaluated_candidates = plan_result.get('evaluated_candidates', [])
                    if evaluated_candidates:
                        st.subheader("Izvērtētie kandidāti")
                        candidates_data = []
                        for candidate in evaluated_candidates:
                            candidates_data.append({
                                "Kandidāts": candidate['crop'],
                                "Kopējā peļņa (3 gadi)": f"{candidate['total_profit']:.2f} EUR"
                            })
                        st.dataframe(candidates_data, use_container_width=True, hide_index=True)
                        st.divider()
                else:
                    st.success(f"3 gadu plāns laukam '{plan_result['field_name']}'")
                
                # Sagatavo tabulu
                plan_data = []
                total_revenue = 0.0
                total_costs = 0.0
                total_profit = 0.0
                
                for entry in plan_result['plan']:
                    crop_display = entry['crop'] if entry['crop'] else "—"
                    sow_months_display = month_names(entry['sow_months']) if entry['sow_months'] else "—"
                    explanation = entry.get('explanation', '')
                    
                    if entry.get('crop'):
                        crop_name = entry['crop']
                        if crop_name in crops_dict:
                            from src.calc import calculate_profit
                            crop_obj = crops_dict[crop_name]
                            prices_csv = load_prices_csv()
                            price_info = get_price_for_crop(crop_obj, prices_csv)
                            price_value, _source_label, _confidence = price_info
                            
                            crop_with_price = CropModel(
                                name=crop_obj.name,
                                group=crop_obj.group,
                                sow_months=crop_obj.sow_months,
                                yield_t_ha=crop_obj.yield_t_ha,
                                cost_eur_ha=crop_obj.cost_eur_ha,
                                price_eur_t=price_value,
                                is_market_crop=crop_obj.is_market_crop
                            )
                            
                            # Izmanto rent_eur_ha no lauka
                            field_rent = getattr(selected_field, "rent_eur_ha", 0.0) or 0.0
                            calc_result = calculate_profit(selected_field, crop_with_price, rent_eur_ha=field_rent)
                            revenue_total = calc_result.revenue_total
                            cost_total = calc_result.cost_total
                            profit_total = calc_result.profit_total
                        else:
                            revenue_total = entry.get('revenue_total', 0.0)
                            cost_total = entry.get('cost_total', 0.0)
                            profit_total = entry.get('profit_total', entry.get('profit', 0.0))
                    else:
                        revenue_total = 0.0
                        cost_total = 0.0
                        profit_total = 0.0
                    
                    total_revenue += revenue_total
                    total_costs += cost_total
                    total_profit += profit_total
                    
                    plan_data.append({
                        "Gads": entry['year'],
                        "Kultūra": crop_display,
                        "Ieņēmumi (EUR)": f"{revenue_total:.2f}" if revenue_total > 0 else "—",
                        "Izdevumi (EUR)": f"{cost_total:.2f}" if cost_total > 0 else "—",
                        "Peļņa (EUR)": f"{profit_total:.2f}" if profit_total > 0 else "—",
                        "Peļņa (EUR/ha)": f"{entry['profit_per_ha']:.2f}" if entry.get('profit_per_ha', 0) > 0 else "—",
                        "Sēšanas mēneši": sow_months_display,
                        "Piezīme": explanation
                    })
                
                st.dataframe(plan_data, use_container_width=True, hide_index=True)
                
                st.divider()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Kopējie ieņēmumi (3 gadi)", f"{total_revenue:.2f} EUR")
                with col2:
                    st.metric("Kopējie izdevumi (3 gadi)", f"{total_costs:.2f} EUR")
                with col3:
                    st.metric("Kopējā peļņa (3 gadi)", f"{total_profit:.2f} EUR")
                
                st.divider()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Vidējā peļņa (uz ha)", f"{plan_result['avg_profit_per_ha']:.2f} EUR/ha")
                with col2:
                    st.metric("Kopējā peļņa (3 gadi)", f"{plan_result['total_profit']:.2f} EUR")
                
                st.divider()
                
                with st.expander("Sistēmas skaidrojums (3 gadi)"):
                    crop_group = "Kultūras"
                    if plan_result['plan'] and plan_result['plan'][0].get('crop'):
                        first_crop_name = plan_result['plan'][0]['crop']
                        if first_crop_name in crops_dict:
                            crop_group = crops_dict[first_crop_name].group
                    
                    price_scenario_value = st.session_state.get("price_scenario_radio", "Bāzes")
                    st.write(f"**Cenu scenārijs:** {price_scenario_value}")
                    st.write(f"**Balstīts uz {crop_group} cenu svārstībām Latvijā**")
                    st.write("**Peļņa aprēķināta 3 gadu griezumā**")
                
                # Iegūst price_change
                price_change = 0
                if price_scenario_value != "Bāzes":
                    try:
                        crops_dict_temp = load_catalog()
                        if crops_dict_temp:
                            first_crop = list(crops_dict_temp.values())[0]
                            price_change = get_price_change_for_scenario(price_scenario_value, first_crop.group)
                    except Exception:
                        pass
                
                report_text = generate_report_text(
                    field=selected_field,
                    planning_horizon="3 gadi",
                    target_year=target_year,
                    price_change=price_change,
                    result_data=plan_result
                )
                st.download_button(
                    "Lejupielādēt atskaiti",
                    data=report_text,
                    file_name=f"atskaite_{safe_filename(selected_field.name)}_{target_year}_3gadi.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            elif reco_type == "recommendation_1y":
                # 1 gada plānošana
                base_result = reco_data.get("base_result")
                scenario_result = reco_data.get("scenario_result")
                base_scenario_result = reco_data.get("base_scenario_result")
                
                # Iegūst price_change no scenārija
                price_change = 0
                if price_scenario != "Bāzes":
                    try:
                        crops_dict_temp = load_catalog()
                        if crops_dict_temp:
                            first_crop = list(crops_dict_temp.values())[0]
                            price_change = get_price_change_for_scenario(price_scenario, first_crop.group)
                    except Exception:
                        pass
                
                # Salīdzina ieteikumus
                if price_change != 0:
                    base_result_original = scenario_result.get('scenario_results', {}).get('base') if scenario_result else None
                    original_crop = base_result_original.get('best_crop') if base_result_original else None
                    adjusted_crop = base_result.get('best_crop') if base_result else None
                    
                    if original_crop != adjusted_crop:
                        st.warning(
                            f"Ieteikums mainījās! "
                            f"Ar {price_change:+.0f}% cenu izmaiņu ieteikums "
                            f"ir **{adjusted_crop or 'nav kultūras'}** "
                            f"(iepriekš bija **{original_crop or 'nav kultūras'}**)."
                        )
                
                # Parāda filtra informāciju (ja ir)
                if filter_info:
                    st.caption(" | ".join(filter_info))
                
                # Parāda diversifikācijas ziņojumu
                if base_result and base_result.get('diversification_applied'):
                    original_crop = base_result.get('original_crop')
                    current_crop = base_result.get('best_crop')
                    st.info(
                        f"Diversifikācija: izvēlēta **{current_crop}** "
                        f"(oriģinālais ieteikums bija **{original_crop}**, bet tas jau ir izvēlēts citam laukam)."
                    )
                
                if not base_result or base_result['best_crop'] is None:
                    # Nav atļautu kultūru - ERROR (sarkans)
                    user_id = st.session_state["user"]
                    all_history = storage.list_plantings(user_id)
                    history = [p for p in all_history if p.field_id == selected_field.id]
                    if not history:
                        st.error("Nav sējumu vēstures šim laukam. Pievienojiet vēsturi, lai iegūtu ieteikumus.")
                    elif base_result and base_result.get('favorites_filter_message'):
                        st.error(base_result['favorites_filter_message'])
                    else:
                        st.error(f"Nav atļautu kultūru: {base_result.get('explanation', 'Nav pieejamu kultūru') if base_result else 'Nav pieejamu kultūru'}")
                else:
                    # ========== B) MAIN RECOMMENDATION CARD ==========
                    # Izmanto saglabātos ieteikumus vai base_result
                    if st.session_state.recommendations:
                        candidates = st.session_state.recommendations
                    else:
                        candidates = base_result.get('candidates', []) if base_result else []
                        st.session_state.recommendations = candidates
                    
                    # Pārbauda, vai indekss ir derīgs
                    if st.session_state.current_recommendation_index >= len(candidates):
                        st.session_state.current_recommendation_index = 0
                    
                    # Iegūst izvēlēto kandidātu
                    selected_candidate = candidates[st.session_state.current_recommendation_index] if candidates else None
                    
                    if not selected_candidate:
                        st.error("Nav pieejamu kandidātu.")
                    else:
                        # Iegūst datus no izvēlētā kandidāta
                        best_crop_name = selected_candidate['name']
                        best_crop_obj = crops_dict.get(best_crop_name)
                        
                        # Iegūst datus no kandidāta
                        revenue_total = selected_candidate.get('revenue_total', 0.0)
                        revenue_per_ha = selected_candidate.get('revenue_per_ha', 0.0)
                        cost_total = selected_candidate.get('cost_total', 0.0)
                        cost_per_ha = selected_candidate.get('cost_per_ha', 0.0)
                        profit_total = selected_candidate.get('profit_total', 0.0)
                        profit_per_ha = selected_candidate.get('profit_per_ha', 0.0)
                        sow_months = selected_candidate.get('sow_months', [])
                        sow_months_str = month_names(sow_months)
                        is_market_crop = selected_candidate.get('is_market_crop', True)
                        
                        # Navigācijas pogas
                        if len(candidates) > 1:
                            col_prev, col_reset, col_next, col_info = st.columns([1, 1, 1, 2])
                            
                            with col_prev:
                                if st.button("Iepriekšējais", disabled=(st.session_state.current_recommendation_index == 0), use_container_width=True, key="prev_reco_btn"):
                                    st.session_state.current_recommendation_index = max(0, st.session_state.current_recommendation_index - 1)
                                    st.rerun()
                            
                            with col_reset:
                                if st.button("Atiestatīt uz labāko", disabled=(st.session_state.current_recommendation_index == 0), use_container_width=True, key="reset_reco_btn"):
                                    st.session_state.current_recommendation_index = 0
                                    st.rerun()
                            
                            with col_next:
                                if st.button("Nākamais", disabled=(st.session_state.current_recommendation_index >= len(candidates) - 1), use_container_width=True, key="next_reco_btn"):
                                    st.session_state.current_recommendation_index = min(len(candidates) - 1, st.session_state.current_recommendation_index + 1)
                                    st.rerun()
                            
                            with col_info:
                                st.caption(f"Ieteikums {st.session_state.current_recommendation_index + 1} no {len(candidates)} (sakārtots pēc peļņas)")
                        
                        # Pārrēķina ar rent_eur_ha no lauka (ja nepieciešams)
                        if best_crop_obj:
                            from src.calc import calculate_profit
                            prices_csv = load_prices_csv()
                            price_info = get_price_for_crop(best_crop_obj, prices_csv)
                            price_value, _source_label, _confidence = price_info
                            
                            crop_with_price = CropModel(
                                name=best_crop_obj.name,
                                group=best_crop_obj.group,
                                sow_months=best_crop_obj.sow_months,
                                yield_t_ha=best_crop_obj.yield_t_ha,
                                cost_eur_ha=best_crop_obj.cost_eur_ha,
                                price_eur_t=price_value,
                                is_market_crop=best_crop_obj.is_market_crop,
                                ph_range=best_crop_obj.ph_range
                            )
                            
                            # Izmanto rent_eur_ha no lauka
                            field_rent = getattr(selected_field, "rent_eur_ha", 0.0) or 0.0
                            calc_result = calculate_profit(selected_field, crop_with_price, rent_eur_ha=field_rent)
                            if calc_result:
                                revenue_total = calc_result.revenue_total
                                revenue_per_ha = calc_result.revenue_per_ha
                                cost_total = calc_result.cost_total
                                cost_per_ha = calc_result.cost_per_ha
                                profit_total = calc_result.profit_total
                                profit_per_ha = calc_result.profit_per_ha
                        
                        # Iegūst profit_breakdown tikai detaļām
                        profit_breakdown = None
                        if best_crop_obj:
                            prices_csv = load_prices_csv()
                            price_info = get_price_for_crop(best_crop_obj, prices_csv)
                            profit_breakdown = profit_eur_detailed(selected_field, best_crop_obj, price_info)
                        
                        # Main recommendation card
                        st.markdown("---")
                        st.markdown("### Ieteikums")
                        
                        # Crop name
                        crop_display = best_crop_name
                        
                        if not is_market_crop:
                            st.markdown(f"#### {crop_display}")
                            st.caption("Agrovides / zālāju kultūra")
                        else:
                            st.markdown(f"#### {crop_display}")
                        
                        # Show label if recommendation is based on favorites
                        if base_result.get('used_favorites_filter'):
                            st.caption("Balstīts uz favorītajām kultūrām")
                        
                        # Key metrics in 3 columns
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric(
                                "Ieņēmumi (kopā)", 
                                f"{revenue_total:.2f} EUR",
                                help=f"Kopējie ieņēmumi laukam '{selected_field.name}' ({selected_field.area_ha} ha) gadā {target_year}"
                            )
                            st.metric(
                                "Ieņēmumi (uz ha)", 
                                f"{revenue_per_ha:.2f} EUR/ha",
                                help=f"Ieņēmumi uz 1 hektāru kultūrai '{best_crop_name}' gadā {target_year}"
                            )
                        with col2:
                            st.metric(
                                "Izmaksas (kopā)", 
                                f"{cost_total:.2f} EUR",
                                help=f"Kopējās izmaksas laukam '{selected_field.name}' ({selected_field.area_ha} ha) gadā {target_year}"
                            )
                            st.metric(
                                "Izmaksas (uz ha)", 
                                f"{cost_per_ha:.2f} EUR/ha",
                                help=f"Izmaksas uz 1 hektāru kultūrai '{best_crop_name}' gadā {target_year}"
                            )
                        with col3:
                            st.metric(
                                "Peļņa (kopā)", 
                                f"{profit_total:.2f} EUR",
                                help=f"Kopējā peļņa laukam '{selected_field.name}' ({selected_field.area_ha} ha) gadā {target_year}"
                            )
                            st.metric(
                                "Peļņa (uz ha)", 
                                f"{profit_per_ha:.2f} EUR/ha",
                                help=f"Prognozētā peļņa uz 1 hektāru kultūrai '{best_crop_name}' gadā {target_year}"
                            )
                        
                        # Sēšanas mēneši atsevišķi zem metrikām
                        st.markdown(f"**Sēšanas mēneši:** {sow_months_str}")
                        
                        # Price source (human readable)
                        if is_market_crop:
                            price_source_text = _get_price_source_text(best_crop_name, crops_dict)
                            if price_source_text:
                                st.caption(price_source_text)
                        else:
                            st.caption("Izvēle balstīta uz augmaiņu un augsnes uzlabošanu, nevis tirgus cenu")
                        
                        # Parāda brīdinājumus, ja ir
                        if selected_candidate.get('warnings'):
                            st.warning(selected_candidate['warnings'])
                        
                        # Favorite info (subtle, not warning)
                        if base_result.get('used_preference'):
                            st.info("Izvēlēts no favorītajām kultūrām")
                            if base_result.get('preference_note'):
                                st.caption(base_result['preference_note'])
                        elif base_result.get('preference_note'):
                            st.caption(base_result['preference_note'])
                        
                        # Starpkultūras ieteikums
                        if include_cover_crops:
                            recommended_cover_crop = base_result.get('recommended_cover_crop')
                            if recommended_cover_crop:
                                st.markdown("---")
                                st.markdown("### Starpkultūras ieteikums")
                                
                                cover_crop_name = recommended_cover_crop.get('name', '')
                                cover_cost_eur_ha = recommended_cover_crop.get('cost_eur_ha', 0.0)
                                cover_benefits = recommended_cover_crop.get('benefits', [])
                                cover_sow_months = recommended_cover_crop.get('sow_months', [])
                                profit_with_cover = base_result.get('profit_with_cover_total', profit_total)
                                
                                st.markdown(f"#### {cover_crop_name}")
                                
                                if cover_benefits:
                                    st.markdown("**Priekšrocības:**")
                                    for benefit in cover_benefits:
                                        st.markdown(f"- {benefit}")
                                
                                cover_cost_total = cover_cost_eur_ha * selected_field.area_ha if selected_field.area_ha > 0 else 0.0
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Izmaksas (EUR/ha)", f"{cover_cost_eur_ha:.2f}")
                                with col2:
                                    st.metric("Izmaksas (kopā)", f"{cover_cost_total:.2f} EUR")
                                
                                profit_with_cover_per_ha = profit_with_cover / selected_field.area_ha if selected_field.area_ha > 0 else 0.0
                                st.metric(
                                    "Peļņa pēc starpkultūras izmaksām",
                                    f"{profit_with_cover:.2f} EUR",
                                    delta=f"{profit_with_cover_per_ha:.2f} EUR/ha",
                                    help="Peļņa pēc starpkultūras izmaksu atskaitīšanas"
                                )
                        
                        st.markdown("---")
                        
                        # ========== PEĻŅAS SADALĪJUMS ==========
                        st.markdown("### Peļņas sadalījums")
                        
                        if best_crop_obj and profit_breakdown:
                            price_source_text = _get_price_source_text(best_crop_name, crops_dict)
                            
                            yield_t_ha = profit_breakdown["yield_t_ha"]
                            price_eur_t = profit_breakdown["price_eur_t"]
                            revenue_per_ha = profit_breakdown["revenue_per_ha"]
                            revenue_total = profit_breakdown["revenue_total"]
                            cost_per_ha = profit_breakdown["cost_per_ha"]
                            cost_total = profit_breakdown["cost_total"]
                            profit_per_ha = profit_breakdown["profit_per_ha"]
                            profit_total = profit_breakdown["profit"]
                            
                            st.markdown(f"**Raža:** {yield_t_ha:.2f} t/ha")
                            st.markdown(f"**Cena:** {price_eur_t:.2f} EUR/t")
                            if price_source_text:
                                st.caption(price_source_text)
                            
                            st.markdown("---")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**Ieņēmumi:**")
                                st.markdown(f"- {revenue_per_ha:.2f} EUR/ha")
                                st.markdown(f"- {revenue_total:.2f} EUR (kopā)")
                            
                            with col2:
                                st.markdown("**Izmaksas:**")
                                st.markdown(f"- {cost_per_ha:.2f} EUR/ha")
                                st.markdown(f"- {cost_total:.2f} EUR (kopā)")
                            
                            st.markdown("---")
                            st.markdown(f"**Peļņa:** {profit_per_ha:.2f} EUR/ha = {profit_total:.2f} EUR (kopā)")
                        
                        # ========== DIAGNOSTIKA ==========
                        debug_info = base_result.get('debug_info')
                        if debug_info:
                            with st.expander("Diagnostika", expanded=False):
                                # Parāda nomu no lauka
                                field_rent = getattr(selected_field, "rent_eur_ha", 0.0) or 0.0
                                st.markdown(f"**Noma (EUR/ha):** {field_rent:.2f}")
                                st.markdown("---")
                                
                                filtered_out = debug_info.get('filtered_out', [])
                                if filtered_out:
                                    st.markdown("#### Izslēgtas kultūras")
                                    st.caption("Kultūras, kas nav atļautas pēc rotācijas noteikumiem")
                                    filtered_out_data = []
                                    for item in filtered_out:
                                        reason_text = "Rotācijas noteikumi"
                                        filtered_out_data.append({
                                            "Kultūra": item['crop'],
                                            "Iemesls": reason_text
                                        })
                                    st.dataframe(filtered_out_data, use_container_width=True, hide_index=True)
                                
                                scored = debug_info.get('scored', [])
                                if scored:
                                    st.markdown("#### Novērtētās kultūras")
                                    scored_sorted = sorted(scored, key=lambda x: x['profit_total'], reverse=True)
                                    scored_data = []
                                    for item in scored_sorted:
                                        diagnostic_warnings = item.get('diagnostic_warnings', [])
                                        
                                        warnings = item.get('warnings', [])
                                        other_warnings = []
                                        if warnings:
                                            warning_labels = {
                                                "yield_too_high": "Raža >20",
                                                "price_too_high": "Cena >1200",
                                                "cost_too_high": "Izmaksas >3000"
                                            }
                                            for w in warnings:
                                                if w in warning_labels:
                                                    other_warnings.append(warning_labels[w])
                                        
                                        all_warnings = diagnostic_warnings + other_warnings
                                        warnings_text = "; ".join(all_warnings) if all_warnings else "—"
                                        
                                        scored_data.append({
                                            "Kultūra": item['crop'],
                                            "Ieņēmumi (EUR/ha)": f"{item['revenue_per_ha']:.2f}",
                                            "Izmaksas (EUR/ha)": f"{item['cost_per_ha']:.2f}",
                                            "Peļņa (EUR/ha)": f"{item['profit_per_ha']:.2f}",
                                            "Peļņa (kopā)": f"{item['profit_total']:.2f}",
                                            "Brīdinājumi": warnings_text
                                        })
                                    st.dataframe(scored_data, use_container_width=True, hide_index=True)
                        
                        # ========== E) ADVANCED ANALYSIS - COLLAPSED ==========
                        with st.expander("Papildu analīze", expanded=False):
                            stability = scenario_result.get('stability', 0) if scenario_result else 0
                            stable_crop = scenario_result.get('stable_crop') if scenario_result else None
                            
                            st.markdown("#### Scenāriju stabilitāte")
                            st.progress(stability / 5)
                            
                            if stability == 5:
                                st.caption("Ļoti stabils ieteikums (visos 5 scenārijos tā pati kultūra)")
                            elif stability >= 3:
                                st.caption("Vidēji stabils ieteikums")
                            else:
                                st.caption("Nestabils ieteikums (cenas stipri ietekmē izvēli)")
                            
                            if stable_crop and stable_crop != base_result['best_crop']:
                                st.caption(f"Stabilākā izvēle visos scenārijos: {stable_crop}")
                            
                            st.markdown("---")
                            
                            # Scenāriju salīdzinājums
                            scenario_results = scenario_result.get('scenario_results', {}) if scenario_result else {}
                            if scenario_results:
                                st.markdown("#### Scenāriju salīdzinājums")
                                scenario_data = []
                                for scenario_name, scenario_data_item in scenario_results.items():
                                    if scenario_data_item and scenario_data_item.get('best_crop'):
                                        scenario_data.append({
                                            "Scenārijs": scenario_name,
                                            "Kultūra": scenario_data_item['best_crop'],
                                            "Peļņa (EUR)": f"{scenario_data_item.get('profit_total', scenario_data_item.get('best_profit', 0.0)):.2f}"
                                        })
                                if scenario_data:
                                    st.dataframe(scenario_data, use_container_width=True, hide_index=True)
        else:
            # Nav rezultāta - parāda ziņojumu
            if st.session_state.get("reco_field_id"):
                st.info("Izvēlieties lauku un citus parametrus, lai saņemtu ieteikumus.")
            else:
                st.info("Izvēlieties lauku, lai saņemtu ieteikumus.")


def show_login():
    """Parāda login/signup formu ar cilnēm."""
    st.title("Farm Planner")
    st.markdown("Lūdzu, pieslēdzieties vai reģistrējieties, lai turpinātu.")
    
    # Pārbauda, vai storage ir pieejams
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta. Lūdzu, atsvaidziniet lapu.")
        return
    
    storage = st.session_state.storage
    
    # Cilnes
    tab1, tab2 = st.tabs(["Pieslēgties", "Reģistrēties"])
    
    with tab1:
        st.markdown("### Pieslēgties")
        with st.form("login_form"):
            username = st.text_input("Lietotājvārds", key="login_username")
            password = st.text_input("Parole", type="password", key="login_password")
            submit = st.form_submit_button("Pieslēgties", use_container_width=True)
            
            if submit:
                if username and password:
                    user = login(storage, username, password)
                    if user:
                        st.rerun()
                    else:
                        st.error("Nepareizs lietotājvārds vai parole.")
                else:
                    st.error("Lūdzu, ievadiet lietotājvārdu un paroli.")
    
    with tab2:
        st.markdown("### Reģistrēties")
        with st.form("signup_form"):
            username = st.text_input("Lietotājvārds", key="signup_username")
            password = st.text_input("Parole", type="password", key="signup_password", help="Vismaz 8 simboli")
            password_repeat = st.text_input("Atkārtot paroli", type="password", key="signup_password_repeat")
            submit = st.form_submit_button("Izveidot kontu", use_container_width=True)
            
            if submit:
                if not username or not password or not password_repeat:
                    st.error("Lūdzu, aizpildiet visus laukus.")
                elif password != password_repeat:
                    st.error("Paroles nesakrīt.")
                else:
                    user = register(storage, username, password)
                    if user:
                        st.success("Konts izveidots veiksmīgi!")
                        st.rerun()
                    else:
                        st.error("Lietotājs ar šādu lietotājvārdu jau eksistē.")


def main():
    """Galvenā funkcija."""
    try:
        # Pārbauda, vai storage ir inicializēts
        # Globālā inicializācija jau notiek faila augšā, bet ja tā neizdevās, mēģinām vēlreiz
        if 'storage' not in st.session_state:
            try:
                st.session_state.storage = Storage()
            except Exception as init_error:
                st.error(f"Kļūda inicializējot sistēmu: {init_error}")
                st.exception(init_error)
                return
        
        if 'storage' not in st.session_state:
            st.error("Sistēma nav inicializēta. Lūdzu, atsvaidziniet lapu.")
            return
        
        storage = st.session_state.storage
        
        # Pārbauda, vai lietotājs ir ielogojies
        if "user" not in st.session_state:
            show_login()
            return
    except Exception as e:
        st.error(f"Kļūda: {e}")
        import traceback
        print(f"Kļūda: {e}")
        print(traceback.format_exc())
        return
    
    # Profesionāls CSS stils
    st.markdown("""
    <style>
    /* Sidebar pogas – profesionāls stils */
    div.stButton > button {
        width: 100%;
        height: 46px;
        border-radius: 8px;
        font-size: 15px;
        font-weight: 500;
        text-align: left;
        padding-left: 14px;
    }

    /* Aktīvā poga */
    button[data-active="true"] {
        background-color: #1f2937 !important;
        border-left: 4px solid #4f46e5;
    }

    /* Mazākas sekundārās pogas */
    .secondary button {
        height: 38px;
        font-size: 14px;
    }

    /* Bīstamās darbības */
    .danger button {
        border: 1px solid #7f1d1d;
        background-color: #2a0f0f;
        color: #fecaca;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Nolasa page no URL (ja uzklikšķina uz Farm Planner)
    query_params = st.query_params
    if "page" in query_params:
        st.session_state.page = query_params["page"]
    
    # Inicializē lapu
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"
    
    page = st.session_state.page
    
    # Sidebar
    with st.sidebar:
        # Lietotāja informācija augšā
        user_id = st.session_state["user"]
        user = storage.get_user_by_id(user_id)
        if user:
            st.markdown(f"**Lietotājs:** {user.username}")
        
        if st.button("Logout", use_container_width=True, key="logout_btn"):
            logout()
            st.rerun()
        
        st.divider()
        
        st.markdown("""
        <style>
        /* Farm Planner virsraksts */
        .sidebar-logo {
            text-align: center;
            font-size: 22px;
            font-weight: 800;
            letter-spacing: 0.5px;
            padding: 8px 0 14px 0;
            cursor: pointer;
        }

        /* noņem linka default stilu */
        .sidebar-logo a {
            text-decoration: none;
            color: inherit;
        }

        /* hover – ļoti viegls, lai neizskatās kā poga */
        .sidebar-logo:hover {
            opacity: 0.85;
        }
        
        /* Sidebar pogas – visas vienāda izmēra */
        section[data-testid="stSidebar"] div.stButton > button {
            width: 100%;
            height: 52px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 600;
            text-align: center;
            margin-bottom: 8px;
        }

        /* Aktīvā poga (vizuāli izceļama) */
        section[data-testid="stSidebar"] div.stButton > button:hover {
            background-color: rgba(255,255,255,0.08);
        }

        /* Noņem liekos caption/mazos tekstus */
        section[data-testid="stSidebar"] small {
            display: none;
        }
        </style>

        <div class="sidebar-logo">
            <a href="?page=Dashboard">Farm Planner</a>
        </div>
        <div style="text-align:center; font-size:12px; opacity:0.6; margin-top:-6px;">
            Lēmumu atbalsta sistēma
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Galvenā navigācija
        if st.button("Dashboard", use_container_width=True):
            st.session_state.page = "Dashboard"
            st.rerun()

        if st.button("Lauki", use_container_width=True):
            st.session_state.page = "Lauki"
            st.rerun()

        if st.button("Sējumu vēsture", use_container_width=True):
            st.session_state.page = "Sējumu vēsture"
            st.rerun()

        if st.button("Ieteikumi", use_container_width=True):
            st.session_state.page = "Ieteikumi"
            st.rerun()

        if st.button("Kultūru katalogs", use_container_width=True):
            st.session_state.page = "Kultūru katalogs"
            st.rerun()

        # Demo dati
        st.divider()
        st.markdown("### Demo")

        if st.button("Ielādēt demo datus", use_container_width=True):
            load_demo_data()
            st.rerun()

        # Dzēst datus
        st.divider()
        st.markdown("### Datu dzēšana")

        confirm_clear = st.checkbox("Apstiprinu dzēšanu", key="confirm_clear")

        if st.button("Dzēst visus datus", use_container_width=True, disabled=not confirm_clear):
            if confirm_clear:
                if clear_all_data():
                    st.rerun()
    
    # Galvenais saturs
    page = st.session_state.page
    if page == "Dashboard":
        show_dashboard_section()
    elif page == "Lauki":
        show_fields_section()
    elif page == "Sējumu vēsture":
        show_history_section()
    elif page == "Ieteikumi":
        show_recommendations_section()
    elif page == "Kultūru katalogs":
        show_catalog_section()
    
    # Footer
    st.divider()
    st.caption("Farm Planner • 2025")


# Streamlit izpilda kodu, kas nav funkcijās, tāpēc izsaucam main() tikai, ja fails tiek palaists tieši
# Ja fails tiek importēts (piemēram, no app.py), main() tiks izsaukta no turienes
if __name__ == "__main__":
    # Pārbaudām, vai storage ir inicializēts
    if 'storage' not in st.session_state:
        st.error("Sistēma nav inicializēta. Lūdzu, atsvaidziniet lapu (F5).")
        st.info("Mēģinot inicializēt sistēmu...")
        try:
            st.session_state.storage = Storage()
            print("Sistēma inicializēta veiksmīgi")
            st.rerun()
        except Exception as e:
            st.error(f"Kļūda inicializējot sistēmu: {e}")
            import traceback
            print(f"Kļūda inicializējot sistēmu: {e}")
            print(traceback.format_exc())
        st.stop()

    # Izsaucam main() funkciju
    try:
        main()
    except Exception as e:
        st.error(f"Kļūda izpildot aplikāciju: {e}")
        import traceback
        print(f"Kļūda izpildot aplikāciju: {e}")
        print(traceback.format_exc())


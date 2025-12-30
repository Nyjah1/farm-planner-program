import json
import logging
import sys
import io
import os
from pathlib import Path
from typing import Dict, List, Optional

# Iestatīt UTF-8 kodējumu Windows sistēmām
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from .models import CropModel, FieldModel, PlantingRecord, SoilType
from .calc import calculate_profit
from .price_validation import validate_price
from .rules import get_allowed_crops
from .scenarios import price_scenarios
from .market_prices import get_price_map
from .price_provider import get_prices_for_catalog, get_price_for_crop
from .prices import load_prices_csv, load_prices_with_fallback
from .cost_overrides import apply_overrides_to_catalog
from .csp_prices import load_csp_prices
from .crop_groups import is_vegetable
from .sanity import validate_crop_numbers
from .cover import recommend_cover_crop

# Moduļa līmeņa mainīgie cenu metadatiem
last_price_update: Optional[str] = None
price_meta: Dict[str, Dict] = {}


def load_catalog(crops_file: str = "data/crops.json", csp_crops_file: str = "data/crops_csp.json") -> Dict[str, CropModel]:
    """
    Nolasa crops.json un crops_csp.json un izveido CropModel dict.
    Mēģina ielādēt cenas ar prioritāti ES tirgum un lokālajām rezervēm,
    atjaunojot crop.price_eur_t un saglabājot meta informāciju.
    
    Args:
        crops_file: Ceļš uz crops.json failu
        csp_crops_file: Ceļš uz crops_csp.json failu
    
    Returns:
        Dict ar kultūras nosaukumu -> CropModel
    """
    global last_price_update
    
    crops_path = Path(crops_file)
    try:
        with open(crops_path, 'r', encoding='utf-8') as f:
            crops_data = json.load(f)
    except json.JSONDecodeError as e:
        msg = (
            f"crops.json nav derīgs JSON (iespējams lieks teksts pēc masīva). "
            f"Fails: {crops_file}, rinda: {e.lineno}, kolonna: {e.colno}"
        )
        raise ValueError(msg)
    
    crops_dict = {}
    
    # Ielādē crops.json (pilnie profili)
    for crop_data in crops_data:
        # Konvertē yield_t_ha no string uz SoilType enum ar validāciju
        # Atbalsta gan vecos kodus ("mals", "kudra"), gan jaunos ("mālaina", "kūdra")
        soil_by_code = {s.code: s for s in SoilType}
        
        # Migrācija: vecie kodi -> jaunie kodi
        old_to_new_code = {
            "mals": "mālaina",
            "kudra": "kūdra"
        }
        
        yield_dict = {}
        for k, v in crop_data["yield_t_ha"].items():
            # Migrē vecos kodus uz jaunajiem
            if k in old_to_new_code:
                k = old_to_new_code[k]
            
            if k not in soil_by_code:
                raise ValueError(f"Nederīgs augsnes tips crops.json: {k}")
            yield_dict[soil_by_code[k]] = v
        
        # Pārbauda un koriģē group, izmantojot is_vegetable()
        crop_name = crop_data['name']
        crop_group = crop_data.get('group', 'Citi')
        if is_vegetable(crop_name, crop_group):
            crop_group = "Dārzeņi"
        
        # Dārzeņiem pēc noklusējuma price_eur_t = None
        price_eur_t = crop_data.get('price_eur_t')
        if crop_group == "Dārzeņi" and price_eur_t is None:
            price_eur_t = None
        elif crop_group == "Dārzeņi" and price_eur_t == 0:
            price_eur_t = None
        
        # Ielādē ph_range, ja ir
        ph_range = None
        if 'ph_range' in crop_data and crop_data['ph_range'] is not None:
            ph_range_data = crop_data['ph_range']
            if isinstance(ph_range_data, list) and len(ph_range_data) == 2:
                ph_range = (float(ph_range_data[0]), float(ph_range_data[1]))
        
        crop = CropModel(
            name=crop_name,
            group=crop_group,
            sow_months=crop_data['sow_months'],
            yield_t_ha=yield_dict,
            cost_eur_ha=crop_data['cost_eur_ha'],
            price_eur_t=price_eur_t,
            is_market_crop=crop_data.get('is_market_crop', True),
            ph_range=ph_range,
            is_organic_supported=crop_data.get('is_organic_supported', True),
            price_bio=crop_data.get('price_bio'),
            yield_modifier_bio=crop_data.get('yield_modifier_bio', 0.85)
        )
        
        crops_dict[crop.name] = crop
    
    # Ielādē crops_user.json (lietotāja pievienotās/rediģētās kultūras)
    crops_user_file = Path("data/crops_user.json")
    if crops_user_file.exists():
        try:
            with open(crops_user_file, 'r', encoding='utf-8') as f:
                user_crops_data = json.load(f)
            
            for user_crop_data in user_crops_data:
                crop_name = user_crop_data.get('name')
                if not crop_name:
                    continue
                
                # Konvertē yield_t_ha no string uz SoilType enum
                soil_by_code = {s.code: s for s in SoilType}
                
                # Migrācija: vecie kodi -> jaunie kodi
                old_to_new_code = {
                    "mals": "mālaina",
                    "kudra": "kūdra"
                }
                
                yield_dict = {}
                user_yield = user_crop_data.get('yield_t_ha', {})
                for k, v in user_yield.items():
                    # Migrē vecos kodus uz jaunajiem
                    if k in old_to_new_code:
                        k = old_to_new_code[k]
                    
                    if k in soil_by_code:
                        yield_dict[soil_by_code[k]] = v
                
                # Pārbauda un koriģē group
                crop_group = user_crop_data.get('group', 'Citi')
                # Dārzeņu piederību noteic tikai pēc grupas
                if is_vegetable(crop_name, crop_group):
                    crop_group = "Dārzeņi"
                
                # Dārzeņiem pēc noklusējuma price_eur_t = None
                price_eur_t = user_crop_data.get('price_eur_t')
                if crop_group == "Dārzeņi" and (price_eur_t is None or price_eur_t == 0):
                    price_eur_t = None
                
                # Ielādē ph_range, ja ir
                ph_range = None
                if 'ph_range' in user_crop_data and user_crop_data['ph_range'] is not None:
                    ph_range_data = user_crop_data['ph_range']
                    if isinstance(ph_range_data, list) and len(ph_range_data) == 2:
                        ph_range = (float(ph_range_data[0]), float(ph_range_data[1]))
                
                # Izveido CropModel
                user_crop = CropModel(
                    name=crop_name,
                    group=crop_group,
                    sow_months=user_crop_data.get('sow_months', []),
                    yield_t_ha=yield_dict,
                    cost_eur_ha=user_crop_data.get('cost_eur_ha', 0.0),
                    price_eur_t=price_eur_t,
                    is_market_crop=user_crop_data.get('is_market_crop', True),
                    ph_range=ph_range,
                    is_organic_supported=user_crop_data.get('is_organic_supported', True),
                    price_bio=user_crop_data.get('price_bio'),
                    yield_modifier_bio=user_crop_data.get('yield_modifier_bio', 0.85)
                )
                
                # Pārraksta vai pievieno (crops_user pārraksta crops.json)
                crops_dict[crop_name] = user_crop
        except Exception as e:
            logging.warning(f"Neizdevās ielādēt crops_user.json: {e}")
            print(f"[WARNING] Neizdevās ielādēt crops_user.json: {e}")
    
    # Ielādē crops_csp.json (CSP saraksts)
    csp_crops_path = Path(csp_crops_file)
    if csp_crops_path.exists():
        try:
            with open(csp_crops_path, 'r', encoding='utf-8') as f:
                csp_crops_data = json.load(f)
            
            for csp_crop_data in csp_crops_data:
                crop_name = csp_crop_data['name']
                
                # Pārbauda un koriģē group, izmantojot is_vegetable()
                crop_group = csp_crop_data.get('group', 'Citi')
                if is_vegetable(crop_name, crop_group):
                    crop_group = "Dārzeņi"
                
                # Ja kultūra jau eksistē crops.json, atjauno tikai cenu no CSP
                if crop_name in crops_dict:
                    existing_crop = crops_dict[crop_name]
                    # Pārbauda un koriģē group arī esošajai kultūrai, izmantojot is_vegetable()
                    final_group = existing_crop.group
                    if is_vegetable(crop_name, final_group):
                        final_group = "Dārzeņi"
                    
                    # Dārzeņiem pēc noklusējuma price_eur_t = None
                    csp_price = csp_crop_data.get('price_eur_t', existing_crop.price_eur_t)
                    if final_group == "Dārzeņi" and (csp_price is None or csp_price == 0):
                        csp_price = None
                    
                    # Atjauno cenu no CSP, bet saglabā ražu/izmaksas no crops.json
                    updated_crop = CropModel(
                        name=existing_crop.name,
                        group=final_group,
                        sow_months=existing_crop.sow_months,
                        yield_t_ha=existing_crop.yield_t_ha,
                        cost_eur_ha=existing_crop.cost_eur_ha,
                        price_eur_t=csp_price,
                        is_market_crop=existing_crop.is_market_crop,
                        ph_range=existing_crop.ph_range
                    )
                    crops_dict[crop_name] = updated_crop
                else:
                    # Ja kultūra nav crops.json, izveido no CSP datiem
                    # yield_t_ha un sow_months ir tukši
                    # Dārzeņiem pēc noklusējuma price_eur_t = None
                    csp_price = csp_crop_data.get('price_eur_t', 0)
                    if crop_group == "Dārzeņi" and (csp_price is None or csp_price == 0):
                        csp_price = None
                    
                    crop = CropModel(
                        name=csp_crop_data['name'],
                        group=crop_group,
                        sow_months=csp_crop_data.get('sow_months', []),
                        yield_t_ha={},
                        cost_eur_ha=csp_crop_data.get('cost_eur_ha', 0),
                        price_eur_t=csp_price,
                        is_market_crop=csp_crop_data.get('is_market_crop', True),
                        ph_range=None
                    )
                    crops_dict[crop_name] = crop
            
            logging.info(f"Ielādētas {len(csp_crops_data)} kultūras no crops_csp.json")
            print(f"[INFO] Ielādētas {len(csp_crops_data)} kultūras no crops_csp.json")
        except Exception as e:
            logging.warning(f"Neizdevās ielādēt crops_csp.json: {e}")
            print(f"[WARNING] Neizdevās ielādēt crops_csp.json: {e}")
    
    # Ielādē CSP cenas kā noklusējuma avotu
    global price_meta, last_price_update
    price_meta = {}
    last_price_update = None
    
    try:
        csp_data = load_csp_prices()
        csp_prices = csp_data.get("prices", {})
        csp_year = csp_data.get("meta", {}).get("year")
        
        # Atjauno cenas no CSP (exact match pēc nosaukuma)
        for crop_name, crop in crops_dict.items():
            if crop_name in csp_prices:
                csp_price_info = csp_prices[crop_name]
                csp_price = csp_price_info.get("price_eur_t")
                
                # Dārzeņiem pēc noklusējuma price_eur_t = None
                if crop.group == "Dārzeņi":
                    csp_price = None
                    updated_crop = CropModel(
                        name=crop.name,
                        group=crop.group,
                        sow_months=crop.sow_months,
                        yield_t_ha=crop.yield_t_ha,
                        cost_eur_ha=crop.cost_eur_ha,
                        price_eur_t=None,
                        is_market_crop=crop.is_market_crop,
                        ph_range=crop.ph_range
                    )
                    crops_dict[crop_name] = updated_crop
                elif csp_price is not None and csp_price > 0:
                    # Aizstāj crop.price_eur_t ar CSP cenu
                    updated_crop = CropModel(
                        name=crop.name,
                        group=crop.group,
                        sow_months=crop.sow_months,
                        yield_t_ha=crop.yield_t_ha,
                        cost_eur_ha=crop.cost_eur_ha,
                        price_eur_t=csp_price,
                        is_market_crop=crop.is_market_crop,
                        ph_range=crop.ph_range
                    )
                    crops_dict[crop_name] = updated_crop
                    
                    # Saglabā meta info par CSP avotu
                    price_meta[crop_name] = {
                        "source": "CSP LAC020",
                        "source_type": "csp",
                        "source_name": "CSP LAC020",
                        "as_of": str(csp_year) if csp_year else None,
                        "year": csp_year,
                        "risk_level": "nezināms",
                        "volatility_pct": None,
                        "proxy_of": None,
                    }
                else:
                    # CSP cena nav derīga, saglabā info, ka nav CSP match
                    price_meta[crop_name] = {
                        "source": "crops.json",
                        "source_type": "manual",
                        "source_name": "Lokālais katalogs",
                        "as_of": None,
                        "year": None,
                        "csp_match": False,
                        "risk_level": "nezināms",
                        "volatility_pct": None,
                        "proxy_of": None,
                    }
            else:
                # Nav CSP cenas, saglabā info, ka nav CSP match
                price_meta[crop_name] = {
                    "source": "crops.json",
                    "source_type": "manual",
                    "source_name": "Lokālais katalogs",
                    "as_of": None,
                    "year": None,
                    "csp_match": False,
                    "risk_level": "nezināms",
                    "volatility_pct": None,
                    "proxy_of": None,
                }
        
        if csp_prices:
            logging.info(f"Ielādētas CSP cenas {len([c for c in crops_dict.keys() if c in csp_prices])} kultūrām no {csp_year}")
            print(f"[INFO] Ielādētas CSP cenas {len([c for c in crops_dict.keys() if c in csp_prices])} kultūrām no {csp_year}")
        else:
            logging.info("Nav atrastu CSP cenu")
            print("[INFO] Nav atrastu CSP cenu")
    
    except Exception as e:
        # Ja CSP ielāde neizdodas, turpina ar crops.json cenām
        error_msg = f"Neizdevās ielādēt CSP cenas: {str(e)}"
        logging.warning(error_msg, exc_info=True)
        print(f"[WARNING] {error_msg}")
        # Inicializē price_meta ar crops.json avotu visām kultūrām
        for crop_name in crops_dict.keys():
            price_meta[crop_name] = {
                "source": "crops.json",
                "source_type": "manual",
                "source_name": "Lokālais katalogs",
                "as_of": None,
                "year": None,
                "csp_match": False,
                "risk_level": "nezināms",
                "volatility_pct": None,
                "proxy_of": None,
            }
    
    # Ielādē cenas ar fallback (CSV > crops.json)
    # Šī funkcija garantē, ka katrai kultūrai ir cena vai raise ValueError
    try:
        prices_with_fallback = load_prices_with_fallback()
    except ValueError as e:
        logging.error(f"Neizdevās ielādēt cenas: {e}")
        raise

    # Mēģina ielādēt cenas (ES tirgus -> lokālais fallback)
    # Šie avoti var pārrakstīt CSP cenas (augstāka prioritāte)
    try:
        combined_prices = get_prices_for_catalog(list(crops_dict.keys())) or {}

        if combined_prices:
            as_of_dates = []
            updated_count = 0
            for crop_name, info in combined_prices.items():
                if crop_name not in crops_dict:
                    continue

                old_crop = crops_dict[crop_name]
                
                # Prioritāte: ES tirgus/local > CSP > CSV > crops.json
                # Ja ir ES/local cena, izmanto to un pārraksta CSP
                if info.get("price_eur_t") and info.get("price_eur_t") > 0:
                    updated_crop = CropModel(
                        name=old_crop.name,
                        group=old_crop.group,
                        sow_months=old_crop.sow_months,
                        yield_t_ha=old_crop.yield_t_ha,
                        cost_eur_ha=old_crop.cost_eur_ha,
                        price_eur_t=info.get("price_eur_t"),
                        is_market_crop=old_crop.is_market_crop,
                        ph_range=old_crop.ph_range
                    )
                    crops_dict[crop_name] = updated_crop
                    
                    # Meta informācija (ES/local pārraksta CSP)
                    price_meta[crop_name] = {
                        "source": info.get("source"),
                        "source_type": info.get("source_type", "market"),
                        "source_name": info.get("source_name", info.get("source")),
                        "as_of": info.get("as_of"),
                        "risk_level": info.get("risk_level", "nezināms"),
                        "volatility_pct": info.get("volatility_pct"),
                        "proxy_of": info.get("proxy_of"),
                    }
                    
                    if info.get("as_of"):
                        as_of_dates.append(info["as_of"])
                    
                    updated_count += 1
                # Ja nav ES/local cenas, paliek CSP vai crops.json cena (jau iestatīta)

            if as_of_dates:
                last_price_update = max(as_of_dates)

            logging.info(f"Ielādētas cenas (EU/local) {updated_count} kultūrām")
            print(f"[INFO] Ielādētas cenas (EU/local) {updated_count} kultūrām")
        else:
            logging.info("Nav atrastu ārējo cenu, izmanto CSP vai crops.json cenas")
            print("[INFO] Nav atrastu ārējo cenu, izmanto CSP vai crops.json cenas")

    except Exception as e:
        # Ja ielāde neizdodas, parāda log un turpina ar crops.json cenām
        error_msg = f"Neizdevās ielādēt cenas no price_provider: {str(e)}"
        logging.warning(error_msg, exc_info=True)
        print(f"[WARNING] {error_msg}")
        price_meta = {}
        last_price_update = None
    
    # Piemēro izmaksu overrides (ja ir)
    crops_dict = apply_overrides_to_catalog(crops_dict)
    
    # Startup validācija: pārbauda yield_t_ha datus
    validate_catalog_yield_data(crops_dict)
    
    return crops_dict


# Globāls mainīgais validācijas rezultātiem
catalog_validation_result: Optional[Dict] = None


def validate_catalog_yield_data(crops_dict: Dict[str, CropModel]) -> Dict:
    """
    Validē, ka katrai kultūrai yield_t_ha satur vismaz 1 atslēgu no SoilType enum.
    
    Args:
        crops_dict: Kultūru vārdnīca
    
    Returns:
        Dict ar validācijas rezultātiem:
        - missing_yield_by_soil: Dict[SoilType, List[str]] - kultūras, kurām trūkst yield katrai augsnei
        - crops_without_yield: List[str] - kultūras bez jebkāda yield datu
    """
    global catalog_validation_result
    
    missing_yield_by_soil: Dict[SoilType, List[str]] = {soil: [] for soil in SoilType}
    crops_without_yield: List[str] = []
    
    for crop_name, crop in crops_dict.items():
        # Pārbauda, vai yield_t_ha ir dict
        if not isinstance(crop.yield_t_ha, dict):
            crops_without_yield.append(crop_name)
            continue
        
        # Pārbauda, vai ir vismaz 1 atslēga no SoilType enum
        has_any_yield = False
        for soil_type in SoilType:
            if soil_type not in crop.yield_t_ha:
                missing_yield_by_soil[soil_type].append(crop_name)
            else:
                has_any_yield = True
        
        if not has_any_yield:
            crops_without_yield.append(crop_name)
    
    # Saglabā rezultātu globālajā mainīgajā
    catalog_validation_result = {
        'missing_yield_by_soil': missing_yield_by_soil,
        'crops_without_yield': crops_without_yield
    }
    
    # Logging
    total_crops = len(crops_dict)
    for soil_type, missing_crops in missing_yield_by_soil.items():
        if missing_crops:
            logging.warning(f"Validācija: {len(missing_crops)} kultūrām trūkst yield datu augsnei {soil_type.label}")
    
    if crops_without_yield:
        logging.warning(f"Validācija: {len(crops_without_yield)} kultūrām nav jebkādu yield datu")
    
    return catalog_validation_result


def get_catalog_validation_result() -> Optional[Dict]:
    """
    Atgriež kataloga validācijas rezultātus.
    
    Returns:
        Dict ar validācijas rezultātiem vai None, ja validācija nav veikta
    """
    global catalog_validation_result
    return catalog_validation_result


def get_last_price_update() -> Optional[str]:
    """
    Atgriež pēdējās cenu atjaunošanas laiku.
    
    Returns:
        Datums formātā "YYYY-MM-DD" vai None
    """
    global last_price_update
    return last_price_update


def get_price_meta() -> Dict[str, Dict]:
    """
    Atgriež cenu metadatus (source, as_of) pa kultūrām.
    """
    return price_meta


def recommend_for_field(
    field: FieldModel,
    history: List[PlantingRecord],
    crops_dict: Dict[str, CropModel],
    target_year: int,
    use_market_prices: bool = True,
    preferred_crops: Optional[List[str]] = None,
    favorite_crops_filter: Optional[set] = None,
    crop_group_filter: Optional[str] = None,
    favorites_plus_group: bool = False,
    include_crops_without_price: bool = False,
    include_vegetables: bool = False,
    allowed_groups: Optional[List[str]] = None,
    debug: bool = False
) -> Dict:
    """
    Ieteic kultūru laukam, pamatojoties uz noteikumiem un peļņu.
    
    Args:
        field: Lauka modelis
        history: Sējumu vēstures ierakstu saraksts
        crops_dict: Kultūru vārdnīca (nosaukums -> CropModel)
        target_year: Gads, kurā plāno sēt
        use_market_prices: Ja True, izmanto ES Agri-food Data Portal cenas
    
    Returns:
        Dict ar: best_crop, best_profit, sow_months, top3, explanation, risk_level, volatility_pct, reasons
    """
    global price_meta

    # Ielādē cenas ar fallback (CSV > crops.json)
    # Šī funkcija garantē, ka katrai kultūrai ir cena vai raise ValueError
    try:
        prices_with_fallback = load_prices_with_fallback()
    except ValueError as e:
        logging.error(f"Neizdevās ielādēt cenas: {e}")
        raise

    # Iegūst atjaunotās cenas no ES Agri-food Data Portal (ja vajag)
    if use_market_prices:
        market_prices = get_price_map()
        
        # Izveido working_crops_dict ar atjaunotām cenām
        working_crops_dict = {}
        for name, crop in crops_dict.items():
            # Izmanto cenu no fallback (CSV > crops.json), nevis crop.price_eur_t
            fallback_price = prices_with_fallback.get(name, {}).get("price_eur_t")
            
            # Ja nav cenas fallback, izmanto crop.price_eur_t no crops.json (var būt 0.0)
            if fallback_price is None:
                fallback_price = crop.price_eur_t if hasattr(crop, 'price_eur_t') and crop.price_eur_t is not None else 0.0
            
            # Ja ir cena no API, izmanto to, citādi izmanto fallback cenu
            new_price = market_prices.get(name, fallback_price)
            
            updated_crop = CropModel(
                name=crop.name,
                group=crop.group,
                sow_months=crop.sow_months,
                yield_t_ha=crop.yield_t_ha,
                cost_eur_ha=crop.cost_eur_ha,
                price_eur_t=new_price,
                ph_range=crop.ph_range
            )
            working_crops_dict[name] = updated_crop
    else:
        # Izmanto oriģinālo crops_dict (piem., scenārijiem)
        working_crops_dict = crops_dict
    
    # 1) Ielādē LV cenu failu
    prices_csv = load_prices_csv()

    # 2) Filtrē kandidātus pirms rotācijas noteikumiem
    # Atlasa tikai tās kultūras, kurām:
    # - crop.price_eur_t nav None
    # - crop.cost_eur_ha > 0
    # - crop.yield_t_ha satur field.soil atslēgu
    # - sow_months nav tukšs
    available_crop_names = list(working_crops_dict.keys())
    
    # Diagnostika: pirms filtrēšanas
    if debug:
        logging.info(f"[DIAGNOSTIKA] Pirms filtrēšanas: {len(available_crop_names)} kultūras kopā")
        print(f"[DIAGNOSTIKA] Pirms filtrēšanas: {len(available_crop_names)} kultūras kopā")
    
    # Filtrē kandidātus pirms rotācijas noteikumiem
    # Svarīgi: Kultūras bez cenas/izmaksām/ražas joprojām tiek evaluated ar brīdinājumu
    filtered_candidates = []
    excluded_by_incomplete_data = []  # Kultūras, kas izslēgtas, jo nav pietiekamu datu (nav sēšanas mēnešu)
    # filtered_out tiks aizpildīts tikai ar rotācijas iemesliem pēc get_allowed_crops()
    filtered_out = []  # Debug: saraksts ar izslēgtajām kultūrām un iemesliem (tikai rotācijas)
    for name in available_crop_names:
        crop = working_crops_dict[name]
        
        # Pārbauda, vai ir sēšanas mēneši
        if not crop.sow_months or len(crop.sow_months) == 0:
            excluded_by_incomplete_data.append(name)
            continue
        
        # Validācija ar sanity check
        warnings = validate_crop_numbers(crop, field.soil)
        
        # Hard fail: ignorē kultūru, ja yield_too_high VAI price_too_high
        if "yield_too_high" in warnings or "price_too_high" in warnings:
            excluded_by_incomplete_data.append(name)
            # Hard fail iemesli nav rotācijas
            continue
        
        # Visas pārbaudes izietas
        # Piezīme: Kultūras bez cenas/izmaksām/ražas joprojām tiek pievienotas filtered_candidates
        # Tās tiks evaluated ar brīdinājumu un fallback vērtībām
        filtered_candidates.append(name)
    
    # Diagnostika: pēc kandidātu filtra
    if debug:
        logging.info(f"[DIAGNOSTIKA] Pēc kandidātu filtra: {len(filtered_candidates)} kultūras palika")
        print(f"[DIAGNOSTIKA] Pēc kandidātu filtra: {len(filtered_candidates)} kultūras palika")
    
    # 2.2) Filtrē dārzeņus (ja include_vegetables == False)
    # Piezīme: Dārzeņi bez cenas jau ir izslēgti 2.1) solī (price_eur_t is None)
    # Šeit tiek izslēgti tikai dārzeņi ar cenu, ja include_vegetables == False
    # Pat ja include_vegetables == True, dārzeņi bez cenas netiek ieteikti
    excluded_by_filter = []  # Kultūras, kas izslēgtas pēc filtra
    filtered_by_vegetables = filtered_candidates
    for name in filtered_candidates:
        crop = working_crops_dict[name]
        # Izslēdz dārzeņus, ja include_vegetables == False
        if not include_vegetables and crop.group == "Dārzeņi":
            excluded_by_filter.append(name)
    
    # Atjauno filtrēto sarakstu
    filtered_by_vegetables = [
        name for name in filtered_candidates
        if name not in excluded_by_filter
    ]
    
    # Diagnostika: pēc dārzeņu filtra
    if debug:
        logging.info(f"[DIAGNOSTIKA] Pēc dārzeņu filtra: {len(filtered_by_vegetables)} kultūras palika")
        print(f"[DIAGNOSTIKA] Pēc dārzeņu filtra: {len(filtered_by_vegetables)} kultūras palika")
    
    # 2.2) Filtrē pēc allowed_groups (ja nav None un nav tukšs)
    filtered_by_allowed_groups = filtered_by_vegetables
    if allowed_groups is not None and len(allowed_groups) > 0:
        allowed_groups_set = set(allowed_groups)
        excluded_by_filter.extend([
            name for name in filtered_by_vegetables
            if working_crops_dict[name].group not in allowed_groups_set
        ])
        filtered_by_allowed_groups = [
            name for name in filtered_by_vegetables
            if working_crops_dict[name].group in allowed_groups_set
        ]
    
    # 2.5) Filtrē pēc grupas (ja izvēlēta) - vecais crop_group_filter (backward compatibility)
    filtered_by_group = filtered_by_allowed_groups
    if crop_group_filter:
        filtered_by_group = [
            name for name in filtered_by_allowed_groups
            if working_crops_dict[name].group == crop_group_filter
        ]
    
    # 2.6) Piemēro favorītu filtru
    used_favorites_filter = False
    filtered_by_favorites = filtered_by_group
    
    if favorite_crops_filter:
        if favorites_plus_group and crop_group_filter:
            # "Favorīti + izvēlētā grupa": ietver favorītus, pat ja tie nav izvēlētajā grupā
            # Bet arī ietver visas kultūras no izvēlētās grupas
            group_crops = filtered_by_group
            favorite_crops = [c for c in filtered_candidates if c in favorite_crops_filter]
            filtered_by_favorites = list(set(group_crops + favorite_crops))
            used_favorites_filter = True
        else:
            # "Tikai favorīti": tikai favorīti (ar vai bez grupas filtra)
            filtered_by_favorites = [c for c in filtered_by_group if c in favorite_crops_filter]
            used_favorites_filter = len(filtered_by_favorites) > 0
    
    # 2.6) Piemēro rotācijas noteikumus
    allowed_crops = get_allowed_crops(
        planting_history=history,
        available_crops=filtered_by_favorites,
        target_year=target_year,
        field_id=field.id
    )
    
    # Debug: filtered_out satur TIKAI kultūras, kas nav allowed_crops (rotācijas iemesli)
    # Noņem visus iepriekšējos iemeslus un aizpilda tikai ar rotācijas iemesliem
    filtered_out = []
    for crop_name in filtered_by_favorites:
        if crop_name not in allowed_crops:
            filtered_out.append({"crop": crop_name, "reason": "rotation_forbidden"})
    
    # 2.6) Ja pēc visiem filtriem nav atļautu kultūru, atgriež skaidru ziņojumu
    if not allowed_crops:
        filter_parts = []
        if crop_group_filter:
            filter_parts.append(f"grupā '{crop_group_filter}'")
        if favorite_crops_filter:
            if favorites_plus_group:
                filter_parts.append("favorītos + izvēlētajā grupā")
            else:
                filter_parts.append("favorītos")
        
        if filter_parts:
            message = f"Izvēlētajā {' / '.join(filter_parts)} nav atļautu kultūru pēc rotācijas noteikumiem."
        else:
            message = "Nav atļautu kultūru pēc sējumu rotācijas noteikumiem."
        
        # Debug info
        debug_info = {
            'candidates_before_rules': available_crop_names,
            'filtered_out': filtered_out,
            'allowed_after_rotation': [],
            'scored': []
        }
        
        return {
            'best_crop': None,
            'best_profit': 0.0,
            'sow_months': [],
            'top3': [],
            'explanation': message,
            'forbidden_crops': [],
            'lower_profit_crops': [],
            'crops_without_price': [],
            'reasons': [],
            'used_preference': False,
            'best_overall': None,
            'preference_note': '',
            'used_favorites_filter': used_favorites_filter,
            'favorites_filter_message': message,
            'crop_group_filter': crop_group_filter,
            'favorites_plus_group': favorites_plus_group,
            'excluded_by_filter': excluded_by_filter,
            'excluded_by_incomplete_data': excluded_by_incomplete_data,
            'debug_info': debug_info,
            'recommended_cover_crop': None,
            'profit_with_cover_total': 0.0,
            'candidates': []
        }
    
    # Noteikt aizliegtas kultūras (rotācijas dēļ) - no filtrētajām kultūrām
    # Filtrē dārzeņus, ja include_vegetables == False
    forbidden_crops = []
    for crop in filtered_by_favorites:
        if crop not in allowed_crops:
            # Ja include_vegetables == False, izlaiž dārzeņus
            if not include_vegetables and working_crops_dict[crop].group == "Dārzeņi":
                continue
            forbidden_crops.append(crop)
    
    if not allowed_crops:
        # Debug info
        debug_info = {
            'candidates_before_rules': available_crop_names,
            'filtered_out': filtered_out,
            'allowed_after_rotation': [],
            'scored': []
        }
        
        return {
            'best_crop': None,
            'best_profit': 0.0,
            'sow_months': [],
            'top3': [],
            'explanation': 'Nav atļautu kultūru pēc sējumu vēstures noteikumiem',
            'forbidden_crops': forbidden_crops,
            'lower_profit_crops': [],
            'excluded_by_filter': excluded_by_filter,
            'excluded_by_incomplete_data': excluded_by_incomplete_data,
            'excluded_by_price_validation': [],
            'debug_info': debug_info
        }
    
    # 3) Aprēķina peļņu katrai atļautajai kultūrai
    crop_profits = []
    crops_without_price = []  # Kultūras bez tirgus cenas
    excluded_by_price_validation = []  # Kultūras ar cenu, kas izslēgtas kā outlier
    scored = []  # Debug: saraksts ar visām novērtētajām kultūrām
    
    # Aprēķina peļņu visām atļautajām kultūrām
    # Svarīgi: Kultūras bez cenas/izmaksām joprojām tiek evaluated ar brīdinājumu
    for crop_name in allowed_crops:
        crop = working_crops_dict[crop_name]
        is_market = getattr(crop, "is_market_crop", True)
        
        # Iegūst cenu (izmantojot get_price_for_crop, kas garantē cenu)
        price_info = get_price_for_crop(crop, prices_csv)
        price_value, _source_label, _confidence = price_info
        
        # Pārbauda, vai kultūrai ir derīga cena (> 0)
        has_price = price_value is not None and price_value > 0
        if not has_price:
            crops_without_price.append(crop_name)
            # Ja nav atļauts iekļaut kultūras bez cenas, izlaiž
            if not include_crops_without_price:
                continue
        
        # Validē cenu pirms peļņas aprēķina (tikai ja ir cena)
        if has_price:
            validation_result = validate_price(crop_name, price_value)
            if not validation_result["valid"]:
                excluded_by_price_validation.append(crop_name)
                continue
        
        # Pārbauda izmaksas
        has_cost = crop.cost_eur_ha > 0
        
        # Atjauno kultūras cenu no price_info (var būt 0, ja nav cenas)
        crop_with_price = CropModel(
            name=crop.name,
            group=crop.group,
            sow_months=crop.sow_months,
            yield_t_ha=crop.yield_t_ha,
            cost_eur_ha=crop.cost_eur_ha,
            price_eur_t=price_value if has_price else 0.0,
            is_market_crop=crop.is_market_crop,
            ph_range=crop.ph_range
        )
        
        # Iegūst nomas maksu
        rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
        
        # Aprēķina peļņu izmantojot calculate_profit()
        # Piezīme: calculate_profit() vienmēr atgriež rezultātu (ar fallback, ja nepieciešams)
        calc_result = calculate_profit(field, crop_with_price, rent_eur_ha=rent_eur_ha)
        
        # calculate_profit() vairs nekad neatgriež None, bet var būt 0 vērtības
        if calc_result is None:
            # Drošības pārbaude (nedrīkst notikt)
            continue
        
        profit_total = calc_result.profit_total
        profit_per_ha = calc_result.profit_per_ha
        
        # Pārbauda pH un piemēro penalizāciju, ja nepieciešams
        ph_penalty = 0.0
        ph_note = None
        field_ph = getattr(field, "ph", None)
        if field_ph is not None and crop.ph_range is not None:
            ph_min, ph_max = crop.ph_range
            if field_ph < ph_min or field_ph > ph_max:
                # pH ārpus optimālā diapazona - penalizācija 10%
                ph_penalty = profit_total * 0.10
                profit_total = profit_total - ph_penalty
                profit_per_ha = profit_total / field.area_ha if field.area_ha > 0 else 0.0
                ph_note = f"pH {field_ph:.1f} ārpus optimālā diapazona ({ph_min:.1f}-{ph_max:.1f}), peļņa samazināta par 10%"

        # risk meta
        meta = price_meta.get(crop_name, {})
        risk_level = meta.get("risk_level", "nezināms")
        volatility = meta.get("volatility_pct")
        crop_profits.append((crop_name, profit_total, crop, risk_level, volatility, is_market, calc_result, ph_note))
        
        # Validācija ar sanity check (arī novērtētajām kultūrām)
        warnings = validate_crop_numbers(crop_with_price, field.soil)
        
        # Pievieno brīdinājumus par cenu/izmaksām/ražu
        warnings_list = list(warnings) if warnings else []
        diagnostic_warnings = []  # Brīdinājumi diagnostikai (neietekmē allowed/forbidden)
        
        if not has_price:
            warnings_list.append("no_price")
            diagnostic_warnings.append("Nav cenas (0 EUR/t).")
        
        if not has_cost:
            warnings_list.append("invalid_cost")
            diagnostic_warnings.append("Nav izmaksu (0 EUR/ha).")
        
        # Pievieno brīdinājumu par ražas fallback, ja izmantots
        if calc_result.yield_fallback_used and calc_result.yield_fallback_warning:
            diagnostic_warnings.append(calc_result.yield_fallback_warning)
        
        # Debug: pievieno scored sarakstam
        scored.append({
            "crop": crop_name,
            "revenue_per_ha": round(calc_result.revenue_per_ha, 2),
            "cost_per_ha": round(calc_result.cost_per_ha, 2),
            "profit_per_ha": round(profit_per_ha, 2),
            "profit_total": round(profit_total, 2),
            "warnings": warnings_list,
            "diagnostic_warnings": diagnostic_warnings
        })
    
    # Pārbauda, vai ir kultūras ar peļņu
    if not crop_profits:
        # Nosaka iemeslu, kāpēc nav kultūru
        if crops_without_price and not include_crops_without_price:
            explanation = f"Nav atļautu kultūru ar tirgus cenu. {len(crops_without_price)} kultūra(s) nav cenas: {', '.join(crops_without_price[:3])}{'...' if len(crops_without_price) > 3 else ''}"
        elif not allowed_crops:
            explanation = "Nav atļautu kultūru pēc sējumu rotācijas noteikumiem"
        else:
            explanation = "Nav atļautu kultūru ar derīgu cenu"
        
        # Debug info
        debug_info = {
            'candidates_before_rules': available_crop_names,
            'filtered_out': filtered_out,
            'allowed_after_rotation': allowed_crops,
            'scored': scored
        }
        
        return {
            'best_crop': None,
            'best_profit': 0.0,
            'sow_months': [],
            'top3': [],
            'explanation': explanation,
            'forbidden_crops': forbidden_crops,
            'lower_profit_crops': [],
            'crops_without_price': crops_without_price,
            'excluded_by_price_validation': excluded_by_price_validation,
            'reasons': [],
            'debug_info': debug_info,
            'recommended_cover_crop': None,
            'profit_with_cover_total': 0.0,
            'candidates': []
        }
    
    # 3) Sakārto pēc peļņas (augstākā pirmā)
    crop_profits.sort(key=lambda x: x[1], reverse=True)
    best_crop_name, best_profit_total, best_crop, best_risk, best_vol, best_is_market, best_calc_result, best_ph_note = crop_profits[0]
    
    # Izveido candidates sarakstu (sakārtots pēc peļņas)
    candidates = []
    for crop_name, profit_total, crop_obj, risk_lvl, vol, _is_market, calc_result, ph_note in crop_profits:
        # Iegūst diagnostic_warnings no scored saraksta
        diagnostic_warnings = []
        for scored_item in scored:
            if scored_item['crop'] == crop_name:
                diagnostic_warnings = scored_item.get('diagnostic_warnings', [])
                break
        
        # Apvieno diagnostic_warnings vienā tekstā
        warnings_text = "; ".join(diagnostic_warnings) if diagnostic_warnings else None
        
        candidates.append({
            'name': crop_name,
            'profit_total': round(profit_total, 2),
            'profit_per_ha': round(calc_result.profit_per_ha, 2),
            'sow_months': crop_obj.sow_months,
            'warnings': warnings_text,
            'revenue_total': round(calc_result.revenue_total, 2),
            'cost_total': round(calc_result.cost_total, 2),
            'revenue_per_ha': round(calc_result.revenue_per_ha, 2),
            'cost_per_ha': round(calc_result.cost_per_ha, 2),
            'risk_level': risk_lvl,
            'volatility_pct': vol,
            'is_market_crop': _is_market,
            'ph_note': ph_note
        })
    
    # Iegūst cenas informāciju labākajai kultūrai
    best_price_info = get_price_for_crop(best_crop, prices_csv)
    best_price_value, best_price_source, best_price_confidence = best_price_info
    
    # 4) Izveido top3 sarakstu (tikai kultūrām ar cenām)
    # Filtrē dārzeņus, ja include_vegetables == False
    top3 = []
    for name, profit_total, crop_obj, risk_lvl, vol, _is_market, calc_result, ph_note in crop_profits[:3]:
        # Ja include_vegetables == False, izlaiž dārzeņus
        if not include_vegetables and crop_obj.group == "Dārzeņi":
            continue
        top3_item = {
            'name': name,
            'profit': round(profit_total, 2),
            'profit_per_ha': round(calc_result.profit_per_ha, 2),
            'profit_total': round(profit_total, 2),
            'revenue_per_ha': round(calc_result.revenue_per_ha, 2),
            'revenue_total': round(calc_result.revenue_total, 2),
            'cost_per_ha': round(calc_result.cost_per_ha, 2),
            'cost_total': round(calc_result.cost_total, 2),
            'risk_level': risk_lvl,
            'volatility_pct': vol,
        }
        if ph_note:
            top3_item['ph_note'] = ph_note
        top3.append(top3_item)
    
    # 5) Atļautas kultūras ar zemāku peļņu (visas, kas nav TOP-3)
    # Filtrē dārzeņus, ja include_vegetables == False
    top3_names = {item['name'] for item in top3}
    lower_profit_crops = []
    for name, profit_total, crop_obj, risk_lvl, vol, _is_market, calc_result, ph_note in crop_profits[3:]:  # Visas pēc TOP-3
        # Ja include_vegetables == False, izlaiž dārzeņus
        if not include_vegetables and crop_obj.group == "Dārzeņi":
            continue
        lower_item = {
            'name': name,
            'profit': round(profit_total, 2),
            'profit_per_ha': round(profit_total / field.area_ha if field.area_ha > 0 else 0.0, 2),
            'profit_total': round(profit_total, 2),
            'revenue_per_ha': round(calc_result.revenue_per_ha, 2),
            'revenue_total': round(calc_result.revenue_total, 2),
            'cost_per_ha': round(calc_result.cost_per_ha, 2),
            'cost_total': round(calc_result.cost_total, 2),
            'risk_level': risk_lvl,
            'volatility_pct': vol,
        }
        if ph_note:
            lower_item['ph_note'] = ph_note
        lower_profit_crops.append(lower_item)
    
    # 6) Ģenerē detalizētu explanation
    profit_per_ha = best_profit_total / field.area_ha if field.area_ha > 0 else 0.0
    
    # Iegūst yield_t_ha konkrētai augsnei
    yield_t_ha_value = None
    if isinstance(best_crop.yield_t_ha, dict) and field.soil in best_crop.yield_t_ha:
        yield_t_ha_value = best_crop.yield_t_ha[field.soil]
    
    explanation_lines = []
    
    # 1. Augsne un yield_t_ha
    soil_label = field.soil.label
    if yield_t_ha_value is not None:
        explanation_lines.append(f"Augsne: {soil_label}, raža: {yield_t_ha_value:.2f} t/ha")
    else:
        explanation_lines.append(f"Augsne: {soil_label}, raža: nav datu")
    
    # 2. Cena un avots
    explanation_lines.append(f"Cena: {best_price_value:.2f} EUR/t (avots: {best_price_source})")
    
    # 3. Ieņēmumi/izdevumi/peļņa
    explanation_lines.append(f"Ieņēmumi: {best_calc_result.revenue_total:.2f} EUR ({best_calc_result.revenue_per_ha:.2f} EUR/ha)")
    explanation_lines.append(f"Izdevumi: {best_calc_result.cost_total:.2f} EUR ({best_calc_result.cost_per_ha:.2f} EUR/ha)")
    explanation_lines.append(f"Peļņa: {best_profit_total:.2f} EUR ({profit_per_ha:.2f} EUR/ha)")
    
    # 4. pH penalizācija (ja ir)
    if best_ph_note:
        # Izvērš ph_note, lai iegūtu procentu
        field_ph = getattr(field, "ph", None)
        if field_ph is not None and best_crop.ph_range is not None:
            ph_min, ph_max = best_crop.ph_range
            if field_ph < ph_min or field_ph > ph_max:
                penalty_pct = 10.0
                explanation_lines.append(f"pH penalizācija: -{penalty_pct}% (pH {field_ph:.1f} ārpus optimālā diapazona {ph_min:.1f}-{ph_max:.1f})")
    
    # 5. Izslēgtas kultūras ar iemesliem
    excluded_reasons = []
    
    # Izslēgtas, jo nav ražas datu vai citi iemesli
    # excluded_by_incomplete_data satur kultūras, kas izslēgtas, jo:
    # - nav cenas (price_eur_t is None)
    # - nav izmaksu (cost_eur_ha <= 0)
    # - nav ražas datu (field.soil nav yield_t_ha)
    # - nav sēšanas mēnešu
    excluded_by_yield = []
    excluded_by_no_price = []
    excluded_by_no_cost = []
    excluded_by_no_sow_months = []
    
    for name in excluded_by_incomplete_data:
        crop = working_crops_dict.get(name)
        if not crop:
            continue
        
        if crop.price_eur_t is None:
            excluded_by_no_price.append(name)
        elif crop.cost_eur_ha <= 0:
            excluded_by_no_cost.append(name)
        elif not isinstance(crop.yield_t_ha, dict) or field.soil not in crop.yield_t_ha:
            excluded_by_yield.append(name)
        elif not crop.sow_months or len(crop.sow_months) == 0:
            excluded_by_no_sow_months.append(name)
    
    if excluded_by_no_price:
        excluded_reasons.append(f"Nav cenas: {', '.join(excluded_by_no_price[:5])}{'...' if len(excluded_by_no_price) > 5 else ''}")
    if excluded_by_yield:
        excluded_reasons.append(f"Nav ražas datu šai augsnei: {', '.join(excluded_by_yield[:5])}{'...' if len(excluded_by_yield) > 5 else ''}")
    
    # Izslēgtas rotācijas dēļ
    if len(allowed_crops) < len(filtered_candidates):
        excluded_by_rotation = [name for name in filtered_candidates if name not in allowed_crops]
        if excluded_by_rotation:
            excluded_reasons.append(f"Rotācija aizliedz: {', '.join(excluded_by_rotation[:5])}{'...' if len(excluded_by_rotation) > 5 else ''}")
    
    # Izslēgtas cenu validācijas dēļ
    if excluded_by_price_validation:
        excluded_reasons.append(f"Cena ārpus diapazona: {', '.join(excluded_by_price_validation[:5])}{'...' if len(excluded_by_price_validation) > 5 else ''}")
    
    if excluded_reasons:
        explanation_lines.append("Izslēgtas kultūras:")
        for reason in excluded_reasons:
            explanation_lines.append(f"  - {reason}")
    
    explanation = "\n".join(explanation_lines)
    
    # Reasons saraksts (saglabāts atpakaļsaderībai)
    reasons: List[str] = []
    if used_favorites_filter:
        reasons.append("Augstākā prognozētā peļņa starp favorītajām kultūrām")
    else:
        reasons.append("Augstākā prognozētā peļņa starp atļautajām kultūrām")
    
    if not reasons:
        reasons.append("Labākā pieejamā izvēle dotajos apstākļos")
    
    # Starpkultūras ieteikums
    recommended_cover_crop = None
    profit_with_cover_total = best_profit_total
    
    # Iegūst galvenās kultūras grupu un sēšanas mēnesi
    main_crop_group = best_crop.group
    sow_month = best_crop.sow_months[0] if best_crop.sow_months else None
    
    if sow_month is not None:
        try:
            cover_crop = recommend_cover_crop(
                main_crop_group=main_crop_group,
                sow_month=sow_month,
                field_soil=field.soil
            )
            
            if cover_crop:
                # Aprēķina starpkultūras izmaksas
                cover_cost_total = cover_crop.cost_eur_ha * field.area_ha if field.area_ha > 0 else 0.0
                profit_with_cover_total = best_profit_total - cover_cost_total
                
                # Saglabā starpkultūras informāciju
                recommended_cover_crop = {
                    'name': cover_crop.name,
                    'cost_eur_ha': cover_crop.cost_eur_ha,
                    'benefits': cover_crop.benefits,
                    'sow_months': cover_crop.sow_months
                }
                
                # Papildina explanation ar starpkultūras informāciju
                explanation_lines.append("")
                explanation_lines.append("Starpkultūras ieteikums:")
                explanation_lines.append(f"  - {cover_crop.name}")
                explanation_lines.append(f"  - Izmaksas: {cover_crop.cost_eur_ha:.2f} EUR/ha ({cover_cost_total:.2f} EUR kopā)")
                explanation_lines.append(f"  - Priekšrocības: {', '.join(cover_crop.benefits)}")
                explanation_lines.append(f"  - Peļņa ar starpkultūru: {profit_with_cover_total:.2f} EUR ({profit_with_cover_total / field.area_ha if field.area_ha > 0 else 0.0:.2f} EUR/ha)")
                
                # Atjauno explanation
                explanation = "\n".join(explanation_lines)
        except Exception as e:
            # Ja neizdodas ielādēt vai ieteikt starpkultūru, izlaiž bez kļūdas
            logging.warning(f"Neizdevās ieteikt starpkultūru: {str(e)}")
    
    # Debug info
    debug_info = {
        'candidates_before_rules': available_crop_names,
        'filtered_out': filtered_out,
        'allowed_after_rotation': allowed_crops,
        'scored': scored
    }
    
    return {
        'best_crop': best_crop_name,
        'best_profit': round(best_profit_total, 2),  # Deprecated, kept for backward compatibility
        'profit_total': round(best_profit_total, 2),
        'profit_per_ha': round(profit_per_ha, 2),
        'revenue_total': round(best_calc_result.revenue_total, 2),
        'revenue_per_ha': round(best_calc_result.revenue_per_ha, 2),
        'cost_total': round(best_calc_result.cost_total, 2),
        'cost_per_ha': round(best_calc_result.cost_per_ha, 2),
        'risk_level': best_risk,
        'volatility_pct': best_vol,
        'is_market_crop': best_is_market,
        'sow_months': best_crop.sow_months,
        'top3': top3,
        'excluded_by_filter': excluded_by_filter,
        'excluded_by_incomplete_data': excluded_by_incomplete_data,
        'excluded_by_price_validation': excluded_by_price_validation,
        'explanation': explanation,
        'forbidden_crops': forbidden_crops,
        'lower_profit_crops': lower_profit_crops,
        'crops_without_price': crops_without_price,
        'reasons': reasons,
        'used_preference': False,  # Deprecated, kept for backward compatibility
        'best_overall': None,  # Deprecated
        'preference_note': '',  # Deprecated
        'used_favorites_filter': used_favorites_filter,
        'crop_group_filter': crop_group_filter,
        'favorites_plus_group': favorites_plus_group,
        'debug_info': debug_info,
        'recommended_cover_crop': recommended_cover_crop,
        'profit_with_cover_total': round(profit_with_cover_total, 2),
        'candidates': candidates
    }


def _build_temp_crops_dict(
    crops_dict: Dict[str, CropModel],
    new_prices: Dict[str, float]
) -> Dict[str, CropModel]:
    """
    Helper funkcija: izveido pagaidu crops_dict ar modificētām cenām.
    
    Args:
        crops_dict: Oriģinālais kultūru vārdnīca
        new_prices: Jaunās cenas vārdnīca (nosaukums -> cena)
    
    Returns:
        Pagaidu crops_dict ar modificētām cenām
    """
    temp_crops_dict = {}
    prices_csv = load_prices_csv()
    for name, crop in crops_dict.items():
        # Nosaka, vai šai kultūrai ir augstas pārliecības LV cena
        price_value, _src_label, confidence = get_price_for_crop(crop, prices_csv)

        if confidence == "high":
            # LV cena ir “truth” – nemaina to ar scenāriju
            effective_price = price_value
        else:
            # Scenārijs drīkst mainīt cenu
            effective_price = new_prices[name]

        temp_crop = CropModel(
            name=crop.name,
            group=crop.group,
            sow_months=crop.sow_months,
            yield_t_ha=crop.yield_t_ha,
            cost_eur_ha=crop.cost_eur_ha,
            price_eur_t=effective_price,
            ph_range=crop.ph_range
        )
        temp_crops_dict[name] = temp_crop
    return temp_crops_dict


def recommend_with_scenarios(
    field: FieldModel,
    history: List[PlantingRecord],
    crops_dict: Dict[str, CropModel],
    target_year: int,
    preferred_crops: Optional[List[str]] = None,
    favorite_crops_filter: Optional[set] = None,
    crop_group_filter: Optional[str] = None,
    favorites_plus_group: bool = False,
    include_crops_without_price: bool = False,
    include_vegetables: bool = False,
    allowed_groups: Optional[List[str]] = None,
    debug: bool = False
) -> Dict:
    """
    Ieteic kultūru ar cenu scenāriju analīzi.
    
    Izveido 5 cenu scenārijus un katrā nosaka labāko kultūru.
    Analizē stabilitāti - cik scenārijos best_crop paliek tas pats.
    
    Piezīme: Atgrieztais 'stable_crop' ir stabilākā izvēle visos scenārijos,
    kas var atšķirties no bāzes scenārija 'best_crop'.
    
    Args:
        field: Lauka modelis
        history: Sējumu vēstures ierakstu saraksts
        crops_dict: Kultūru vārdnīca (nosaukums -> CropModel)
        target_year: Gads, kurā plāno sēt
    
    Returns:
        Dict ar: stable_crop, stability (cik scenāriju no 5), scenario_results
    """
    # Ielādē cenas ar fallback (CSV > crops.json)
    # Šī funkcija garantē, ka katrai kultūrai ir cena vai raise ValueError
    try:
        prices_with_fallback = load_prices_with_fallback()
    except ValueError as e:
        logging.error(f"Neizdevās ielādēt cenas: {e}")
        raise

    # Iegūst atjaunotās cenas no ES Agri-food Data Portal
    market_prices = get_price_map()
    
    # Izveido bāzes cenu vārdnīcu ar atjaunotām cenām
    base_prices = {}
    for name, crop in crops_dict.items():
        # Izmanto cenu no fallback (CSV > crops.json), nevis crop.price_eur_t
        fallback_price = prices_with_fallback.get(name, {}).get("price_eur_t")
        
        # Ja nav cenas fallback, izmanto crop.price_eur_t no crops.json (var būt 0.0)
        if fallback_price is None:
            fallback_price = crop.price_eur_t if hasattr(crop, 'price_eur_t') and crop.price_eur_t is not None else 0.0
        
        # Ja ir cena no API, izmanto to, citādi izmanto fallback cenu
        base_prices[name] = market_prices.get(name, fallback_price)
    
    # Izveido scenārijus
    scenarios = price_scenarios(base_prices)
    
    # Katrā scenārijā nosaka best_crop
    scenario_results = {}
    best_crops = []
    
    for scenario_name, scenario_prices in scenarios.items():
        # Izveido pagaidu crops_dict ar scenārija cenām
        temp_crops_dict = _build_temp_crops_dict(crops_dict, scenario_prices)
        
        result = recommend_for_field(
            field=field,
            history=history,
            crops_dict=temp_crops_dict,
            target_year=target_year,
            use_market_prices=False,  # Scenārijiem izmanto scenārija cenas, nevis API cenas
            preferred_crops=preferred_crops,
            favorite_crops_filter=favorite_crops_filter,
            crop_group_filter=crop_group_filter,
            favorites_plus_group=favorites_plus_group,
            include_crops_without_price=include_crops_without_price,
            include_vegetables=include_vegetables,
            allowed_groups=allowed_groups,
            debug=debug
        )
        scenario_results[scenario_name] = result
        if result['best_crop']:
            best_crops.append(result['best_crop'])
    
    # Analizē stabilitāti
    if not best_crops:
        return {
            'stable_crop': None,
            'stability': 0,
            'scenario_results': scenario_results
        }
    
    # Skaita, cik scenārijos best_crop ir tas pats
    # Atgriež stabilāko izvēli (visbiežāk sastopamo)
    from collections import Counter
    crop_counts = Counter(best_crops)
    most_common_crop, count = crop_counts.most_common(1)[0]
    
    return {
        'stable_crop': most_common_crop,  # Stabilākā izvēle visos scenārijos
        'stability': count,  # Cik scenāriju no 5 (maksimums 5)
        'scenario_results': scenario_results
    }


def plan_for_years(
    field: FieldModel,
    history: List[PlantingRecord],
    crops_dict: Dict[str, CropModel],
    start_year: int,
    years: int = 3,
    preferred_crops: Optional[List[str]] = None,
    favorite_crops_filter: Optional[set] = None,
    crop_group_filter: Optional[str] = None,
    favorites_plus_group: bool = False,
    include_crops_without_price: bool = False,
    include_vegetables: bool = False,
    allowed_groups: Optional[List[str]] = None,
    user_id: Optional[int] = None
) -> Dict:
    """
    Plāno kultūras vairākiem gadiem uz priekšu.
    
    Katru gadu izmanto recommend_for_field() un pievieno virtuālu
    PlantingRecord history, lai rotācijas noteikumi strādā nākamajam gadam.
    
    Args:
        field: Lauka modelis
        history: Sējumu vēstures ierakstu saraksts (tikai šim field)
        crops_dict: Kultūru vārdnīca (nosaukums -> CropModel)
        start_year: Sākuma gads plānošanai
        years: Gadu skaits (noklusējums: 3)
    
    Returns:
        Dict ar plānu un statistiku:
        {
            "field_id": int,
            "field_name": str,
            "start_year": int,
            "years": int,
            "plan": [
                {
                    "year": int,
                    "crop": Optional[str],
                    "profit": float,
                    "profit_per_ha": float,
                    "sow_months": list[int],
                    "explanation": str
                },
                ...
            ],
            "total_profit": float,
            "avg_profit_per_ha": float
        }
    """
    # Kopija vēsturei (lai nemainītu oriģinālo)
    virtual_history = history.copy()
    plan = []
    total_profit = 0.0
    prices_csv = load_prices_csv()
    
    # Plāno katru gadu
    for year_offset in range(years):
        target_year = start_year + year_offset
        
        # Iegūst ieteikumu šim gadam
        result = recommend_for_field(
            field=field,
            history=virtual_history,
            crops_dict=crops_dict,
            target_year=target_year,
            preferred_crops=preferred_crops,
            favorite_crops_filter=favorite_crops_filter,
            crop_group_filter=crop_group_filter,
            favorites_plus_group=favorites_plus_group,
            include_crops_without_price=include_crops_without_price,
            include_vegetables=include_vegetables,
            allowed_groups=allowed_groups
        )
        
        # Sagatavo plāna ierakstu
        if result['best_crop'] is None:
            # Nav atļautu kultūru
            plan_entry = {
                "year": target_year,
                "crop": None,
                "profit": 0.0,
                "profit_per_ha": 0.0,
                "sow_months": [],
                "explanation": result.get('explanation', 'Nav atļautu kultūru')
            }
        else:
            # Ir ieteikums
            # Aprēķina peļņu tieši, nevis izmanto result['best_profit']
            best_crop_obj = crops_dict[result['best_crop']]
            price_info = get_price_for_crop(best_crop_obj, prices_csv)
            price_value, _source_label, _confidence = price_info
            
            # Atjauno kultūras cenu no price_info
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
            
            # Iegūst nomas maksu
            rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
            
            # Aprēķina peļņu izmantojot calculate_profit()
            calc_result = calculate_profit(field, crop_with_price, rent_eur_ha=rent_eur_ha)
            if calc_result is None:
                continue  # Izlaiž, ja nav cenas vai ražas
            profit_total = calc_result.profit_total
            profit_per_ha = calc_result.profit_per_ha
            total_profit += profit_total
            
            # Pievieno favorītu informāciju
            crop_note = ""
            if result.get('used_preference'):
                crop_note = " (favorīts)"
            elif result.get('best_overall') and result['best_overall']['name'] != result['best_crop']:
                crop_note = " (labākais kopumā)"
            
            plan_entry = {
                "year": target_year,
                "crop": result['best_crop'],
                "profit": round(profit_total, 2),
                "profit_total": round(profit_total, 2),
                "profit_per_ha": round(profit_per_ha, 2),
                "revenue_total": round(calc_result.revenue_total, 2),
                "revenue_per_ha": round(calc_result.revenue_per_ha, 2),
                "cost_total": round(calc_result.cost_total, 2),
                "cost_per_ha": round(calc_result.cost_per_ha, 2),
                "sow_months": result['sow_months'],
                "explanation": result.get('explanation', '') + crop_note
            }
            
            # Pievieno virtuālu PlantingRecord history, lai rotācijas noteikumi strādā
            virtual_planting = PlantingRecord(
                field_id=field.id,
                year=target_year,
                crop=result['best_crop'],
                owner_user_id=field.owner_user_id
            )
            virtual_history.append(virtual_planting)
        
        plan.append(plan_entry)
    
    # Aprēķina vidējo peļņu uz ha
    avg_profit_per_ha = total_profit / (field.area_ha * years) if field.area_ha > 0 and years > 0 else 0.0
    
    return {
        "field_id": field.id,
        "field_name": field.name,
        "start_year": start_year,
        "years": years,
        "plan": plan,
        "total_profit": round(total_profit, 2),
        "avg_profit_per_ha": round(avg_profit_per_ha, 2)
    }


def plan_for_years_lookahead(
    field: FieldModel,
    history: List[PlantingRecord],
    crops_dict: Dict[str, CropModel],
    start_year: int,
    years: int = 3,
    candidates: int = 3,
    preferred_crops: Optional[List[str]] = None,
    favorite_crops_filter: Optional[set] = None,
    crop_group_filter: Optional[str] = None,
    favorites_plus_group: bool = False,
    include_crops_without_price: bool = False,
    include_vegetables: bool = False,
    allowed_groups: Optional[List[str]] = None,
    user_id: Optional[int] = None
) -> Dict:
    """
    Plāno kultūras vairākiem gadiem uz priekšu, izmantojot lookahead algoritmu.
    
    Algoritms:
    1) Aprēķina 1. gada ieteikumu
    2) Paņem TOP-3 kandidātus no 1. gada rezultāta
    3) Katram kandidātam simulē visus gadus un saskaita kopējo peļņu
    4) Izvēlas labāko kandidātu pēc kopējās peļņas
    
    Args:
        field: Lauka modelis
        history: Sējumu vēstures ierakstu saraksts (tikai šim field)
        crops_dict: Kultūru vārdnīca (nosaukums -> CropModel)
        start_year: Sākuma gads plānošanai
        years: Gadu skaits (noklusējums: 3)
        candidates: Kandidātu skaits (noklusējums: 3)
    
    Returns:
        Dict ar plānu un statistiku (tāda pati struktūra kā plan_for_years)
        + "method": "lookahead"
        + "evaluated_candidates": [{"crop": str, "total_profit": float}, ...]
    """
    # 1) Aprēķina 1. gada ieteikumu
    first_year_result = recommend_for_field(
        field=field,
        history=history,
        crops_dict=crops_dict,
        target_year=start_year,
        preferred_crops=preferred_crops,
        favorite_crops_filter=favorite_crops_filter,
        crop_group_filter=crop_group_filter,
        favorites_plus_group=favorites_plus_group,
        include_crops_without_price=include_crops_without_price,
        include_vegetables=include_vegetables,
        allowed_groups=allowed_groups
    )
    
    # Ja nav atļautu kultūru, atgriež to pašu, ko plan_for_years
    if first_year_result['best_crop'] is None:
        return plan_for_years(
            field=field,
            history=history,
            crops_dict=crops_dict,
            start_year=start_year,
            years=years,
            preferred_crops=preferred_crops,
            favorite_crops_filter=favorite_crops_filter,
            crop_group_filter=crop_group_filter,
            favorites_plus_group=favorites_plus_group,
            include_crops_without_price=include_crops_without_price
        )
    
    # 2) Paņem TOP-3 kandidātus no 1. gada rezultāta
    top_candidates = first_year_result.get('top3', [])
    if not top_candidates:
        # Ja nav top3, izmanto tikai best_crop
        top_candidates = [{'name': first_year_result['best_crop'], 'profit': first_year_result['best_profit']}]
    
    # Ierobežo kandidātu skaitu
    top_candidates = top_candidates[:candidates]
    
    # 3) Katram kandidātam simulē visus gadus
    evaluated_candidates = []
    prices_csv = load_prices_csv()
    
    for candidate in top_candidates:
        candidate_crop = candidate['name']
        
        # Aprēķina 1. gada peļņu tieši
        candidate_crop_obj = crops_dict[candidate_crop]
        price_info = get_price_for_crop(candidate_crop_obj, prices_csv)
        price_value, _source_label, _confidence = price_info
        
        # Atjauno kultūras cenu no price_info
        crop_with_price = CropModel(
            name=candidate_crop_obj.name,
            group=candidate_crop_obj.group,
            sow_months=candidate_crop_obj.sow_months,
            yield_t_ha=candidate_crop_obj.yield_t_ha,
            cost_eur_ha=candidate_crop_obj.cost_eur_ha,
            price_eur_t=price_value,
            is_market_crop=candidate_crop_obj.is_market_crop,
            ph_range=candidate_crop_obj.ph_range
        )
        
        # Iegūst nomas maksu
        rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
        
        # Aprēķina peļņu izmantojot calculate_profit()
        calc_result = calculate_profit(field, crop_with_price, rent_eur_ha=rent_eur_ha)
        if calc_result is None:
            continue  # Izlaiž, ja nav cenas vai ražas
        first_profit = calc_result.profit_total
        
        # Pārbauda, vai kandidāts ir favorīts
        is_favorite = preferred_crops and candidate_crop in preferred_crops
        
        # Izveido virtual_history kopiju
        virtual_history = history.copy()
        
        # Pievieno PlantingRecord ar šo kandidātu start_year
        virtual_planting = PlantingRecord(
            field_id=field.id,
            year=start_year,
            crop=candidate_crop,
            owner_user_id=field.owner_user_id
        )
        virtual_history.append(virtual_planting)
        
        # Atlikušos (years-1) gadus izrēķina greedy ar recommend_for_field
        candidate_total_profit = first_profit  # Sāk ar aprēķināto 1. gada peļņu (float, neapaļotu)
        
        # Ja years > 1, simulē nākamos gadus
        if years > 1:
            for year_offset in range(1, years):
                target_year = start_year + year_offset
                
                # Iegūst ieteikumu šim gadam
                result = recommend_for_field(
                    field=field,
                    history=virtual_history,
                    crops_dict=crops_dict,
                    target_year=target_year,
                    preferred_crops=preferred_crops,
                    favorite_crops_filter=favorite_crops_filter,
                    include_crops_without_price=include_crops_without_price,
                    include_vegetables=include_vegetables,
                    allowed_groups=allowed_groups
                )
                
                if result['best_crop'] is not None:
                    # Aprēķina peļņu tieši, nevis izmanto result['best_profit']
                    year_crop_obj = crops_dict[result['best_crop']]
                    year_price_info = get_price_for_crop(year_crop_obj, prices_csv)
                    price_value, _source_label, _confidence = year_price_info
                    
                    # Atjauno kultūras cenu no price_info
                    crop_with_price = CropModel(
                        name=year_crop_obj.name,
                        group=year_crop_obj.group,
                        sow_months=year_crop_obj.sow_months,
                        yield_t_ha=year_crop_obj.yield_t_ha,
                        cost_eur_ha=year_crop_obj.cost_eur_ha,
                        price_eur_t=price_value,
                        is_market_crop=year_crop_obj.is_market_crop,
                        ph_range=year_crop_obj.ph_range
                    )
                    
                    # Iegūst nomas maksu
                    rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
                    
                    # Aprēķina peļņu izmantojot calculate_profit()
                    calc_result = calculate_profit(field, crop_with_price, rent_eur_ha=rent_eur_ha)
                    if calc_result is None:
                        break  # Izlaiž gadu, ja nav cenas vai ražas
                    year_profit = calc_result.profit_total
                    candidate_total_profit += year_profit
                    
                    # Pievieno virtuālu PlantingRecord history
                    virtual_planting = PlantingRecord(
                        field_id=field.id,
                        year=target_year,
                        crop=result['best_crop'],
                        owner_user_id=field.owner_user_id
                    )
                    virtual_history.append(virtual_planting)
        
        evaluated_candidates.append({
            'crop': candidate_crop,
            'total_profit': round(candidate_total_profit, 2)
        })
    
    # Sakārto kandidātus dilstoši pēc total_profit
    evaluated_candidates.sort(key=lambda x: x['total_profit'], reverse=True)
    
    # 4) Salīdzina kandidātus pēc kopējās peļņas
    # 5) Izvēlas kandidātu ar lielāko total_profit (pirmais sarakstā pēc sakārtošanas)
    best_candidate = evaluated_candidates[0]
    best_crop = best_candidate['crop']
    
    # Tagad izveido galīgo plānu ar izvēlēto kandidātu
    virtual_history = history.copy()
    plan = []
    total_profit = 0.0
    
    # 1. gads - izvēlētais kandidāts
    first_year_crop = crops_dict[best_crop]
    first_year_price_info = get_price_for_crop(first_year_crop, prices_csv)
    price_value, _source_label, _confidence = first_year_price_info
    
    # Atjauno kultūras cenu no price_info
    crop_with_price = CropModel(
        name=first_year_crop.name,
        group=first_year_crop.group,
        sow_months=first_year_crop.sow_months,
        yield_t_ha=first_year_crop.yield_t_ha,
        cost_eur_ha=first_year_crop.cost_eur_ha,
        price_eur_t=price_value,
        is_market_crop=first_year_crop.is_market_crop,
        ph_range=first_year_crop.ph_range
    )
    
    # Iegūst nomas maksu
    rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
    
    # Aprēķina peļņu izmantojot calculate_profit()
    calc_result = calculate_profit(field, crop_with_price, rent_eur_ha=rent_eur_ha)
    if calc_result is None:
        # Ja nav cenas vai ražas, atgriež tukšu rezultātu
        return {
            'best_crop': None,
            'best_profit': 0.0,
            'sow_months': [],
            'top3': [],
            'explanation': 'Nav iespējams aprēķināt peļņu - nav cenas vai ražas',
            'forbidden_crops': [],
            'lower_profit_crops': [],
            'crops_without_price': [],
            'excluded_by_price_validation': [],
            'reasons': []
        }
    first_year_profit = calc_result.profit_total
    first_year_profit_per_ha = calc_result.profit_per_ha
    total_profit += first_year_profit
    
    # Pievieno favorītu informāciju
    favorite_note = ""
    if preferred_crops and best_crop in preferred_crops:
        favorite_note = " (favorīts)"
    
    plan.append({
        "year": start_year,
        "crop": best_crop,
        "profit": round(calc_result.profit_total, 2),
        "profit_total": round(calc_result.profit_total, 2),
        "profit_per_ha": round(calc_result.profit_per_ha, 2),
        "revenue_total": round(calc_result.revenue_total, 2),
        "revenue_per_ha": round(calc_result.revenue_per_ha, 2),
        "cost_total": round(calc_result.cost_total, 2),
        "cost_per_ha": round(calc_result.cost_per_ha, 2),
        "sow_months": first_year_crop.sow_months,
        "explanation": f"Look-ahead izvēle (simulēta kopējā peļņa {best_candidate['total_profit']:.2f} EUR {years} gados){favorite_note}"
    })
    
    # Pievieno virtuālu PlantingRecord
    virtual_planting = PlantingRecord(
        field_id=field.id,
        year=start_year,
        crop=best_crop,
        owner_user_id=field.owner_user_id
    )
    virtual_history.append(virtual_planting)
    
    # Atlikušie gadi - greedy ar recommend_for_field
    # Ja years <= 1, nav jāveido cikli nākamajiem gadiem
    if years > 1:
        for year_offset in range(1, years):
            target_year = start_year + year_offset
            
            result = recommend_for_field(
                field=field,
                history=virtual_history,
                crops_dict=crops_dict,
                target_year=target_year,
                preferred_crops=preferred_crops,
                include_crops_without_price=include_crops_without_price,
                include_vegetables=include_vegetables,
                allowed_groups=allowed_groups
            )
            
            if result['best_crop'] is None:
                plan_entry = {
                    "year": target_year,
                    "crop": None,
                    "profit": 0.0,
                    "profit_per_ha": 0.0,
                    "sow_months": [],
                    "explanation": result.get('explanation', 'Nav atļautu kultūru')
                }
            else:
                # Izmanto profit_total un profit_per_ha no result
                profit_total = result.get('profit_total', result.get('best_profit', 0.0))
                profit_per_ha = result.get('profit_per_ha', profit_total / field.area_ha if field.area_ha > 0 else 0.0)
                total_profit += profit_total
                
                # Pievieno favorītu informāciju
                crop_note = ""
                if result.get('used_preference'):
                    crop_note = " (favorīts)"
                elif result.get('best_overall') and result['best_overall']['name'] != result['best_crop']:
                    crop_note = " (labākais kopumā)"
                
                plan_entry = {
                    "year": target_year,
                    "crop": result['best_crop'],
                    "profit": round(profit_total, 2),
                    "profit_total": round(profit_total, 2),
                    "profit_per_ha": round(profit_per_ha, 2),
                    "revenue_total": round(result.get('revenue_total', 0.0), 2),
                    "revenue_per_ha": round(result.get('revenue_per_ha', 0.0), 2),
                    "cost_total": round(result.get('cost_total', 0.0), 2),
                    "cost_per_ha": round(result.get('cost_per_ha', 0.0), 2),
                    "sow_months": result['sow_months'],
                    "explanation": result.get('explanation', '') + crop_note
                }
                
                # Pievieno virtuālu PlantingRecord
                virtual_planting = PlantingRecord(
                    field_id=field.id,
                    year=target_year,
                    crop=result['best_crop'],
                    owner_user_id=field.owner_user_id
                )
                virtual_history.append(virtual_planting)
            
            plan.append(plan_entry)
    
    # Aprēķina vidējo peļņu uz ha
    avg_profit_per_ha = total_profit / (field.area_ha * years) if field.area_ha > 0 and years > 0 else 0.0
    
    return {
        "field_id": field.id,
        "field_name": field.name,
        "start_year": start_year,
        "years": years,
        "plan": plan,
        "total_profit": round(total_profit, 2),
        "avg_profit_per_ha": round(avg_profit_per_ha, 2),
        "method": "lookahead",
        "evaluated_candidates": evaluated_candidates
    }


def recommend_for_all_fields_with_limits(
    fields: List[FieldModel],
    histories_by_field: Dict[int, List[PlantingRecord]],
    crops_dict: Dict[str, CropModel],
    target_year: int,
    max_area_per_crop: Dict[str, float],
    use_market_prices: bool = True,
    preferred_crops: Optional[List[str]] = None,
    favorite_crops_filter: Optional[set] = None,
    crop_group_filter: Optional[str] = None,
    favorites_plus_group: bool = False,
    include_crops_without_price: bool = False,
    include_vegetables: bool = False,
    allowed_groups: Optional[List[str]] = None
) -> List[Dict]:
    """
    Ieteic kultūras visiem laukiem kopā, respektējot maksimālo platību vienai kultūrai.
    
    Args:
        fields: Lauku saraksts
        histories_by_field: Vārdnīca ar field_id -> PlantingRecord sarakstu
        crops_dict: Kultūru vārdnīca (nosaukums -> CropModel)
        target_year: Gads, kurā plāno sēt
        max_area_per_crop: Vārdnīca ar kultūras nosaukumu -> maksimālā platība ha
        use_market_prices: Ja True, izmanto ES Agri-food Data Portal cenas
        preferred_crops: Priekšroku kultūru saraksts
        favorite_crops_filter: Favorītu kultūru filtra kopums
        crop_group_filter: Kultūru grupas filtrs
        favorites_plus_group: Vai izmantot favorītus + grupu
        include_crops_without_price: Vai iekļaut kultūras bez cenas
        include_vegetables: Vai iekļaut dārzeņus
        allowed_groups: Atļauto grupu saraksts
    
    Returns:
        Saraksts ar rezultātiem katram laukam:
        [
            {
                "field_id": int,
                "field_name": str,
                "chosen_crop": Optional[str],
                "profit": float,
                "profit_per_ha": float,
                "warnings": List[str]
            },
            ...
        ]
    """
    from .price_provider import get_price_for_crop
    from .sanity import validate_crop_numbers
    prices_csv = load_prices_csv()
    
    # Ielādē cenas ar fallback
    try:
        prices_with_fallback = load_prices_with_fallback()
    except ValueError as e:
        logging.error(f"Neizdevās ielādēt cenas: {e}")
        raise
    
    # Iegūst atjaunotās cenas no ES Agri-food Data Portal (ja vajag)
    if use_market_prices:
        market_prices = get_price_map()
    else:
        market_prices = {}
    
    # 1) Katram laukam aprēķina atļautās kultūras un peļņu
    field_candidates = {}  # field_id -> [(crop_name, profit, profit_per_ha), ...] sakārtots pēc peļņas
    
    for field in fields:
        field_id = field.id
        history = histories_by_field.get(field_id, [])
        
        # Filtrē kandidātus pirms rotācijas noteikumiem (līdzīgi kā recommend_for_field)
        available_crop_names = list(crops_dict.keys())
        filtered_candidates = []
        
        for crop_name in available_crop_names:
            crop = crops_dict[crop_name]
            
            # Pārbauda, vai ir sēšanas mēneši
            if not crop.sow_months or len(crop.sow_months) == 0:
                continue
            
            # Validācija ar sanity check
            warnings = validate_crop_numbers(crop, field.soil)
            
            # Hard fail: ignorē kultūru, ja yield_too_high VAI price_too_high
            if "yield_too_high" in warnings or "price_too_high" in warnings:
                continue
            
            filtered_candidates.append(crop_name)
        
        # Filtrē dārzeņus
        if not include_vegetables:
            filtered_candidates = [c for c in filtered_candidates if crops_dict[c].group != "Dārzeņi"]
        
        # Filtrē pēc allowed_groups
        if allowed_groups is not None and len(allowed_groups) > 0:
            allowed_groups_set = set(allowed_groups)
            filtered_candidates = [c for c in filtered_candidates if crops_dict[c].group in allowed_groups_set]
        
        # Filtrē pēc grupas
        if crop_group_filter:
            filtered_candidates = [c for c in filtered_candidates if crops_dict[c].group == crop_group_filter]
        
        # Filtrē pēc favorītiem
        if favorite_crops_filter:
            if favorites_plus_group and crop_group_filter:
                group_crops = filtered_candidates
                favorite_crops = [c for c in available_crop_names if c in favorite_crops_filter]
                filtered_candidates = list(set(group_crops + favorite_crops))
            else:
                filtered_candidates = [c for c in filtered_candidates if c in favorite_crops_filter]
        
        # Piemēro rotācijas noteikumus
        allowed_crops = get_allowed_crops(history, filtered_candidates, target_year, field_id)
        
        # Aprēķina peļņu katram kandidātam
        candidates = []
        for crop_name in allowed_crops:
            crop = crops_dict[crop_name]
            
            # Iegūst cenu (līdzīgi kā recommend_for_field)
            fallback_price = prices_with_fallback.get(crop_name, {}).get("price_eur_t")
            if fallback_price is None:
                fallback_price = crop.price_eur_t if hasattr(crop, 'price_eur_t') and crop.price_eur_t is not None else 0.0
            
            if use_market_prices:
                new_price = market_prices.get(crop_name, fallback_price)
            else:
                new_price = fallback_price
            
            # Atjauno kultūras cenu
            crop_with_price = CropModel(
                name=crop.name,
                group=crop.group,
                sow_months=crop.sow_months,
                yield_t_ha=crop.yield_t_ha,
                cost_eur_ha=crop.cost_eur_ha,
                price_eur_t=new_price,
                is_market_crop=crop.is_market_crop,
                ph_range=crop.ph_range
            )
            
            # Aprēķina peļņu
            rent_eur_ha = getattr(field, "rent_eur_ha", 0.0)
            calc_result = calculate_profit(field, crop_with_price, rent_eur_ha=rent_eur_ha)
            
            if calc_result is None:
                continue
            
            profit_total = calc_result.profit_total
            profit_per_ha = calc_result.profit_per_ha
            
            # Pārbauda pH un piemēro penalizāciju, ja nepieciešams
            field_ph = getattr(field, "ph", None)
            if field_ph is not None and crop.ph_range is not None:
                ph_min, ph_max = crop.ph_range
                if field_ph < ph_min or field_ph > ph_max:
                    ph_penalty = profit_total * 0.10
                    profit_total = profit_total - ph_penalty
                    profit_per_ha = profit_total / field.area_ha if field.area_ha > 0 else 0.0
            
            candidates.append((crop_name, profit_total, profit_per_ha))
        
        # Sakārto pēc peļņas (augošā secībā, lai varētu ņemt labāko)
        candidates.sort(key=lambda x: x[1], reverse=True)
        field_candidates[field_id] = candidates
    
    # 2) Greedy algoritms: izvēlas kultūras visiem laukiem
    results = []
    # Inicializē used_area_by_crop ar visām kultūrām no kataloga (nevis tikai no max_area_per_crop)
    all_crop_names_in_catalog = set(crops_dict.keys())
    used_area_by_crop = {crop: 0.0 for crop in all_crop_names_in_catalog}
    
    # Izveido lauku sarakstu ar "grūtības" punktiem (labākā un 2. labākā peļņas starpība)
    field_priorities = []
    for field_id, candidates in field_candidates.items():
        if len(candidates) >= 2:
            best_profit = candidates[0][1]
            second_profit = candidates[1][1]
            difficulty = best_profit - second_profit  # Jo mazāka starpība, jo grūtāk izvēlēties
        elif len(candidates) == 1:
            difficulty = 0.0  # Tikai viens variants
        else:
            difficulty = float('inf')  # Nav kandidātu
        
        field_priorities.append((field_id, difficulty, candidates))
    
    # Sakārto pēc grūtības (visgrūtākos pirmos)
    field_priorities.sort(key=lambda x: x[1])
    
    # Iterē laukus un izvēlas kultūras
    for field_id, difficulty, candidates in field_priorities:
        field = next(f for f in fields if f.id == field_id)
        chosen_crop = None
        chosen_profit = 0.0
        chosen_profit_per_ha = 0.0
        warnings = []
        
        # Mēģina izvēlēties kandidātu, kas nepārsniedz limitu
        for crop_name, profit, profit_per_ha in candidates:
            max_area = max_area_per_crop.get(crop_name, float('inf'))
            current_area = used_area_by_crop.get(crop_name, 0.0)
            
            if current_area + field.area_ha <= max_area:
                # Derīgs kandidāts
                chosen_crop = crop_name
                chosen_profit = profit
                chosen_profit_per_ha = profit_per_ha
                used_area_by_crop[crop_name] = current_area + field.area_ha
                break
        
        # Ja neviens kandidāts neder, izvēlas labāko un pievieno brīdinājumu
        if chosen_crop is None and candidates:
            crop_name, profit, profit_per_ha = candidates[0]
            chosen_crop = crop_name
            chosen_profit = profit
            chosen_profit_per_ha = profit_per_ha
            max_area = max_area_per_crop.get(crop_name, float('inf'))
            current_area = used_area_by_crop.get(crop_name, 0.0)
            warnings.append(f"Kultūra '{crop_name}' pārsniedz maksimālo platību ({max_area:.1f} ha). Pašreizējā platība: {current_area + field.area_ha:.1f} ha")
            used_area_by_crop[crop_name] = current_area + field.area_ha
        
        results.append({
            "field_id": field_id,
            "field_name": field.name,
            "chosen_crop": chosen_crop,
            "profit": round(chosen_profit, 2),
            "profit_per_ha": round(chosen_profit_per_ha, 2),
            "warnings": warnings
        })
    
    return results


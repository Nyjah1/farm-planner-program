"""
Kombinētais cenu piegādātājs: ES tirgus dati, lokālās cenas un atvasinātās cenas.
"""
import sys
import io
import os
from typing import Dict, List, Any, Tuple, Optional

# Iestatīt UTF-8 kodējumu Windows sistēmām
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from .market_prices import (
    get_latest_prices_for_catalog,
    calculate_price_volatility,
    risk_level_from_volatility,
)
from .local_prices import load_local_prices
from .models import CropModel
import json
from pathlib import Path
from functools import lru_cache


def get_prices_for_catalog(crop_names: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Atgriež cenas norādītajām kultūrām, dodot priekšroku ES tirgus cenām.

    Loģika:
    1) Mēģina ielādēt ES cenas (market_prices.get_latest_prices_for_catalog)
    2) Ielādē lokālās cenas (local_prices.load_local_prices)
    3) Katram crop_name:
       - Ja ir ES cena -> izmanto to, source = "EU market"
       - Citādi, ja ir lokālā cena -> izmanto to, source = "Local statistics"
       - Citādi -> neiekļauj (planner fallback uz crops.json)

    Returns:
        Dict ar kultūras nosaukumu -> {price_eur_t, volatility_pct, risk_level, source, as_of}
    """
    result: Dict[str, Dict[str, Any]] = {}

    # 1) ES cenas
    try:
        eu_prices = get_latest_prices_for_catalog(crop_names) or {}
    except Exception as e:
        print(f"[WARN] Neizdevās ielādēt ES cenas: {e}")
        eu_prices = {}

    # 2) Lokālās cenas (fallback)
    try:
        local_prices = load_local_prices() or {}
    except Exception as e:
        print(f"[WARN] Neizdevās ielādēt lokālās cenas: {e}")
        local_prices = {}

    # 3) Ielādē price_proxy no crops.json (bāzes kataloga), ja vajag
    base_catalog = {}
    proxy_map = {}
    try:
        crops_file = Path("data/crops.json")
        if crops_file.exists():
            with open(crops_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("name")
                        if not name:
                            continue
                        base_catalog[name] = item.get("price_eur_t")
                        proxy_map[name] = item.get("price_proxy")
    except Exception as e:
        print(f"[WARN] Nevar nolasīt price_proxy no crops.json: {e}")
        base_catalog = {}
        proxy_map = {}

    # 4) Kombinēšana ar prioritāti ES datiem
    for name in crop_names:
        volatility = None
        risk_level = "nezināms"

        if name in eu_prices:
            info = eu_prices[name]
            # Nav vēstures datu; atstājam vol/risk pēc noklusējuma
            result[name] = {
                "price_eur_t": info.get("price_eur_t"),
                "volatility_pct": volatility,
                "risk_level": risk_level,
                "source": "EU market",
                "as_of": info.get("as_of"),
            }
        elif name in local_prices:
            info = local_prices[name]
            # Nav vēstures datu; atstājam vol/risk pēc noklusējuma
            result[name] = {
                "price_eur_t": info.get("price_eur_t"),
                "volatility_pct": volatility,
                "risk_level": risk_level,
                "source": "Local statistics",
                "as_of": info.get("as_of"),
            }
        else:
            # Proxy cena, ja ir price_proxy
            proxy = proxy_map.get(name)
            proxy_price = None
            proxy_source = None
            if proxy:
                # Mēģina paņemt cenu no jau atrastajām cenām
                if proxy in eu_prices:
                    proxy_price = eu_prices[proxy].get("price_eur_t")
                    proxy_source = "EU market"
                elif proxy in local_prices:
                    proxy_price = local_prices[proxy].get("price_eur_t")
                    proxy_source = "Local statistics"
                elif proxy in base_catalog:
                    proxy_price = base_catalog.get(proxy)
                    proxy_source = "Local catalog"

            if proxy_price is not None:
                result[name] = {
                    "price_eur_t": proxy_price,
                    "volatility_pct": volatility,
                    "risk_level": risk_level,
                    "source": "Proxy price",
                    "as_of": None,
                    "proxy_of": proxy,
                    "note": "Cena aprēķināta no līdzīgas kultūras",
                }
            else:
                # Nav cenas un nav proxy
                result[name] = {
                    "price_eur_t": 0,
                    "volatility_pct": volatility,
                    "risk_level": risk_level,
                    "source": "Nav cenas",
                    "as_of": None,
                }

    return result


@lru_cache()
def _load_base_catalog() -> Dict[str, Dict[str, Any]]:
    """
    Nolasa bāzes katalogu no crops.json, lai iegūtu grupas un kataloga cenas.
    """
    catalog: Dict[str, Dict[str, Any]] = {}
    try:
        crops_file = Path("data/crops.json")
        if not crops_file.exists():
            return catalog

        with crops_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return catalog

        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            group = item.get("group")
            price = item.get("price_eur_t")
            if not name or not group:
                continue
            catalog[name] = {
                "group": group,
                "price_eur_t": price,
            }
    except Exception as e:
        print(f"[WARN] Neizdevās nolasīt bāzes katalogu no crops.json: {e}")
    return catalog


def _group_average_price(
    target_group: str,
    prices_csv: Dict[str, Dict[str, Any]],
) -> Optional[float]:
    """
    Aprēķina grupas vidējo cenu (no citu tās pašas grupas kultūru cenām).

    Prioritāte:
    - Ja ir cena CSV (LV cenas) -> izmanto to
    - Citādi, ja ir kataloga cena (price_eur_t > 0) -> izmanto to
    """
    base_catalog = _load_base_catalog()
    values: List[float] = []

    for name, info in base_catalog.items():
        if info.get("group") != target_group:
            continue

        price_value: Optional[float] = None

        # 1) Mēģina paņemt cenu no CSV
        csv_row = prices_csv.get(name)
        if csv_row is not None:
            raw = csv_row.get("price_eur_t")
            try:
                price_value = float(raw)
            except (TypeError, ValueError):
                price_value = None

        # 2) Ja nav CSV cenas, izmanto kataloga cenu (>0)
        if price_value is None:
            base_price = info.get("price_eur_t")
            if isinstance(base_price, (int, float)) and base_price > 0:
                price_value = float(base_price)

        if price_value is not None:
            values.append(price_value)

    if not values:
        return None
    return sum(values) / len(values)


def get_price_for_crop(
    crop: CropModel,
    prices_csv: Dict[str, Dict[str, Any]],
) -> Tuple[float, str, str]:
    """
    Atgriež cenu vienai kultūrai ar avota aprakstu un pārliecības līmeni.

    Prioritāte:
    1) Ja prices_csv satur crop.name ar price_eur_t:
       - confidence = "high"
       - source_label = "LV cenu fails"
    2) Citādi, ja crop.price_eur_t > 0 (kataloga cena):
       - confidence = "medium"
       - source_label = "Kultūru katalogs"
    3) Citādi:
       - confidence = "low"
       - source_label = "Grupas vidējā cena"
       - cena = vidējā no citu šīs grupas kultūru cenām

    Funkcija nekad neatgriež None cenai – ja nav datu, atgriež 0.0.
    """
    name = crop.name

    # 1) LV cenu fails (CSV)
    csv_row = prices_csv.get(name)
    if csv_row is not None:
        raw = csv_row.get("price_eur_t")
        try:
            price_value = float(raw)
            return price_value, "LV cenu fails", "high"
        except (TypeError, ValueError):
            pass

    # 2) Kataloga cena, ja ir > 0
    if isinstance(crop.price_eur_t, (int, float)) and crop.price_eur_t > 0:
        return float(crop.price_eur_t), "Kultūru katalogs", "medium"

    # 3) Grupas vidējā cena (no citām kultūrām tajā pašā grupā)
    avg_price = _group_average_price(crop.group, prices_csv)
    if avg_price is not None:
        return avg_price, "Grupas vidējā cena", "low"

    # Galējais fallback – nav datu, bet cena nedrīkst būt None
    return 0.0, "Grupas vidējā cena", "low"



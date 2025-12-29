"""
Lokālās (fallback) cenu ielāde no data/local_prices.json.
"""
import json
from pathlib import Path
from typing import Dict, Any


def load_local_prices() -> Dict[str, Dict[str, Any]]:
    """
    Nolasa lokālās cenas no data/local_prices.json.

    Returns:
        Dict ar kultūras nosaukumu -> {price_eur_t, source, as_of}
        Ja fails nav vai ir kļūda, atgriež tukšu dict.
    """
    path = Path("data/local_prices.json")
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Nevar nolasīt local_prices.json: {e}")
        return {}

    if not isinstance(data, dict):
        print("[WARN] local_prices.json nav dict formātā.")
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for crop_name, info in data.items():
        # Ignorē komentārus vai metadatus
        if isinstance(crop_name, str) and crop_name.startswith("_"):
            continue

        if not isinstance(info, dict):
            continue

        price = info.get("price_eur_t")
        if not isinstance(price, (int, float)):
            continue  # pamata validācija: jābūt skaitlim

        result[crop_name] = {
            "price_eur_t": float(price),
            "source": info.get("source"),
            "as_of": info.get("as_of"),
        }

    return result


import csv
import json
from pathlib import Path
from typing import Dict


def load_prices_csv(path: str = "data/prices_lv.csv") -> Dict[str, Dict]:
    """
    Nolasa cenas no CSV un atgriež dict:
    {
        "Kvieši": {
            "price_eur_t": 210.0,
            "source_type": "manual" | "market" | "proxy",
            "source_name": "User input" | "Euronext" | "Derived from wheat",
            "date": "2025-12-23" | None
        },
        ...
    }

    Noteikumi:
    - Ja price_eur_t nav skaitlis, konkrēto kultūru neiekļauj rezultātā.
    - Ja source_type nav norādīts, noklusējuma vērtība ir "manual" (backward compatibility).
    """
    prices: Dict[str, Dict] = {}
    csv_path = Path(path)

    if not csv_path.exists():
        return prices

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("crop_name") or "").strip()
            price_raw = (row.get("price_eur_t") or "").strip()
            source_type = (row.get("source_type") or "").strip()
            source_name = (row.get("source_name") or "").strip()
            date = (row.get("date") or "").strip()

            if not name:
                continue

            # Mēģina pārvērst cenu par float; ja neizdodas, izlaiž šo ierakstu
            try:
                price_value = float(price_raw)
            except (TypeError, ValueError):
                continue

            # Backward compatibility: ja nav source_type, noklusējuma vērtība ir "manual"
            if not source_type:
                source_type = "manual"
            
            # Backward compatibility: ja nav source_name, izmanto noklusējuma vērtības
            if not source_name:
                if source_type == "manual":
                    source_name = "User input"
                elif source_type == "market":
                    source_name = "Market data"
                elif source_type == "proxy":
                    source_name = "Derived price"
                else:
                    source_name = "Unknown"

            prices[name] = {
                "price_eur_t": price_value,
                "source_type": source_type,
                "source_name": source_name,
                "date": date if date else None,
            }

    return prices


def load_prices_with_fallback(csv_path: str = "data/prices_lv.csv", crops_json_path: str = "data/crops.json") -> Dict[str, Dict]:
    """
    Ielādē cenas ar fallback loģiku: CSV > crops.json.
    
    Prioritāte:
    1) Ja cena ir CSV → izmanto to (source_type="manual"|"market"|"proxy" no CSV)
    2) Ja CSV nav, bet crops.json ir price_eur_t → izmanto to (source_type="proxy", source_name="Derived from catalog")
    3) Ja nav nekur → atgriež None (nav cenas)
    
    Args:
        csv_path: Ceļš uz prices_lv.csv
        crops_json_path: Ceļš uz crops.json
    
    Returns:
        Dict ar struktūru:
        {
            "Kvieši": {
                "price_eur_t": 210.0,
                "source_type": "market" | "proxy" | "manual",
                "source_name": "Euronext" | "Derived from wheat" | "User input",
                "date": "2025-12-23" | None
            },
            ...
        }
        
        Ja kultūrai nav cenas, tā nav iekļauta rezultātā.
    """
    # 1) Ielādē cenas no CSV
    csv_prices = load_prices_csv(csv_path)
    
    # 2) Ielādē kultūras no crops.json
    crops_json_path_obj = Path(crops_json_path)
    crops_data = []
    
    if crops_json_path_obj.exists():
        try:
            with open(crops_json_path_obj, 'r', encoding='utf-8') as f:
                crops_data = json.load(f)
                if not isinstance(crops_data, list):
                    crops_data = []
        except Exception as e:
            print(f"[WARN] Neizdevās nolasīt crops.json: {e}")
            crops_data = []
    
    # 3) Izveido gala dict
    result: Dict[str, Dict] = {}
    
    # Vispirms pievieno visas kultūras no crops.json (lai zinātu, kuras kultūras eksistē)
    crops_dict = {}
    for crop in crops_data:
        crop_name = crop.get('name', '').strip()
        if crop_name:
            crops_dict[crop_name] = crop
    
    # Tagad apstrādā katru kultūru
    for crop_name in crops_dict.keys():
        # Prioritāte 1: CSV
        if crop_name in csv_prices:
            csv_info = csv_prices[crop_name]
            result[crop_name] = {
                "price_eur_t": csv_info["price_eur_t"],
                "source_type": csv_info.get("source_type", "manual"),
                "source_name": csv_info.get("source_name", "User input"),
                "date": csv_info.get("date")
            }
        else:
            # Prioritāte 2: crops.json
            crop = crops_dict[crop_name]
            price_eur_t = crop.get('price_eur_t') or crop.get('prices_eur_t')
            
            if price_eur_t is not None and price_eur_t != 0:
                try:
                    price_float = float(price_eur_t)
                    result[crop_name] = {
                        "price_eur_t": price_float,
                        "source_type": "proxy",
                        "source_name": "Derived from catalog",
                        "date": None
                    }
                except (TypeError, ValueError):
                    # Cena nav derīgs skaitlis - neiekļauj rezultātā
                    pass
            # Ja nav cenas nekur, neiekļauj rezultātā (nevis atgriež 0.0)
    
    return result


def save_price_to_csv(crop_name: str, price_eur_t: float, source_type: str = "manual", source_name: str = "User input", date: str = None, csv_path: str = "data/prices_lv.csv") -> bool:
    """
    Saglabā vai atjauno cenu CSV failā.
    
    Args:
        crop_name: Kultūras nosaukums
        price_eur_t: Cena EUR/t
        source_type: "manual" | "market" | "proxy"
        source_name: Avota nosaukums
        date: Datums (YYYY-MM-DD) vai None
        csv_path: Ceļš uz CSV failu
    
    Returns:
        True, ja saglabāšana veiksmīga, False citādi
    """
    from datetime import datetime
    
    csv_file = Path(csv_path)
    
    # Ielādē esošās cenas
    existing_prices = load_prices_csv(csv_path)
    
    # Atjauno vai pievieno jaunu cenu
    existing_prices[crop_name] = {
        "price_eur_t": float(price_eur_t),
        "source_type": source_type,
        "source_name": source_name,
        "date": date if date else datetime.now().strftime("%Y-%m-%d")
    }
    
    # Saglabā CSV failu
    try:
        # Izveido direktoriju, ja neeksistē
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Raksta CSV ar visām cenām
        with csv_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["crop_name", "price_eur_t", "source_type", "source_name", "date"])
            writer.writeheader()
            
            for name, price_info in existing_prices.items():
                writer.writerow({
                    "crop_name": name,
                    "price_eur_t": price_info["price_eur_t"],
                    "source_type": price_info.get("source_type", "manual"),
                    "source_name": price_info.get("source_name", "User input"),
                    "date": price_info.get("date", "")
                })
        
        return True
    except Exception as e:
        print(f"[ERROR] Neizdevās saglabāt cenu: {e}")
        return False


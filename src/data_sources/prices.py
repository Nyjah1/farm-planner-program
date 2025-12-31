import csv
import json
from pathlib import Path
from typing import Dict


def load_prices_csv(path: str = "data/prices.csv") -> Dict[str, float]:
    """
    Nolasa kultūru cenas no CSV faila.
    
    CSV formāts: crop,price_eur_t (ar header rindu)
    
    Args:
        path: Ceļš uz CSV failu
    
    Returns:
        Vārdnīca: kultūras nosaukums -> cena eiro/t
    
    Raises:
        FileNotFoundError: Ja fails nav atrasts
        ValueError: Ja fails nav derīgs
    """
    prices_path = Path(path)
    if not prices_path.exists():
        raise FileNotFoundError(f"CSV fails nav atrasts: {path}")
    
    prices = {}
    try:
        with open(prices_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                crop = row['crop'].strip()
                try:
                    price = float(row['price_eur_t'].strip())
                    prices[crop] = price
                except (ValueError, KeyError) as e:
                    raise ValueError(f"Kļūda CSV rindā: {row} - {e}")
    except Exception as e:
        raise ValueError(f"Neizdevās nolasīt CSV failu: {e}")
    
    return prices


def load_prices_fallback(path: str = "data/crops.json") -> Dict[str, float]:
    """
    Nolasa kultūru cenas no crops.json faila (fallback variants).
    
    Args:
        path: Ceļš uz crops.json failu
    
    Returns:
        Vārdnīca: kultūras nosaukums -> cena eiro/t
    
    Raises:
        FileNotFoundError: Ja fails nav atrasts
        ValueError: Ja fails nav derīgs
    """
    crops_path = Path(path)
    if not crops_path.exists():
        raise FileNotFoundError(f"JSON fails nav atrasts: {path}")
    
    prices = {}
    try:
        with open(crops_path, 'r', encoding='utf-8') as f:
            crops_data = json.load(f)
        
        for crop_data in crops_data:
            crop_name = crop_data.get('name', '').strip()
            price = crop_data.get('price_eur_t')
            
            if not crop_name:
                continue
            
            if price is None:
                raise ValueError(f"Kultūrai '{crop_name}' nav norādīta cena")
            
            try:
                prices[crop_name] = float(price)
            except (ValueError, TypeError):
                raise ValueError(f"Kultūrai '{crop_name}' nepareiza cenas vērtība: {price}")
    
    except json.JSONDecodeError as e:
        raise ValueError(f"Neizdevās parsēt JSON failu: {e}")
    except Exception as e:
        raise ValueError(f"Neizdevās nolasīt JSON failu: {e}")
    
    return prices


def get_prices() -> Dict[str, float]:
    """
    Iegūst kultūru cenas no pieejamā avota.
    
    Mēģina nolasīt no CSV faila, ja tas nav pieejams, 
    tad izmanto fallback uz crops.json.
    
    Returns:
        Vārdnīca: kultūras nosaukums -> cena eiro/t
    
    Raises:
        FileNotFoundError: Ja nav pieejams neviens avots
        ValueError: Ja dati nav derīgi
    """
    # Mēģina nolasīt no CSV
    try:
        return load_prices_csv()
    except FileNotFoundError:
        # Ja CSV nav, izmanto fallback uz crops.json
        try:
            return load_prices_fallback()
        except FileNotFoundError:
            raise FileNotFoundError(
                "Nav atrasts ne CSV fails (data/prices.csv), "
                "ne JSON fails (data/crops.json)"
            )


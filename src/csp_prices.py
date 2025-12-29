"""
CSP LAC020 cenu ielādes modulis.

Nolasa CSP LAC020 CSV failu un atgriež cenas pēdējam pieejamajam gadam.
"""
import csv
import re
from pathlib import Path
from typing import Dict, Any, Optional


def load_csp_prices(path: str = "data/csp_LAC020.csv") -> Dict[str, Any]:
    """
    Nolasa CSP LAC020 CSV failu un atgriež cenas pēdējam pieejamajam gadam.
    
    Args:
        path: Ceļš uz CSV failu
        
    Returns:
        Dict ar:
        - meta: {"source": "CSP LAC020", "year": int}
        - prices: {crop_name: {"price_eur_t": float, "source_type": "csp", "source_name": "CSP LAC020", "year": int}}
    """
    csv_path = Path(path)
    
    if not csv_path.exists():
        return {
            "meta": {"source": "CSP LAC020", "year": None},
            "prices": {}
        }
    
    prices = {}
    latest_year = None
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            
            # Izlaiž pirmo rindu (nosaukums)
            next(reader, None)
            
            # Izlaiž otro rindu (tukša)
            next(reader, None)
            
            # Nolasa header (3. rinda)
            header = next(reader, None)
            if not header:
                return {
                    "meta": {"source": "CSP LAC020", "year": None},
                    "prices": {}
                }
            
            # Atrod pēdējo gadu (pēdējā kolonna ar skaitli)
            year_columns = []
            for idx, col in enumerate(header):
                # Noņem citātus, ja ir
                col_clean = col.strip('"')
                # Mēģina atrast gadu (4 cipari)
                year_match = re.search(r'\b(20\d{2})\b', col_clean)
                if year_match:
                    year = int(year_match.group(1))
                    year_columns.append((idx, year))
            
            if not year_columns:
                return {
                    "meta": {"source": "CSP LAC020", "year": None},
                    "prices": {}
                }
            
            # Pēdējais gads ir pēdējā kolonna ar gadu
            latest_year_col_idx, latest_year = year_columns[-1]
            
            # Nolasa datus
            for row in reader:
                if not row or len(row) <= latest_year_col_idx:
                    continue
                
                # Pirmā kolonna ir kultūras nosaukums
                crop_name = row[0].strip('"').strip()
                if not crop_name:
                    continue
                
                # Cena no pēdējās kolonnas ar gadu
                price_str = row[latest_year_col_idx].strip('"').strip()
                
                # Izlaiž, ja cena ir "…" vai tukša
                if not price_str or price_str == "…" or price_str == "...":
                    continue
                
                # Mēģina pārveidot uz float
                try:
                    price_eur_t = float(price_str.replace(',', '.'))
                except (ValueError, AttributeError):
                    continue
                
                # Saglabā cenu
                prices[crop_name] = {
                    "price_eur_t": price_eur_t,
                    "source_type": "csp",
                    "source_name": "CSP LAC020",
                    "year": latest_year
                }
        
        return {
            "meta": {
                "source": "CSP LAC020",
                "year": latest_year
            },
            "prices": prices
        }
    
    except Exception as e:
        # Ja ir kļūda, atgriež tukšu rezultātu
        print(f"Kļūda ielādējot CSP cenas: {e}")
        return {
            "meta": {"source": "CSP LAC020", "year": None},
            "prices": {}
        }


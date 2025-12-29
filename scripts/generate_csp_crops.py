"""
Skripts, kas ģenerē data/crops_csp.json no CSP LAC020 CSV faila.
"""
import sys
from pathlib import Path

# Pievieno src direktoriju ceļam
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.csp_prices import load_csp_prices
from src.crop_groups import is_vegetable


def determine_group(crop_name: str) -> str:
    """
    Nosaka kultūras grupu pēc nosaukuma.
    Izmanto is_vegetable() lai noteiktu dārzeņus.
    Atgriež None, ja kultūra nav atpazīta (tiks izslēgta).
    """
    # Pārbauda, vai kultūra ir dārzenis
    if is_vegetable(crop_name):
        return "Dārzeņi"
    
    name_lower = crop_name.lower()
    
    # Eļļaugi
    if "rapša" in name_lower or "rapsis" in name_lower:
        return "Eļļaugi"
    
    # Graudaugi
    if any(word in name_lower for word in ["graudi", "kvieši", "mieži", "auzas", "rudzi", "tritikāle", "griķi"]):
        return "Graudaugi"
    
    # Pākšaugi
    if any(word in name_lower for word in ["pākšaugi", "zirņi", "pupas", "lupīnas", "soja"]):
        return "Pākšaugi"
    
    # Nav atpazīta - tiks izslēgta
    return None


def should_exclude_crop(crop_name: str) -> bool:
    """
    Pārbauda, vai kultūra jāizslēdz (gaļa, piens, olas, vilna, ogas).
    """
    name_lower = crop_name.lower()
    exclude_keywords = [
        'gaļa', 'pien', 'ola', 'vilna',
        'zemenes', 'avenes', 'upenes', 'plūmes', 'ķirši'
    ]
    return any(keyword in name_lower for keyword in exclude_keywords)


def generate_csp_crops(output_path: str = "data/crops_csp.json"):
    """
    Ģenerē crops_csp.json no CSP LAC020 CSV faila.
    """
    # Ielādē CSP cenas
    csp_data = load_csp_prices()
    csp_prices = csp_data.get("prices", {})
    csp_year = csp_data.get("meta", {}).get("year")
    
    if not csp_prices:
        print("Nav atrastu CSP cenu")
        return
    
    # Izveido crops_csp sarakstu
    crops_csp = []
    for crop_name, price_info in csp_prices.items():
        # Izslēdz gaļu, pienu, olas, vilnu un ogas
        if should_exclude_crop(crop_name):
            continue
        
        price_eur_t = price_info.get("price_eur_t")
        if price_eur_t is None or price_eur_t <= 0:
            continue
        
        group = determine_group(crop_name)
        
        # Izslēdz kultūras, kurām nav noteikta grupa (t.i., "Citi")
        if group is None:
            continue
        
        crop_entry = {
            "name": crop_name,
            "group": group,
            "sow_months": [],
            "yield_t_ha": {},
            "cost_eur_ha": 0,
            "price_eur_t": price_eur_t,
            "is_market_crop": True
        }
        
        crops_csp.append(crop_entry)
    
    # Saglabā JSON failu
    import json
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(crops_csp, f, ensure_ascii=False, indent=2)
    
    print(f"Ģenerēts crops_csp.json ar {len(crops_csp)} kultūrām no CSP {csp_year}")
    print(f"Saglabāts: {output_file}")


if __name__ == "__main__":
    generate_csp_crops()


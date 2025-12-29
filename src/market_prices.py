"""
ES Agri-food Data Portal cenu ielāde un kešošana.
"""
import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


# ES Agri-food Data Portal API base URL
API_BASE_URL = "https://agridata.ec.europa.eu/api/cereal"
CACHE_FILE = Path("data/cache_prices.json")
CACHE_DURATION_HOURS = 24
REQUEST_TIMEOUT = 15


class APIError(Exception):
    """Kļūda, kad API nav sasniedzams."""
    pass


def parse_price_to_float(s: str) -> float:
    """
    Pārvērš cenu no "172,00" uz 172.0.
    
    Args:
        s: Cenas virkne ar komatu kā decimālo atdalītāju
    
    Returns:
        Float vērtība
    """
    if not s:
        return 0.0
    
    # Aizvieto komatu ar punktu un pārvērš uz float
    try:
        return float(s.replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0


@lru_cache(maxsize=1)
def fetch_cereal_products() -> List[Dict]:
    """
    Iegūst graudaugu produktu sarakstu no ES Agri-food Data Portal API.
    
    Returns:
        List ar produktu dict objektiem
    
    Raises:
        APIError: Ja API nav sasniedzams
    """
    url = f"{API_BASE_URL}/products"
    
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Izmet exception, ja status nav 200
        return response.json()
    except requests.exceptions.Timeout:
        raise APIError(f"API pieprasījums pārsniedza laika limitu ({REQUEST_TIMEOUT}s): {url}")
    except requests.exceptions.ConnectionError:
        raise APIError(f"Nevar izveidot savienojumu ar API: {url}")
    except requests.exceptions.HTTPError as e:
        raise APIError(f"API atgrieza HTTP kļūdu {e.response.status_code}: {url}")
    except requests.exceptions.RequestException as e:
        raise APIError(f"API pieprasījuma kļūda: {str(e)}")
    except (ValueError, json.JSONDecodeError) as e:
        raise APIError(f"Nevar parsēt API atbildi kā JSON: {str(e)}")


def fetch_cereal_prices(
    product_codes: List[str],
    begin_date: str,
    end_date: str
) -> List[Dict]:
    """
    Iegūst graudaugu cenas no ES Agri-food Data Portal API.
    
    Args:
        product_codes: Produktu kodu saraksts (piem., ["C1100", "C1200"])
        begin_date: Sākuma datums formātā "dd/mm/yyyy"
        end_date: Beigu datums formātā "dd/mm/yyyy"
    
    Returns:
        List ar cenu dict objektiem
    
    Raises:
        APIError: Ja API nav sasniedzams
    """
    url = f"{API_BASE_URL}/prices"
    
    # Sagatavo parametrus
    params = {
        'productCodes': ','.join(product_codes),
        'beginDate': begin_date,
        'endDate': end_date
    }
    
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Izmet exception, ja status nav 200
        return response.json()
    except requests.exceptions.Timeout:
        raise APIError(f"API pieprasījums pārsniedza laika limitu ({REQUEST_TIMEOUT}s): {url}")
    except requests.exceptions.ConnectionError:
        raise APIError(f"Nevar izveidot savienojumu ar API: {url}")
    except requests.exceptions.HTTPError as e:
        raise APIError(f"API atgrieza HTTP kļūdu {e.response.status_code}: {url}")
    except requests.exceptions.RequestException as e:
        raise APIError(f"API pieprasījuma kļūda: {str(e)}")
    except (ValueError, json.JSONDecodeError) as e:
        raise APIError(f"Nevar parsēt API atbildi kā JSON: {str(e)}")


def _load_cache() -> Optional[Dict]:
    """Ielādē kešu no faila."""
    if not CACHE_FILE.exists():
        return None
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Pārbauda, vai kešs nav novecojis
        cached_time_str = cache_data.get('timestamp')
        if cached_time_str:
            cached_time = datetime.fromisoformat(cached_time_str)
            if datetime.now() - cached_time < timedelta(hours=CACHE_DURATION_HOURS):
                return cache_data
        
        return None
    except Exception:
        return None


def _save_cache(price_map: Dict[str, float], timestamp: datetime) -> None:
    """Saglabā kešu failā."""
    # Izveido direktoriju, ja neeksistē
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    cache_data = {
        'timestamp': timestamp.isoformat(),
        'prices': price_map
    }
    
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # Neizmet kļūdu, ja nevar saglabāt kešu


def _load_fallback_prices() -> Dict[str, float]:
    """
    Ielādē cenas no crops.json kā fallback.
    
    Returns:
        Dict ar kultūru nosaukumiem un cenām
    """
    crops_file = Path("data/crops.json")
    if not crops_file.exists():
        return {}
    
    try:
        with open(crops_file, 'r', encoding='utf-8') as f:
            crops_data = json.load(f)
        
        price_map = {}
        for crop_data in crops_data:
            name = crop_data.get('name')
            price = crop_data.get('price_eur_t')
            if name and price:
                price_map[name] = float(price)
        
        return price_map
    except Exception:
        return {}


def get_price_map() -> Dict[str, float]:
    """
    Iegūst cenu kartējumu no ES Agri-food Data Portal vai fallback.
    
    Returns:
        Dict ar kultūru nosaukumiem un cenām: {"Kvieši": 210.0, "Mieži": 195.0, ...}
    """
    # 1) Pārbauda kešu
    cache_data = _load_cache()
    if cache_data:
        return cache_data.get('prices', {})
    
    # 2) Mēģina iegūt cenas no API
    price_map = {}
    fallback_prices = _load_fallback_prices()
    
    # Ja nav fallback, atgriež tukšu dict
    if not fallback_prices:
        return {}
    
    # 3) Saglabā kešu ar fallback cenām
    if fallback_prices:
        _save_cache(fallback_prices, datetime.now())
    
    return fallback_prices


def get_price_update_time() -> Optional[datetime]:
    """
    Atgriež keša atjaunošanas laiku.
    
    Returns:
        Datetime vai None, ja nav keša
    """
    cache_data = _load_cache()
    if cache_data and cache_data.get('timestamp'):
        try:
            return datetime.fromisoformat(cache_data['timestamp'])
        except Exception:
            return None
    return None


def calculate_price_volatility(prices: List[float]) -> float:
    """
    Aprēķina cenu svārstīgumu procentos.

    Loģika:
    - Ja mazāk par 3 cenām, atgriež 0 (nav pietiekami datu)
    - (max - min) / average * 100, noapaļots līdz 1 zīmei
    """
    if not prices or len(prices) < 3:
        return 0.0

    max_p = max(prices)
    min_p = min(prices)
    avg_p = sum(prices) / len(prices)
    if avg_p == 0:
        return 0.0

    vol = (max_p - min_p) / avg_p * 100
    return round(vol, 1)


def risk_level_from_volatility(volatility: float) -> str:
    """
    Atgriež riska līmeni pēc svārstīguma.
    """
    if volatility < 5:
        return "zems"
    if volatility <= 12:
        return "vidējs"
    return "augsts"


def get_price_history(crop_name: str) -> List[Tuple[str, float]]:
    """
    Iegūst cenas vēsturi vienai kultūrai (pēdējās ~90 dienas).

    Returns:
        Saraksts ar (datums YYYY-MM-DD, cena) pāriem. Ja nav datu, atgriež tukšu sarakstu.
    """
    try:
        # 1) Atrod produkta kodu
        product_map = _build_product_name_to_code_map()
        if not product_map:
            return []

        code = _find_product_code_for_crop(crop_name, product_map)
        if not code:
            return []

        # 2) Datumu diapazons ~90 dienas
        end_date = datetime.now()
        begin_date = end_date - timedelta(days=90)
        begin_date_str = begin_date.strftime("%d/%m/%Y")
        end_date_str = end_date.strftime("%d/%m/%Y")

        # 3) Ielādē cenas
        prices = fetch_cereal_prices([code], begin_date_str, end_date_str)
        if not prices:
            return []

        history: List[Tuple[str, float]] = []

        for p in prices:
            # atlasīt tikai ierakstus ar atbilstošu produktu kodu
            p_code = str(p.get("productCode") or p.get("ProductCode") or p.get("code") or "")
            if p_code != str(code):
                continue

            date_str = (
                p.get("endDate")
                or p.get("EndDate")
                or p.get("date")
                or p.get("Date")
                or p.get("asOf")
                or p.get("AsOf")
            )
            if not date_str:
                continue

            # Parsē datumu
            date_iso = None
            try:
                if "/" in date_str:
                    date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
                elif "-" in date_str and len(date_str) >= 10:
                    date_iso = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
            except Exception:
                continue

            if not date_iso:
                continue

            price_val = (
                p.get("price")
                or p.get("Price")
                or p.get("value")
                or p.get("Value")
                or p.get("averagePrice")
                or p.get("AveragePrice")
            )
            if price_val is None:
                continue

            price_float = parse_price_to_float(str(price_val))
            if price_float <= 0:
                continue

            history.append((date_iso, price_float))

        # Sakārto pēc datuma
        history.sort(key=lambda x: x[0])
        return history

    except Exception as e:
        print(f"[WARN] Neizdevās iegūt cenu vēsturi {crop_name}: {e}")
        return []


def _build_product_name_to_code_map() -> Dict[str, str]:
    """
    Izveido mapingu no produktu nosaukumiem uz produktu kodiem.
    
    Returns:
        Dict ar productName -> productCode
    """
    try:
        products = fetch_cereal_products()
        name_to_code = {}
        
        for product in products:
            # Pārbauda dažādus iespējamos lauku nosaukumus
            name = product.get('productName') or product.get('name') or product.get('ProductName')
            code = product.get('productCode') or product.get('code') or product.get('ProductCode')
            
            if name and code:
                name_to_code[name] = str(code)
        
        return name_to_code
    except APIError:
        return {}


def _find_product_code_for_crop(crop_name: str, product_map: Dict[str, str]) -> Optional[str]:
    """
    Atrod EC produkta kodu mūsu kultūras nosaukumam.
    
    Args:
        crop_name: Mūsu kultūras nosaukums (piem., "Kvieši")
        product_map: Mapings no produktu nosaukumiem uz kodiem
    
    Returns:
        Produkta kods vai None, ja nav atrasts
    """
    # Mūsu kultūra -> EC produkta nosaukumu meklēšanas loģika
    crop_to_ec_mapping = {
        "Kvieši": ["Soft wheat", "Common wheat", "Wheat", "Soft Wheat", "Common Wheat"],
        "Mieži": ["Feed barley", "Barley", "Feed Barley"],
        "Auzas": ["Oats", "Oat"],
    }
    
    # Ja ir tiešs mapping, izmanto to
    if crop_name in crop_to_ec_mapping:
        search_names = crop_to_ec_mapping[crop_name]
    else:
        # Fallback: mēģina atrast pēc nosaukuma (lowercase contains)
        crop_lower = crop_name.lower()
        search_names = []
        for ec_name in product_map.keys():
            if crop_lower in ec_name.lower() or ec_name.lower() in crop_lower:
                search_names.append(ec_name)
    
    # Mēģina atrast produkta kodu
    for ec_name in search_names:
        # Precīzs match
        if ec_name in product_map:
            return product_map[ec_name]
        
        # Case-insensitive match
        for product_name, code in product_map.items():
            if product_name.lower() == ec_name.lower():
                return code
    
    # Fallback: meklē pēc contains (lowercase)
    crop_lower = crop_name.lower()
    for product_name, code in product_map.items():
        product_lower = product_name.lower()
        if crop_lower in product_lower or product_lower in crop_lower:
            return code
    
    return None


def get_latest_prices_for_catalog(crop_names: List[str]) -> Dict[str, Dict]:
    """
    Iegūst pēdējās cenas no EC agridata visām norādītajām kultūrām.
    
    Args:
        crop_names: Mūsu kultūru nosaukumu saraksts (piem., ["Kvieši", "Mieži"])
    
    Returns:
        Dict ar struktūru:
        {
            "Kvieši": {
                "price_eur_t": 210.0,
                "as_of": "2025-01-15",
                "source": "EC agridata"
            },
            ...
        }
        Ja kādai kultūrai nav atrasts produkts vai cena, tā nav rezultātā.
    """
    result = {}
    
    try:
        # 1) Izveido mapingu no produktu nosaukumiem uz kodiem
        product_map = _build_product_name_to_code_map()
        if not product_map:
            return result  # Nav produktu, atgriež tukšu dict
        
        # 2) Atrod produktu kodus mūsu kultūrām
        crop_to_code = {}
        for crop_name in crop_names:
            code = _find_product_code_for_crop(crop_name, product_map)
            if code:
                crop_to_code[crop_name] = code
        
        if not crop_to_code:
            return result  # Nav atrastu produktu kodu
        
        # 3) Sagatavo datumu diapazonu (pēdējās 90 dienas)
        end_date = datetime.now()
        begin_date = end_date - timedelta(days=90)
        
        begin_date_str = begin_date.strftime("%d/%m/%Y")
        end_date_str = end_date.strftime("%d/%m/%Y")
        
        # 4) Ielādē cenas visiem produktu kodiem
        # Grupē kodus pa 10, lai nepieprasītu pārāk daudz uzreiz
        all_codes = list(set(crop_to_code.values()))
        all_prices = []
        
        # Ja ir daudz kodu, sadalām pa 10
        batch_size = 10
        for i in range(0, len(all_codes), batch_size):
            batch_codes = all_codes[i:i + batch_size]
            try:
                prices = fetch_cereal_prices(batch_codes, begin_date_str, end_date_str)
                all_prices.extend(prices)
            except APIError:
                # Ja kāds batch neizdodas, turpinām ar nākamo
                continue
        
        if not all_prices:
            return result  # Nav cenu datu
        
        # 5) Katrai kultūrai atrod pēdējo (max endDate) ierakstu
        for crop_name, product_code in crop_to_code.items():
            # Filtrē cenas pēc produkta koda
            crop_prices = [
                p for p in all_prices
                if str(p.get('productCode') or p.get('ProductCode') or p.get('code', '')) == str(product_code)
            ]
            
            if not crop_prices:
                continue  # Nav cenu šai kultūrai
            
            # Atrod pēdējo ierakstu (max endDate)
            latest_price = None
            latest_date = None
            
            for price_record in crop_prices:
                # Mēģina iegūt datumu no dažādiem laukiem
                date_str = (
                    price_record.get('endDate') or
                    price_record.get('EndDate') or
                    price_record.get('date') or
                    price_record.get('Date') or
                    price_record.get('asOf') or
                    price_record.get('AsOf')
                )
                
                if not date_str:
                    continue
                
                # Parsē datumu (var būt dažādos formātos)
                try:
                    # Mēģina "dd/mm/yyyy"
                    if '/' in date_str:
                        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                    # Mēģina "yyyy-mm-dd"
                    elif '-' in date_str and len(date_str) >= 10:
                        date_obj = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    else:
                        continue
                    
                    if latest_date is None or date_obj > latest_date:
                        latest_date = date_obj
                        latest_price = price_record
                except (ValueError, TypeError):
                    continue
            
            if latest_price and latest_date:
                # Parsē cenu
                price_str = (
                    latest_price.get('price') or
                    latest_price.get('Price') or
                    latest_price.get('value') or
                    latest_price.get('Value') or
                    latest_price.get('averagePrice') or
                    latest_price.get('AveragePrice')
                )
                
                if price_str:
                    price_float = parse_price_to_float(str(price_str))
                    if price_float > 0:
                        result[crop_name] = {
                            "price_eur_t": price_float,
                            "as_of": latest_date.strftime("%Y-%m-%d"),
                            "source": "EC agridata"
                        }
    
    except Exception:
        # Ja kaut kas neizdodas, atgriež tukšu dict (fallback izmantos crops.json)
        return result
    
    return result

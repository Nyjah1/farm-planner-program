"""
LAD bloku datu iegūšana no ArcGIS REST API.
"""
import requests
from typing import Dict, Optional


# Kešs GeoJSON datiem
_geojson_cache: Dict[str, Dict] = {}


def fetch_block_geojson(block_code: str) -> Optional[Dict]:
    """
    Iegūst bloka GeoJSON datus no LAD ArcGIS REST API.
    
    Args:
        block_code: Bloka kods (piemēram, "1234567890")
    
    Returns:
        GeoJSON dictionary vai None, ja nav atrasts
    """
    # Pārbauda kešu
    if block_code in _geojson_cache:
        return _geojson_cache[block_code]
    
    base = "https://karte.lad.gov.lv/arcgis/rest/services"
    
    # Mēģina dažādus layer indeksus
    for layer_idx in range(6):  # 0..5
        # Mēģina dažādus lauku nosaukumus
        field_names = ["LBKODS", "BLOK_KODS", "KODS"]
        
        for field_name in field_names:
            try:
                # Veido URL
                url = f"{base}/MapServer/{layer_idx}/query"
                
                # Query parametri
                params = {
                    "where": f"{field_name}='{block_code}'",
                    "outFields": "*",
                    "returnGeometry": "true",
                    "f": "geojson"
                }
                
                # Izsauc API
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                
                # Pārbauda, vai ir features
                if "features" in data and len(data["features"]) > 0:
                    # Saglabā kešā
                    _geojson_cache[block_code] = data
                    return data
                    
            except (requests.RequestException, KeyError, ValueError) as e:
                # Turpina ar nākamo opciju
                continue
    
    # Nav atrasts
    return None


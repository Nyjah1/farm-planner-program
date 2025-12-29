"""
LAD bloku informācijas iegūšana no ArcGIS REST API.
"""
import requests
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urlencode


def fetch_block_info(block_code: str, debug: bool = False) -> Optional[Dict]:
    """
    Iegūst bloka informāciju no LAD ArcGIS REST API.
    
    Args:
        block_code: Bloka kods (piemēram, "59276-37098")
        debug: Ja True, izdrukā debug informāciju
    
    Returns:
        Dictionary ar:
        - area_ha (float | None): Platība hektāros
        - edited_at (str | None): Labošanas datums formātā "YYYY-MM-DD"
        - raw_attributes (dict): Visi atribūti debugging
        Vai None, ja nav atrasts
    """
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
                    "returnGeometry": "false",  # Nav vajadzīga ģeometrija
                    "f": "json"
                }
                
                # Veido pilnu URL ar parametriem (debug izmantošanai)
                full_url = f"{url}?{urlencode(params)}"
                
                # Izsauc API
                response = requests.get(url, params=params, timeout=10)
                
                # Debug izvade
                if debug:
                    print(f"[DEBUG] Request URL: {full_url}")
                    print(f"[DEBUG] Status Code: {response.status_code}")
                
                response.raise_for_status()
                
                # Mēģina parsēt kā JSON
                try:
                    data = response.json()
                    
                    # Debug izvade JSON
                    if debug:
                        print(f"[DEBUG] Response is JSON")
                        if isinstance(data, dict):
                            print(f"[DEBUG] JSON keys: {list(data.keys())}")
                            if "features" in data and len(data["features"]) > 0:
                                feature = data["features"][0]
                                if "attributes" in feature:
                                    attrs = feature["attributes"]
                                    print(f"[DEBUG] Attributes field names: {list(attrs.keys())}")
                except ValueError:
                    # Nav JSON
                    if debug:
                        text_preview = response.text[:500]
                        print(f"[DEBUG] Response is NOT JSON (first 500 chars):")
                        print(text_preview)
                    continue
                
                # Pārbauda, vai ir features
                if "features" in data and len(data["features"]) > 0:
                    # Paņem pirmo feature
                    feature = data["features"][0]
                    attributes = feature.get("attributes", {})
                    
                    # Mēģina atrast platību
                    area_ha = None
                    area_fields = ["Platiba", "PLATIBA", "Area", "AREA_HA", "PLAT_HA", "PLATIBA_HA"]
                    for field in area_fields:
                        if field in attributes and attributes[field] is not None:
                            try:
                                area_ha = float(attributes[field])
                                break
                            except (ValueError, TypeError):
                                continue
                    
                    # Mēģina atrast labošanas datumu
                    edited_at = None
                    edited_fields = ["Labots", "LABOTS", "Edited", "EDITED", "EDIT_DATE", "LabotsDatums"]
                    for field in edited_fields:
                        if field in attributes and attributes[field] is not None:
                            try:
                                value = attributes[field]
                                # Ja ir timestamp (ms), pārveido uz datumu
                                if isinstance(value, (int, float)):
                                    # Pārbauda, vai ir timestamp (ms vai sekundes)
                                    if value > 1000000000000:  # Milisekundes
                                        dt = datetime.fromtimestamp(value / 1000)
                                    else:  # Sekundes
                                        dt = datetime.fromtimestamp(value)
                                    edited_at = dt.strftime("%Y-%m-%d")
                                elif isinstance(value, str):
                                    # Ja jau ir string, mēģina parsēt
                                    edited_at = value
                                break
                            except (ValueError, TypeError, OSError):
                                continue
                    
                    return {
                        "area_ha": area_ha,
                        "edited_at": edited_at,
                        "raw_attributes": attributes
                    }
                    
            except (requests.RequestException, KeyError, ValueError) as e:
                # Turpina ar nākamo opciju
                continue
    
    # Nav atrasts
    return None


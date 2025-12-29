"""
Vienkāršs cookie manager Streamlit lietotnei, izmantojot failu sistēmu.
"""
import json
from pathlib import Path
from typing import Optional, Dict


COOKIE_FILE = Path("data/auth_cookies.json")


def get_cookie(name: str) -> Optional[str]:
    """
    Iegūst cookie vērtību no faila.
    
    Args:
        name: Cookie nosaukums
        
    Returns:
        Cookie vērtība vai None
    """
    if not COOKIE_FILE.exists():
        return None
    
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
            return cookies.get(name)
    except (json.JSONDecodeError, IOError):
        return None


def set_cookie(name: str, value: str, expires_days: int = 30):
    """
    Iestata cookie vērtību failā.
    
    Args:
        name: Cookie nosaukums
        value: Cookie vērtība
        expires_days: Derīguma termiņš dienās (netiek izmantots failu sistēmā, bet saglabāts metadata)
    """
    # Izveido direktoriju, ja nav
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Ielādē esošos cookies
    cookies = {}
    if COOKIE_FILE.exists():
        try:
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
        except (json.JSONDecodeError, IOError):
            cookies = {}
    
    # Atjaunina cookie
    cookies[name] = value
    cookies[f"{name}_expires_days"] = expires_days
    
    # Saglabā
    try:
        with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f)
    except IOError:
        pass  # Nevar saglabāt, bet nav kritiski


def delete_cookie(name: str):
    """
    Dzēš cookie no faila.
    
    Args:
        name: Cookie nosaukums
    """
    if not COOKIE_FILE.exists():
        return
    
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        
        # Dzēš cookie un tā expires
        cookies.pop(name, None)
        cookies.pop(f"{name}_expires_days", None)
        
        # Saglabā
        with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f)
    except (json.JSONDecodeError, IOError):
        pass


def get_auth_cookie() -> Optional[Dict[str, str]]:
    """
    Iegūst autentifikācijas cookie (user_id, username, auth_token).
    
    Returns:
        Dict ar user_id, username, auth_token vai None
    """
    user_id = get_cookie("user_id")
    username = get_cookie("username")
    auth_token = get_cookie("auth_token")
    
    if user_id and username and auth_token:
        try:
            return {
                "user_id": str(user_id),
                "username": str(username),
                "auth_token": str(auth_token)
            }
        except (ValueError, TypeError):
            return None
    
    return None


def set_auth_cookie(user_id: int, username: str, auth_token: str, expires_days: int = 30):
    """
    Iestata autentifikācijas cookie.
    
    Args:
        user_id: Lietotāja ID
        username: Lietotājvārds
        auth_token: Auth token
        expires_days: Derīguma termiņš dienās
    """
    set_cookie("user_id", str(user_id), expires_days)
    set_cookie("username", username, expires_days)
    set_cookie("auth_token", auth_token, expires_days)


def clear_auth_cookie():
    """
    Dzēš autentifikācijas cookie.
    """
    delete_cookie("user_id")
    delete_cookie("username")
    delete_cookie("auth_token")


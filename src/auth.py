"""
Autentifikācijas modulis ar lietotājvārdu un paroli.
"""
import streamlit as st
import secrets
import hashlib
import logging
from typing import Optional
from datetime import datetime, timedelta

try:
    from extra_streamlit_components import CookieManager  # type: ignore
    EXTRA_STREAMLIT_AVAILABLE = True
except ImportError:
    EXTRA_STREAMLIT_AVAILABLE = False
    CookieManager = None  # type: ignore

from .storage import Storage
from .models import UserModel


def get_cookie_manager() -> Optional[CookieManager]:
    """Atgriež CookieManager instance no extra-streamlit-components."""
    if not EXTRA_STREAMLIT_AVAILABLE:
        return None
    
    try:
        if "cookie_manager" not in st.session_state:
            cm = CookieManager()
            st.session_state.cookie_manager = cm
        return st.session_state.cookie_manager
    except Exception as e:
        logging.debug(f"CookieManager inicializācijas kļūda: {e}")
        return None


def hash_token(token: str) -> str:
    """Hash token ar SHA256."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def login(storage: Storage, username: str, password: str, remember_me: bool = False) -> Optional[UserModel]:
    """
    Ielogo lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        remember_me: Vai saglabāt session uz ierīces (True = 30 dienas, False = tikai sesija)
        
    Returns:
        UserModel vai None, ja autentifikācija neizdevās
    """
    user = storage.authenticate_user(username, password)
    if user:
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        
        session_token = secrets.token_urlsafe(32)
        token_hash = hash_token(session_token)
        
        if remember_me:
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
        else:
            expires_at = (datetime.now() + timedelta(days=1)).isoformat()
        
        if storage.create_remember_token(user.id, token_hash, expires_at):
            cookies = get_cookie_manager()
            if cookies is not None:
                try:
                    cookies.set("fp_remember_token", session_token)
                except Exception as cookie_error:
                    logging.debug(f"Neizdevās saglabāt cookie: {cookie_error}")
        
        return user
    return None


def register(storage: Storage, username: str, password: str, display_name: Optional[str] = None, remember_me: bool = False) -> Optional[UserModel]:
    """
    Reģistrē jaunu lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        display_name: Opcionāls parādāmais vārds (ja nav, izmanto username)
        remember_me: Vai saglabāt session uz ierīces (True = 30 dienas, False = tikai sesija)
        
    Returns:
        UserModel vai None, ja reģistrācija neizdevās
    """
    user = storage.create_user(username, password, display_name)
    if user:
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        
        session_token = secrets.token_urlsafe(32)
        token_hash = hash_token(session_token)
        
        if remember_me:
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
        else:
            expires_at = (datetime.now() + timedelta(days=1)).isoformat()
        
        if storage.create_remember_token(user.id, token_hash, expires_at):
            cookies = get_cookie_manager()
            if cookies is not None:
                try:
                    cookies.set("fp_remember_token", session_token)
                except Exception as cookie_error:
                    logging.debug(f"Neizdevās saglabāt cookie: {cookie_error}")
        
        return user
    return None


def get_current_user_from_cookie(storage: Storage) -> Optional[UserModel]:
    """
    Pārbauda, vai ir derīgs remember_token cookie un atgriež UserModel.
    Ja token nav derīgs, dzēš cookie.
    
    Args:
        storage: Storage instance
        
    Returns:
        UserModel vai None, ja nav derīga token
    """
    cookies = get_cookie_manager()
    if cookies is None:
        return None
    
    try:
        session_token = cookies.get("fp_remember_token")
        
        if not session_token:
            return None
        
        token_hash = hash_token(session_token)
        user_id = storage.verify_remember_token(token_hash)
        
        if user_id:
            user = storage.get_user_by_id(user_id)
            if user:
                st.session_state["user"] = user.id
                st.session_state["username"] = user.username
                return user
        else:
            try:
                cookies.delete("fp_remember_token")
            except Exception:
                pass
    except Exception as e:
        logging.debug(f"Cookie pārbaudes kļūda: {e}")
        try:
            if cookies:
                cookies.delete("fp_remember_token")
        except Exception:
            pass
        return None
    
    return None


def logout(storage: Storage):
    """Izlogo lietotāju un izdzēš remember_token."""
    cookies = get_cookie_manager()
    if cookies is not None:
        try:
            session_token = cookies.get("fp_remember_token")
            
            if session_token:
                token_hash = hash_token(session_token)
                storage.revoke_remember_token(token_hash)
                cookies.delete("fp_remember_token")
        except Exception as e:
            logging.debug(f"Logout cookie kļūda: {e}")
    
    if "user" in st.session_state:
        del st.session_state["user"]
    if "username" in st.session_state:
        del st.session_state["username"]


def require_login(storage: Storage) -> Optional[UserModel]:
    """
    Pārbauda, vai lietotājs ir ielogots. Ja nav, atgriež None.
    
    Svarīgi: Nekad neizmantot tikai st.session_state kā auth avotu.
    Vienmēr pārbaudīt cookie, lai nodrošinātu, ka lietotājs ir ielogots arī pēc refresh.
    
    Args:
        storage: Storage instance
        
    Returns:
        UserModel vai None, ja nav ielogots
    """
    user = get_current_user_from_cookie(storage)
    if user:
        return user
    
    if "user" in st.session_state:
        user_id = st.session_state["user"]
        user = storage.get_user_by_id(user_id)
        if user:
            return user
    
    return None

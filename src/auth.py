"""
Autentifikācijas modulis ar lietotājvārdu un paroli.
Atbalsta gan extra-streamlit-components CookieManager (Streamlit Cloud), gan failu sistēmu (lokāli).
"""
import streamlit as st
import secrets
import hashlib
import os
from typing import Optional, Union
from datetime import datetime, timedelta

try:
    from extra_streamlit_components import CookieManager  # type: ignore
    EXTRA_STREAMLIT_AVAILABLE = True
except ImportError:
    EXTRA_STREAMLIT_AVAILABLE = False
    CookieManager = None  # type: ignore

from .storage import Storage
from .models import UserModel

# Fallback uz failu sistēmu lokāli
try:
    from .cookie_manager import get_cookie as file_get_cookie, set_cookie as file_set_cookie, delete_cookie as file_delete_cookie
    FILE_COOKIE_AVAILABLE = True
except ImportError:
    FILE_COOKIE_AVAILABLE = False


class CookieManagerWrapper:
    """Wrapper klase, kas atbalsta gan CookieManager, gan failu sistēmu."""
    
    def __init__(self, cookie_manager: Optional[CookieManager] = None):
        self.cookie_manager = cookie_manager
        self.use_file_fallback = cookie_manager is None and FILE_COOKIE_AVAILABLE
    
    def get(self, name: str) -> Optional[str]:
        """Iegūst cookie vērtību."""
        if self.cookie_manager is not None:
            try:
                return self.cookie_manager.get(name)
            except Exception as e:
                # Fallback uz failu sistēmu, ja CookieManager neizdodas
                if FILE_COOKIE_AVAILABLE:
                    return file_get_cookie(name)
                return None
        elif self.use_file_fallback:
            return file_get_cookie(name)
        return None
    
    def set(self, name: str, value: str):
        """Iestata cookie vērtību."""
        if self.cookie_manager is not None:
            try:
                self.cookie_manager.set(name, value)
            except Exception as e:
                # Fallback uz failu sistēmu, ja CookieManager neizdodas
                if FILE_COOKIE_AVAILABLE:
                    file_set_cookie(name, value, expires_days=30)
        elif self.use_file_fallback:
            file_set_cookie(name, value, expires_days=30)
    
    def delete(self, name: str):
        """Dzēš cookie."""
        if self.cookie_manager is not None:
            try:
                self.cookie_manager.delete(name)
            except Exception:
                # Fallback uz failu sistēmu
                if FILE_COOKIE_AVAILABLE:
                    file_delete_cookie(name)
        elif self.use_file_fallback:
            file_delete_cookie(name)


def get_cookie_manager() -> Optional[CookieManagerWrapper]:
    """
    Atgriež CookieManagerWrapper instance.
    Vispirms mēģina izmantot extra-streamlit-components CookieManager,
    ja tas nav pieejams vai neizdodas, izmanto failu sistēmu fallback.
    """
    # Mēģina izmantot extra-streamlit-components CookieManager
    cookie_manager = None
    if EXTRA_STREAMLIT_AVAILABLE:
        try:
            if "cookie_manager" not in st.session_state:
                cm = CookieManager()
                st.session_state.cookie_manager = cm
            cookie_manager = st.session_state.cookie_manager
        except Exception as e:
            # CookieManager neizdevās inicializēt, izmantosim fallback
            pass
    
    # Ja CookieManager nav pieejams, izmantojam failu sistēmu fallback
    if cookie_manager is None and not FILE_COOKIE_AVAILABLE:
        return None
    
    # Izveido wrapper
    if "cookie_manager_wrapper" not in st.session_state:
        st.session_state.cookie_manager_wrapper = CookieManagerWrapper(cookie_manager)
    
    return st.session_state.cookie_manager_wrapper


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
        remember_me: Vai saglabāt session uz ierīces
        
    Returns:
        UserModel vai None, ja autentifikācija neizdevās
    """
    user = storage.authenticate_user(username, password)
    if user:
        # Saglabā user_id session_state (per-browser, per-session)
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        
        # Ja remember_me, ģenerē un saglabā session token
        if remember_me:
            # Ģenerē drošu token
            session_token = secrets.token_urlsafe(32)
            token_hash = hash_token(session_token)
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            
            # Saglabā token hash DB
            if storage.create_remember_token(user.id, token_hash, expires_at):
                cookies = get_cookie_manager()
                if cookies is not None:
                    try:
                        # Saglabā plaintext token cookie (tikai šeit, DB glabā hash)
                        cookies.set("fp_remember_token", session_token)
                    except Exception:
                        # Kļūda saglabājot cookie, bet token jau ir DB, tāpēc nav kritiski
                        pass
        
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
        remember_me: Vai saglabāt session uz ierīces
        
    Returns:
        UserModel vai None, ja reģistrācija neizdevās
    """
    user = storage.create_user(username, password, display_name)
    if user:
        # Saglabā user_id session_state (per-browser, per-session)
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        
        # Ja remember_me, ģenerē un saglabā session token
        if remember_me:
            # Ģenerē drošu token
            session_token = secrets.token_urlsafe(32)
            token_hash = hash_token(session_token)
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            
            # Saglabā token hash DB
            if storage.create_remember_token(user.id, token_hash, expires_at):
                cookies = get_cookie_manager()
                if cookies is not None:
                    try:
                        # Saglabā plaintext token cookie (tikai šeit, DB glabā hash)
                        cookies.set("fp_remember_token", session_token)
                    except Exception:
                        # Kļūda saglabājot cookie, bet token jau ir DB, tāpēc nav kritiski
                        pass
        
        return user
    return None


def get_current_user_from_cookie(storage: Storage) -> Optional[UserModel]:
    """
    Pārbauda, vai ir derīgs remember_token cookie un atgriež UserModel.
    
    Args:
        storage: Storage instance
        
    Returns:
        UserModel vai None, ja nav derīga token
    """
    cookies = get_cookie_manager()
    if cookies is None:
        return None
    
    try:
        # Iegūst token no cookie
        session_token = cookies.get("fp_remember_token")
        
        if not session_token:
            return None
        
        # Hash token un meklē DB
        token_hash = hash_token(session_token)
        user_id = storage.verify_remember_token(token_hash)
        
        if user_id:
            # Iegūst lietotāju
            user = storage.get_user_by_id(user_id)
            if user:
                # Atjauno session_state
                st.session_state["user"] = user.id
                st.session_state["username"] = user.username
                return user
    except Exception:
        # Kļūda lasot cookie, bet nav kritiski
        return None
    
    return None


def logout(storage: Storage):
    """Izlogo lietotāju un izdzēš remember_token."""
    cookies = get_cookie_manager()
    if cookies is not None:
        try:
            session_token = cookies.get("fp_remember_token")
            
            if session_token:
                # Hash token un invalidē DB
                token_hash = hash_token(session_token)
                storage.revoke_remember_token(token_hash)
                
                # Dzēš cookie
                cookies.delete("fp_remember_token")
        except Exception:
            # Kļūda dzēšot cookie, bet nav kritiski
            pass
    
    # Notīra session_state
    if "user" in st.session_state:
        del st.session_state["user"]
    if "username" in st.session_state:
        del st.session_state["username"]


def require_login(storage: Storage) -> Optional[UserModel]:
    """
    Pārbauda, vai lietotājs ir ielogots. Ja nav, atgriež None.
    Vispirms pārbauda session_state, pēc tam cookie.
    
    Args:
        storage: Storage instance
        
    Returns:
        UserModel vai None, ja nav ielogots
    """
    # Pārbauda session_state (per-browser, per-session)
    if "user" in st.session_state:
        user_id = st.session_state["user"]
        user = storage.get_user_by_id(user_id)
        if user:
            return user
    
    # Pārbauda cookie (remember me)
    user = get_current_user_from_cookie(storage)
    if user:
        return user
    
    return None

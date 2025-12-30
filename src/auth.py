"""
Autentifikācijas modulis ar lietotājvārdu un paroli.
"""
import streamlit as st
import secrets
from typing import Optional
from datetime import datetime, timedelta
from streamlit_cookies_manager import CookieManager
from .storage import Storage
from .models import UserModel


def get_cookie_manager() -> Optional[CookieManager]:
    """Atgriež CookieManager instance."""
    try:
        if "cookie_manager" not in st.session_state:
            cm = CookieManager()
            # Pārbauda, vai CookieManager ir gatavs
            if hasattr(cm, 'ready') and not cm.ready():
                print("CookieManager nav gatavs")
                return None
            st.session_state.cookie_manager = cm
        return st.session_state.cookie_manager
    except Exception as e:
        # Ja CookieManager nevar tikt inicializēts, atgriež None
        print(f"CookieManager inicializācijas kļūda: {e}")
        return None


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
        st.session_state["user"] = user.id
        
        # Ja remember_me, ģenerē un saglabā session token
        if remember_me:
            session_token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            
            if storage.create_session(user.id, session_token, expires_at):
                cookies = get_cookie_manager()
                if cookies is not None:
                    try:
                        cookies["fp_session"] = session_token
                        cookies.save()
                    except Exception as cookie_error:
                        print(f"Neizdevās saglabāt cookie: {cookie_error}")
        
        return user
    return None


def register(storage: Storage, username: str, password: str, remember_me: bool = False) -> Optional[UserModel]:
    """
    Reģistrē jaunu lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        remember_me: Vai saglabāt session uz ierīces
        
    Returns:
        UserModel vai None, ja reģistrācija neizdevās
    """
    user = storage.create_user(username, password)
    if user:
        st.session_state["user"] = user.id
        
        # Ja remember_me, ģenerē un saglabā session token
        if remember_me:
            session_token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            
            if storage.create_session(user.id, session_token, expires_at):
                cookies = get_cookie_manager()
                if cookies is not None:
                    try:
                        cookies["fp_session"] = session_token
                        cookies.save()
                    except Exception as cookie_error:
                        print(f"Neizdevās saglabāt cookie: {cookie_error}")
        
        return user
    return None


def check_session_cookie(storage: Storage) -> Optional[int]:
    """
    Pārbauda, vai ir derīgs session cookie un atgriež user_id.
    
    Args:
        storage: Storage instance
        
    Returns:
        user_id vai None, ja nav derīga session
    """
    cookies = get_cookie_manager()
    if cookies is None:
        return None
    
    try:
        session_token = cookies.get("fp_session")
        
        if not session_token:
            return None
        
        session = storage.get_session_by_token(session_token)
        if session:
            return session["user_id"]
    except Exception as e:
        print(f"Cookie pārbaudes kļūda: {e}")
        return None
    
    return None


def logout(storage: Storage):
    """Izlogo lietotāju un izdzēš session."""
    cookies = get_cookie_manager()
    if cookies is not None:
        try:
            session_token = cookies.get("fp_session")
            
            if session_token:
                storage.delete_session_by_token(session_token)
                if "fp_session" in cookies:
                    del cookies["fp_session"]
                    cookies.save()
        except Exception as e:
            print(f"Logout cookie kļūda: {e}")
    
    if "user" in st.session_state:
        del st.session_state["user"]

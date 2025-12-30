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


def get_cookie_manager() -> CookieManager:
    """Atgriež CookieManager instance."""
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = CookieManager()
    return st.session_state.cookie_manager


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
                cookies.set("fp_session", session_token, expires_days=30)
        
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
                cookies.set("fp_session", session_token, expires_days=30)
        
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
    session_token = cookies.get("fp_session")
    
    if not session_token:
        return None
    
    session = storage.get_session_by_token(session_token)
    if session:
        return session["user_id"]
    
    return None


def logout(storage: Storage):
    """Izlogo lietotāju un izdzēš session."""
    cookies = get_cookie_manager()
    session_token = cookies.get("fp_session")
    
    if session_token:
        storage.delete_session_by_token(session_token)
        cookies.delete("fp_session")
    
    if "user" in st.session_state:
        del st.session_state["user"]

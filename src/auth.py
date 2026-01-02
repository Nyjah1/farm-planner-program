"""
Autentifikācijas modulis ar lietotājvārdu un paroli.
"""
import streamlit as st
from typing import Optional

from .storage import Storage
from .models import UserModel


def login(storage: Storage, username: str, password: str) -> Optional[UserModel]:
    """
    Ielogo lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        
    Returns:
        UserModel vai None, ja autentifikācija neizdevās
    """
    user = storage.authenticate_user(username, password)
    if user:
        # Saglabā user_id session_state (per-browser, per-session)
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        return user
    return None


def register(storage: Storage, username: str, password: str, display_name: Optional[str] = None) -> Optional[UserModel]:
    """
    Reģistrē jaunu lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        display_name: Opcionāls parādāmais vārds (ja nav, izmanto username)
        
    Returns:
        UserModel vai None, ja reģistrācija neizdevās
    """
    user = storage.create_user(username, password, display_name)
    if user:
        # Saglabā user_id session_state (per-browser, per-session)
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        return user
    return None


def get_current_user_from_cookie(storage: Storage) -> Optional[UserModel]:
    """
    Vairs netiek izmantota - atstāta tikai backward compatibility.
    Atgriež None, jo remember me funkcionalitāte ir noņemta.
    """
    return None


def logout(storage: Storage):
    """Izlogo lietotāju."""
    # Notīra session_state
    if "user" in st.session_state:
        del st.session_state["user"]
    if "username" in st.session_state:
        del st.session_state["username"]


def require_login(storage: Storage) -> Optional[UserModel]:
    """
    Pārbauda, vai lietotājs ir ielogots. Ja nav, atgriež None.
    Pārbauda tikai session_state.
    
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
    
    return None

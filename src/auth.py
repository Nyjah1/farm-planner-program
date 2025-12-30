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
        st.session_state["user"] = user.id
        return user
    return None


def register(storage: Storage, username: str, password: str) -> Optional[UserModel]:
    """
    Reģistrē jaunu lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        
    Returns:
        UserModel vai None, ja reģistrācija neizdevās
    """
    user = storage.create_user(username, password)
    if user:
        st.session_state["user"] = user.id
        return user
    return None


def logout():
    """Izlogo lietotāju."""
    if "user" in st.session_state:
        del st.session_state["user"]

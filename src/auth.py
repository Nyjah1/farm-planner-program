"""
Autentifikācijas modulis ar lietotājvārdu un paroli.
"""
import streamlit as st
import bcrypt
import uuid
from datetime import datetime
from typing import Optional
from .storage import Storage
from .models import UserModel


def login(storage: Storage, username: str, password: str, remember_me: bool = False) -> Optional[UserModel]:
    """
    Ielogo lietotāju.
    
    Args:
        storage: Storage instance
        username: Lietotājvārds
        password: Parole
        remember_me: Vai saglabāt sesiju uz ierīces
        
    Returns:
        UserModel vai None, ja autentifikācija neizdevās
    """
    user = storage.authenticate_user(username, password)
    if user:
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        
        if remember_me:
            try:
                from extra_streamlit_components import CookieManager
                cookies = CookieManager()
                cookie_token = str(uuid.uuid4())
                cookies.set("fp_session", cookie_token)
                st.session_state["fp_session_token"] = cookie_token
            except:
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
        display_name: Opcionāls parādāmais vārds
        remember_me: Vai saglabāt sesiju uz ierīces
        
    Returns:
        UserModel vai None, ja reģistrācija neizdevās
    """
    user = storage.create_user(username, password, display_name)
    if user:
        st.session_state["user"] = user.id
        st.session_state["username"] = user.username
        
        if remember_me:
            try:
                from extra_streamlit_components import CookieManager
                cookies = CookieManager()
                cookie_token = str(uuid.uuid4())
                cookies.set("fp_session", cookie_token)
                st.session_state["fp_session_token"] = cookie_token
            except:
                pass
        
        return user
    return None


def logout(storage: Storage):
    """
    Izlogo lietotāju un notīra sesiju.
    
    Args:
        storage: Storage instance
    """
    if "user" in st.session_state:
        del st.session_state["user"]
    if "username" in st.session_state:
        del st.session_state["username"]
    if "fp_session_token" in st.session_state:
        del st.session_state["fp_session_token"]
    
    try:
        from extra_streamlit_components import CookieManager
        cookies = CookieManager()
        cookies.delete("fp_session")
    except:
        pass


def require_login(storage: Storage) -> Optional[UserModel]:
    """
    Pārbauda, vai lietotājs ir ielogots.
    
    Args:
        storage: Storage instance
        
    Returns:
        UserModel vai None, ja nav ielogots
    """
    if "user" in st.session_state:
        user_id = st.session_state["user"]
        user = storage.get_user_by_id(user_id)
        if user:
            return user
    
    try:
        from extra_streamlit_components import CookieManager
        cookies = CookieManager()
        cookie_token = cookies.get("fp_session")
        if cookie_token and cookie_token == st.session_state.get("fp_session_token"):
            if "user" in st.session_state:
                user_id = st.session_state["user"]
                user = storage.get_user_by_id(user_id)
                if user:
                    return user
    except:
        pass
    
    return None

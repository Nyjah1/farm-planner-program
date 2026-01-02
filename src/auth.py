import streamlit as st
import bcrypt
import uuid
from datetime import datetime, timedelta

from src.storage import Storage

COOKIE_KEY = "fp_auth_token"
COOKIE_DAYS = 30


def _get_storage() -> Storage:
    if "storage" not in st.session_state or st.session_state.storage is None:
        st.session_state.storage = Storage()
    return st.session_state.storage


def _set_user_session(user: dict) -> None:
    st.session_state["user"] = user


def _clear_user_session() -> None:
    if "user" in st.session_state:
        del st.session_state["user"]


def _get_cookie_manager():
    # Cookie var nebūt pieejams visās vidēs.
    # Ja nav - vienkārši strādājam bez "remember me".
    try:
        import extra_streamlit_components as stx
        return stx.CookieManager()
    except Exception:
        return None


def _set_remember_cookie(token: str) -> None:
    cm = _get_cookie_manager()
    if cm is None:
        return
    expires_at = datetime.utcnow() + timedelta(days=COOKIE_DAYS)
    cm.set(COOKIE_KEY, token, expires_at=expires_at)


def _get_remember_cookie() -> str | None:
    cm = _get_cookie_manager()
    if cm is None:
        return None
    return cm.get(COOKIE_KEY)


def _delete_remember_cookie() -> None:
    cm = _get_cookie_manager()
    if cm is None:
        return
    cm.delete(COOKIE_KEY)


def require_login() -> bool:
    # 1) ja jau sesijā ir lietotājs
    if st.session_state.get("user"):
        return True

    # 2) mēģinam atjaunot no cookie
    token = _get_remember_cookie()
    if not token:
        return False

    storage = _get_storage()
    user = storage.get_user_by_auth_token(token)
    if user:
        _set_user_session(user)
        return True

    return False


def login() -> None:
    st.subheader("Ielogoties")

    username = st.text_input("Lietotājvārds", key="login_username")
    password = st.text_input("Parole", type="password", key="login_password")
    remember = st.checkbox("Atcerēties mani uz šīs ierīces", value=True, key="login_remember")

    col1, col2 = st.columns(2)
    with col1:
        do_login = st.button("Ielogoties", use_container_width=True)
    with col2:
        do_logout = st.button("Izlogoties", use_container_width=True)

    if do_logout:
        logout()
        st.success("Izlogots.")
        st.rerun()

    if not do_login:
        return

    if not username or not password:
        st.error("Ievadiet lietotājvārdu un paroli.")
        return

    storage = _get_storage()
    user = storage.get_user_by_username(username.strip())
    if not user:
        st.error("Nepareizs lietotājvārds vai parole.")
        return

    stored_hash = user.get("password_hash")
    if not stored_hash:
        st.error("Lietotājam nav iestatīta parole.")
        return

    ok = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    if not ok:
        st.error("Nepareizs lietotājvārds vai parole.")
        return

    # Izveido tokenu (ja grib atcerēties)
    if remember:
        token = storage.create_auth_token(user["id"])
        _set_remember_cookie(token)

    _set_user_session(user)
    st.success("Ielogojies!")
    st.rerun()


def register() -> None:
    st.subheader("Reģistrācija")

    username = st.text_input("Lietotājvārds", key="reg_username")
    password = st.text_input("Parole", type="password", key="reg_password")
    password2 = st.text_input("Atkārtot paroli", type="password", key="reg_password2")

    do_reg = st.button("Reģistrēties", use_container_width=True)
    if not do_reg:
        return

    username = (username or "").strip()
    if not username:
        st.error("Lietotājvārds ir obligāts.")
        return
    if not password or password != password2:
        st.error("Paroles nesakrīt.")
        return
    if len(password) < 6:
        st.error("Parolei jābūt vismaz 6 simboliem.")
        return

    storage = _get_storage()
    if storage.get_user_by_username(username):
        st.error("Šāds lietotājvārds jau eksistē.")
        return

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = storage.create_user(username=username, password_hash=pw_hash)

    _set_user_session(user)
    st.success("Reģistrācija veiksmīga!")
    st.rerun()


def logout() -> None:
    _delete_remember_cookie()
    _clear_user_session()

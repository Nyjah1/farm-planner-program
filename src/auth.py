"""
Autentifikācijas modulis ar lokāliem lietotājiem.
"""
import bcrypt
import os
import uuid
from typing import Optional, Dict
from datetime import datetime, timedelta

from .db import get_db_cursor, get_connection, is_postgres, _get_auto_increment, _get_placeholder


def _get_placeholder():
    """Atgriež placeholder atkarībā no datubāzes veida."""
    return '%s' if is_postgres() else '?'


def ensure_auth_tables(storage):
    """
    Izveido users tabulu, ja tā nav, un veic migrācijas.
    
    Args:
        storage: Storage instance (tiek izmantots tikai, lai pārbaudītu, vai ir inicializēts)
    """
    id_type = _get_auto_increment()
    
    with get_db_cursor() as cursor:
        # Migrācija: ja ir username kolonna, pārveido uz email
        try:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
            result = cursor.fetchone()
            if result and 'username' in result[0] and 'email' not in result[0]:
                # Migrācija: pievieno email kolonnu
                cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
                # Kopē datus no username uz email
                cursor.execute("UPDATE users SET email = username WHERE email IS NULL")
                # Izdzēs username kolonnu (SQLite nevar tieši, bet mēs to ignorēsim)
        except Exception:
            pass
        
        # Izveido users tabulu ar email
        if is_postgres():
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {id_type},
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    remember_token TEXT,
                    remember_token_expires TIMESTAMP,
                    farming_type TEXT DEFAULT 'konvencionāla'
                )
            """)
        else:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {id_type},
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    remember_token TEXT,
                    remember_token_expires TEXT,
                    farming_type TEXT DEFAULT 'konvencionāla'
                )
            """)
        
        # Migrācija: pievieno remember_token kolonnas, ja tās nav
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN remember_token TEXT")
        except Exception:
            pass
        
        try:
            if is_postgres():
                cursor.execute("ALTER TABLE users ADD COLUMN remember_token_expires TIMESTAMP")
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN remember_token_expires TEXT")
        except Exception:
            pass
        
        # Migrācija: pievieno farming_type kolonnu
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN farming_type TEXT DEFAULT 'konvencionāla'")
        except Exception:
            pass
        
        # Migrācija: pievieno email kolonnu, ja nav
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
            # Ja ir username, kopē uz email
            try:
                cursor.execute("UPDATE users SET email = username WHERE email IS NULL")
            except Exception:
                pass
        except Exception:
            pass


def hash_password(password: str) -> str:
    """
    Hash paroli ar bcrypt.
    
    Args:
        password: Parole kā string
        
    Returns:
        Hashēta parole kā string
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Pārbauda, vai parole atbilst hash.
    
    Args:
        password: Parole kā string
        password_hash: Hashēta parole kā string
        
    Returns:
        True, ja parole atbilst, False citādi
    """
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def create_user(storage, email: str, password: str) -> Optional[Dict]:
    """
    Izveido jaunu lietotāju.
    
    Args:
        storage: Storage instance
        email: E-pasta adrese
        password: Parole
        
    Returns:
        User dict ar id un email vai None, ja neizdevās
    """
    placeholder = _get_placeholder()
    
    # Pārbauda, vai lietotājs jau eksistē
    with get_db_cursor() as cursor:
        cursor.execute(f"SELECT id FROM users WHERE email = {placeholder}", (email,))
        if cursor.fetchone():
            return None  # Lietotājs jau eksistē
    
    # Hash paroli
    password_hash = hash_password(password)
    
    # Izveido lietotāju
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if is_postgres():
            cursor.execute(
                f"INSERT INTO users (email, password_hash) VALUES ({placeholder}, {placeholder}) RETURNING id",
                (email, password_hash)
            )
            user_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                f"INSERT INTO users (email, password_hash) VALUES ({placeholder}, {placeholder})",
                (email, password_hash)
            )
            user_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        return {"id": user_id, "email": email}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def authenticate(storage, email: str, password: str) -> Optional[Dict]:
    """
    Autentificē lietotāju.
    
    Args:
        storage: Storage instance
        email: E-pasta adrese
        password: Parole
        
    Returns:
        User dict ar id un email vai None, ja autentifikācija neizdevās
    """
    placeholder = _get_placeholder()
    
    with get_db_cursor() as cursor:
        cursor.execute(
            f"SELECT id, email, password_hash FROM users WHERE email = {placeholder}",
            (email,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        user_id, db_email, password_hash = row
        
        # Pārbauda paroli
        if verify_password(password, password_hash):
            return {"id": user_id, "email": db_email}
        else:
            return None


def ensure_admin_user(storage) -> bool:
    """
    Izveido admin lietotāju no env, ja nav neviena lietotāja DB.
    
    Args:
        storage: Storage instance
        
    Returns:
        True, ja admin izveidots vai jau eksistē, False, ja env nav uzstādīts
    """
    # Pārbauda, vai ir kāds lietotājs
    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        
        if count > 0:
            return True  # Jau ir lietotāji
    
    # Nav neviena lietotāja - izveido admin no env
    admin_email = os.getenv("FARM_ADMIN_EMAIL")
    admin_password = os.getenv("FARM_ADMIN_PASS")
    
    if not admin_email or not admin_password:
        return False  # Env nav uzstādīts
    
    # Izveido admin lietotāju
    user = create_user(storage, admin_email, admin_password)
    return user is not None


def register_user(storage, email: str, password: str) -> Dict:
    """
    Reģistrē jaunu lietotāju.
    
    Args:
        storage: Storage instance
        email: E-pasta adrese
        password: Parole (vismaz 8 simboli)
        
    Returns:
        User dict ar id un email
        
    Raises:
        ValueError: Ja validācija neizdodas vai email jau eksistē
    """
    # Validācija: email
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not email or not re.match(email_pattern, email):
        raise ValueError("Lūdzu, ievadiet derīgu e-pasta adresi.")
    
    # Validācija: password
    if not password or len(password) < 8:
        raise ValueError("Parolei jābūt vismaz 8 simboliem.")
    
    placeholder = _get_placeholder()
    
    # Pārbauda, vai lietotājs jau eksistē
    with get_db_cursor() as cursor:
        cursor.execute(f"SELECT id FROM users WHERE email = {placeholder}", (email,))
        if cursor.fetchone():
            raise ValueError("Lietotājs ar šādu e-pasta adresi jau eksistē.")
    
    # Hash paroli
    password_hash = hash_password(password)
    
    # Izveido lietotāju
    created_at = datetime.now().isoformat()
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if is_postgres():
            cursor.execute(
                f"INSERT INTO users (email, password_hash, created_at) VALUES ({placeholder}, {placeholder}, {placeholder}) RETURNING id",
                (email, password_hash, created_at)
            )
            user_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                f"INSERT INTO users (email, password_hash, created_at) VALUES ({placeholder}, {placeholder}, {placeholder})",
                (email, password_hash, created_at)
            )
            user_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        return {"id": user_id, "email": email}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_count(storage) -> int:
    """
    Iegūst lietotāju skaitu DB.
    
    Args:
        storage: Storage instance
        
    Returns:
        Lietotāju skaits
    """
    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]


def generate_remember_token() -> str:
    """
    Ģenerē nejaušu remember token (UUID4).
    
    Returns:
        Token kā string
    """
    return str(uuid.uuid4())


def set_remember_token(storage, user_id: int, remember: bool) -> Optional[str]:
    """
    Iestata vai noņem remember token lietotājam.
    
    Args:
        storage: Storage instance
        user_id: Lietotāja ID
        remember: True, ja jāiestata token, False, ja jānoņem
        
    Returns:
        Token string, ja remember=True, citādi None
    """
    placeholder = _get_placeholder()
    
    if not remember:
        # Noņem token
        with get_db_cursor() as cursor:
            cursor.execute(
                f"UPDATE users SET remember_token = NULL, remember_token_expires = NULL WHERE id = {placeholder}",
                (user_id,)
            )
        return None
    
    # Ģenerē jaunu token
    token = generate_remember_token()
    expires = (datetime.now() + timedelta(days=30)).isoformat()
    
    with get_db_cursor() as cursor:
        cursor.execute(
            f"UPDATE users SET remember_token = {placeholder}, remember_token_expires = {placeholder} WHERE id = {placeholder}",
            (token, expires, user_id)
        )
    
    return token


def validate_remember_token(storage, token: str) -> Optional[Dict]:
    """
    Validē remember token un atgriež lietotāja informāciju, ja token ir derīgs.
    
    Args:
        storage: Storage instance
        token: Remember token
        
    Returns:
        User dict ar id un username vai None, ja token nav derīgs
    """
    placeholder = _get_placeholder()
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, email, remember_token_expires FROM users WHERE remember_token = {placeholder}",
            (token,)
        )
        row = cursor.fetchone()
        
        if not row:
            cursor.close()
            conn.close()
            return None
        
        user_id, email, expires_str = row
        
        # Pārbauda, vai token nav beidzies
        if expires_str:
            try:
                if is_postgres():
                    # PostgreSQL atgriež datetime objektu
                    if isinstance(expires_str, datetime):
                        expires = expires_str
                    else:
                        expires = datetime.fromisoformat(str(expires_str))
                else:
                    # SQLite atgriež string
                    expires = datetime.fromisoformat(expires_str)
                
                if datetime.now() > expires:
                    # Token beidzies - izdzēš to
                    cursor.execute(
                        f"UPDATE users SET remember_token = NULL, remember_token_expires = NULL WHERE id = {placeholder}",
                        (user_id,)
                    )
                    conn.commit()
                    cursor.close()
                    conn.close()
                    return None
            except (ValueError, TypeError):
                # Nevar parsēt datumu - uzskata par nederīgu
                cursor.close()
                conn.close()
                return None
        
        cursor.close()
        conn.close()
        return {"id": user_id, "email": email}
    except Exception:
        conn.rollback()
        conn.close()
        raise


def clear_remember_token(storage, user_id: int):
    """
    Noņem remember token lietotājam.
    
    Args:
        storage: Storage instance
        user_id: Lietotāja ID
    """
    set_remember_token(storage, user_id, remember=False)


def get_user_farming_type(storage, user_id: int) -> str:
    """
    Iegūst lietotāja saimniekošanas veidu (konvencionāla/bioloģiska).
    
    Args:
        storage: Storage instance
        user_id: Lietotāja ID
        
    Returns:
        "konvencionāla" vai "bioloģiska" (noklusējums: "konvencionāla")
    """
    placeholder = _get_placeholder()
    
    with get_db_cursor() as cursor:
        cursor.execute(
            f"SELECT farming_type FROM users WHERE id = {placeholder}",
            (user_id,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
        return "konvencionāla"


def set_user_farming_type(storage, user_id: int, farming_type: str) -> bool:
    """
    Iestata lietotāja saimniekošanas veidu.
    
    Args:
        storage: Storage instance
        user_id: Lietotāja ID
        farming_type: "konvencionāla" vai "bioloģiska"
        
    Returns:
        True, ja veiksmīgi, False citādi
    """
    if farming_type not in ["konvencionāla", "bioloģiska"]:
        return False
    
    placeholder = _get_placeholder()
    
    with get_db_cursor() as cursor:
        cursor.execute(
            f"UPDATE users SET farming_type = {placeholder} WHERE id = {placeholder}",
            (farming_type, user_id)
        )
        return cursor.rowcount > 0


def is_field_organic(field, user_farming_type: str) -> bool:
    """
    Nosaka, vai lauks ir bioloģisks, ņemot vērā gan lauka specifisko iestatījumu, gan globālo iestatījumu.
    
    Args:
        field: FieldModel instance
        user_farming_type: Lietotāja globālais saimniekošanas veids ("konvencionāla" vai "bioloģiska")
        
    Returns:
        True, ja lauks ir bioloģisks, False citādi
    """
    if field.is_organic is not None:
        # Lauka specifiskais iestatījums pārraksta globālo
        return field.is_organic
    # Izmanto globālo iestatījumu
    return user_farming_type == "bioloģiska"

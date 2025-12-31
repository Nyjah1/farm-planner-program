"""
Datu bāzes savienojuma modulis ar atbalstu gan SQLite, gan PostgreSQL.
"""
import os
import sqlite3
from pathlib import Path
from typing import Union, Optional
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extensions import connection as psycopg2_connection
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2_connection = None

# Tipu alias
DBConnection = Union[sqlite3.Connection, psycopg2_connection]


def get_database_url() -> Optional[str]:
    """
    Atgriež DATABASE_URL no st.secrets vai vides mainīgā.
    
    Vispirms meklē st.secrets["DB_URL"], pēc tam os.environ["DATABASE_URL"].
    
    Returns:
        DATABASE_URL string vai None, ja nav iestatīts vai nav derīgs
    """
    # Mēģina iegūt no Streamlit secrets (Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'DB_URL' in st.secrets:
            url = st.secrets['DB_URL']
            if url and _is_valid_database_url(url):
                return url
    except Exception:
        pass
    
    # Fallback uz vides mainīgo
    url = os.environ.get('DATABASE_URL')
    if url and _is_valid_database_url(url):
        return url
    
    return None


def _is_valid_database_url(url: str) -> bool:
    """
    Pārbauda, vai DATABASE_URL ir derīgs formāts.
    
    Args:
        url: DATABASE_URL string
        
    Returns:
        True, ja URL ir derīgs, False citādi
    """
    if not url or not isinstance(url, str):
        return False
    
    # Noņem whitespace
    url = url.strip()
    
    # Pārbauda, vai nav tukšs
    if not url:
        return False
    
    # Validācija: jāsākas ar postgresql:// vai postgres://
    if not (url.startswith('postgresql://') or url.startswith('postgres://')):
        return False
    
    # Pārbauda, vai nav acīmredzami nepareizs (piemēram, satur "npx" vai citas komandas)
    # Ja satur "npx", "npm", "neonctl" vai citas komandas, bet nav derīgs URL formāts, tas ir nepareizs
    invalid_keywords = ['npx', 'npm', 'neonctl', 'init', 'run ', 'exec']
    url_lower = url.lower()
    for keyword in invalid_keywords:
        if keyword in url_lower:
            # Pārbauda, vai tas nav daļa no derīga URL (piemēram, hostname)
            # Ja satur "=" vai nav tipiska URL struktūra, tas ir nepareizs
            if '=' in url or '@' not in url:
                return False
    
    return True


def is_postgres() -> bool:
    """
    Pārbauda, vai jāizmanto PostgreSQL.
    
    Returns:
        True, ja DATABASE_URL ir iestatīts, False citādi
    """
    return get_database_url() is not None


def get_connection() -> DBConnection:
    """
    Atgriež datubāzes savienojumu.
    
    Ja DATABASE_URL ir iestatīts un derīgs, izmanto PostgreSQL (psycopg2).
    Pretējā gadījumā izmanto SQLite.
    
    Returns:
        sqlite3.Connection vai psycopg2.connection
        
    Raises:
        ValueError: Ja DATABASE_URL ir iestatīts, bet nav derīgs formāts
    """
    database_url = get_database_url()
    
    if database_url:
        # PostgreSQL
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2-binary nav instalēts. "
                "Instalējiet ar: pip install psycopg2-binary"
            )
        
        # Pārbauda, vai URL ir derīgs
        if not _is_valid_database_url(database_url):
            raise ValueError(
                "DB_URL nav iestatīts pareizi. "
                "DB_URL jābūt PostgreSQL connection string, kas sākas ar 'postgresql://' vai 'postgres://'. "
                "Atver Streamlit Cloud Settings → Secrets un ieliec pareizu DB_URL vai noņem DB_URL, lai izmantotu SQLite."
            )
        
        try:
            # Parse DATABASE_URL (Render formāts: postgresql://user:pass@host:port/dbname)
            # psycopg2 atbalsta tiešu DATABASE_URL izmantošanu
            return psycopg2.connect(database_url)
        except Exception as e:
            # Ja neizdodas savienoties, izvada labāku kļūdas ziņojumu
            raise ValueError(
                f"Neizdevās savienoties ar PostgreSQL datubāzi. "
                f"Pārbaudiet DB_URL Streamlit Cloud Settings → Secrets. "
                f"Kļūda: {e}"
            ) from e
    else:
        # SQLite (fallback)
        db_path = "data/farm.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(db_path)


@contextmanager
def get_db_cursor():
    """
    Context manager datubāzes kursora iegūšanai.
    
    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM table")
    
    Automātiski veic rollback, ja notiek kļūda.
    """
    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        # Kritiski: jāveic rollback, lai novērstu "transaction is aborted" kļūdu
        conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        conn.close()


def execute_sql(sql: str, params: tuple = None) -> list:
    """
    Izpilda SQL vaicājumu un atgriež rezultātus.
    
    Args:
        sql: SQL vaicājums
        params: Parametri vaicājumam
        
    Returns:
        Rezultātu saraksts
    """
    with get_db_cursor() as cursor:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchall()


def execute_sql_one(sql: str, params: tuple = None):
    """
    Izpilda SQL vaicājumu un atgriež vienu rezultātu.
    
    Args:
        sql: SQL vaicājums
        params: Parametri vaicājumam
        
    Returns:
        Vienu rezultātu vai None
    """
    with get_db_cursor() as cursor:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchone()


def get_lastrowid(cursor) -> int:
    """
    Atgriež pēdējo ievietotā rindas ID.
    
    Args:
        cursor: Datu bāzes kursors
        
    Returns:
        Pēdējā rindas ID
    """
    if is_postgres():
        # PostgreSQL atgriež pēdējo ID no cursor
        return cursor.fetchone()[0] if cursor.rowcount > 0 else None
    else:
        # SQLite
        return cursor.lastrowid


def _get_placeholder() -> str:
    """Atgriež placeholder atkarībā no datubāzes veida."""
    return '%s' if is_postgres() else '?'


def _get_auto_increment() -> str:
    """Atgriež AUTO INCREMENT sintaksi atkarībā no datubāzes veida."""
    if is_postgres():
        return 'SERIAL'
    else:
        return 'INTEGER PRIMARY KEY AUTOINCREMENT'


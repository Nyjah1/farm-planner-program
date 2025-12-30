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
        DATABASE_URL string vai None, ja nav iestatīts
    """
    # Mēģina iegūt no Streamlit secrets (Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'DB_URL' in st.secrets:
            return st.secrets['DB_URL']
    except Exception:
        pass
    
    # Fallback uz vides mainīgo
    return os.environ.get('DATABASE_URL')


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
    
    Ja DATABASE_URL ir iestatīts, izmanto PostgreSQL (psycopg2).
    Pretējā gadījumā izmanto SQLite.
    
    Returns:
        sqlite3.Connection vai psycopg2.connection
    """
    database_url = get_database_url()
    
    if database_url:
        # PostgreSQL
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2-binary nav instalēts. "
                "Instalējiet ar: pip install psycopg2-binary"
            )
        
        # Parse DATABASE_URL (Render formāts: postgresql://user:pass@host:port/dbname)
        # psycopg2 atbalsta tiešu DATABASE_URL izmantošanu
        return psycopg2.connect(database_url)
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
    """
    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
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


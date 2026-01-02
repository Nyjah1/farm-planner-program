"""
Datu glabāšanas klase ar atbalstu gan SQLite, gan PostgreSQL.
"""
import json
import sys
import io
import os
from pathlib import Path
from typing import List, Optional, Dict, Union

# Iestatīt UTF-8 kodējumu Windows sistēmām
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from .db import get_connection, get_db_cursor, is_postgres, get_lastrowid, _get_placeholder, _get_auto_increment
from .models import FieldModel, PlantingRecord, SoilType, UserModel
import bcrypt
from datetime import datetime


def _get_insert_or_replace(table: str, columns: List[str], values: List[str]) -> str:
    """
    Atgriež INSERT OR REPLACE SQL atkarībā no datubāzes veida.
    
    Args:
        table: Tabulas nosaukums
        columns: Kolonnu saraksts
        values: Vērtību placeholders
        
    Returns:
        SQL vaicājums
    """
    placeholders = ', '.join(values)
    cols = ', '.join(columns)
    
    if is_postgres():
        # PostgreSQL izmanto ON CONFLICT
        pk_cols = ['field_id', 'year'] if table == 'plantings' else ['id']
        conflict_cols = ', '.join(pk_cols)
        update_cols = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in pk_cols])
        return f"""
            INSERT INTO {table} ({cols})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_cols}
        """
    else:
        # SQLite izmanto INSERT OR REPLACE
        return f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"


class Storage:
    """Datu glabāšanas klase ar atbalstu gan SQLite, gan PostgreSQL."""
    
    def __init__(self, db_path: str = "data/farm.db"):
        """
        Inicializē datubāzi un izveido tabulas.
        
        Args:
            db_path: Ceļš uz SQLite datubāzi (tiek ignorēts, ja izmanto PostgreSQL)
            
        Raises:
            ValueError: Ja datubāzes inicializācija neizdodas
        """
        self.db_path = db_path
        self._init_successful = False
        if not is_postgres():
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._init_db()
            self._init_successful = True
        except Exception as e:
            self._init_successful = False
            error_msg = str(e)
            if "DB_URL" in error_msg or "postgresql" in error_msg.lower():
                # DB URL problēma
                raise ValueError(
                    "DB_URL nav iestatīts pareizi. "
                    "DB_URL jābūt PostgreSQL connection string, kas sākas ar 'postgresql://' vai 'postgres://'. "
                    "Atver Streamlit Cloud Settings → Secrets un ieliec pareizu DB_URL vai noņem DB_URL, lai izmantotu SQLite."
                ) from e
            else:
                # Cita datubāzes kļūda
                raise ValueError(
                    f"Kļūda inicializējot datubāzi: {error_msg}. "
                    "Pārbaudiet datubāzes savienojumu un mēģiniet vēlreiz."
                ) from e
    
    def _init_db(self):
        """Izveido tabulas, ja tās nav. Ja kāda tabula neizdodas, pārtrauc ar kļūdu."""
        # Enable pgcrypto extension for UUID generation (PostgreSQL only)
        if is_postgres():
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            except Exception as e:
                # pgcrypto might already exist or not be available, continue
                print(f"Brīdinājums: neizdevās izveidot pgcrypto extension: {e}")
        
        # Users tabula ar PRIMARY KEY - JĀBŪT PIRMAJAI
        # Izveido ar vienu transakciju, lai nodrošinātu, ka PRIMARY KEY ir definēts
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            username TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL UNIQUE,
                            password_hash TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot users tabulu: {e}") from e
        
        # Migrācija: nodrošina, ka users.id ir PRIMARY KEY (jāizpilda pirms citām tabulām)
        try:
            self._migrate_users_table()
        except Exception as e:
            raise RuntimeError(f"Kļūda migrējot users tabulu: {e}") from e
        
        # User sessions tabula ar FK uz users.id (users tabula jau ir izveidota ar PRIMARY KEY)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS user_sessions (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            session_token TEXT UNIQUE NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            expires_at TIMESTAMPTZ NOT NULL
                        )
                    """)
                else:
                    id_type = _get_auto_increment()
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS user_sessions (
                            id {id_type},
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            session_token TEXT NOT NULL UNIQUE,
                            created_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot user_sessions tabulu: {e}") from e
        
        # Auth tokens tabula ar FK uz users.id (users tabula jau ir izveidota ar PRIMARY KEY)
        # token_hash ir PRIMARY KEY (drošības labad glabājam hash, nevis plaintext token)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS auth_tokens (
                            token TEXT PRIMARY KEY,
                            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            expires_at TIMESTAMPTZ NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS auth_tokens (
                            token TEXT PRIMARY KEY,
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            expires_at TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot auth_tokens tabulu: {e}") from e
        
        # Lauku tabula ar FK uz users.id (users tabula jau ir izveidota ar PRIMARY KEY)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS fields (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            name TEXT NOT NULL,
                            area_ha REAL NOT NULL CHECK(area_ha > 0),
                            soil TEXT NOT NULL,
                            block_code TEXT,
                            lad_area_ha REAL,
                            lad_last_edited TEXT,
                            lad_last_synced TEXT,
                            rent_eur_ha REAL DEFAULT 0.0,
                            ph REAL,
                            is_organic INTEGER
                        )
                    """)
                else:
                    id_type = _get_auto_increment()
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS fields (
                            id {id_type},
                            owner_user_id INTEGER NOT NULL REFERENCES users(id),
                            name TEXT NOT NULL,
                            area_ha REAL NOT NULL CHECK(area_ha > 0),
                            soil TEXT NOT NULL,
                            block_code TEXT,
                            lad_area_ha REAL,
                            lad_last_edited TEXT,
                            lad_last_synced TEXT,
                            rent_eur_ha REAL DEFAULT 0.0,
                            ph REAL,
                            is_organic INTEGER
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot fields tabulu: {e}") from e
        
        # Stādīšanas ierakstu tabula ar FK uz users.id un fields.id (abas tabulas jau ir izveidotas)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS plantings (
                            field_id UUID NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
                            year INTEGER NOT NULL,
                            crop TEXT NOT NULL,
                            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            PRIMARY KEY (field_id, year)
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS plantings (
                            field_id INTEGER NOT NULL REFERENCES fields(id),
                            year INTEGER NOT NULL,
                            crop TEXT NOT NULL,
                            owner_user_id INTEGER NOT NULL REFERENCES users(id),
                            PRIMARY KEY (field_id, year)
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot plantings tabulu: {e}") from e
        
        # Favorites tabula ar FK uz users.id (users tabula jau ir izveidota ar PRIMARY KEY)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS favorites (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            crop_code TEXT NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            UNIQUE(user_id, crop_code)
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS favorites (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            crop_code TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            UNIQUE(user_id, crop_code)
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot favorites tabulu: {e}") from e
        
        # Field history tabula ar FK uz users.id un fields.id (abas tabulas jau ir izveidotas)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS field_history (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            field_id UUID NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
                            op_date DATE NOT NULL,
                            action TEXT NOT NULL,
                            notes TEXT,
                            crop TEXT,
                            amount NUMERIC,
                            unit TEXT,
                            cost_eur NUMERIC,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        )
                    """)
                    # Indeksi PostgreSQL
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_field_history_field_date 
                        ON field_history(field_id, op_date DESC)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_field_history_owner 
                        ON field_history(owner_user_id)
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS field_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL REFERENCES users(id),
                            field_id INTEGER NOT NULL REFERENCES fields(id),
                            op_date TEXT NOT NULL,
                            action TEXT NOT NULL,
                            notes TEXT,
                            crop TEXT,
                            amount REAL,
                            unit TEXT,
                            cost_eur REAL,
                            created_at TEXT DEFAULT (datetime('now'))
                        )
                    """)
                    # Indeksi SQLite
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_field_history_field_date 
                        ON field_history(field_id, op_date DESC)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_field_history_owner 
                        ON field_history(owner_user_id)
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot field_history tabulu: {e}") from e
        
        # Carbon factors tabula (oglekļa koeficienti)
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS carbon_factors (
                            action_key TEXT PRIMARY KEY,
                            co2e_kg_per_ha REAL NOT NULL,
                            unit TEXT DEFAULT 'kgCO2e/ha',
                            note TEXT
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS carbon_factors (
                            action_key TEXT PRIMARY KEY,
                            co2e_kg_per_ha REAL NOT NULL,
                            unit TEXT DEFAULT 'kgCO2e/ha',
                            note TEXT
                        )
                    """)
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot carbon_factors tabulu: {e}") from e
        
        # Ielādē default koeficientus, ja tabula ir tukša
        try:
            self._load_default_carbon_factors()
        except Exception as e:
            print(f"Brīdinājums: neizdevās ielādēt default oglekļa koeficientus: {e}")
        
        # Migrācija: pievieno kolonnas, ja tās neeksistē
        try:
            self._migrate_columns()
        except Exception as e:
            raise RuntimeError(f"Kļūda migrējot kolonnas: {e}") from e
        
        # Foreign key constraints jau ir tabulu definīcijās, nav nepieciešama atsevišķa migrācija
        # Migrācija tiek izpildīta tikai, ja tabulas jau eksistē bez FK (backward compatibility)
        try:
            self._migrate_foreign_keys()
        except Exception as e:
            # Migrācija nav kritiska, ja tabulas jau ir ar FK
            print(f"Brīdinājums: migrācija foreign key constraints: {e}")
        
        # Izpilda migrāciju augsnes vērtībām
        try:
            self.migrate_soil_values()
        except Exception as e:
            raise RuntimeError(f"Kļūda migrējot augsnes vērtības: {e}") from e
        
        # Migrācija: pārnes datus no plantings uz field_history (tikai vienu reizi)
        try:
            self._migrate_plantings_to_field_history()
        except Exception as e:
            # Migrācija nav kritiska, ja neizdodas
            print(f"Brīdinājums: migrācija no plantings uz field_history: {e}")
        
        # Migrācija: izveido admin user, ja nav neviena lietotāja
        try:
            self._ensure_admin_user()
        except Exception as e:
            raise RuntimeError(f"Kļūda izveidojot admin lietotāju: {e}") from e
    
    def _load_default_carbon_factors(self):
        """Ielādē default oglekļa koeficientus, ja tabula ir tukša."""
        placeholder = _get_placeholder()
        
        # Pārbauda, vai tabula ir tukša
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM carbon_factors")
            count = cursor.fetchone()[0]
            
            if count > 0:
                return  # Tabula nav tukša, nav nepieciešams ielādēt default
        
        # Default koeficienti
        default_factors = {
            "Aršana": 250.0,
            "Dziļirdināšana": 180.0,
            "Diskošana": 120.0,
            "Kultivēšana": 80.0,
            "Ecēšana": 40.0,
            "Veltņošana": 20.0,
            "Mēslošana": 150.0,
            "Miglošana": 60.0,
            "Kaļķošana": 200.0,
            "Kūlšana": 90.0,
            "Sēšana": 60.0,
            "Starpsējums / Segkultūra": -300.0,
            "Zaļmēslojuma iestrāde": -200.0,
            "Mulčēšana": -120.0,
            "Apūdeņošana": 110.0,
            "Cits": 0.0
        }
        
        # Ielādē default koeficientus
        with get_db_cursor() as cursor:
            for action_key, co2e_value in default_factors.items():
                if is_postgres():
                    cursor.execute(
                        f"""
                        INSERT INTO carbon_factors (action_key, co2e_kg_per_ha, unit)
                        VALUES ({placeholder}, {placeholder}, 'kgCO2e/ha')
                        ON CONFLICT (action_key) DO NOTHING
                        """,
                        (action_key, co2e_value)
                    )
                else:
                    cursor.execute(
                        f"""
                        INSERT OR IGNORE INTO carbon_factors (action_key, co2e_kg_per_ha, unit)
                        VALUES ({placeholder}, {placeholder}, 'kgCO2e/ha')
                        """,
                        (action_key, co2e_value)
                    )
    
    def _migrate_users_table(self):
        """Migrācija: nodrošina, ka users.id ir PRIMARY KEY un username ir UNIQUE."""
        if is_postgres():
            # PostgreSQL: pārbauda, vai tabula eksistē
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'users'
                        )
                    """)
                    table_exists = cursor.fetchone()[0]
            except Exception as e:
                print(f"Migrācija users tabula eksistence: {e}")
                return
            
            if table_exists:
                # Tabula eksistē - pārbauda un pievieno constraints, ja nepieciešams
                
                # Pārbauda, vai id ir PRIMARY KEY
                try:
                    with get_db_cursor() as cursor:
                        cursor.execute("""
                            SELECT constraint_name 
                            FROM information_schema.table_constraints 
                            WHERE table_name = 'users' 
                            AND constraint_type = 'PRIMARY KEY'
                        """)
                        if not cursor.fetchone():
                            # Nav PRIMARY KEY - pārbauda, vai id kolonna eksistē un ir NOT NULL
                            cursor.execute("""
                                SELECT column_name, is_nullable, data_type
                                FROM information_schema.columns 
                                WHERE table_name = 'users' 
                                AND column_name = 'id'
                            """)
                            id_col = cursor.fetchone()
                            
                            if id_col:
                                # Ja id nav NOT NULL, padara to NOT NULL
                                if id_col[1] == 'YES':
                                    cursor.execute("ALTER TABLE users ALTER COLUMN id SET NOT NULL")
                                
                                # Pievieno PRIMARY KEY
                                cursor.execute("ALTER TABLE users ADD PRIMARY KEY (id)")
                            else:
                                # Nav id kolonnas - izveido
                                cursor.execute("ALTER TABLE users ADD COLUMN id BIGSERIAL PRIMARY KEY")
                except Exception as e:
                    print(f"Migrācija users PRIMARY KEY: {e}")
                
                # Pārbauda, vai username ir UNIQUE
                try:
                    with get_db_cursor() as cursor:
                        cursor.execute("""
                            SELECT constraint_name 
                            FROM information_schema.table_constraints 
                            WHERE table_name = 'users' 
                            AND constraint_type = 'UNIQUE'
                            AND constraint_name LIKE '%username%'
                        """)
                        if not cursor.fetchone():
                            # Nav UNIQUE constraint - pievieno
                            cursor.execute("ALTER TABLE users ADD CONSTRAINT users_username_unique UNIQUE (username)")
                except Exception as e:
                    print(f"Migrācija users UNIQUE: {e}")
                
                # Pārbauda, vai created_at ir ar DEFAULT
                try:
                    with get_db_cursor() as cursor:
                        cursor.execute("""
                            SELECT column_default 
                            FROM information_schema.columns 
                            WHERE table_name = 'users' 
                            AND column_name = 'created_at'
                        """)
                        row = cursor.fetchone()
                        if not row or not row[0]:
                            # Nav DEFAULT - pievieno
                            cursor.execute("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now()")
                except Exception as e:
                    print(f"Migrācija users created_at DEFAULT: {e}")
        else:
            # SQLite: PRIMARY KEY jau ir definēts ar INTEGER PRIMARY KEY AUTOINCREMENT
            # Pārbauda, vai username ir UNIQUE (jau ir definēts ar UNIQUE constraint)
            pass
    
    def _migrate_foreign_keys(self):
        """Migrācija: pievieno foreign key constraints uz users(id)."""
        if is_postgres():
            # PostgreSQL: vispirms pārbauda, vai users.id ir PRIMARY KEY
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'users' 
                        AND constraint_type = 'PRIMARY KEY'
                    """)
                    has_pk = cursor.fetchone() is not None
                    
                    if not has_pk:
                        raise RuntimeError("users.id nav PRIMARY KEY, nevar pievienot foreign key constraints")
            except Exception as e:
                raise RuntimeError(f"Kļūda pārbaudot users PRIMARY KEY: {e}") from e
            
            # Pievieno foreign key constraints, ja tās nav (katra savā transakcijā)
            
            # Migrācija: pārveido auth_tokens tabulu uz jauno struktūru (token kā PRIMARY KEY)
            # Tikai PostgreSQL (SQLite nav nepieciešama migrācija, jo tabula tiek izveidota ar pareizo struktūru)
            if is_postgres():
                try:
                    with get_db_cursor() as cursor:
                        # Pārbauda, vai tabula eksistē ar veco struktūru (token_hash kolonna)
                        cursor.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'auth_tokens' 
                            AND column_name = 'token_hash'
                        """)
                        if cursor.fetchone():
                            # Vecā struktūra - migrē uz jauno
                            # 1. Izveido jaunu tabulu ar pareizo struktūru
                            cursor.execute("""
                                CREATE TABLE IF NOT EXISTS auth_tokens_new (
                                    token TEXT PRIMARY KEY,
                                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                                    expires_at TIMESTAMPTZ NOT NULL,
                                    created_at TIMESTAMPTZ DEFAULT NOW()
                                )
                            """)
                            # 2. Kopē datus no vecās tabulas (izlaiž dublikātus)
                            # Izmantojam DISTINCT ON, lai izvairītos no dublikātiem
                            cursor.execute("""
                                INSERT INTO auth_tokens_new (token, user_id, expires_at, created_at)
                                SELECT DISTINCT ON (token_hash) token_hash, user_id, expires_at, created_at
                                FROM auth_tokens
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM auth_tokens_new WHERE token = auth_tokens.token_hash
                                )
                            """)
                            # 3. Dzēš veco tabulu
                            cursor.execute("DROP TABLE IF EXISTS auth_tokens")
                            # 4. Pārdēvē jauno tabulu
                            cursor.execute("ALTER TABLE auth_tokens_new RENAME TO auth_tokens")
                except Exception as e:
                    # Ja migrācija neizdodas, turpinām (var būt, ka tabula jau ir pareiza)
                    print(f"Migrācija auth_tokens struktūra: {e}")
            
            # auth_tokens.user_id -> users.id FK constraint
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'auth_tokens' 
                        AND constraint_type = 'FOREIGN KEY'
                        AND constraint_name LIKE '%user_id%'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("""
                            ALTER TABLE auth_tokens 
                            ADD CONSTRAINT auth_tokens_user_id_fkey 
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        """)
            except Exception as e:
                print(f"Migrācija auth_tokens FK: {e}")
            
            # fields.owner_user_id -> users.id
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'fields' 
                        AND constraint_type = 'FOREIGN KEY'
                        AND constraint_name LIKE '%owner_user_id%'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("""
                            ALTER TABLE fields 
                            ADD CONSTRAINT fields_owner_user_id_fkey 
                            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
                        """)
            except Exception as e:
                print(f"Migrācija fields FK: {e}")
            
            # plantings.owner_user_id -> users.id
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'plantings' 
                        AND constraint_type = 'FOREIGN KEY'
                        AND constraint_name LIKE '%owner_user_id%'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("""
                            ALTER TABLE plantings 
                            ADD CONSTRAINT plantings_owner_user_id_fkey 
                            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
                        """)
            except Exception as e:
                print(f"Migrācija plantings FK: {e}")
            
            # user_sessions.user_id -> users.id
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'user_sessions' 
                        AND constraint_type = 'FOREIGN KEY'
                        AND constraint_name LIKE '%user_id%'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("""
                            ALTER TABLE user_sessions 
                            ADD CONSTRAINT user_sessions_user_id_fkey 
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        """)
            except Exception as e:
                print(f"Migrācija user_sessions FK: {e}")
            
            # plantings.field_id -> fields.id (ja nav)
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'plantings' 
                        AND constraint_type = 'FOREIGN KEY'
                        AND constraint_name LIKE '%field_id%'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("""
                            ALTER TABLE plantings 
                            ADD CONSTRAINT plantings_field_id_fkey 
                            FOREIGN KEY (field_id) REFERENCES fields(id) ON DELETE CASCADE
                        """)
            except Exception as e:
                print(f"Migrācija plantings field_id FK: {e}")
        else:
            # SQLite: foreign key constraints tiek pievienotas tabulas izveides laikā
            # Bet var mēģināt pievienot arī pēc tam
            try:
                # SQLite nevar pievienot foreign key pēc tabulas izveides viegli
                # Bet var pārbaudīt, vai tabulas ir pareizi definētas
                pass
            except Exception as e:
                print(f"Migrācija SQLite FK: {e}")
    
    def _migrate_columns(self):
        """Pievieno jaunas kolonnas, ja tās neeksistē."""
        with get_db_cursor() as cursor:
            # Migrācija: maina user_id uz owner_user_id fields tabulā
            try:
                cursor.execute("ALTER TABLE fields ADD COLUMN owner_user_id INTEGER")
                # Kopē datus no user_id uz owner_user_id, ja user_id eksistē
                try:
                    cursor.execute("UPDATE fields SET owner_user_id = user_id WHERE owner_user_id IS NULL")
                except Exception:
                    pass
            except Exception:
                pass
            
            # Pievieno citas kolonnas fields tabulai
            new_columns = [
                ("block_code", "TEXT"),
                ("lad_area_ha", "REAL"),
                ("lad_last_edited", "TEXT"),
                ("lad_last_synced", "TEXT"),
                ("rent_eur_ha", "REAL DEFAULT 0.0"),
                ("ph", "REAL"),
                ("is_organic", "INTEGER")
            ]
            
            for col_name, col_type in new_columns:
                try:
                    cursor.execute(f"ALTER TABLE fields ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
            
            # Migrācija: pievieno owner_user_id plantings tabulai
            try:
                cursor.execute("ALTER TABLE plantings ADD COLUMN owner_user_id INTEGER")
                # Kopē datus no user_id uz owner_user_id, ja user_id eksistē
                try:
                    cursor.execute("UPDATE plantings SET owner_user_id = user_id WHERE owner_user_id IS NULL")
                except Exception:
                    pass
            except Exception:
                pass
            
            # Migrācija: piešķir owner_user_id esošajiem ierakstiem
            cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
            first_user_row = cursor.fetchone()
            
            if first_user_row:
                first_user_id = first_user_row[0]
            else:
                # Nav neviena lietotāja - izveido admin user
                admin_user = self.create_user("admin", "admin123")
                if admin_user:
                    first_user_id = admin_user.id
                else:
                    first_user_id = 1
            
            # Aizpilda owner_user_id esošajiem ierakstiem
            placeholder = _get_placeholder()
            cursor.execute(
                f"UPDATE fields SET owner_user_id = {placeholder} WHERE owner_user_id IS NULL",
                (first_user_id,)
            )
            cursor.execute(
                f"UPDATE plantings SET owner_user_id = {placeholder} WHERE owner_user_id IS NULL",
                (first_user_id,)
            )
    
    def _migrate_plantings_to_field_history(self):
        """
        Migrācija: pārnes datus no plantings tabulas uz field_history.
        Izpilda tikai vienu reizi, ja field_history ir tukša.
        """
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Pārbauda, vai field_history tabula eksistē un ir tukša
            if is_postgres():
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'field_history'
                    )
                """)
                field_history_exists = cursor.fetchone()[0]
                
                if not field_history_exists:
                    return  # Tabula nav izveidota, nav ko migrēt
                
                cursor.execute("SELECT COUNT(*) FROM field_history")
                field_history_count = cursor.fetchone()[0]
                
                if field_history_count > 0:
                    return  # field_history nav tukša, migrācija jau izpildīta
                
                # Pārbauda, vai plantings tabula eksistē
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'plantings'
                    )
                """)
                plantings_exists = cursor.fetchone()[0]
                
                if not plantings_exists:
                    return  # Nav plantings tabulas, nav ko migrēt
                
                # Iegūst visus plantings ierakstus
                cursor.execute("SELECT field_id, year, crop, owner_user_id FROM plantings")
                plantings_rows = cursor.fetchall()
                
                if not plantings_rows:
                    return  # Nav datu plantings tabulā
                
                # Pārnes datus uz field_history
                for row in plantings_rows:
                    field_id, year, crop, owner_user_id = row
                    op_date = f"{year}-01-01"  # YYYY-01-01 formāts
                    action = "Sēšana"
                    notes = "Migrēts no sējumu vēstures"
                    
                    cursor.execute(
                        f"""
                        INSERT INTO field_history 
                        (owner_user_id, field_id, op_date, action, crop, notes)
                        VALUES ({placeholder}, {placeholder}, {placeholder}::DATE, {placeholder}, {placeholder}, {placeholder})
                        """,
                        (owner_user_id, field_id, op_date, action, crop, notes)
                    )
            else:
                # SQLite
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='field_history'
                """)
                if not cursor.fetchone():
                    return  # Tabula nav izveidota
                
                cursor.execute("SELECT COUNT(*) FROM field_history")
                field_history_count = cursor.fetchone()[0]
                
                if field_history_count > 0:
                    return  # field_history nav tukša, migrācija jau izpildīta
                
                # Pārbauda, vai plantings tabula eksistē
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='plantings'
                """)
                if not cursor.fetchone():
                    return  # Nav plantings tabulas
                
                # Iegūst visus plantings ierakstus
                cursor.execute("SELECT field_id, year, crop, owner_user_id FROM plantings")
                plantings_rows = cursor.fetchall()
                
                if not plantings_rows:
                    return  # Nav datu plantings tabulā
                
                # Pārnes datus uz field_history
                for row in plantings_rows:
                    field_id, year, crop, owner_user_id = row
                    op_date = f"{year}-01-01"  # YYYY-01-01 formāts
                    action = "Sēšana"
                    notes = "Migrēts no sējumu vēstures"
                    
                    cursor.execute(
                        f"""
                        INSERT INTO field_history 
                        (owner_user_id, field_id, op_date, action, crop, notes, created_at)
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, datetime('now'))
                        """,
                        (owner_user_id, field_id, op_date, action, crop, notes)
                    )
    
    def _ensure_admin_user(self):
        """Izveido admin user, ja nav neviena lietotāja."""
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            if count == 0:
                self.create_user("admin", "admin123")
    
    def migrate_soil_values(self):
        """Migrē vecās augsnes vērtības uz jaunajām (label -> code, vecie kodi -> jaunie kodi)."""
        # Mapping no vecajām label uz code
        label_to_code = {
            "Smilšaina (Podzolaugsne)": "smilts",
            "Auglīga (Velēnu karbonātaugsne)": "mālaina",
            "Mālaina (Velēnu karbonātaugsne)": "mālaina",
            "Kūdraina (Kūdraugsne)": "kūdra",
            "Mitra (Glejaugsne)": "mitra"
        }
        
        # Mapping no vecajiem kodiem uz jaunajiem
        old_code_to_new = {
            "mals": "mālaina",
            "kudra": "kūdra"
        }
        
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Atrod visus laukus ar vecajām label vērtībām un migrē uz code
            for label, code in label_to_code.items():
                cursor.execute(
                    f"UPDATE fields SET soil = {placeholder} WHERE soil = {placeholder}",
                    (code, label)
                )
            
            # Migrē vecos kodus uz jaunajiem
            for old_code, new_code in old_code_to_new.items():
                cursor.execute(
                    f"UPDATE fields SET soil = {placeholder} WHERE soil = {placeholder}",
                    (new_code, old_code)
                )
    
    def create_user(self, username: str, password: str, display_name: Optional[str] = None) -> Optional[UserModel]:
        """Izveido jaunu lietotāju."""
        placeholder = _get_placeholder()
        
        # Pārbauda, vai lietotājs jau eksistē
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT id FROM users WHERE username = {placeholder}", (username,))
            if cursor.fetchone():
                return None
        
        # Hash paroli
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        created_at = datetime.now().isoformat()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if is_postgres():
                cursor.execute(
                    f"INSERT INTO users (username, password_hash, created_at) VALUES ({placeholder}, {placeholder}, {placeholder}) RETURNING id",
                    (username, password_hash, created_at)
                )
                user_id = cursor.fetchone()[0]
            else:
                cursor.execute(
                    f"INSERT INTO users (username, password_hash, created_at) VALUES ({placeholder}, {placeholder}, {placeholder})",
                    (username, password_hash, created_at)
                )
                user_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            return UserModel(id=user_id, username=username, password_hash=password_hash, created_at=created_at)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        """Autentificē lietotāju."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT id, username, password_hash, created_at FROM users WHERE username = {placeholder}",
                (username,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            user_id, db_username, password_hash, created_at = row
            
            if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                return UserModel(id=user_id, username=db_username, password_hash=password_hash, created_at=created_at)
            else:
                return None
    
    def get_user_by_id(self, user_id: Union[int, str]) -> Optional[UserModel]:
        """Iegūst lietotāju pēc ID."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT id, username, password_hash, created_at FROM users WHERE id = {placeholder}",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            user_id, username, password_hash, created_at = row
            # Convert UUID to string if needed (PostgreSQL)
            if is_postgres() and hasattr(user_id, '__str__'):
                user_id = str(user_id)
            # Convert datetime to string if needed
            if hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            return UserModel(id=user_id, username=username, password_hash=password_hash, created_at=str(created_at))
    
    def create_session(self, user_id: Union[int, str], session_token: str, expires_at: str) -> bool:
        """Izveido jaunu session ierakstu."""
        placeholder = _get_placeholder()
        created_at = datetime.now().isoformat()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO user_sessions (user_id, session_token, created_at, expires_at) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (user_id, session_token, created_at, expires_at)
            )
            conn.commit()
            cursor.close()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_session_by_token(self, session_token: str) -> Optional[Dict]:
        """Iegūst session pēc token un pārbauda, vai tas nav beidzies."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT user_id, expires_at FROM user_sessions WHERE session_token = {placeholder}",
                (session_token,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            user_id, expires_at_str = row
            
            # Pārbauda, vai session nav beidzies
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() > expires_at:
                    # Session beidzies - izdzēš to
                    self.delete_session_by_token(session_token)
                    return None
            except (ValueError, TypeError):
                # Nevar parsēt datumu - uzskata par nederīgu
                self.delete_session_by_token(session_token)
                return None
            
            return {"user_id": user_id, "expires_at": expires_at_str}
    
    def delete_session_by_token(self, session_token: str) -> bool:
        """Dzēš session pēc token."""
        placeholder = _get_placeholder()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM user_sessions WHERE session_token = {placeholder}",
                (session_token,)
            )
            conn.commit()
            cursor.close()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def create_remember_token(self, user_id: Union[int, str], token_hash: str, expires_at: str) -> bool:
        """
        Izveido jaunu remember token ierakstu.
        
        Args:
            user_id: Lietotāja ID
            token_hash: Token hash (SHA256)
            expires_at: Derīguma termiņš (ISO format string)
        
        Returns:
            True, ja izveidots veiksmīgi, False citādi
        """
        placeholder = _get_placeholder()
        created_at = datetime.now().isoformat()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # token_hash ir PRIMARY KEY (glabājam hash drošības labad)
            cursor.execute(
                f"INSERT INTO auth_tokens (token, user_id, expires_at, created_at) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (token_hash, user_id, expires_at, created_at)
            )
            conn.commit()
            cursor.close()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def verify_remember_token(self, token_hash: str) -> Optional[Union[int, str]]:
        """
        Pārbauda, vai token_hash ir derīgs un atgriež user_id.
        Ja token nav derīgs vai beidzies, dzēš to no DB.
        
        Args:
            token_hash: Token hash (SHA256)
        
        Returns:
            user_id (int vai str/UUID) vai None, ja token nav derīgs
        """
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # token_hash ir PRIMARY KEY (kolonna nosaukums ir "token")
            cursor.execute(
                f"SELECT user_id, expires_at FROM auth_tokens WHERE token = {placeholder}",
                (token_hash,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            user_id, expires_at_str = row
            
            # Convert UUID to string if needed (PostgreSQL)
            if is_postgres() and hasattr(user_id, '__str__'):
                user_id = str(user_id)
            
            # Convert datetime to string if needed
            if hasattr(expires_at_str, 'isoformat'):
                expires_at_str = expires_at_str.isoformat()
            
            # Pārbauda, vai token nav beidzies
            try:
                expires_at = datetime.fromisoformat(str(expires_at_str))
                if datetime.now() > expires_at:
                    # Token beidzies - izdzēš to
                    self.revoke_remember_token(token_hash)
                    return None
            except (ValueError, TypeError):
                # Nevar parsēt datumu - uzskata par nederīgu
                self.revoke_remember_token(token_hash)
                return None
            
            return user_id
    
    def revoke_remember_token(self, token_hash: str) -> bool:
        """
        Invalidē remember token (izdzēš no DB).
        
        Args:
            token_hash: Token hash (SHA256)
        
        Returns:
            True, ja izdzēsts veiksmīgi, False citādi
        """
        placeholder = _get_placeholder()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # token_hash ir PRIMARY KEY (kolonna nosaukums ir "token")
            cursor.execute(
                f"DELETE FROM auth_tokens WHERE token = {placeholder}",
                (token_hash,)
            )
            conn.commit()
            cursor.close()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def add_field(self, field: FieldModel, user_id: Union[int, str]) -> FieldModel:
        """Pievieno lauku datubāzē."""
        placeholder = _get_placeholder()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Konvertē is_organic uz INTEGER (None -> None, True -> 1, False -> 0)
            is_organic_int = None if field.is_organic is None else (1 if field.is_organic else 0)
            
            if is_postgres():
                cursor.execute(
                    f"INSERT INTO fields (owner_user_id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) RETURNING id",
                    (user_id, field.name, field.area_ha, field.soil.code, field.block_code, field.lad_area_ha, field.lad_last_edited, field.lad_last_synced, field.rent_eur_ha, field.ph, is_organic_int)
                )
                field_id = cursor.fetchone()[0]
                # Convert UUID to string if needed
                if hasattr(field_id, '__str__'):
                    field_id = str(field_id)
            else:
                cursor.execute(
                    f"INSERT INTO fields (owner_user_id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (user_id, field.name, field.area_ha, field.soil.code, field.block_code, field.lad_area_ha, field.lad_last_edited, field.lad_last_synced, field.rent_eur_ha, field.ph, is_organic_int)
                )
                field_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            
            return FieldModel(
                id=field_id,
                name=field.name,
                area_ha=field.area_ha,
                soil=field.soil,
                owner_user_id=user_id,
                block_code=field.block_code,
                lad_area_ha=field.lad_area_ha,
                lad_last_edited=field.lad_last_edited,
                lad_last_synced=field.lad_last_synced,
                rent_eur_ha=field.rent_eur_ha,
                ph=field.ph,
                is_organic=field.is_organic
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def list_fields(self, user_id: Union[int, str]) -> List[FieldModel]:
        """Atgriež visus laukus konkrētam lietotājam."""
        # Mapping no vecajām label uz code (backward compatibility)
        label_to_code = {
            "Smilšaina (Podzolaugsne)": "smilts",
            "Auglīga (Velēnu karbonātaugsne)": "mālaina",
            "Mālaina (Velēnu karbonātaugsne)": "mālaina",
            "Kūdraina (Kūdraugsne)": "kūdra",
            "Mitra (Glejaugsne)": "mitra"
        }
        
        # Mapping no vecajiem kodiem uz jaunajiem (migrācija)
        old_code_to_new = {
            "mals": "mālaina",
            "kudra": "kūdra"
        }
        
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic, owner_user_id FROM fields WHERE owner_user_id = {placeholder}",
                (user_id,)
            )
            rows = cursor.fetchall()
            
            fields = []
            for row in rows:
                field_id = row[0]
                owner_user_id = row[11]
                soil_code = row[3]
                
                # Convert UUID to string if needed (PostgreSQL)
                if is_postgres():
                    if hasattr(field_id, '__str__'):
                        field_id = str(field_id)
                    if hasattr(owner_user_id, '__str__'):
                        owner_user_id = str(owner_user_id)
                
                # Ja ir vecā label vērtība, konvertē uz code
                if soil_code in label_to_code:
                    soil_code = label_to_code[soil_code]
                
                # Migrē vecos kodus uz jaunajiem
                if soil_code in old_code_to_new:
                    soil_code = old_code_to_new[soil_code]
                
                # Atrod SoilType enum pēc code (ar noklusējumu drošībai)
                soil = next((s for s in SoilType if s.code == soil_code), SoilType.SMILTS)
                
                # Apstrādā rent_eur_ha - ja ir None vai nav kolonnas, izmanto 0.0
                rent_value = 0.0
                if len(row) > 8 and row[8] is not None:
                    try:
                        rent_value = float(row[8])
                    except (TypeError, ValueError):
                        rent_value = 0.0
                
                # Apstrādā ph - ja ir None vai nav kolonnas, izmanto None
                ph_value = None
                if len(row) > 9 and row[9] is not None:
                    try:
                        ph_value = float(row[9])
                    except (TypeError, ValueError):
                        ph_value = None
                
                # Apstrādā is_organic - konvertē no INTEGER uz bool vai None
                is_organic_value = None
                if len(row) > 10 and row[10] is not None:
                    is_organic_value = bool(row[10])
                
                # Extract owner_user_id (may have been converted above)
                if len(row) > 11:
                    row_owner_user_id = row[11]
                    if is_postgres() and hasattr(row_owner_user_id, '__str__'):
                        row_owner_user_id = str(row_owner_user_id)
                else:
                    row_owner_user_id = user_id
                
                fields.append(FieldModel(
                    id=field_id,
                    name=row[1],
                    area_ha=row[2],
                    soil=soil,
                    owner_user_id=row_owner_user_id,
                    block_code=row[4] if len(row) > 4 else None,
                    lad_area_ha=row[5] if len(row) > 5 else None,
                    lad_last_edited=row[6] if len(row) > 6 else None,
                    lad_last_synced=row[7] if len(row) > 7 else None,
                    rent_eur_ha=rent_value,
                    ph=ph_value,
                    is_organic=is_organic_value
                ))
            
            return fields
    
    def update_field(
        self,
        field_id: int,
        user_id: int,
        name: str,
        area_ha: float,
        soil: SoilType,
        block_code: Optional[str] = None,
        lad_area_ha: Optional[float] = None,
        lad_last_edited: Optional[str] = None,
        lad_last_synced: Optional[str] = None,
        rent_eur_ha: float = 0.0,
        ph: Optional[float] = None,
        is_organic: Optional[bool] = None
    ) -> bool:
        """Atjauno lauka datus (tikai, ja pieder lietotājam)."""
        placeholder = _get_placeholder()
        
        # Pārbauda, vai lauks pieder lietotājam
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT owner_user_id FROM fields WHERE id = {placeholder}",
                (field_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            row_user_id = row[0]
            # Convert UUID to string if needed for comparison
            if is_postgres() and hasattr(row_user_id, '__str__'):
                row_user_id = str(row_user_id)
            if str(row_user_id) != str(user_id):
                return False
        
        # Konvertē is_organic uz INTEGER (None -> None, True -> 1, False -> 0)
        is_organic_int = None if is_organic is None else (1 if is_organic else 0)
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"UPDATE fields SET name={placeholder}, area_ha={placeholder}, soil={placeholder}, block_code={placeholder}, lad_area_ha={placeholder}, lad_last_edited={placeholder}, lad_last_synced={placeholder}, rent_eur_ha={placeholder}, ph={placeholder}, is_organic={placeholder} WHERE id={placeholder} AND owner_user_id={placeholder}",
                (name, area_ha, soil.code, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic_int, field_id, user_id)
            )
            return cursor.rowcount > 0
    
    def add_planting(self, planting: PlantingRecord, user_id: Union[int, str]) -> PlantingRecord:
        """Pievieno stādīšanas ierakstu (tikai, ja field_id pieder lietotājam)."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Pārbauda, vai field_id pieder lietotājam
            cursor.execute(
                f"SELECT owner_user_id FROM fields WHERE id = {placeholder} AND owner_user_id = {placeholder}",
                (planting.field_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Lauks nav atrasts vai nepieder lietotājam")
            
            # Pievieno ar owner_user_id
            sql = _get_insert_or_replace(
                'plantings',
                ['field_id', 'year', 'crop', 'owner_user_id'],
                [placeholder, placeholder, placeholder, placeholder]
            )
            cursor.execute(sql, (planting.field_id, planting.year, planting.crop, user_id))
            
            return PlantingRecord(
                field_id=planting.field_id,
                year=planting.year,
                crop=planting.crop,
                owner_user_id=user_id
            )
    
    def list_plantings(self, user_id: Union[int, str]) -> List[PlantingRecord]:
        """Atgriež visus stādīšanas ierakstus konkrētam lietotājam."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT field_id, year, crop, owner_user_id FROM plantings WHERE owner_user_id = {placeholder}",
                (user_id,)
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                field_id = row[0]
                owner_user_id = row[3] if len(row) > 3 else user_id
                # Convert UUID to string if needed (PostgreSQL)
                if is_postgres():
                    if hasattr(field_id, '__str__'):
                        field_id = str(field_id)
                    if hasattr(owner_user_id, '__str__'):
                        owner_user_id = str(owner_user_id)
                result.append(PlantingRecord(
                    field_id=field_id,
                    year=row[1],
                    crop=row[2],
                    owner_user_id=owner_user_id
                ))
            return result
    
    def delete_field(self, field_id: Union[int, str], user_id: Union[int, str]) -> bool:
        """Dzēš lauku un visus saistītos stādīšanas ierakstus (tikai, ja pieder lietotājam)."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Dzēš saistītos ierakstus (tikai no šī lietotāja)
            cursor.execute(
                f"DELETE FROM plantings WHERE field_id = {placeholder} AND owner_user_id = {placeholder}",
                (field_id, user_id)
            )
            
            # Dzēš lauku (tikai, ja pieder lietotājam)
            cursor.execute(
                f"DELETE FROM fields WHERE id = {placeholder} AND owner_user_id = {placeholder}",
                (field_id, user_id)
            )
            return cursor.rowcount > 0
    
    def clear_user_data(self, user_id: Union[int, str]) -> bool:
        """Dzēš visus datus konkrētam lietotājam."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Dzēš plantings tieši pēc owner_user_id
            cursor.execute(
                f"DELETE FROM plantings WHERE owner_user_id = {placeholder}",
                (user_id,)
            )
            
            # Dzēš fields
            cursor.execute(
                f"DELETE FROM fields WHERE owner_user_id = {placeholder}",
                (user_id,)
            )
            return True
    
    def get_favorites(self, user_id) -> List[str]:
        """Atgriež favorīto kultūru sarakstu konkrētam lietotājam."""
        placeholder = _get_placeholder()
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT crop_code FROM favorites WHERE user_id = {placeholder} ORDER BY created_at",
                (user_id,)
            )
            rows = cursor.fetchall()
            return [row[0] for row in rows] if rows else []
    
    def set_favorites(self, favorites: List[str], user_id) -> bool:
        """Saglabā favorīto kultūru sarakstu konkrētam lietotājam."""
        placeholder = _get_placeholder()
        try:
            with get_db_cursor() as cursor:
                # Dzēš esošos favorītus
                cursor.execute(
                    f"DELETE FROM favorites WHERE user_id = {placeholder}",
                    (user_id,)
                )
                
                # Ievieto jaunos favorītus
                for crop_code in favorites:
                    if is_postgres():
                        cursor.execute(
                            f"INSERT INTO favorites (user_id, crop_code) VALUES ({placeholder}, {placeholder})",
                            (user_id, crop_code)
                        )
                    else:
                        cursor.execute(
                            f"INSERT INTO favorites (user_id, crop_code, created_at) VALUES ({placeholder}, {placeholder}, datetime('now'))",
                            (user_id, crop_code)
                        )
                return True
        except Exception as e:
            print(f"[ERROR] Neizdevās saglabāt favorītus: {e}")
            return False
    
    def add_field_history(
        self,
        owner_user_id: Union[int, str],
        field_id: Union[int, str],
        op_date: str,  # ISO format date string (YYYY-MM-DD)
        action: str,
        notes: Optional[str] = None,
        crop: Optional[str] = None,
        amount: Optional[float] = None,
        unit: Optional[str] = None,
        cost_eur: Optional[float] = None
    ) -> bool:
        """
        Pievieno jaunu ierakstu lauka vēsturē.
        
        Args:
            owner_user_id: Lietotāja ID
            field_id: Lauka ID
            op_date: Operācijas datums (ISO format: YYYY-MM-DD)
            action: Operācijas veids (piemēram, "Sēšana", "Apstrāde", "Novākšana")
            notes: Opcionālas piezīmes
            crop: Opcionāla kultūra
            amount: Opcionāls daudzums
            unit: Opcionāla mērvienība
            cost_eur: Opcionālas izmaksas eiro
            
        Returns:
            True, ja ieraksts pievienots veiksmīgi, False citādi
        """
        placeholder = _get_placeholder()
        
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute(
                        f"""
                        INSERT INTO field_history 
                        (owner_user_id, field_id, op_date, action, notes, crop, amount, unit, cost_eur)
                        VALUES ({placeholder}, {placeholder}, {placeholder}::DATE, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                        """,
                        (owner_user_id, field_id, op_date, action, notes, crop, amount, unit, cost_eur)
                    )
                else:
                    # SQLite: op_date kā TEXT
                    cursor.execute(
                        f"""
                        INSERT INTO field_history 
                        (owner_user_id, field_id, op_date, action, notes, crop, amount, unit, cost_eur, created_at)
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, datetime('now'))
                        """,
                        (owner_user_id, field_id, op_date, action, notes, crop, amount, unit, cost_eur)
                    )
                return True
        except Exception as e:
            print(f"[ERROR] Neizdevās pievienot lauka vēstures ierakstu: {e}")
            return False
    
    def list_field_history(
        self,
        owner_user_id: Union[int, str],
        field_id: Union[int, str]
    ) -> List[Dict]:
        """
        Atgriež lauka vēstures ierakstus sakārtotus pēc datuma (DESC) un ID (DESC).
        
        Args:
            owner_user_id: Lietotāja ID
            field_id: Lauka ID
            
        Returns:
            Saraksts ar vārdnīcām, katrā: id, owner_user_id, field_id, op_date, action, 
            notes, crop, amount, unit, cost_eur, created_at
        """
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, owner_user_id, field_id, op_date, action, notes, crop, amount, unit, cost_eur, created_at
                FROM field_history
                WHERE owner_user_id = {placeholder} AND field_id = {placeholder}
                ORDER BY op_date DESC, id DESC
                """,
                (owner_user_id, field_id)
            )
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                history_id = row[0]
                row_owner_user_id = row[1]
                row_field_id = row[2]
                
                # Convert UUID to string if needed (PostgreSQL)
                if is_postgres():
                    if hasattr(history_id, '__str__'):
                        history_id = str(history_id)
                    if hasattr(row_owner_user_id, '__str__'):
                        row_owner_user_id = str(row_owner_user_id)
                    if hasattr(row_field_id, '__str__'):
                        row_field_id = str(row_field_id)
                
                # Convert datetime to string if needed
                created_at = row[10]
                if hasattr(created_at, 'isoformat'):
                    created_at = created_at.isoformat()
                
                result.append({
                    'id': history_id,
                    'owner_user_id': row_owner_user_id,
                    'field_id': row_field_id,
                    'op_date': str(row[3]),  # DATE or TEXT
                    'action': row[4],
                    'notes': row[5],
                    'crop': row[6],
                    'amount': float(row[7]) if row[7] is not None else None,
                    'unit': row[8],
                    'cost_eur': float(row[9]) if row[9] is not None else None,
                    'created_at': str(created_at)
                })
            
            return result
    
    def delete_field_history(
        self,
        owner_user_id: Union[int, str],
        history_id: Union[int, str]
    ) -> bool:
        """
        Dzēš lauka vēstures ierakstu (tikai, ja tas pieder lietotājam).
        
        Args:
            owner_user_id: Lietotāja ID
            history_id: Vēstures ieraksta ID
            
        Returns:
            True, ja ieraksts izdzēsts, False citādi
        """
        placeholder = _get_placeholder()
        
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    f"""
                    DELETE FROM field_history
                    WHERE id = {placeholder} AND owner_user_id = {placeholder}
                    """,
                    (history_id, owner_user_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[ERROR] Neizdevās dzēst lauka vēstures ierakstu: {e}")
            return False
    
    def update_field_history(
        self,
        owner_user_id: Union[int, str],
        history_id: Union[int, str],
        op_date: Optional[str] = None,
        action: Optional[str] = None,
        notes: Optional[str] = None,
        crop: Optional[str] = None,
        amount: Optional[float] = None,
        unit: Optional[str] = None,
        cost_eur: Optional[float] = None
    ) -> bool:
        """
        Atjauno lauka vēstures ierakstu (tikai, ja tas pieder lietotājam).
        
        Args:
            owner_user_id: Lietotāja ID
            history_id: Vēstures ieraksta ID
            op_date: Jauns operācijas datums (ISO format: YYYY-MM-DD)
            action: Jauns operācijas veids
            notes: Jaunas piezīmes
            crop: Jauna kultūra
            amount: Jauns daudzums
            unit: Jauna mērvienība
            cost_eur: Jaunas izmaksas eiro
            
        Returns:
            True, ja ieraksts atjaunots, False citādi
        """
        placeholder = _get_placeholder()
        
        # Veido UPDATE SET daļu tikai ar mainītajiem laukiem
        updates = []
        params = []
        
        if op_date is not None:
            if is_postgres():
                updates.append(f"op_date = {placeholder}::DATE")
            else:
                updates.append(f"op_date = {placeholder}")
            params.append(op_date)
        
        if action is not None:
            updates.append(f"action = {placeholder}")
            params.append(action)
        
        if notes is not None:
            updates.append(f"notes = {placeholder}")
            params.append(notes)
        
        if crop is not None:
            updates.append(f"crop = {placeholder}")
            params.append(crop)
        
        if amount is not None:
            updates.append(f"amount = {placeholder}")
            params.append(amount)
        
        if unit is not None:
            updates.append(f"unit = {placeholder}")
            params.append(unit)
        
        if cost_eur is not None:
            updates.append(f"cost_eur = {placeholder}")
            params.append(cost_eur)
        
        if not updates:
            # Nav ko atjaunot
            return False
        
        # Pievieno WHERE nosacījumus
        params.extend([history_id, owner_user_id])
        
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE field_history
                    SET {', '.join(updates)}
                    WHERE id = {placeholder} AND owner_user_id = {placeholder}
                    """,
                    tuple(params)
                )
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[ERROR] Neizdevās atjaunot lauka vēstures ierakstu: {e}")
            return False
    
    def get_carbon_factor(self, action_key: str) -> float:
        """
        Atgriež oglekļa koeficientu (kgCO2e/ha) konkrētai darbībai.
        
        Args:
            action_key: Darbības nosaukums (piemēram, "Sēšana", "Aršana")
            
        Returns:
            Koeficients kgCO2e/ha (0, ja nav atrasts)
        """
        placeholder = _get_placeholder()
        
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT co2e_kg_per_ha FROM carbon_factors
                    WHERE action_key = {placeholder}
                    """,
                    (action_key,)
                )
                row = cursor.fetchone()
                if row:
                    return float(row[0])
                return 0.0
        except Exception as e:
            print(f"[ERROR] Neizdevās iegūt oglekļa koeficientu: {e}")
            return 0.0
    
    def get_all_carbon_factors(self) -> Dict[str, Dict]:
        """
        Atgriež visus oglekļa koeficientus.
        
        Returns:
            Vārdnīca ar action_key -> {co2e_kg_per_ha, unit, note}
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT action_key, co2e_kg_per_ha, unit, note
                    FROM carbon_factors
                    ORDER BY action_key
                """)
                rows = cursor.fetchall()
                
                result = {}
                for row in rows:
                    result[row[0]] = {
                        'co2e_kg_per_ha': float(row[1]),
                        'unit': row[2] or 'kgCO2e/ha',
                        'note': row[3]
                    }
                return result
        except Exception as e:
            print(f"[ERROR] Neizdevās iegūt oglekļa koeficientus: {e}")
            return {}
    
    def update_carbon_factor(
        self,
        action_key: str,
        co2e_kg_per_ha: float,
        unit: Optional[str] = None,
        note: Optional[str] = None
    ) -> bool:
        """
        Atjauno vai izveido oglekļa koeficientu.
        
        Args:
            action_key: Darbības nosaukums
            co2e_kg_per_ha: Koeficients kgCO2e/ha
            unit: Mērvienība (default: 'kgCO2e/ha')
            note: Piezīme
            
        Returns:
            True, ja veiksmīgi saglabāts
        """
        placeholder = _get_placeholder()
        
        if unit is None:
            unit = 'kgCO2e/ha'
        
        try:
            with get_db_cursor() as cursor:
                if is_postgres():
                    cursor.execute(
                        f"""
                        INSERT INTO carbon_factors (action_key, co2e_kg_per_ha, unit, note)
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})
                        ON CONFLICT (action_key) 
                        DO UPDATE SET 
                            co2e_kg_per_ha = EXCLUDED.co2e_kg_per_ha,
                            unit = EXCLUDED.unit,
                            note = EXCLUDED.note
                        """,
                        (action_key, co2e_kg_per_ha, unit, note)
                    )
                else:
                    cursor.execute(
                        f"""
                        INSERT OR REPLACE INTO carbon_factors (action_key, co2e_kg_per_ha, unit, note)
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})
                        """,
                        (action_key, co2e_kg_per_ha, unit, note)
                    )
                return True
        except Exception as e:
            print(f"[ERROR] Neizdevās saglabāt oglekļa koeficientu: {e}")
            return False
    
    def reset_carbon_factors_to_default(self) -> bool:
        """
        Atjauno visus oglekļa koeficientus uz default vērtībām.
        
        Returns:
            True, ja veiksmīgi atjaunots
        """
        try:
            # Dzēš visus esošos koeficientus
            with get_db_cursor() as cursor:
                cursor.execute("DELETE FROM carbon_factors")
            
            # Ielādē default koeficientus
            self._load_default_carbon_factors()
            return True
        except Exception as e:
            print(f"[ERROR] Neizdevās atjaunot default oglekļa koeficientus: {e}")
            return False

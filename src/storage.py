"""
Datu glabāšanas klase ar atbalstu gan SQLite, gan PostgreSQL.
"""
import json
import sys
import io
import os
from pathlib import Path
from typing import List, Optional

# Iestatīt UTF-8 kodējumu Windows sistēmām
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from .db import get_connection, get_db_cursor, is_postgres, get_lastrowid, _get_placeholder, _get_auto_increment
from .models import FieldModel, PlantingRecord, SoilType


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
        """
        self.db_path = db_path
        if not is_postgres():
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Izveido tabulas, ja tās nav."""
        with get_db_cursor() as cursor:
            # Lauku tabula
            id_type = _get_auto_increment()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS fields (
                    id {id_type},
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    area_ha REAL NOT NULL CHECK(area_ha > 0),
                    soil TEXT NOT NULL,
                    block_code TEXT,
                    lad_area_ha REAL,
                    lad_last_edited TEXT,
                    lad_last_synced TEXT,
                    rent_eur_ha REAL DEFAULT 0.0,
                    ph REAL
                )
            """)
            
            # Stādīšanas ierakstu tabula
            if is_postgres():
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plantings (
                        field_id INTEGER NOT NULL,
                        year INTEGER NOT NULL,
                        crop TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        PRIMARY KEY (field_id, year),
                        FOREIGN KEY (field_id) REFERENCES fields(id) ON DELETE CASCADE
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plantings (
                        field_id INTEGER NOT NULL,
                        year INTEGER NOT NULL,
                        crop TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        PRIMARY KEY (field_id, year),
                        FOREIGN KEY (field_id) REFERENCES fields(id)
                    )
                """)
            
            # Migrācija: pievieno kolonnas, ja tās neeksistē
            self._migrate_columns()
            
            # Izpilda migrāciju augsnes vērtībām
            self.migrate_soil_values()
    
    def _migrate_columns(self):
        """Pievieno jaunas kolonnas, ja tās neeksistē."""
        with get_db_cursor() as cursor:
            # Pārbauda un pievieno kolonnas fields tabulai
            new_columns = [
                ("user_id", "INTEGER"),
                ("block_code", "TEXT"),
                ("lad_area_ha", "REAL"),
                ("lad_last_edited", "TEXT"),
                ("lad_last_synced", "TEXT"),
                ("rent_eur_ha", "REAL DEFAULT 0.0"),
                ("ph", "REAL"),
                ("is_organic", "INTEGER")  # 0 = False, 1 = True, NULL = izmanto globālo iestatījumu
            ]
            
            for col_name, col_type in new_columns:
                try:
                    if is_postgres():
                        cursor.execute(f"ALTER TABLE fields ADD COLUMN {col_name} {col_type}")
                    else:
                        cursor.execute(f"ALTER TABLE fields ADD COLUMN {col_name} {col_type}")
                except Exception:
                    # Kolonna jau eksistē
                    pass
            
            # Migrācija: piešķir user_id esošajiem ierakstiem
            # Iegūst pirmā lietotāja ID vai izveido admin user
            cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
            first_user_row = cursor.fetchone()
            
            if first_user_row:
                first_user_id = first_user_row[0]
            else:
                # Nav neviena lietotāja - izveido admin user
                from .auth import create_user
                import os
                admin_email = os.getenv("FARM_ADMIN_EMAIL", "admin@example.com")
                admin_password = os.getenv("FARM_ADMIN_PASS", "admin123")
                admin_user = create_user(self, admin_email, admin_password)
                if admin_user:
                    first_user_id = admin_user["id"]
                else:
                    first_user_id = 1  # Fallback
            
            # Aizpilda user_id esošajiem fields ierakstiem
            placeholder = _get_placeholder()
            cursor.execute(
                f"UPDATE fields SET user_id = {placeholder} WHERE user_id IS NULL",
                (first_user_id,)
            )
            
            # Pievieno user_id plantings tabulai, ja nav
            try:
                if is_postgres():
                    cursor.execute("ALTER TABLE plantings ADD COLUMN user_id INTEGER")
                else:
                    cursor.execute("ALTER TABLE plantings ADD COLUMN user_id INTEGER")
            except Exception:
                # Kolonna jau eksistē
                pass
            
            # Aizpilda user_id esošajiem plantings ierakstiem
            cursor.execute(
                f"UPDATE plantings SET user_id = {placeholder} WHERE user_id IS NULL",
                (first_user_id,)
            )
    
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
    
    def add_field(self, field: FieldModel, user_id: int) -> FieldModel:
        """Pievieno lauku datubāzē."""
        placeholder = _get_placeholder()
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Konvertē is_organic uz INTEGER (None -> None, True -> 1, False -> 0)
            is_organic_int = None if field.is_organic is None else (1 if field.is_organic else 0)
            
            if is_postgres():
                cursor.execute(
                    f"INSERT INTO fields (user_id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) RETURNING id",
                    (user_id, field.name, field.area_ha, field.soil.code, field.block_code, field.lad_area_ha, field.lad_last_edited, field.lad_last_synced, field.rent_eur_ha, field.ph, is_organic_int)
                )
                field_id = cursor.fetchone()[0]
            else:
                cursor.execute(
                    f"INSERT INTO fields (user_id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
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
    
    def list_fields(self, user_id: int) -> List[FieldModel]:
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
                f"SELECT id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic FROM fields WHERE user_id = {placeholder}",
                (user_id,)
            )
            rows = cursor.fetchall()
            
            fields = []
            for row in rows:
                soil_code = row[3]
                
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
                
                fields.append(FieldModel(
                    id=row[0],
                    name=row[1],
                    area_ha=row[2],
                    soil=soil,
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
        
        # Konvertē is_organic uz INTEGER (None -> None, True -> 1, False -> 0)
        is_organic_int = None if is_organic is None else (1 if is_organic else 0)
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"UPDATE fields SET name={placeholder}, area_ha={placeholder}, soil={placeholder}, block_code={placeholder}, lad_area_ha={placeholder}, lad_last_edited={placeholder}, lad_last_synced={placeholder}, rent_eur_ha={placeholder}, ph={placeholder}, is_organic={placeholder} WHERE id={placeholder} AND user_id={placeholder}",
                (name, area_ha, soil.code, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, is_organic_int, field_id, user_id)
            )
            return cursor.rowcount > 0
    
    def add_planting(self, planting: PlantingRecord, user_id: int) -> PlantingRecord:
        """Pievieno stādīšanas ierakstu (tikai, ja field_id pieder lietotājam)."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Pārbauda, vai field_id pieder lietotājam
            cursor.execute(
                f"SELECT user_id FROM fields WHERE id = {placeholder} AND user_id = {placeholder}",
                (planting.field_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Lauks nav atrasts vai nepieder lietotājam")
            
            # Pievieno ar user_id
            sql = _get_insert_or_replace(
                'plantings',
                ['field_id', 'year', 'crop', 'user_id'],
                [placeholder, placeholder, placeholder, placeholder]
            )
            cursor.execute(sql, (planting.field_id, planting.year, planting.crop, user_id))
            
            return planting
    
    def list_plantings(self, user_id: int) -> List[PlantingRecord]:
        """Atgriež visus stādīšanas ierakstus konkrētam lietotājam."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT field_id, year, crop FROM plantings WHERE user_id = {placeholder}",
                (user_id,)
            )
            rows = cursor.fetchall()
            return [
                PlantingRecord(
                    field_id=row[0],
                    year=row[1],
                    crop=row[2]
                )
                for row in rows
            ]
    
    def delete_field(self, field_id: int, user_id: int) -> bool:
        """Dzēš lauku un visus saistītos stādīšanas ierakstus (tikai, ja pieder lietotājam)."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Dzēš saistītos ierakstus (tikai no šī lietotāja)
            cursor.execute(
                f"DELETE FROM plantings WHERE field_id = {placeholder} AND user_id = {placeholder}",
                (field_id, user_id)
            )
            
            # Dzēš lauku (tikai, ja pieder lietotājam)
            cursor.execute(
                f"DELETE FROM fields WHERE id = {placeholder} AND user_id = {placeholder}",
                (field_id, user_id)
            )
            return cursor.rowcount > 0
    
    def clear_user_data(self, user_id: int) -> bool:
        """Dzēš visus datus konkrētam lietotājam."""
        placeholder = _get_placeholder()
        
        with get_db_cursor() as cursor:
            # Dzēš plantings tieši pēc user_id
            cursor.execute(
                f"DELETE FROM plantings WHERE user_id = {placeholder}",
                (user_id,)
            )
            
            # Dzēš fields
            cursor.execute(
                f"DELETE FROM fields WHERE user_id = {placeholder}",
                (user_id,)
            )
            return True
    
    def get_favorites(self, user_id: int) -> List[str]:
        """Atgriež favorīto kultūru sarakstu konkrētam lietotājam."""
        # Ja izmanto PostgreSQL, glabā datubāzē
        if is_postgres():
            placeholder = _get_placeholder()
            with get_db_cursor() as cursor:
                cursor.execute(
                    f"SELECT favorites FROM user_favorites WHERE user_id = {placeholder}",
                    (user_id,)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        return json.loads(row[0])
                    except (json.JSONDecodeError, TypeError):
                        return []
                return []
        else:
            # SQLite: izmanto JSON failus
            favorites_path = Path(f"data/favorites_{user_id}.json")
            if not favorites_path.exists():
                return []
            
            try:
                with open(favorites_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("favorites", [])
            except Exception as e:
                print(f"[WARN] Neizdevās ielādēt favorītus: {e}")
                return []
    
    def set_favorites(self, favorites: List[str], user_id: int) -> bool:
        """Saglabā favorīto kultūru sarakstu konkrētam lietotājam."""
        # Ja izmanto PostgreSQL, glabā datubāzē
        if is_postgres():
            placeholder = _get_placeholder()
            with get_db_cursor() as cursor:
                # Izveido tabulu, ja tā nav
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_favorites (
                        user_id INTEGER PRIMARY KEY,
                        favorites TEXT
                    )
                """)
                
                favorites_json = json.dumps(favorites, ensure_ascii=False)
                sql = _get_insert_or_replace(
                    'user_favorites',
                    ['user_id', 'favorites'],
                    [placeholder, placeholder]
                )
                cursor.execute(sql, (user_id, favorites_json))
                return True
        else:
            # SQLite: izmanto JSON failus
            favorites_path = Path(f"data/favorites_{user_id}.json")
            favorites_path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                data = {"favorites": favorites}
                with open(favorites_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"[ERROR] Neizdevās saglabāt favorītus: {e}")
                return False

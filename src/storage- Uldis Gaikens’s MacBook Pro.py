import sqlite3
import json
from pathlib import Path
from typing import List, Optional

from .models import FieldModel, PlantingRecord, SoilType


class Storage:
    """Datu glabāšanas klase ar SQLite."""
    
    def __init__(self, db_path: str = "data/farm.db"):
        """Inicializē datubāzi un izveido tabulas."""
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Izveido tabulas, ja tās nav."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Lauku tabula
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    area_ha REAL NOT NULL CHECK(area_ha > 0),
                    soil TEXT NOT NULL
                )
            """)
            
            # Stādīšanas ierakstu tabula
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
            
            # Pievieno jaunas kolonnas, ja tās neeksistē
            new_columns = [
                ("user_id", "INTEGER"),  # Pievieno user_id, ja nav
                ("block_code", "TEXT"),
                ("lad_area_ha", "REAL"),
                ("lad_last_edited", "TEXT"),
                ("lad_last_synced", "TEXT"),
                ("rent_eur_ha", "REAL"),
                ("ph", "REAL")
            ]
            
            for col_name, col_type in new_columns:
                try:
                    if col_name == "user_id":
                        # Īpaša apstrāde user_id - pievieno kolonnu un iestata default vērtību
                        cursor.execute(f"ALTER TABLE fields ADD COLUMN {col_name} {col_type} DEFAULT 1")
                        # Aizpilda esošos ierakstus ar 1, ja ir NULL
                        cursor.execute("UPDATE fields SET user_id = 1 WHERE user_id IS NULL")
                    else:
                        cursor.execute(f"ALTER TABLE fields ADD COLUMN {col_name} {col_type}")
                    conn.commit()
                except sqlite3.OperationalError:
                    # Kolonna jau eksistē
                    pass
            
            # Pievieno user_id plantings tabulai, ja nav
            try:
                cursor.execute("ALTER TABLE plantings ADD COLUMN user_id INTEGER DEFAULT 1")
                # Aizpilda esošos ierakstus ar 1, ja ir NULL
                cursor.execute("UPDATE plantings SET user_id = 1 WHERE user_id IS NULL")
                conn.commit()
            except sqlite3.OperationalError:
                # Kolonna jau eksistē
                pass
            
            conn.commit()
            
            # Izpilda migrāciju augsnes vērtībām
            self.migrate_soil_values()
    
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
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Atrod visus laukus ar vecajām label vērtībām un migrē uz code
            for label, code in label_to_code.items():
                cursor.execute(
                    "UPDATE fields SET soil = ? WHERE soil = ?",
                    (code, label)
                )
            
            # Migrē vecos kodus uz jaunajiem
            for old_code, new_code in old_code_to_new.items():
                cursor.execute(
                    "UPDATE fields SET soil = ? WHERE soil = ?",
                    (new_code, old_code)
                )
            
            conn.commit()
    
    def add_field(self, field: FieldModel, user_id: int) -> FieldModel:
        """Pievieno lauku datubāzē."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Pārbauda, vai user_id kolonna eksistē
            try:
                cursor.execute("SELECT user_id FROM fields LIMIT 1")
            except sqlite3.OperationalError:
                # Kolonna nav, pievieno
                cursor.execute("ALTER TABLE fields ADD COLUMN user_id INTEGER DEFAULT 1")
            
            cursor.execute(
                "INSERT INTO fields (user_id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, field.name, field.area_ha, field.soil.code, field.block_code, field.lad_area_ha, field.lad_last_edited, field.lad_last_synced, field.rent_eur_ha, field.ph)
            )
            field_id = cursor.lastrowid
            conn.commit()
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
                ph=field.ph
            )
    
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
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Pārbauda, vai user_id kolonna eksistē
            try:
                cursor.execute("SELECT user_id FROM fields LIMIT 1")
                # Filtrē pēc user_id
                cursor.execute("SELECT id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph FROM fields WHERE user_id = ?", (user_id,))
            except sqlite3.OperationalError:
                # Kolonna nav, atgriež visus (backward compatibility)
                cursor.execute("SELECT id, name, area_ha, soil, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph FROM fields")
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
                    ph=ph_value
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
        ph: Optional[float] = None
    ) -> bool:
        """Atjauno lauka datus (tikai, ja pieder lietotājam)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE fields SET name=?, area_ha=?, soil=?, block_code=?, lad_area_ha=?, lad_last_edited=?, lad_last_synced=?, rent_eur_ha=?, ph=? WHERE id=? AND user_id=?",
                    (name, area_ha, soil.code, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, field_id, user_id)
                )
            except sqlite3.OperationalError:
                # user_id kolonna nav, izmanto veco formātu (backward compatibility)
                cursor.execute(
                    "UPDATE fields SET name=?, area_ha=?, soil=?, block_code=?, lad_area_ha=?, lad_last_edited=?, lad_last_synced=?, rent_eur_ha=?, ph=? WHERE id=?",
                    (name, area_ha, soil.code, block_code, lad_area_ha, lad_last_edited, lad_last_synced, rent_eur_ha, ph, field_id)
                )
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
    
    def add_planting(self, planting: PlantingRecord, user_id: int) -> PlantingRecord:
        """Pievieno stādīšanas ierakstu (tikai, ja field_id pieder lietotājam)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Pārbauda, vai field_id pieder lietotājam
            try:
                cursor.execute("SELECT user_id FROM fields WHERE id = ? AND user_id = ?", (planting.field_id, user_id))
                row = cursor.fetchone()
                if not row:
                    raise ValueError("Lauks nav atrasts vai nepieder lietotājam")
            except sqlite3.OperationalError:
                # user_id kolonna nav, atļauj (backward compatibility)
                pass
            
            # Pievieno ar user_id
            try:
                cursor.execute(
                    "INSERT OR REPLACE INTO plantings (field_id, year, crop, user_id) VALUES (?, ?, ?, ?)",
                    (planting.field_id, planting.year, planting.crop, user_id)
                )
            except sqlite3.OperationalError:
                # user_id kolonna nav, izmanto veco formātu (backward compatibility)
                cursor.execute(
                    "INSERT OR REPLACE INTO plantings (field_id, year, crop) VALUES (?, ?, ?)",
                    (planting.field_id, planting.year, planting.crop)
                )
            conn.commit()
            return planting
    
    def list_plantings(self, user_id: int) -> List[PlantingRecord]:
        """Atgriež visus stādīšanas ierakstus konkrētam lietotājam."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                # Vispirms mēģina filtrēt pēc plantings.user_id (ja kolonna eksistē)
                cursor.execute("SELECT user_id FROM plantings LIMIT 1")
                # Kolonna eksistē, izmanto tiešo filtrēšanu
                cursor.execute("SELECT field_id, year, crop FROM plantings WHERE user_id = ?", (user_id,))
            except sqlite3.OperationalError:
                # user_id kolonna nav plantings, filtrē caur fields
                try:
                    cursor.execute("SELECT user_id FROM fields LIMIT 1")
                    # Filtrē pēc user_id caur fields
                    cursor.execute("""
                        SELECT p.field_id, p.year, p.crop 
                        FROM plantings p
                        INNER JOIN fields f ON p.field_id = f.id
                        WHERE f.user_id = ?
                    """, (user_id,))
                except sqlite3.OperationalError:
                    # Nav user_id kolonnas vispār, atgriež visus (backward compatibility)
                    cursor.execute("SELECT field_id, year, crop FROM plantings")
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Dzēš saistītos ierakstus (tikai no šī lietotāja)
            try:
                cursor.execute("DELETE FROM plantings WHERE field_id = ? AND user_id = ?", (field_id, user_id))
            except sqlite3.OperationalError:
                # user_id kolonna nav, izmanto veco formātu (backward compatibility)
                cursor.execute("DELETE FROM plantings WHERE field_id = ?", (field_id,))
            
            # Dzēš lauku (tikai, ja pieder lietotājam)
            cursor.execute("DELETE FROM fields WHERE id = ? AND user_id = ?", (field_id, user_id))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            return deleted
    
    def clear_user_data(self, user_id: int) -> bool:
        """Dzēš visus datus konkrētam lietotājam."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            try:
                # Pārbauda, vai plantings tabulā ir user_id kolonna
                try:
                    cursor.execute("SELECT user_id FROM plantings LIMIT 1")
                    # Dzēš plantings tieši pēc user_id
                    cursor.execute("DELETE FROM plantings WHERE user_id = ?", (user_id,))
                except sqlite3.OperationalError:
                    # Nav user_id kolonnas plantings, dzēš caur fields
                    cursor.execute("""
                        DELETE FROM plantings 
                        WHERE field_id IN (SELECT id FROM fields WHERE user_id = ?)
                    """, (user_id,))
                
                # Dzēš fields
                cursor.execute("DELETE FROM fields WHERE user_id = ?", (user_id,))
                
                conn.commit()
                return True
            except sqlite3.OperationalError:
                # user_id kolonna nav, neko nedara
                return False
    
    def get_favorites(self, user_id: int) -> List[str]:
        """Atgriež favorīto kultūru sarakstu konkrētam lietotājam."""
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


from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserModel(BaseModel):
    """Lietotāja modelis."""
    id: Union[int, str]  # int for SQLite, str (UUID) for PostgreSQL
    username: str
    password_hash: str
    created_at: str  # ISO format datetime string


class SoilType(Enum):
    SMILTS = ("smilts", "Smilts (podzolaugsne)")
    MALS = ("mālaina", "Mālaina (velēnu karbonātaugsne)")
    KUDRA = ("kūdra", "Kūdra (kūdraugsne)")
    MITRA = ("mitra", "Mitra (glejaugsne)")

    def __init__(self, code: str, label: str):
        self.code = code
        self.label = label

    @classmethod
    def from_label(cls, label: str) -> "SoilType":
        for s in cls:
            if s.label == label:
                return s
        raise ValueError(f"Nederīgs augsnes nosaukums: {label}")


class FieldModel(BaseModel):
    """Lauka modelis."""
    id: Union[int, str]  # int for SQLite, str (UUID) for PostgreSQL
    name: str
    area_ha: float = Field(gt=0, description="Lauka platība hektāros")
    soil: SoilType
    owner_user_id: Union[int, str]  # int for SQLite, str (UUID) for PostgreSQL
    block_code: Optional[str] = None
    lad_area_ha: Optional[float] = None
    lad_last_edited: Optional[str] = None  # YYYY-MM-DD
    lad_last_synced: Optional[str] = None  # kad mēs pēdējo reizi ielasījām no LAD
    rent_eur_ha: float = Field(default=0.0, ge=0, description="Nomas maksa eiro uz hektāru")
    ph: Optional[float] = Field(default=None, description="Augsnes pH vērtība")
    is_organic: Optional[bool] = Field(default=None, description="Vai lauks ir bioloģisks (None = izmanto globālo iestatījumu)")


class PlantingRecord(BaseModel):
    """Stādīšanas ieraksts."""
    field_id: Union[int, str]  # int for SQLite, str (UUID) for PostgreSQL
    year: int
    crop: str  # Kultūras nosaukums
    owner_user_id: Union[int, str]  # int for SQLite, str (UUID) for PostgreSQL


class CropModel(BaseModel):
    """Kultūras modelis."""
    name: str
    group: str  # Kultūras grupa
    sow_months: list[int] = Field(description="Mēneši, kad var sēt (1-12)")
    yield_t_ha: Dict[SoilType, float] = Field(description="Raža tonnās uz hektāru pēc augsnes veida")
    cost_eur_ha: float = Field(description="Izmaksas eiro uz hektāru")
    price_eur_t: Optional[float] = Field(default=None, description="Cena eiro uz tonnu")
    is_market_crop: bool = True
    ph_range: Optional[Tuple[float, float]] = Field(default=None, description="pH diapazons (min, max)")
    is_organic_supported: bool = Field(default=True, description="Vai kultūra atbalsta bioloģisko audzēšanu")
    price_bio: Optional[float] = Field(default=None, description="BIO cena eiro uz tonnu (ja pieejama)")
    yield_modifier_bio: float = Field(default=0.85, description="Ražas modifikators BIO režīmam (0.85 = -15%)")


class CoverCropModel(BaseModel):
    """Starpkultūras modelis."""
    name: str
    sow_months: list[int] = Field(description="Mēneši, kad var sēt (1-12)")
    benefits: List[str] = Field(description="Starpkultūras priekšrocības")
    cost_eur_ha: float = Field(description="Izmaksas eiro uz hektāru")
    allowed_after_groups: List[str] = Field(description="Kultūru grupas, pēc kurām var sēt šo starpkultūru")


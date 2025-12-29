"""
Kultūru grupu noteikšanas palīgfunkcijas.
"""
from typing import Optional


def normalize(s: str) -> str:
    """
    Normalizē virkni: noņem atstarpes un pārvērš uz mazajiem burtiem.
    
    Args:
        s: Virkne
        
    Returns:
        Normalizēta virkne
    """
    return s.strip().lower()


def is_vegetable(name: str, group: Optional[str] = None) -> bool:
    """
    Atgriež True, ja kultūra ir dārzenis.
    
    Noteikumi:
    1) Ja group jau ir "Dārzeņi" -> True
    2) Citādi skatās pēc nosaukuma (case-insensitive, bez diakritikas normalizācijas nav obligāta)
    
    Dārzeņu atslēgvārdi (sākotnējais saraksts):
    kartupeļ, burkān, kāpost, sīpol, ķiplok, biet, gurķ, tomāt, paprik,
    salāt, ķirb, kabač, cukīn, redīs, rutk, purav, selerij, pētersīl,
    dilles, spināt, pupiņas (zaļās), zirnīši (zaļie)
    
    Args:
        name: Kultūras nosaukums
        group: Kultūras grupa (opcionāli)
        
    Returns:
        True, ja kultūra ir dārzenis, citādi False
    """
    # 1) Ja group jau ir "Dārzeņi" -> True
    if group is not None and normalize(group) == "dārzeņi":
        return True
    
    # 2) Skatās pēc nosaukuma (case-insensitive)
    name_normalized = normalize(name)
    
    # Dārzeņu atslēgvārdi
    vegetable_keywords = [
        "kartupeļ",
        "burkān",
        "kāpost",
        "sīpol",
        "ķiplok",
        "biet",
        "gurķ",
        "tomāt",
        "paprik",
        "salāt",
        "ķirb",
        "kabač",
        "cukīn",
        "redīs",
        "rutk",
        "purav",
        "selerij",
        "pētersīl",
        "pētersīļ",
        "dilles",
        "spināt",
        "pupiņas",
        "zirnīši"
    ]
    
    # Pārbauda, vai nosaukumā ir kāds no atslēgvārdiem
    for keyword in vegetable_keywords:
        if keyword in name_normalized:
            return True
    
    return False


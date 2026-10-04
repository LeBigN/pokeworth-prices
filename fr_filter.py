"""Filtre « marché français » des annonces : ne garde que les produits scellés en version française.

Cardmarket et TCGplayer ne distinguent pas la langue d'un produit scellé ; seules les annonces eBay portent un titre.
Règle (stricte) : une annonce est française si
  1. aucune mention d'une autre langue (anglais, japonais, coréen, chinois, allemand, italien, espagnol…) n'apparaît ;
  2. ET le titre mentionne le français (« FR », « VF », « français »…), ou le nom FRANÇAIS de l'extension (qui diffère
     du nom anglais : « Évolution Céleste » et non « Evolving Skies »).
Une annonce sans aucune indication de langue, ou avec le seul nom anglais de l'extension, est écartée.
"""
from __future__ import annotations

import re

from cardmarket_source import SET_EN, norm

# Mentions d'une autre langue (comparées au titre normalisé : minuscules, sans accents).
_FOREIGN = re.compile(
    r"\b(english|anglaise?|eng|en\s*version|us\s*version|usa|japanese|japonaise?|japon|japan|jpn|jp|jap|korean|coreenne?|"
    r"kor|chinese|chinoise?|german|allemande?|deutsch|de\s*version|italian|italienne?|ita|spanish|espagnole?|esp|"
    r"portuguese|portugais|thai|thailandais|indonesian|dutch|nederlands|polish)\b"
)
_FRENCH = re.compile(r"\b(fr|vf|fra|francais|francaise|french|version\s+francaise|edition\s+francaise)\b")


def language_hint(title: str) -> str | None:
    """`"fr"`, `"other"` (autre langue) ou `None` (rien d'explicite)."""
    text = norm(title)
    if _FOREIGN.search(text):
        return "other"
    if _FRENCH.search(text):
        return "fr"
    return None


def is_french_listing(title: str, item: dict) -> bool:
    """Vrai si l'annonce `title` est une version française du produit `item` du catalogue."""
    hint = language_hint(title)
    if hint == "other":
        return False
    if hint == "fr":
        return True
    # Aucune mention de langue : le nom français de l'extension fait foi, seulement s'il diffère du nom anglais.
    fr_name = norm(item.get("extension_fr", ""))
    en_name = norm(SET_EN.get(item.get("set_code", ""), ""))
    if not fr_name or fr_name == en_name:
        return False
    return fr_name in norm(title)

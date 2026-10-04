"""Mélange de plusieurs sources de prix en un prix de marché unique et lissé (aucune dépendance réseau).

Deux étapes :
1. `blend()` : moyenne pondérée des sources d'un produit, après rejet des valeurs aberrantes ;
2. `smooth()` : lissage exponentiel avec le prix précédent, et plafonnement de la variation entre deux exécutions,
   pour qu'une offre isolée (annonce erronée, produit vendu à perte) ne fasse pas sauter la courbe.
"""
from __future__ import annotations

import statistics

# Poids par source : Cardmarket est la référence du marché européen ; eBay France reflète les prix réellement
# demandés aux particuliers ; TCGplayer (États-Unis, produits en anglais) sert de garde-fou.
WEIGHTS = {"cardmarket": 0.60, "ebay_sold": 0.30, "ebay": 0.25, "tcgplayer": 0.15}

OUTLIER_RATIO = 0.45          # une source à plus de 45 % de la médiane des autres est écartée
SMOOTHING_ALPHA = 0.6         # poids de la nouvelle valeur (0.6 = réactif mais amorti)
MAX_STEP = 0.25               # variation maximale acceptée entre deux exécutions (±25 %)


def blend(prices: dict[str, float]) -> tuple[float | None, list[str]]:
    """`prices` : {source: prix en euros}. Renvoie (prix mélangé, sources retenues)."""
    valid = {k: v for k, v in prices.items() if v and v > 0}
    if not valid:
        return None, []
    if len(valid) == 1:
        (name, value), = valid.items()
        return round(value, 2), [name]

    kept = dict(valid)
    if len(valid) >= 3:
        # Avec 3 sources ou plus, on compare chacune à la médiane des autres.
        for name, value in valid.items():
            others = [v for k, v in valid.items() if k != name]
            ref = statistics.median(others)
            if ref > 0 and abs(value - ref) / ref > OUTLIER_RATIO:
                kept.pop(name, None)
        if not kept:                      # tout diverge : on se rabat sur la médiane globale
            median = statistics.median(valid.values())
            return round(median, 2), sorted(valid)
    else:
        # Avec 2 sources, si elles divergent trop, la référence (poids le plus fort) l'emporte.
        a, b = sorted(valid, key=lambda k: -WEIGHTS.get(k, 0.1))
        if abs(valid[a] - valid[b]) / max(valid[a], valid[b]) > OUTLIER_RATIO + 0.15:
            kept = {a: valid[a]}

    total = sum(WEIGHTS.get(k, 0.1) for k in kept)
    value = sum(v * WEIGHTS.get(k, 0.1) for k, v in kept.items()) / total
    return round(value, 2), sorted(kept)


def smooth(new: float | None, previous: float | None) -> float | None:
    """Lissage exponentiel + plafonnement de la variation par rapport au dernier prix publié."""
    if new is None:
        return previous
    if not previous or previous <= 0:
        return round(new, 2)
    value = SMOOTHING_ALPHA * new + (1 - SMOOTHING_ALPHA) * previous
    low, high = previous * (1 - MAX_STEP), previous * (1 + MAX_STEP)
    return round(min(max(value, low), high), 2)

"""Source de prix : fichiers publics Cardmarket (aucune clé d'API nécessaire).

Cardmarket publie chaque jour deux fichiers JSON pour Pokémon (jeu n° 6) :
  - la liste des produits non-cartes (boosters, displays, coffrets…), avec leur `idProduct` ;
  - le « price guide » : avg / low / trend / avg1 / avg7 / avg30 en euros, par `idProduct`.

Les noms de produits Cardmarket sont en anglais : chaque produit du catalogue français est associé à son
`idProduct` par (1) une correspondance manuelle dans `cardmarket_map.json` (prioritaire), sinon
(2) une correspondance automatique : nom anglais de l'extension + type de produit (display, ETB, bundle…).
`python build_feed.py --report` liste ce qui n'a pas été trouvé, avec des candidats à copier dans
`cardmarket_map.json` ({"id-du-catalogue": 123456}).

Les prix Cardmarket couvrent toutes les langues (le fichier ne distingue pas les offres françaises) :
`low_fr` reçoit donc le prix « low » toutes langues confondues.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import unicodedata
import urllib.request

BASE = "https://downloads.s3.cardmarket.com/productCatalog"
PRODUCTS_URL = f"{BASE}/productList/products_nonsingles_6.json"
PRICE_GUIDE_URL = f"{BASE}/priceGuide/price_guide_6.json"
HERE = pathlib.Path(__file__).resolve().parent

# Code d'extension du catalogue -> nom anglais utilisé par Cardmarket.
SET_EN = {
    "ME01": "Mega Evolution", "ME02": "Phantasmal Flames", "ME02.5": "Ascended Heroes",
    "ME03": "Perfect Order", "ME04": "Chaos Rising", "ME05": "Pitch Black", "ME05.5": "30th Celebration",
    "ME06": "Reign of Delta",
    "EV01": "Scarlet & Violet", "EV02": "Paldea Evolved", "EV03": "Obsidian Flames", "EV03.5": "151",
    "EV04": "Paradox Rift", "EV04.5": "Paldean Fates", "EV05": "Temporal Forces", "EV06": "Twilight Masquerade",
    "EV06.5": "Shrouded Fable", "EV07": "Stellar Crown", "EV08": "Surging Sparks",
    "EV08.5": "Prismatic Evolutions", "EV09": "Journey Together", "EV10": "Destined Rivals",
    "EV10.5": "Black Bolt White Flare", "EV10.5B": "Black Bolt", "EV10.5W": "White Flare",
    "EB01": "Sword & Shield", "EB02": "Rebel Clash", "EB03": "Darkness Ablaze", "EB03.5": "Champion's Path",
    "EB04": "Vivid Voltage", "EB04.5": "Shining Fates", "EB05": "Battle Styles", "EB06": "Chilling Reign",
    "EB07": "Evolving Skies", "CEL25": "Celebrations", "EB08": "Fusion Strike", "EB09": "Brilliant Stars",
    "EB10": "Astral Radiance", "EB10.5": "Pokemon GO", "EB11": "Lost Origin", "EB12": "Silver Tempest",
    "EB12.5": "Crown Zenith",
    "SL01": "Sun & Moon", "SL02": "Guardians Rising", "SL03": "Burning Shadows", "SL03.5": "Shining Legends",
    "SL04": "Crimson Invasion", "SL05": "Ultra Prism", "SL06": "Forbidden Light", "SL07": "Celestial Storm",
    "SL07.5": "Dragon Majesty", "SL08": "Lost Thunder", "SL09": "Team Up", "SL10": "Unbroken Bonds",
    "DET1": "Detective Pikachu", "SL11": "Unified Minds", "SL11.5": "Hidden Fates", "SL12": "Cosmic Eclipse",
    "XY01": "XY", "XY02": "Flashfire", "XY03": "Furious Fists", "XY04": "Phantom Forces", "XY05": "Primal Clash",
    "XY06": "Roaring Skies", "XY07": "Ancient Origins", "XY08": "BREAKthrough", "XY09": "BREAKpoint",
    "XY10": "Fates Collide", "XY11": "Steam Siege", "XY12": "Evolutions",
}

# Mots français fréquents des noms de coffrets -> anglais (les noms de Pokémon identiques n'ont pas besoin de traduction).
FR_EN = {
    "coffret": "box", "figurine": "figure", "dresseur": "trainer", "elite": "elite", "poster": "poster",
    "premium": "premium", "ultra": "ultra", "super": "super", "collection": "collection", "pouvoirs": "powers",
    "classeur": "binder", "mini": "mini", "boite": "tin", "deck": "deck", "combat": "battle",
}
STOP = {"de", "du", "des", "la", "le", "les", "et", "d", "l", "ex", "the", "of", "and", "pokemon", "tcg", "sealed"}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {t for t in norm(text).split() if t not in STOP}


def kind_of(name: str) -> str:
    """Type de produit d'après le nom anglais Cardmarket."""
    n = norm(name)
    if "case" in n.split() or "sleeved" in n or "code card" in n:
        return "ignore"
    if "elite trainer box" in n:
        return "etb"
    if "booster box" in n or "display" in n.split():
        return "display"
    if "booster bundle" in n or n.endswith(" bundle"):
        return "bundle"
    if "3 pack" in n or "three pack" in n or "tripack" in n:
        return "tripack"
    if "tin" in n.split():
        return "tin"
    if "blister" in n or "2 pack" in n or "duopack" in n:
        return "blister"
    if "battle deck" in n or "theme deck" in n or "starter" in n:
        return "other"
    return "coffret"


def _download(url: str) -> dict:
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PokeWorth-feed/1.0"}), timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001
            last = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Téléchargement impossible ({url}) : {last}")


class CardmarketSource:
    def __init__(self, items: list[dict], products_file: str | None = None, guide_file: str | None = None,
                 map_file: pathlib.Path = HERE / "cardmarket_map.json"):
        products = json.loads(pathlib.Path(products_file).read_text("utf-8")) if products_file else _download(PRODUCTS_URL)
        guide = json.loads(pathlib.Path(guide_file).read_text("utf-8")) if guide_file else _download(PRICE_GUIDE_URL)
        self._index(
            items,
            {p["idProduct"]: p for p in products.get("products", [])},
            {g["idProduct"]: g for g in guide.get("priceGuides", [])},
            json.loads(map_file.read_text("utf-8")) if map_file.exists() else {},
        )

    def _index(self, items: list[dict], products: dict, guide: dict, manual: dict) -> None:
        """Construit l'index de correspondance (réutilisé par les autres sources, ex. TCGplayer)."""
        self.products = products
        self.guide = guide
        self.manual = manual
        self.matches: dict[str, int] = {}
        self.unmatched: dict[str, list[tuple[float, int, str]]] = {}

        self._catalog = [
            {"id": pid, "name": p["name"], "kind": kind_of(p["name"]), "tokens": tokens(p["name"])}
            for pid, p in self.products.items() if kind_of(p["name"]) != "ignore"
        ]
        set_tokens = {code: tokens(en) for code, en in SET_EN.items()}
        # Extensions « génériques » (Sun & Moon, XY, 151…) : on écarte les produits d'une extension plus longue qui les contient.
        self._rivals = {
            code: [t for other, t in set_tokens.items() if other != code and toks < t]
            for code, toks in set_tokens.items()
        }
        self._set_tokens = set_tokens
        for item in items:
            self._match(item)

    # -- correspondance ------------------------------------------------------------------------

    def _match(self, item: dict) -> None:
        iid = item["id"]
        if iid in self.manual:
            self.matches[iid] = int(self.manual[iid])
            return
        code, kind = item["set_code"], item["categorie"]
        wanted = self._set_tokens.get(code)
        if not wanted:
            self.unmatched[iid] = []
            return
        title_tokens = {FR_EN.get(t, t) for t in tokens(item["titre"].split("–")[0])}
        scored: list[tuple[float, int, str]] = []
        for cand in self._catalog:
            if not wanted <= cand["tokens"]:
                continue
            if any(r <= cand["tokens"] for r in self._rivals.get(code, [])):
                continue
            if cand["kind"] != kind:
                continue
            extra = cand["tokens"] - wanted
            if kind == "coffret":
                own = {t for t in title_tokens} - wanted
                score = len(extra & own) / max(1, len(extra | own))
            else:
                # Un seul produit de ce type par extension : on préfère le nom le plus court (version standard).
                score = 1.0 / (1 + len(extra))
                if "pokemon center" in norm(self.products[cand["id"]]["name"]):
                    score *= 0.5
            scored.append((round(score, 3), cand["id"], self.products[cand["id"]]["name"]))
        scored.sort(key=lambda s: (-s[0], s[1]))
        threshold = 0.4 if kind == "coffret" else 0.0
        if scored and scored[0][0] > threshold and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            self.matches[iid] = scored[0][1]
        else:
            self.unmatched[iid] = scored[:3]

    # -- prix ----------------------------------------------------------------------------------

    def quote(self, item: dict) -> dict:
        pid = self.matches.get(item["id"])
        if pid is None:
            raise LookupError("produit Cardmarket non associé (voir --report)")
        g = self.guide.get(pid)
        if not g:
            raise LookupError(f"pas de prix pour idProduct {pid}")
        trend = g.get("trend") or g.get("avg") or None
        if not trend or trend <= 0:
            raise LookupError(f"prix nul pour idProduct {pid}")
        return {"trend": round(float(trend), 2),
                "low_fr": round(float(g["low"]), 2) if g.get("low") else None,
                "avg_30d": round(float(g["avg30"]), 2) if g.get("avg30") else None}

    def report(self, items: list[dict]) -> str:
        lines = [f"{len(self.matches)}/{len(items)} produits associés, {len(self.unmatched)} à traiter", ""]
        by_id = {i["id"]: i for i in items}
        for iid, cands in self.unmatched.items():
            lines.append(f"{iid}  ({by_id[iid]['titre']})")
            for score, pid, name in cands:
                lines.append(f"    {pid}  {name}  [{score}]")
            if not cands:
                lines.append("    aucun candidat — ajouter à cardmarket_map.json")
        return "\n".join(lines)

#!/usr/bin/env python3
"""Génère prices.json, le fichier de prix lu par l'app PokeWorth.

Ce script est le SEUL endroit qui connaît le fournisseur de prix.
Pour en changer, il suffit de réécrire `fetch_quote()`.

Usage :
    python build_feed.py [--catalog items_pokemon_fr.json] [--out prices.json] [--report]
    (aucune clé d'API : les fichiers de prix publics Cardmarket sont utilisés)

Le fichier précédent est relu pour conserver l'historique (un point par jour, 90 jours).
Si un item échoue, son dernier prix connu est conservé sans ajouter de point d'historique.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

from blend import blend, smooth
from cardmarket_source import CardmarketSource
from market_sources import EbaySource, TcgplayerSource

HERE = pathlib.Path(__file__).resolve().parent
CATALOG_CANDIDATES = [
    HERE.parent / "PokeWorth" / "Resources" / "items_pokemon_fr.json",   # dans le projet
    HERE / "items_pokemon_fr.json",                                       # copie à côté du script
]
HISTORY_DAYS = 90


_SOURCE = None
_EXTRA = {}          # sources complémentaires : {"tcgplayer": ..., "ebay": ...}


def fetch_quote(item: dict, previous_trend=None) -> dict:
    """Prix d'un produit : Cardmarket (référence) mélangé à TCGplayer et eBay, puis lissé.

    Renvoie {"trend", "low_fr", "avg_30d", "sources"} en euros. Lève une exception si AUCUNE source n'a de prix :
    l'ancien prix est alors conservé. Pour changer de fournisseur, il suffit de réécrire cette fonction.
    """
    prices, extra = {}, {}
    try:
        cm = _SOURCE.quote(item)
        prices["cardmarket"] = cm["trend"]
        extra = {"low_fr": cm["low_fr"], "avg_30d": cm["avg_30d"]}
    except LookupError:
        pass
    for name, source in _EXTRA.items():
        try:
            prices[name] = source.quote_eur(item)
        except Exception:  # noqa: BLE001 - une source secondaire ne bloque jamais le prix
            pass
    value, kept = blend(prices)
    if value is None:
        raise LookupError("aucune source n'a de prix pour ce produit")
    return {"trend": smooth(value, previous_trend), "sources": kept, **extra}


# --- Le reste est indépendant du fournisseur -------------------------------------------------

def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_history(history: list, now: dt.datetime, trend) -> list:
    """Un point par jour (le dernier de la journée l'emporte), fenêtre glissante de 90 jours."""
    points = {parse(h["date"]).date().isoformat(): h for h in history}
    if trend is not None:
        points[now.date().isoformat()] = {"date": iso(now), "trend": trend}
    cutoff = (now - dt.timedelta(days=HISTORY_DAYS)).date().isoformat()
    return [points[day] for day in sorted(points) if day >= cutoff]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", help="chemin de items_pokemon_fr.json")
    parser.add_argument("--out", default=str(HERE / "prices.json"))
    parser.add_argument("--report", action="store_true", help="affiche les produits non associés et quitte")
    parser.add_argument("--products-file", help="(test) liste de produits Cardmarket locale")
    parser.add_argument("--guide-file", help="(test) price guide Cardmarket local")
    parser.add_argument("--no-extra", action="store_true", help="Cardmarket seul (sans TCGplayer ni eBay)")
    args = parser.parse_args()

    catalog_path = pathlib.Path(args.catalog) if args.catalog else next(
        (p for p in CATALOG_CANDIDATES if p.exists()), None
    )
    if catalog_path is None or not catalog_path.exists():
        sys.exit("Catalogue introuvable : passez --catalog chemin/vers/items_pokemon_fr.json")

    items = load_json(catalog_path)["items"]
    global _SOURCE
    _SOURCE = CardmarketSource(items, args.products_file, args.guide_file)
    if args.report:
        print(_SOURCE.report(items))
        return
    if not args.no_extra and not args.products_file:
        try:
            _EXTRA["tcgplayer"] = TcgplayerSource(items, map_file=HERE / "tcgplayer_map.json")
        except Exception as error:  # noqa: BLE001
            print(f"! TCGplayer ignoré : {error}", file=sys.stderr)
        ebay = EbaySource.from_env()
        if ebay:
            _EXTRA["ebay"] = ebay
    print("Sources actives :", ", ".join(["cardmarket", *_EXTRA]))
    out = pathlib.Path(args.out)
    previous = {}
    if out.exists():
        previous = {p["id"]: p for p in load_json(out).get("prices", [])}

    now = dt.datetime.now(dt.timezone.utc)
    prices, failures = [], 0

    for item in items:
        old = previous.get(item["id"], {})
        try:
            quote = fetch_quote(item, old.get("trend"))
            fresh = True
        except Exception as error:  # noqa: BLE001 - on garde l'ancien prix quoi qu'il arrive
            print(f"! {item['id']} : {error}", file=sys.stderr)
            failures += 1
            quote = {key: old.get(key) for key in ("trend", "low_fr", "avg_30d")}
            fresh = False

        prices.append({
            "id": item["id"],
            "trend": quote.get("trend"),
            "low_fr": quote.get("low_fr"),
            "avg_30d": quote.get("avg_30d"),
            "sources": quote.get("sources") or old.get("sources"),
            "history": merge_history(old.get("history", []), now, quote.get("trend") if fresh else None),
        })

    if failures == len(items):
        sys.exit("Aucun prix récupéré : prices.json n'est pas modifié.")

    feed = {"version": 1, "updated_at": iso(now), "currency": "EUR", "prices": prices}
    out.write_text(json.dumps(feed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items) - failures}/{len(items)} prix mis à jour -> {out}")


if __name__ == "__main__":
    main()

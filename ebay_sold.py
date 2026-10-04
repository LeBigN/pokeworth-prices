"""Ventes réellement conclues sur eBay.fr (API Marketplace Insights) : la « vraie cote » française.

ATTENTION : l'API Marketplace Insights d'eBay est en accès restreint (« Limited Release »). Les clés gratuites
du programme développeur ne l'ouvrent pas par défaut : il faut en faire la demande à eBay (developer.ebay.com ▸
Application Growth Check). Sans cet accès, `EbaySoldSource.from_env()` renvoie `None` et le pipeline retombe
automatiquement sur les annonces actives (`EbaySource`). Aucune collecte de pages web (scraping) n'est faite :
les conditions d'utilisation d'eBay l'interdisent.

Variables d'environnement : EBAY_CLIENT_ID, EBAY_CLIENT_SECRET (les mêmes que pour l'API Browse).
Seules les ventes françaises (filtre `fr_filter`) des 60 derniers jours sont retenues ; la médiane (sans valeurs
aberrantes) est le prix de vente observé. Au moins 3 ventes sont nécessaires.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import statistics
import time
import urllib.parse
import urllib.request

from cardmarket_source import kind_of, tokens
from fr_filter import is_french_listing

SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
WINDOW_DAYS = 60
MIN_SALES = 3


def sold_stats(item: dict, sales: list[dict], now: dt.datetime | None = None) -> dict | None:
    """Statistiques des ventes conclues d'un produit : {"median", "low", "n"} ou `None` (trop peu de ventes).

    `sales` : éléments `itemSales` de l'API (`title`, `lastSoldPrice.value`, `lastSoldDate`, `totalSoldQuantity`).
    Une vente est retenue si le titre parle bien du produit (extension + type), est en français, date de moins de
    60 jours et n'est pas un prix aberrant (hors de 0,5 à 1,8 fois la médiane).
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    need = tokens(item["extension_fr"])
    kind = item["categorie"]
    prices = []
    for sale in sales:
        title = sale.get("title", "")
        if not need <= tokens(title) and not _english_set_in(title, item):
            continue
        k = kind_of(title)
        if k != "ignore" and k != kind and kind != "coffret":
            continue
        if not is_french_listing(title, item):
            continue
        try:
            sold_at = dt.datetime.fromisoformat(sale["lastSoldDate"].replace("Z", "+00:00"))
            if (now - sold_at).days > WINDOW_DAYS:
                continue
            value = float(sale["lastSoldPrice"]["value"])
            if sale["lastSoldPrice"].get("currency", "EUR") != "EUR":
                continue
        except (KeyError, ValueError, TypeError):
            continue
        prices.extend([value] * max(1, min(int(sale.get("totalSoldQuantity") or 1), 5)))
    if len(prices) < MIN_SALES:
        return None
    med = statistics.median(prices)
    kept = [p for p in prices if 0.5 * med <= p <= 1.8 * med]
    if len(kept) < MIN_SALES:
        return None
    return {"median": round(statistics.median(kept), 2), "low": round(min(kept), 2), "n": len(kept)}


def _english_set_in(title: str, item: dict) -> bool:
    """Les titres avec la mention FR mais le nom anglais de l'extension (« Evolving Skies display FR ») restent valides."""
    from cardmarket_source import SET_EN
    name = SET_EN.get(item.get("set_code", ""))
    return bool(name) and tokens(name) <= tokens(title)


class EbaySoldSource:
    """Ventes conclues eBay.fr (API Marketplace Insights, accès restreint)."""

    API = "https://api.ebay.com"

    def __init__(self, client_id: str, client_secret: str):
        self._token = self._auth(client_id, client_secret)
        self.last_stats: dict[str, dict] = {}

    @classmethod
    def from_env(cls):
        cid, secret = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
        if not (cid and secret):
            return None
        try:
            return cls(cid, secret)
        except Exception as error:  # noqa: BLE001 - accès Insights non accordé : on retombe sur les annonces actives
            print(f"! eBay ventes réalisées indisponible (accès Marketplace Insights non accordé ?) : {error}")
            return None

    def _auth(self, cid: str, secret: str) -> str:
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
        req = urllib.request.Request(f"{self.API}/identity/v1/oauth2/token", data=body, headers={
            "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["access_token"]

    def _search(self, query: str) -> list[dict]:
        params = urllib.parse.urlencode({"q": query, "limit": 100, "filter": "conditions:{NEW}"})
        req = urllib.request.Request(f"{self.API}/buy/marketplace_insights/v1_beta/item_sales/search?{params}", headers={
            "Authorization": f"Bearer {self._token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_FR"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("itemSales", [])

    def quote_eur(self, item: dict) -> float | None:
        query = f'pokemon {item["titre"].split("–")[0].strip()} {item["extension_fr"]}'
        try:
            sales = self._search(query)
        except Exception:  # noqa: BLE001
            return None
        time.sleep(0.2)
        stats = sold_stats(item, sales)
        if stats:
            self.last_stats[item["id"]] = stats
        return stats["median"] if stats else None

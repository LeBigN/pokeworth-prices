"""Sources de prix complémentaires à Cardmarket : TCGplayer (via tcgcsv.com) et eBay France (API Browse).

Les deux sont facultatives : si une source est indisponible (réseau, clé absente), elle est ignorée et le prix
repose sur les autres sources. Chaque source expose `quote(item) -> float | None` (prix en euros).
"""
from __future__ import annotations

import base64
import json
import os
import statistics
import time
import urllib.parse
import urllib.request

from cardmarket_source import CardmarketSource, _download, kind_of, norm, tokens
from fr_filter import is_french_listing

TCGCSV = "https://tcgcsv.com/tcgplayer/3"          # 3 = Pokémon
FX_URL = "https://api.frankfurter.app/latest?from=USD&to=EUR"


class TcgplayerSource(CardmarketSource):
    """Produits scellés TCGplayer (anglais, USD) associés au catalogue avec la même logique que Cardmarket.

    Données : tcgcsv.com, miroir public quotidien des prix TCGplayer (pas de clé). Conversion USD -> EUR au taux du jour.
    """

    def __init__(self, items, groups_file=None, fx_rate=None, map_file=None):  # noqa: D107
        products, guide = {}, {}
        groups = json.loads(open(groups_file, encoding="utf-8").read()) if groups_file else _download(f"{TCGCSV}/groups")
        for group in groups.get("results", []):
            gid = group["groupId"]
            try:
                prods = _download(f"{TCGCSV}/{gid}/products").get("results", [])
                prices = _download(f"{TCGCSV}/{gid}/prices").get("results", [])
            except Exception:  # noqa: BLE001 - un groupe indisponible n'empêche pas les autres
                continue
            for p in prods:
                # Une carte porte un numéro dans `extendedData` ; un produit scellé n'en a pas.
                if any(e.get("name") == "Number" for e in p.get("extendedData", [])):
                    continue
                products[p["productId"]] = {"name": f'{group["name"]} {p["name"]}'}
            for pr in prices:
                if pr.get("subTypeName", "Normal") == "Normal" and pr["productId"] in products:
                    guide[pr["productId"]] = pr
        self.fx = fx_rate or _fx_rate()
        manual_path = map_file
        manual = json.loads(manual_path.read_text("utf-8")) if manual_path and manual_path.exists() else {}
        self._index(items, {k: {"idProduct": k, **v} for k, v in products.items()}, guide, manual)

    def quote_eur(self, item: dict) -> float | None:
        pid = self.matches.get(item["id"])
        price = (self.guide.get(pid) or {}).get("marketPrice") if pid else None
        return round(float(price) * self.fx, 2) if price and price > 0 else None


def _fx_rate() -> float:
    try:
        return float(_download(FX_URL)["rates"]["EUR"])
    except Exception:  # noqa: BLE001
        return 0.86     # repli prudent si le taux n'est pas joignable


class EbaySource:
    """Annonces neuves à prix fixe sur eBay.fr (API Browse). Clés gratuites : developer.ebay.com.

    Variables d'environnement : EBAY_CLIENT_ID, EBAY_CLIENT_SECRET. Le prix retenu est la médiane des annonces
    pertinentes (les annonces d'un autre produit ou à prix aberrant sont écartées).
    """

    API = "https://api.ebay.com"

    def __init__(self, client_id: str, client_secret: str):
        self._token = self._auth(client_id, client_secret)

    @classmethod
    def from_env(cls):
        cid, secret = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
        if not (cid and secret):
            return None
        try:
            return cls(cid, secret)
        except Exception as error:  # noqa: BLE001
            print(f"! eBay indisponible : {error}")
            return None

    def _auth(self, cid: str, secret: str) -> str:
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                       "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
        req = urllib.request.Request(f"{self.API}/identity/v1/oauth2/token", data=body, headers={
            "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["access_token"]

    def quote_eur(self, item: dict) -> float | None:
        query = f'pokemon {item["titre"].split("–")[0]} {item["extension_fr"]} scellé'
        params = urllib.parse.urlencode({
            "q": query, "limit": 40,
            "filter": "buyingOptions:{FIXED_PRICE},conditions:{NEW},priceCurrency:EUR",
        })
        req = urllib.request.Request(f"{self.API}/buy/browse/v1/item_summary/search?{params}", headers={
            "Authorization": f"Bearer {self._token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_FR"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except Exception:  # noqa: BLE001
            return None
        time.sleep(0.2)
        return listing_median(item, data.get("itemSummaries", []))


def listing_median(item: dict, summaries: list[dict]) -> float | None:
    """Médiane des annonces qui parlent bien de ce produit (extension + type), sans prix aberrants."""
    need = tokens(item["extension_fr"])
    kind = item["categorie"]
    prices = []
    for s in summaries:
        title = s.get("title", "")
        if not need <= tokens(title):
            continue
        if not is_french_listing(title, item):      # marché français uniquement (versions EN/JP écartées)
            continue
        k = kind_of(title)
        if k != "ignore" and k != kind and kind != "coffret":
            continue
        try:
            prices.append(float(s["price"]["value"]))
        except (KeyError, ValueError):
            pass
    if len(prices) < 3:
        return None
    med = statistics.median(prices)
    kept = [p for p in prices if 0.5 * med <= p <= 1.8 * med]
    return round(statistics.median(kept), 2) if len(kept) >= 3 else None

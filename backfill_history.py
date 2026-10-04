#!/usr/bin/env python3
"""Reconstitue l'historique de prix des produits (à lancer UNE fois, puis éventuellement de temps en temps).

Cardmarket ne publie aucun historique de prix des produits scellés (seulement le prix du jour). Le seul historique public
et gratuit est celui de TCGplayer : tcgcsv.com archive chaque jour tous les prix TCGplayer depuis février 2024
(https://tcgcsv.com/archive/tcgplayer/prices-AAAA-MM-JJ.ppmd.7z).

Ce script en tire la FORME de la courbe de chaque produit déjà associé à TCGplayer, puis la cale sur le niveau de prix
actuel du flux (prix Cardmarket mélangé) : la courbe garde ainsi une continuité avec les relevés réels.
Les points créés portent `"est": true` : l'app les trace en pointillés avec la mention « estimation ». Dès qu'un vrai
relevé quotidien existe pour un jour donné, il remplace l'estimation de ce jour.

Usage :
    pip install py7zr
    python backfill_history.py [--months 12] [--daily-days 35] [--out prices.json] [--dry-run]

Aucune clé d'API. Les dates dont l'archive est indisponible sont simplement ignorées.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import sys
import tempfile
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ARCHIVE_URL = "https://tcgcsv.com/archive/tcgplayer/prices-{date}.ppmd.7z"
FX_HISTORY_URL = "https://api.frankfurter.app/{date}?from=USD&to=EUR"
POKEMON_CATEGORY = "3"
PRICES_PATH = re.compile(rf"(^|/){POKEMON_CATEGORY}/\d+/prices$")
USER_AGENT = {"User-Agent": "pokeworth-prices/1.0 (+https://github.com)"}


# --- Dates -----------------------------------------------------------------------------------

def wanted_dates(today: dt.date, months: int, daily_days: int) -> list[dt.date]:
    """Un jour sur un pendant `daily_days` jours (hier et avant), puis un par semaine jusqu'à `months` mois."""
    dates = {today - dt.timedelta(days=n) for n in range(1, daily_days + 1)}
    day = today - dt.timedelta(days=daily_days + 7)
    limit = today - dt.timedelta(days=round(months * 30.4))
    while day >= limit:
        dates.add(day)
        day -= dt.timedelta(days=7)
    return sorted(dates)


# --- Lecture d'une archive -------------------------------------------------------------------

def download(url: str, target: pathlib.Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=120) as response, open(target, "wb") as out:
            shutil.copyfileobj(response, out)
        return True
    except Exception as error:  # noqa: BLE001 - une date manquante n'arrête pas le reste
        print(f"  archive indisponible ({error})", file=sys.stderr)
        return False


def read_prices_dir(root: pathlib.Path, wanted: set[int]) -> dict[int, float]:
    """Lit les fichiers `.../3/<groupe>/prices` extraits sous `root` : {productId: prix de marché en USD}."""
    prices: dict[int, float] = {}
    for path in root.rglob("prices"):
        if not PRICES_PATH.search(path.as_posix()):
            continue
        try:
            rows = json.loads(path.read_text("utf-8")).get("results", [])
        except (ValueError, OSError):
            continue
        for row in rows:
            pid = row.get("productId")
            if pid not in wanted:
                continue
            value = row.get("marketPrice") or row.get("midPrice")
            if not value or value <= 0:
                continue
            # « Normal » est la variante des produits scellés ; une autre variante ne remplace jamais « Normal ».
            if pid not in prices or row.get("subTypeName", "Normal") == "Normal":
                prices[pid] = float(value)
    return prices


def read_archive(path: pathlib.Path, wanted: set[int]) -> dict[int, float]:
    import py7zr  # importé ici : le reste du script (et les tests) n'en a pas besoin

    work = pathlib.Path(tempfile.mkdtemp(prefix="tcgcsv_"))
    try:
        with py7zr.SevenZipFile(path) as archive:
            targets = [name for name in archive.getnames() if PRICES_PATH.search(name)]
            if not targets:
                return {}
            archive.extract(path=work, targets=targets)
        return read_prices_dir(work, wanted)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def fx_on(day: dt.date, fallback: float, cache: dict) -> float:
    if day in cache:
        return cache[day]
    try:
        req = urllib.request.Request(FX_HISTORY_URL.format(date=day.isoformat()), headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as response:
            cache[day] = float(json.loads(response.read())["rates"]["EUR"])
    except Exception:  # noqa: BLE001
        cache[day] = fallback
    return cache[day]


# --- Construction des estimations -------------------------------------------------------------

SCALE_RANGE = (0.2, 5.0)      # au-delà, TCGplayer et le flux ne parlent clairement pas du même produit


def estimate_points(usd_by_day: dict[dt.date, float], fx_by_day: dict[dt.date, float],
                    trend_now: float, eur_now: float, first_real_day: dt.date | None) -> list[dict]:
    """Points estimés d'un produit : prix TCGplayer du jour (en euros) × facteur de calage sur le prix actuel du flux."""
    if not trend_now or not eur_now or eur_now <= 0:
        return []
    scale = trend_now / eur_now
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        return []
    points = []
    for day in sorted(usd_by_day):
        if first_real_day and day >= first_real_day:
            continue                                   # un vrai relevé existe : pas d'estimation
        euros = usd_by_day[day] * fx_by_day[day]
        points.append({"date": f"{day.isoformat()}T12:00:00Z", "trend": round(euros * scale, 2), "est": True})
    return points


def apply_estimates(history: list[dict], estimates: list[dict]) -> list[dict]:
    """Remplace les anciennes estimations par les nouvelles ; les relevés réels ne sont jamais touchés."""
    real = [p for p in history if not p.get("est")]
    real_days = {p["date"][:10] for p in real}
    fresh = [p for p in estimates if p["date"][:10] not in real_days]
    return sorted(real + fresh, key=lambda p: p["date"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", help="chemin de items_pokemon_fr.json")
    parser.add_argument("--out", default=str(HERE / "prices.json"), help="prices.json à enrichir (il doit déjà exister)")
    parser.add_argument("--months", type=int, default=12, help="profondeur de l'historique (défaut : 12 mois)")
    parser.add_argument("--daily-days", type=int, default=28, help="jours récents reconstitués jour par jour")
    parser.add_argument("--dry-run", action="store_true", help="n'écrit rien, affiche seulement le bilan")
    args = parser.parse_args()

    from build_feed import CATALOG_CANDIDATES, clip_before_release, load_json, merge_history, parse   # import tardif : build_feed charge les sources
    from market_sources import TcgplayerSource

    catalog_path = pathlib.Path(args.catalog) if args.catalog else next((p for p in CATALOG_CANDIDATES if p.exists()), None)
    out = pathlib.Path(args.out)
    if catalog_path is None or not out.exists():
        sys.exit("Catalogue ou prices.json introuvable (lancez d'abord build_feed.py).")
    items = load_json(catalog_path)["items"]
    feed = load_json(out)
    prices = {p["id"]: p for p in feed["prices"]}

    print("Association des produits TCGplayer…")
    source = TcgplayerSource(items, map_file=HERE / "tcgplayer_map.json")
    wanted_ids = {pid for iid, pid in source.matches.items() if iid in prices}
    print(f"{len(wanted_ids)} produits associés")
    if not wanted_ids:
        sys.exit("Aucun produit associé à TCGplayer : rien à reconstituer.")

    usd: dict[int, dict[dt.date, float]] = {pid: {} for pid in wanted_ids}
    fx_cache: dict = {}
    today = dt.datetime.now(dt.timezone.utc).date()
    dates = wanted_dates(today, args.months, args.daily_days)
    ok = 0
    with tempfile.TemporaryDirectory(prefix="tcgcsv_dl_") as tmp:
        for day in dates:
            print(f"{day.isoformat()} ({ok} archives lues)", flush=True)
            archive = pathlib.Path(tmp) / f"{day.isoformat()}.7z"
            if not download(ARCHIVE_URL.format(date=day.isoformat()), archive):
                continue
            try:
                found = read_archive(archive, wanted_ids)
            except Exception as error:  # noqa: BLE001
                print(f"  illisible ({error})", file=sys.stderr)
                found = {}
            finally:
                archive.unlink(missing_ok=True)
            if found:
                ok += 1
                fx_on(day, source.fx, fx_cache)
                for pid, value in found.items():
                    usd[pid][day] = value
    if ok == 0:
        sys.exit("Aucune archive exploitable : le flux n'est pas modifié.")

    fx_by_day = {day: fx_cache.get(day, source.fx) for pid in usd for day in usd[pid]}
    now = dt.datetime.now(dt.timezone.utc)
    enriched = 0
    for item in items:
        pid = source.matches.get(item["id"])
        entry = prices.get(item["id"])
        if pid is None or entry is None or not usd.get(pid):
            continue
        history = entry.get("history") or []
        real_days = sorted(parse(p["date"]).date() for p in history if not p.get("est"))
        eur_now = source.quote_eur(item)
        estimates = estimate_points(usd[pid], fx_by_day, entry.get("trend"), eur_now, real_days[0] if real_days else None)
        if not estimates:
            continue
        entry["history"] = clip_before_release(merge_history(apply_estimates(history, estimates), now, None),
                                               item.get("date_sortie"))
        enriched += 1
    print(f"{enriched} produits enrichis à partir de {ok} archives")
    if args.dry_run:
        return
    out.write_text(json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()

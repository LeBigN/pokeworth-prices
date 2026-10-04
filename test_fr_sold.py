"""Tests du filtre FR, des ventes eBay réalisées et du raccord à la date de sortie : python3 test_fr_sold.py"""
import datetime as dt

from build_feed import clip_before_release
from ebay_sold import sold_stats
from fr_filter import is_french_listing, language_hint

ITEM = {"id": "display-eb07", "extension_fr": "Évolution Céleste", "set_code": "EB07", "categorie": "display",
        "titre": "Display 36 boosters – Évolution Céleste"}
NOW = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc)


def sale(title, price, days_ago=5, qty=1, cur="EUR"):
    day = (NOW - dt.timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    return {"title": title, "lastSoldPrice": {"value": str(price), "currency": cur}, "lastSoldDate": day,
            "totalSoldQuantity": qty}


def test_language_hint():
    assert language_hint("Display Evolving Skies Japanese") == "other"
    assert language_hint("Display Évolution Céleste FR scellé") == "fr"
    assert language_hint("Display Évolution Céleste scellé") is None
    assert language_hint("Display evolving skies ENGLISH sealed") == "other"


def test_french_listing():
    assert is_french_listing("Display Évolution Céleste 36 boosters", ITEM)       # nom français de l'extension
    assert is_french_listing("Evolving Skies Display FR", ITEM)                     # mention FR
    assert not is_french_listing("Evolving Skies Display", ITEM)                    # nom anglais, aucune langue
    assert not is_french_listing("Display Évolution Céleste version anglaise", ITEM)
    assert not is_french_listing("Display Évolution Céleste JP", ITEM)
    assert not is_french_listing("Display Evolving Skies", ITEM)


def test_sold_stats_median_fr_only():
    sales = [sale("Display Évolution Céleste 36 boosters FR", 640), sale("Display Evolution Celeste scellé", 660),
             sale("Display Évolution Céleste FR", 650), sale("Evolving Skies Booster Box English", 900),
             sale("Display Évolution Céleste japonais", 300), sale("Display Évolution Céleste FR", 2500)]
    stats = sold_stats(ITEM, sales, NOW)
    assert stats and stats["n"] == 3 and stats["median"] == 650 and stats["low"] == 640, stats


def test_sold_stats_old_and_other_currency_ignored():
    sales = [sale("Display Évolution Céleste FR", 640, days_ago=120), sale("Display Évolution Céleste FR", 650),
             sale("Display Évolution Céleste FR", 700, cur="USD"), sale("Display Évolution Céleste FR", 655)]
    assert sold_stats(ITEM, sales, NOW) is None                                      # 2 ventes valides seulement


def test_sold_stats_quantity_counts():
    assert sold_stats(ITEM, [sale("Display Évolution Céleste FR", 650, qty=3)], NOW)["n"] == 3


def test_clip_before_release():
    history = [{"date": "2021-06-01T12:00:00Z", "trend": 100.0}, {"date": "2021-06-18T12:00:00Z", "trend": 120.0},
               {"date": "2026-10-01T12:00:00Z", "trend": 650.0}]
    assert [h["trend"] for h in clip_before_release(history, "2021-06-18")] == [120.0, 650.0]
    assert clip_before_release(history, None) == history


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

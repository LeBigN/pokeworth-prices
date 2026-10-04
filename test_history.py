"""Tests de l'historique : python3 test_history.py (aucun réseau ; la lecture 7z n'est testée que si py7zr est installé)."""
import datetime as dt
import json
import pathlib
import tempfile

import backfill_history as bh
from build_feed import average_30d, merge_history

D = dt.date


def test_wanted_dates():
    dates = bh.wanted_dates(D(2026, 10, 3), months=12, daily_days=28)
    assert D(2026, 10, 2) in dates and D(2026, 10, 3) not in dates
    assert len([d for d in dates if d >= D(2026, 9, 5)]) == 28           # un jour sur un récemment
    older = [d for d in dates if d < D(2026, 9, 5)]
    assert all((older[i + 1] - older[i]).days == 7 for i in range(len(older) - 1))   # puis une par semaine
    assert min(dates) >= D(2025, 9, 25)
    print("ok wanted_dates", len(dates))


def make_tree(root: pathlib.Path):
    for group, rows in {"100": [{"productId": 1, "marketPrice": 10.0, "subTypeName": "Normal"},
                                {"productId": 1, "marketPrice": 99.0, "subTypeName": "Holofoil"},
                                {"productId": 2, "marketPrice": 0, "subTypeName": "Normal"},
                                {"productId": 3, "marketPrice": 5.0}],
                        "200": [{"productId": 4, "marketPrice": None, "midPrice": 7.5, "subTypeName": "Normal"}]}.items():
        d = root / "2026-01-01" / "3" / group
        d.mkdir(parents=True)
        (d / "prices").write_text(json.dumps({"success": True, "results": rows}))
    other = root / "2026-01-01" / "1" / "999"          # autre jeu : ignoré
    other.mkdir(parents=True)
    (other / "prices").write_text(json.dumps({"results": [{"productId": 1, "marketPrice": 1.0}]}))


def test_read_dir():
    with tempfile.TemporaryDirectory() as tmp:
        make_tree(pathlib.Path(tmp))
        got = bh.read_prices_dir(pathlib.Path(tmp), {1, 2, 4})
    assert got == {1: 10.0, 4: 7.5}, got            # « Normal » prioritaire, prix nul ignoré, produit non voulu ignoré
    print("ok read_prices_dir")


def test_read_archive():
    try:
        import py7zr
    except ImportError:
        print("-- py7zr absent : lecture d'archive non testée")
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        make_tree(tmp / "src")
        archive = tmp / "a.7z"
        with py7zr.SevenZipFile(archive, "w") as z:
            z.writeall(tmp / "src" / "2026-01-01", "2026-01-01")
        assert bh.read_archive(archive, {1, 4}) == {1: 10.0, 4: 7.5}
    print("ok read_archive (7z)")


def test_estimates():
    usd = {D(2026, 9, 1): 100.0, D(2026, 9, 10): 110.0, D(2026, 10, 1): 120.0}
    fx = {d: 0.9 for d in usd}
    pts = bh.estimate_points(usd, fx, trend_now=200.0, eur_now=100.0, first_real_day=D(2026, 10, 1))
    assert [p["date"][:10] for p in pts] == ["2026-09-01", "2026-09-10"]       # rien à partir du premier relevé réel
    assert pts[0]["trend"] == 180.0 and pts[0]["est"] is True                   # 100 $ × 0,9 × 2
    assert bh.estimate_points(usd, fx, 200.0, 5.0, None) == []                  # calage aberrant (×40) : produit écarté
    assert bh.estimate_points(usd, fx, 200.0, 0, None) == []
    print("ok estimate_points")


def test_apply():
    real = {"date": "2026-10-02T10:00:00Z", "trend": 50.0}
    old_est = {"date": "2026-09-01T12:00:00Z", "trend": 1.0, "est": True}
    new = [{"date": "2026-09-01T12:00:00Z", "trend": 40.0, "est": True},
           {"date": "2026-10-02T12:00:00Z", "trend": 49.0, "est": True}]
    out = bh.apply_estimates([old_est, real], new)
    assert [p["trend"] for p in out] == [40.0, 50.0], out       # ancienne estimation remplacée, jour réel préservé
    print("ok apply_estimates")


def test_merge_keeps_est_and_real_wins():
    now = dt.datetime(2026, 10, 3, 9, 0, tzinfo=dt.timezone.utc)
    hist = [{"date": "2026-09-01T12:00:00Z", "trend": 40.0, "est": True},
            {"date": "2026-10-03T03:00:00Z", "trend": 41.0, "est": True}]
    out = merge_history(hist, now, 50.0, 30.0)
    assert out[0].get("est") is True and out[0]["trend"] == 40.0
    assert out[-1]["trend"] == 50.0 and "est" not in out[-1], out    # le relevé réel du jour remplace l'estimation
    print("ok merge_history")


def test_average_30d():
    now = dt.datetime(2026, 10, 3, 9, 0, tzinfo=dt.timezone.utc)
    h = [{"date": f"2026-10-0{d}T09:00:00Z", "trend": v} for d, v in ((1, 10.0), (2, 20.0), (3, 30.0))]
    assert average_30d(h, now) == 20.0
    assert average_30d(h[:2], now) is None
    assert average_30d(h + [{"date": "2026-09-20T12:00:00Z", "trend": 999.0, "est": True}], now) == 20.0   # estimations exclues
    print("ok average_30d")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()

"""Tests du mélange de prix : python3 test_blend.py"""
from blend import blend, smooth


def test_single_source():
    assert blend({"cardmarket": 100.0}) == (100.0, ["cardmarket"])


def test_weighted_average():
    value, used = blend({"cardmarket": 100.0, "ebay": 110.0, "tcgplayer": 95.0})
    assert used == ["cardmarket", "ebay", "tcgplayer"]
    assert abs(value - (100 * .6 + 110 * .25 + 95 * .15) / 1.0) < 0.01


def test_outlier_rejected():
    value, used = blend({"cardmarket": 100.0, "ebay": 250.0, "tcgplayer": 105.0})
    assert "ebay" not in used and 100 <= value <= 105


def test_two_sources_diverge_keeps_reference():
    assert blend({"cardmarket": 100.0, "ebay": 300.0}) == (100.0, ["cardmarket"])


def test_invalid_values_ignored():
    assert blend({"cardmarket": 0, "ebay": None or 0}) == (None, [])


def test_smooth_first_value():
    assert smooth(120.0, None) == 120.0


def test_smooth_damps_and_clamps():
    assert smooth(110.0, 100.0) == 106.0            # 0.6*110 + 0.4*100
    assert smooth(400.0, 100.0) == 125.0            # plafonné à +25 %
    assert smooth(10.0, 100.0) == 75.0              # plafonné à -25 %


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

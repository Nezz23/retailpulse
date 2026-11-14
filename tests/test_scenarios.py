import json

import pandas as pd
import pytest

from retailpulse import config, scenarios


def lines(rows):
    """(sub_category, discount, sales, profit) -> the columns the scenario model reads from sales_wide."""
    df = pd.DataFrame(rows, columns=["sub_category", "discount", "sales", "profit"])
    df["gross_sales"] = df["sales"] / (1 - df["discount"])
    df["implied_cost"] = df["sales"] - df["profit"]
    return df


# a full-price line and a 50%-off line: list price 80, cost 60, so it sells at 40 and loses 20
PEN = lines([("Art", 0.0, 100.0, 30.0), ("Art", 0.5, 40.0, -20.0)])


def test_cap_reprices_only_lines_above_it_and_keeps_cost():
    r = scenarios.cap(PEN, 0.2)
    # 80 * (1 - 0.2) = 64 against cost 60 -> +4; the full-price line is untouched
    assert r["lines_capped"] == 1
    assert r["revenue"] == pytest.approx(164.0) and r["profit"] == pytest.approx(34.0)
    assert r["profit_change"] == pytest.approx(24.0) and r["revenue_change"] == pytest.approx(24.0)


def test_demand_loss_scales_price_and_cost_of_capped_lines_only():
    r = scenarios.cap(PEN, 0.2, loss=0.5)
    # half the volume: sales 32, cost 30 -> +2 instead of -20
    assert r["revenue_change"] == pytest.approx(32.0 - 40.0)
    assert r["profit_change"] == pytest.approx(2.0 + 20.0)


def test_losing_all_capped_volume_recovers_exactly_its_baseline_loss():
    r = scenarios.cap(PEN, 0.2, loss=1.0)
    assert r["profit_change"] == pytest.approx(20.0) and r["revenue"] == pytest.approx(100.0)


def test_cap_above_every_discount_is_the_baseline():
    r = scenarios.cap(PEN, 0.6, loss=0.5)
    assert r["lines_capped"] == 0 and r["profit_change"] == 0 and r["revenue_change"] == 0


def test_targeted_cap_leaves_other_sub_categories_alone():
    df = pd.concat([PEN, lines([("Chairs", 0.5, 40.0, -20.0)])], ignore_index=True)
    assert scenarios.cap(df, 0.2, sub_categories=["Chairs"])["lines_capped"] == 1


def test_recommendation_skips_a_bigger_gain_that_caps_profitable_lines():
    # 15% discounts make money, 50% discounts lose it. Per 50% line a 10% cap recovers 0.75 * (72 - 60) + 20 = 29
    # vs 23 for a 20% cap, but costs each 15% line 25 - 0.75 * (90 - 60) = 2.5: 10 * 6 - 2 * 2.5 > 0 on paper
    df = lines([("X", 0.0, 100.0, 30.0)] + [("X", 0.15, 85.0, 25.0)] * 2 + [("X", 0.5, 40.0, -20.0)] * 10)
    grid = scenarios.grid(df)
    by_cap = grid[grid["demand_loss"] == scenarios.PLANNING_LOSS].set_index("cap")
    assert not by_cap.loc[0.10, "only_loss_making_levels"] and by_cap.loc[0.20, "only_loss_making_levels"]
    assert by_cap.loc[0.10, "profit_change"] > by_cap.loc[0.20, "profit_change"]
    assert scenarios.recommend(grid)["cap"] == 0.15     # tightest cap that still leaves the 15% lines alone


def test_threshold_is_the_lowest_discount_level_with_negative_margin():
    n = scenarios.MIN_LINES
    df = lines([("X", 0.0, 100.0, 20.0)] * n + [("X", 0.2, 80.0, 4.0)] * n + [("X", 0.3, 70.0, -5.0)] * n
               + [("X", 0.7, 30.0, -40.0)] * (n - 1))       # too few lines at 70% to report
    t = scenarios.threshold_table(df, "sub_category").iloc[0]
    assert t["max_profitable_discount"] == 0.2 and t["loss_threshold_discount"] == 0.3


def test_run_on_the_pipeline_writes_valid_json(built, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    out = scenarios.run(charts=False)
    saved = json.loads((tmp_path / "scenarios.json").read_text(), parse_constant=pytest.fail)   # rejects NaN
    assert saved["year"] == 2026 == out["year"]
    # fixture 2026: the 50%-off Pen (list 80, cost 60) is the only line above any cap
    assert {r["lines_capped"] for r in saved["blanket_caps"]} == {1}
    assert saved["baseline"]["profit"] == pytest.approx(60 - 20 + 12 - 6 + 25 + 5)

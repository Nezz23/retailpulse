import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest

from retailpulse import analysis, config, forecast, tableau
from retailpulse.db import query


def lines(rows):
    """(year, order, sales, profit, discount, sub_category) -> the frame analysis.load_lines() returns."""
    df = pd.DataFrame(rows, columns=["year", "order_id", "sales", "profit", "discount", "sub_category"])
    df["line_margin"] = df["profit"] / df["sales"]
    return df


def test_margin_is_a_ratio_of_sums_not_an_average_of_line_margins():
    df = lines([(2025, "a", 100.0, 50.0, 0, "X"), (2025, "b", 900.0, 0.0, 0, "X")])
    assert analysis.margin(df) == pytest.approx(0.05)           # mean of line margins would say 0.25


def test_margin_change_ci_brackets_a_clear_drop():
    rng = np.random.default_rng(0)
    prev = [(2025, f"p{i}", 100.0, 30.0 + rng.normal(0, 1), 0, "X") for i in range(300)]
    cur = [(2026, f"c{i}", 100.0, 10.0 + rng.normal(0, 1), 0, "X") for i in range(300)]
    r = analysis.margin_change_ci(lines(prev + cur), 2026, n_boot=300)
    assert r["change_pp"] == pytest.approx(-20, abs=0.5)
    assert r["ci95_pp"][1] < 0 and r["share_of_bootstrap_below_zero"] == 1.0


def test_seasonal_naive_repeats_last_year_and_scores_exactly():
    idx = pd.date_range("2023-01-01", periods=36, freq="MS")
    s = pd.Series(np.tile(np.arange(1, 13, dtype=float) * 10, 3), index=idx)
    fc = forecast.seasonal_naive(s.iloc[:24], 12)
    assert list(fc["forecast"]) == list(s.iloc[24:])
    sc = forecast.score(s.iloc[24:], fc)
    assert sc["mape_pct"] == 0 and sc["coverage95_pct"] == 100


def test_seasonality_index_averages_to_one_per_year():
    idx = pd.date_range("2023-01-01", periods=24, freq="MS")
    s = pd.Series(np.tile([1.0] * 11 + [13.0], 2), index=idx)
    season = forecast.seasonality(s)
    assert season.loc[season.month == 12, "mean"].item() == pytest.approx(13 / 2)
    assert season["mean"].mean() == pytest.approx(1.0)


def test_every_tableau_formula_references_a_real_field(built):
    cols = list(query("SELECT * FROM analytics.sales_wide LIMIT 0").columns)
    assert tableau.unknown_references(cols) == {}
    assert tableau.case_collisions(cols) == set()


def test_field_dictionary_documents_every_extract_column(built):
    cols = query("SELECT * FROM analytics.sales_wide LIMIT 0").columns
    doc = (config.ROOT / "tableau" / "field_dictionary.md").read_text()
    assert [c for c in cols if f"`{c}`" not in doc] == []


def test_generated_workbook_is_well_formed_and_complete(tmp_path, monkeypatch):
    out = tmp_path / "data"
    out.mkdir()
    pd.DataFrame({"order_date": ["2026-01-01"], "sales": [1.0], "profit": [0.5]}).to_csv(out / "sales_wide.csv",
                                                                                         index=False)
    pd.DataFrame({"month": ["2026-01-01"], "revenue": [1.0]}).to_csv(out / "forecast.csv", index=False)
    monkeypatch.setattr(config, "TABLEAU_DIR", out)
    twb = tmp_path / "w.twb"
    tableau.write_workbook(twb)
    root = ET.parse(twb).getroot()
    captions = {c.get("caption") for c in root.iter("column") if c.find("calculation") is not None}
    assert {c.name for c in tableau.CALCS} | {p.name for p in tableau.PARAMS} <= captions
    # every reference to another calc or a parameter was rewritten to its internal name
    formulas = [c.find("calculation").get("formula") for c in root.iter("column") if c.find("calculation") is not None]
    names = {c.name for c in tableau.CALCS} | {p.name for p in tableau.PARAMS}
    assert not [f for f in formulas for n in names if f"[{n}]" in f]

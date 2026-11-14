import pandas as pd
import pytest

from retailpulse import pipeline
from retailpulse.db import query

from .conftest import sheets


def test_validation_rejects_missing_or_mistyped_columns():
    s = sheets()
    s["Orders"] = s["Orders"].drop(columns=["Profit"])
    with pytest.raises(pipeline.SchemaError):
        pipeline.validate(s)
    s = sheets()
    s["Orders"]["Sales"] = s["Orders"]["Sales"].astype(str)
    with pytest.raises(pipeline.SchemaError):
        pipeline.validate(s)


def test_profile_reports_the_source_quirks():
    p = pipeline.profile(sheets()["Orders"])
    assert p["exact_duplicate_lines"] == 1
    assert p["product_ids_with_several_names"] == 1          # P3: Desk and Desk Lamp
    assert p["orders_with_several_customers"] == 1           # O-6
    assert p["loss_making_lines"] == 3


def test_normalize_drops_only_the_exact_duplicate():
    o, *_, stats = pipeline.normalize(sheets())
    assert stats["exact_duplicates_removed"] == 1 and len(o) == 9
    assert 10 not in set(o["row_id"])                       # the later Row ID of the pair is the one dropped


def test_business_rules_catch_impossible_lines():
    s = sheets()
    s["Orders"].loc[0, "Ship Date"] = s["Orders"].loc[0, "Order Date"] - pd.Timedelta(days=1)
    s["Orders"].loc[1, "Profit"] = 999.0                      # profit above sales -> negative implied cost
    o, *_ = pipeline.normalize(s)
    rules = pipeline.business_rules(o)
    assert rules["ship date before order date"] == 1
    assert rules["negative implied cost (profit above sales)"] == 1


def test_quality_checks_pass_on_the_built_marts(built):
    assert all(pipeline.quality_checks().values())


def test_reused_product_id_becomes_two_products(built):
    p = query("SELECT product_name FROM mart.dim_product WHERE product_id = 'P3' ORDER BY 1")
    assert list(p.product_name) == ["Desk", "Desk Lamp"]


def test_discount_fields_are_derived_consistently(built):
    f = query("SELECT gross_sales::float g, discount_amount::float d, implied_cost::float c FROM mart.fct_sales "
              "WHERE row_id = 5")
    assert (f.g[0], f.d[0], f.c[0]) == (80.0, 40.0, 60.0)    # 40 at 50% off; cost = 40 - (-20)


def test_multi_customer_order_goes_to_the_larger_customer(built):
    o = query("SELECT customer_id, sales::float FROM mart.fct_orders WHERE order_id = 'O-6'")
    assert (o.customer_id[0], o.sales[0]) == ("C4", 60.0)


def test_yearly_kpis_match_hand_calculation(built):
    k = query("SELECT year, revenue::float, profit::float, margin_pct::float, orders, aov::float, "
              "revenue_yoy_pct::float FROM analytics.yearly_kpis ORDER BY year")
    y25, y26 = k.iloc[0], k.iloc[1]
    # 2025: 100 + 20 + 80 = 200 revenue, 30 + 10 - 10 = 30 profit, 2 orders
    assert (y25.revenue, y25.profit, y25.margin_pct, y25.orders, y25.aov) == (200.0, 30.0, 15.0, 2, 100.0)
    # 2026: 200 + 40 + 60 + 30 + 50 + 10 = 390 revenue; growth 95%
    assert (y26.revenue, y26.revenue_yoy_pct) == (390.0, 95.0)


def test_margin_bridge_mix_and_rate_add_up_to_the_margin_change(built):
    b = query("SELECT sum(mix_effect_pp)::float + sum(rate_effect_pp)::float AS total FROM analytics.margin_bridge "
              "WHERE year = 2026")
    k = query("SELECT margin_change_pp::float m FROM analytics.yearly_kpis WHERE year = 2026")
    assert b.total[0] == pytest.approx(k.m[0], abs=0.01)


def test_cohort_retention_counts_returning_customers(built):
    c = query("SELECT quarters_since_first, active_customers, retention_pct::float FROM analytics.cohort_retention "
              "WHERE cohort_quarter = '2025-01-01' ORDER BY 1")
    # cohort Q1 2025 = C1, C2; C1 orders again in Q1 2026 (4 quarters later), C2 in Q1 2026 too (O-5)
    assert list(c.itertuples(index=False, name=None)) == [(0, 2, 100.0), (4, 2, 100.0)]


def test_discount_bands_cover_every_line(built):
    d = query("SELECT discount_band, lines, profit::float FROM analytics.discount_bands ORDER BY 1")
    assert dict(zip(d.discount_band, d.lines)) == {"0%": 7, "1-20%": 1, "41-80%": 1}
    assert d.lines.sum() == 9


def test_unprofitable_products_use_lifetime_profit(built):
    p = query("SELECT product_name, is_unprofitable FROM analytics.product_performance ORDER BY 1")
    # Pen loses 20 on one line but earns 40 elsewhere; Desk Lamp only ever lost money
    assert dict(zip(p.product_name, p.is_unprofitable)) == {"Chair": False, "Desk": False, "Desk Lamp": True,
                                                            "Pen": False}

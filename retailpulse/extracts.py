"""Write every analytics view to data/tableau/<view>.csv: the Tableau data sources (Tableau Public reads CSV)."""
from . import config
from .db import query

VIEWS = ("sales_wide", "yearly_kpis", "monthly_trends", "product_performance", "subcategory_margin",
         "regional_performance", "discount_bands", "margin_bridge", "customer_rfm", "cohort_retention",
         "segment_summary", "returns_summary")


def run() -> dict[str, int]:
    config.TABLEAU_DIR.mkdir(parents=True, exist_ok=True)
    counts = {}
    for v in VIEWS:
        df = query(f"SELECT * FROM analytics.{v}")
        df.to_csv(config.TABLEAU_DIR / f"{v}.csv", index=False)
        counts[v] = len(df)
    return counts


if __name__ == "__main__":
    print(run())

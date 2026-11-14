# RetailPulse: Retail Profitability Intelligence for Tableau

**A Tableau-first BI platform that explains why profit lags revenue.** A reproducible Python pipeline loads retail transactions into a PostgreSQL star schema. Twelve SQL analytical views and a statistics layer feed Tableau-ready extracts, 37 calculated fields (LOD expressions, table calculations, parameters) and a six-dashboard specification.

> **Data honesty up front:** the dataset is **Tableau's official Sample Superstore, a synthetic dataset**. It is the only well-known public retail dataset with recorded profit *and* discount fields at line level. Every finding below describes this sample, not a real company.

> **Tableau status:** the data sources, the calculations, and a starter workbook (`tableau/RetailPulse.twb`) are generated and checked by automated tests. **The workbook has not yet been opened in Tableau**, because Tableau isn't installed on the build machine. Dashboard screenshots and the Tableau Public link will be added once the dashboards are built from [`tableau/dashboard_spec.md`](tableau/dashboard_spec.md).

## The business problem

Revenue is growing but profit is not keeping pace. Leadership's questions, and what this data says:

| Question | Answer | Evidence |
|---|---|---|
| Is profitability declining? | Revenue grew **21.4%** in 2026, but profit grew only **16.0%**, and margin moved from 13.46% to **12.87% (−0.6pp)**. **The total-margin dip is not statistically significant** (order-level bootstrap 95% CI −5.6 to +4.8pp). | Descriptive + bootstrap |
| Where is margin falling? | The margin bridge splits the −0.60pp into **+1.26pp from favourable mix** and **−1.86pp from lower margins within sub-categories**. The largest falls: **Machines −11.7pp, Binders −9.9pp, Tables −8.4pp**. | SQL decomposition (reconciles exactly) |
| Are discounts reducing profitability? | Strongly associated. The three biggest margin falls all came with deeper discounts (**+8.2, +7.4, +5.1pp** discount rate). Across all 17 sub-categories, discount change tracks margin change (**Spearman ρ −0.66, p 0.004**). **Every discount level from 30% up loses money**. Lines discounted above 20% are 15.7% of revenue and lose **$136K**. | Association, not causation |
| How strong is the discount link at line level? | With sub-category, region and segment held fixed, **+10 points of discount ↔ −19.9pp line margin** (95% CI −20.3 to −19.5; R² 0.82). | OLS, HC1 robust SEs |
| Which products and regions underperform? | **304 of 1,894 products lose money** in total ($77.6K, equal to 26.6% of total profit). **Central** has the lowest margin (7.9%) and the deepest discounting (24.6%). 12 states/provinces are loss-making, led by **Texas, Ohio and Pennsylvania**. | Descriptive |
| Which segments contribute most? | Consumer brings the most revenue ($1.17M) at the lowest margin (11.6%). Home Office has the highest margin (14.0%). | Descriptive |
| How does retention look? | 98.5% of customers order more than once. Quarterly cohorts average **35.7% active four quarters after first purchase**. | Cohort analysis |
| What should we expect next? | Holt-Winters projects **$735K** of revenue for the next 12 months, but with **~23% monthly error** on the 2026 holdout. **Sep, Nov and Dec run 63–82% above** an average month. | Time-based validation |

**Recommendation:** cap discounts at 20% in Machines, Binders and Tables, and A/B test the cap before rolling it out. Start a price and discount review with the top 20 loss-making products and the three worst states. This follows from the associations above, and a test is how to establish causation.

## Dataset

| | |
|---|---|
| Source | [Tableau Sample – Superstore](https://public.tableau.com/app/sample-data/sample_-_superstore.xls), downloaded by the pipeline from Tableau's sample-data page (sha256 `5045ed4fec49cae2cc0fdc5ab0d204ba09efa767fe00c996822499e8cc42fbbd`, last saved Oct 2025) |
| Nature | **Synthetic** sample data published by Tableau for learning and demos; © Tableau / Salesforce. The raw file is not committed; derived extracts are included for convenience |
| Size | 10,194 order lines, 5,111 orders, 804 customers, 1,862 product IDs, 2023-01-03 to 2026-12-30, US and Canada |
| Fields | Orders sheet (21 columns: order, customer, segment, geography, product hierarchy, sales, quantity, discount, profit), plus Returns (296 orders) and People (regional managers) |

**Why this dataset.** The brief needed recorded profit and discounts.

| Candidate | Why it was rejected |
|---|---|
| Olist (real, Brazil) | Has no cost or profit fields |
| UCI Online Retail II | Already used in another project of mine, and has no costs |
| Iowa Liquor Sales | Real costs, but a fixed statutory markup and no discounts |

Choosing Superstore gives up realism for completeness. That trade-off is stated wherever results appear.

**Data quality: what the pipeline found and did** (`results/data_quality.json`)

| Issue | Count | Handling |
|---|---|---|
| Exact duplicate lines (identical apart from Row ID) | 2 | Dropped; the first Row ID is kept |
| Product IDs reused for different product names | 32 IDs | Surrogate `product_key` over (ID, name), giving 1,894 products |
| Orders carrying several customer IDs | 2 orders × 4 customers (HO-15231…15234, identical lines in 2025 and 2026) | Each order goes to the customer with the most sales. The 3 customers who appear only on these orders have no attributed orders, so RFM covers 801 of 804 |
| Mixed-type postal codes (numeric US, text Canada) | 211 text | Stored as text |
| Missing values, ship-before-order, non-positive sales or quantity, discount outside [0, 1), profit above sales | 0 | Checked as business rules; the load fails on any violation |

## Architecture

```mermaid
flowchart LR
  SRC[Tableau Sample Superstore<br/>.xls · Orders / Returns / People] --> PY[Python pipeline<br/>schema validation · profiling ·<br/>dedupe · business rules]
  PY --> STG[(PostgreSQL<br/>staging)]
  STG --> MART[mart: star schema<br/>fct_sales · fct_orders<br/>dim_customer · dim_product ·<br/>dim_geography · dim_date]
  MART --> QC{7 data-quality<br/>assertions}
  MART --> V[analytics: 12 SQL views<br/>KPIs · YoY · rolling · Pareto/ABC ·<br/>margin bridge · RFM · cohorts]
  V --> ST[Statistics<br/>bootstrap · OLS w/ fixed effects ·<br/>Spearman]
  V --> FC[Forecast<br/>seasonal naive · Holt-Winters · SARIMA<br/>12-month holdout]
  V --> EX[Tableau extracts<br/>data/tableau/*.csv]
  ST & FC --> INS[Evidence-typed insights]
  INS --> EX
  CF[tableau.py<br/>37 calcs · 4 parameters] --> TWB[RetailPulse.twb<br/>+ calculated_fields.md]
  EX --> TWB
  TWB --> TAB[Tableau: 6 dashboards<br/>per dashboard_spec.md]
```

**Star schema**

| Table | Grain | Key | Notes |
|---|---|---|---|
| `mart.fct_sales` | order line | `row_id` | FKs → `dim_date` (order and ship), `dim_customer`, `dim_product`, `dim_geography`. Derived `gross_sales`, `discount_amount`, `implied_cost = sales − profit`, `is_returned` |
| `mart.fct_orders` | order | `order_id` | Sums of lines; FK → `dim_customer` |
| `mart.dim_customer` | customer | `customer_id` | Name, segment |
| `mart.dim_product` | product | `product_key` (surrogate) | Unique (`product_id`, `product_name`); category and sub-category |
| `mart.dim_geography` | postal location | `geo_key` (surrogate) | Country, region, state, city, postal code, regional manager |
| `mart.dim_date` | day | `date` | Calendar 2023–2027 |

**Data-quality assertions** run after every build and stop the pipeline on failure:

- fact rows reconcile to staging
- sales reconcile to staging
- profit reconciles to staging
- every order date is in `dim_date`
- every region has a manager
- gross sales = sales + discount amount
- order totals equal line totals

## SQL analytics (`sql/02_analytics.sql`)

| View | Technique |
|---|---|
| `yearly_kpis` | CTE, `lag()` for YoY growth and margin change, `FILTER` for loss-order share |
| `monthly_trends` | Rolling 3-month average and a rolling 12-month margin (window frames); 12-month `lag` YoY |
| `product_performance` | `dense_rank` overall and within sub-category, running-sum Pareto, ABC classes |
| `subcategory_margin`, `regional_performance` | Partitioned windows for share-of-year and YoY margin change |
| `margin_bridge` | **Mix vs rate decomposition** of the YoY margin change; the effects sum exactly to the change (tested) |
| `customer_rfm` | `ntile(5)` R/F/M scores with named segments |
| `cohort_retention` | Quarterly acquisition cohorts with `first_value` cohort sizes |
| `discount_bands`, `segment_summary`, `returns_summary` | Conditional aggregation, revenue-weighted discount rates |

**Metric definitions** are written at the top of the file. Margin is always a ratio of sums, never an average of line margins, and a test enforces this.

## Tableau layer

| Artifact | What it is |
|---|---|
| [`data/tableau/*.csv`](data/tableau) | 15 extracts. `sales_wide.csv` (10,192 lines) is the main data source; the others are pre-aggregated views, the forecast, and the insights |
| [`tableau/calculated_fields.md`](tableau/calculated_fields.md) | **37 calculated fields:** 7 LOD expressions (e.g. `{FIXED [customer_id] : MIN([order_date])}` for cohorts, `{FIXED : SUM([profit]) / SUM([sales])}` as the company benchmark), 6 table calculations (`LOOKUP` YoY, `WINDOW_AVG`, `RUNNING_SUM`/`TOTAL` Pareto, `RANK_UNIQUE` top-N), and **4 parameters** (Metric, Top N, Discount Cap, Selected Region) |
| [`tableau/field_dictionary.md`](tableau/field_dictionary.md) | Every extract column, defined |
| [`tableau/dashboard_spec.md`](tableau/dashboard_spec.md) | Six dashboards: wireframes, chart specs, interactions (parameter, filter and highlight actions, drill-down), design tokens (navy and neutral, colour-blind-checked categorical palette), and a feature checklist |
| `tableau/RetailPulse.twb` | Generated starter workbook: both data sources, all parameters and calculations. **Unverified until opened in Tableau** |

All of these are generated from one definition (`retailpulse/tableau.py`). Tests fail if a formula references a field that doesn't exist, if a calc name collides with a column (Tableau names are case-insensitive), or if an extract column is missing from the field dictionary.

**Finishing the workbook** (manual, about 2–3 hours):

1. Install the free [Tableau Public](https://public.tableau.com/app/discover) app, e.g. `brew install --cask tableau-public`.
2. Open `tableau/RetailPulse.twb`.
3. Follow the *Assembly* section of `dashboard_spec.md`.
4. Save to Tableau Public.

## Forecasting (`results/forecast.json`)

Setup: train on 2023-01 to 2025-12, test on all 12 months of 2026, then refit the winner on everything.

| Method | MAE | MAPE | Annual total error | 80% / 95% interval coverage |
|---|---|---|---|---|
| Seasonal naive | $15,793 | 24.4% | −17.7% | 66.7% / 66.7% |
| **Holt-Winters** (damped, multiplicative season), **selected** | $14,031 | **23.3%** | −20.1% | 66.7% / 91.7% |
| SARIMA(0,1,1)(0,1,1)₁₂ on log revenue | $15,135 | 28.2% | **+5.9%** | 75.0% / 100% |

The selection rule (lowest MAPE) was fixed before the results were seen. The honest reading:

- With 36 training months, no method forecasts individual months well.
- SARIMA is far better on the annual total.
- Use the forecast for seasonal planning, not budgeting.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
createdb retailpulse                        # PostgreSQL 15+; or set DATABASE_URL
.venv/bin/python -m retailpulse             # download, load, build, analyse, export extracts (~3 s after the download)
createdb retailpulse_test && .venv/bin/python -m pytest -q   # 20 tests against a real Postgres
# or: docker compose up                     # Postgres + pipeline in containers
```

**Tests** use hand-built lines that reproduce every source quirk (a duplicate, a reused product ID, a multi-customer order, a return, discounted loss lines) and run them through the real pipeline and SQL:

- schema validation and business rules
- KPI, cohort, discount-band and unprofitable-product values checked against hand calculations
- the margin bridge reconciles to the margin change
- bootstrap and seasonality maths
- the seasonal-naive forecast and its scoring
- Tableau formula references, the field dictionary, and the generated workbook

CI runs them against a PostgreSQL 17 service container and builds the Docker image.

## Technical challenges

| Challenge | Fix |
|---|---|
| Product IDs are not unique products | A naive `dim_product` keyed on the ID silently merges 32 pairs of different products. A surrogate key over (ID, name) fixes it, and a test covers it |
| Ratio metrics | The averages of line margins and the margin of the totals disagree badly here (loss lines are small). Every margin is a ratio of sums, in SQL and in Tableau |
| A headline that isn't significant | The total-margin dip looked like the story. The bootstrap showed it is noise at the total level, so the analysis moved to *where* margin moved (the margin bridge) and *what moved with it* (discounts) |
| Floating-point sums | Two break-even products summed to −5e-15 and were counted as unprofitable. Values are rounded to cents before flagging |

## Limitations

- **Synthetic data.** Relationships (especially discount → profit) may be built into the generator, so they say nothing about real retail.
- **No independent cost data.** `implied_cost` is just `sales − profit`, so shipping, COGS and overhead can't be separated.
- **Association, not causation.** Deeper discounts may be a *response* to weak products, not their cause. Testing a discount cap is the way to find out.
- **Returns.** Returned orders keep their recorded sales and profit (the source has no refund amounts). Returns are reported separately.
- **Small time series.** 48 monthly points limit the forecast.

## Future improvements

- Build and publish the six dashboards to Tableau Public, then add screenshots and the link here.
- Re-run the pipeline on a real retailer's data with a cost feed (the schema and tests are dataset-agnostic past the loader).
- Add a designed discount-cap experiment and an uplift analysis.
- Add a Tableau Hyper extract (`tableauhyperapi`) for faster workbooks.

# RetailPulse: Retail Decision Intelligence

**A retail analytics platform that explains why profit lags revenue, forecasts demand and flags what changed.** A reproducible Python pipeline loads retail transactions into a PostgreSQL star schema. Twelve SQL analytical views and a statistics layer feed a published Tableau **Executive Overview** dashboard with year-over-year KPIs, parameter-driven metric switching and Top N ranking, and insight text computed from the data.

> **Data honesty up front:** the dataset is **Tableau's official Sample Superstore, a synthetic dataset**. It is the only well-known public retail dataset with recorded profit *and* discount fields at line level. Every finding below describes this sample, not a real company.

**Live dashboard:** [RetailPulse Executive Overview on Tableau Public](https://public.tableau.com/app/profile/neha.kothavade/viz/RetailPulse_ExecutiveOverview_approved/ExecutiveOverview)

**Live decision app (Streamlit):** [retailpulse9030.streamlit.app](https://retailpulse9030.streamlit.app/) · six pages, including an interactive discount simulator.

> A second, **real** source sits alongside the synthetic one: **UCI Online Retail II**, 1.07M invoice lines from a UK
> online retailer, 2009–2011. It powers the demand forecast and daily anomaly detection. It has no cost data, so no
> profit or margin is ever derived from it.

![Executive Overview](docs/screenshots/executive_overview.png)

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

**Recommendation:** cap discounts at 20% company-wide, starting with Machines, Binders and Tables, and roll the cap out as a randomized test. Test a tighter cap in Tables, Storage and Supplies, where a 20% discount already loses money. Start a price and discount review with the most exposed products and the three worst states. This follows from the associations above and the modeled scenarios below; a test is how to establish causation.

## Discount optimization and what-if scenarios

Full business case, methodology and risks: **[docs/discount_business_case.md](docs/discount_business_case.md)**.

> The thresholds are observed associations. The dollar figures are **modeled opportunities, not realized savings**.
> They come from repricing 2026 order lines under stated assumptions, on synthetic data.

| Question | Answer |
|---|---|
| Where does discounting stop paying? | Every category is profitable at a 20% discount. Losses start at 30% (Furniture), 40% (Technology) and 70% (Office Supplies). In **Tables, Storage and Supplies**, the 20% level already loses money. |
| What is at stake? | In 2026, lines discounted above 20% (463 of 3,379) lost **$47.8K**, against total profit of $95.9K. |
| Which products are most exposed? | High-ticket machines, binding systems and conference tables. The top one, a 3D printer, lost $9.2K on two deep-discount lines. |
| What would a cap do? | A **20% cap** models **+$47.8K to +$71.9K** profit, and +$65.9K if 25% of the capped volume is lost. Margin moves from 12.87% to 20.5–22.6%. |
| Why 20% and not 10%? | A 10% cap shows more on paper (+$98.4K at 25% demand loss), but it also caps profitable 15–20% lines. If that capped volume is lost, its gain falls to +$14.0K. A 20% cap only touches discount levels that already lose money, so profit rises whatever share of that volume is lost. |

| Margin by discount level | Modeled profit change by cap and demand loss |
|---|---|
| ![](docs/figures/margin_by_discount.png) | ![](docs/figures/cap_scenarios.png) |

**The model.** Lines above the cap are repriced at list × (1 − cap), with unit cost held fixed. A demand-loss share
L, from 0% to 100%, removes that part of their revenue and cost. The recommendation rule is coded and tested: among
caps that touch only loss-making discount levels, pick the one with the largest gain at L = 25%. Outputs are in
`results/scenarios.json` and `scenarios.csv`.

## Decision intelligence extensions

| Capability | Source | Module | Output |
|---|---|---|---|
| Incremental ingestion (simulated feed) | Online Retail II · real | `retailpulse/ingest.py`, `sql/03_uci.sql` | `uci.lines`, `uci.ingest_log` |
| 30/60/90-day demand forecast | Online Retail II · real | `retailpulse/forecast_daily.py` | `results/uci_forecast.json`, `.csv` |
| Anomaly detection with severity | both | `retailpulse/anomalies.py` | `results/anomalies.json` |
| Weekly executive report | both | `retailpulse/report.py`, `.github/workflows/report.yml` | self-contained HTML |
| Decision app | both | `streamlit_app.py`, `app/` | 6 pages on committed snapshots |

### Data: UCI Online Retail II

Data card: [docs/uci_data_card.md](docs/uci_data_card.md).

- **Source and integrity.** Chen (2012), CC BY 4.0. The SHA-256 is verified on every read.
- **Duplicates.** Profiling found 34,335 exact duplicate lines and about 20K cancellations. The real export has no
  line number, so a `UNIQUE NULLS NOT DISTINCT` key over all eight fields does the deduplication. A full replay
  rejected exactly the 34,335 duplicates and kept 1,033,036 lines.
- **Revenue definition.** Net product revenue: cancellations are netted in. Postage, fees, bad-debt adjustments and
  zero prices are left out.

### Ingestion is a simulated feed

The data ends in 2011, so each run **replays** the next window of history after the last successful batch:

```bash
python -m retailpulse.ingest --days 7
```

| Guarantee | How |
|---|---|
| Idempotent | Re-running a window loads 0 rows |
| All or nothing | One transaction per batch |
| Restartable | The watermark only moves on success |
| Logged | Every batch, failed ones included, gets a row in `uci.ingest_log` |
| Schedulable | A crontab line is in the data card |

### Demand forecast: 30, 60 and 90 days (`results/uci_forecast.json`)

The series is daily net revenue. A **known closure calendar** (Saturdays, bank holidays, Christmas Dec 24–Jan 3) is
verified against every zero day in the data. The forecast also drops the partial last day.

The backtest is **rolling-origin**:

- 11 origins, 28 days apart.
- The earliest test window crosses New Year, as the forward forecast does.
- Each model sees only days up to its origin; a test enforces this.

| Model (mean over folds) | WAPE 30d | WAPE 60d | WAPE 90d | Bias, 90-day total | 80% / 95% interval cover | Year-end fold WAPE |
|---|---|---|---|---|---|---|
| Weekly naive (**baseline**) | 44.9% | 47.4% | 49.8% | -12.4% | 77% / 92% | 103.2% |
| Same weekday last year | 36.5% | 36.1% | 35.1% | -2.9% | 83% / 90% | 38.1% |
| Holt-Winters (weekly) | 44.3% | 46.9% | 49.4% | -14.9% | 91% / 97% | 102.9% |
| SARIMAX + annual Fourier + closures | 32.3% | 32.4% | 32.4% | -2.5% | 84% / 94% | 44.4% |
| **SARIMAX / last-year blend (selected)** | 31.3% | 31.1% | 30.6% | -2.7% | 87% / 94% | 36.2% |

**What the backtest showed:**

- **SARIMAX.** It was best on most folds, but it overshot the New Year fold total by
  19%, carrying the November peak into January.
- **Same weekday last year.** This knows the post-Christmas drop, so the equal-weight blend fixes most of the
  overshoot.
- **The blend.** It has the lowest 90-day WAPE, **19.1 points better** than the weekly
  naive baseline.

Forecast from 2011-12-09:

| Horizon | Forecast | Backtest range |
|---|---|---|
| 30 days | £592K | £550K–£726K |
| 60 days | £1.31M | £1.20M–£1.49M |
| 90 days | £1.97M | £1.79M–£2.20M |

The backtest range is the min–max of the selected model's own errors across the overlapping folds. It is a rough
range, not a confidence interval.

### Anomalies (`results/anomalies.json`)

**Two detectors, one per source:**

- **Superstore, monthly.** Revenue, profit and margin are scored against a leave-one-year-out year × month
  expectation.
- **Online Retail II, daily.** Each trading day is compared with the median of the same weekday over the previous
  8 weeks. The baseline only looks backwards, so the detector could run every morning.

**Severity bands** are robust z of 4, 5 and 6 or more. They were calibrated by simulation: under 1% of noise-only
months reach 4, and a test enforces it. A first version flagged 45 of 144 months; it fitted too closely, which made
the residual spread look small.

**Current flags:**

- **Online Retail II: 5 days.** Most are the last trading days before the Christmas shutdown and the first day
  after it.
- **Superstore: 3 months.** The worst is January 2024, at a −17% margin.

Context lists what moved alongside each flag: sub-categories, invoice concentration, cancellations and nearby
closures. **No root cause is claimed.**

### Weekly executive report

`python -m retailpulse.report` writes a self-contained HTML report containing:

- per-source KPIs, week-over-week and year-over-year
- the latest forecast
- recent anomalies
- rule-based recommendations, each tied to a number in the data

**Scheduling and configuration:**

- **Schedule.** `.github/workflows/report.yml` runs every Monday 07:00 UTC and on demand, with any historical week
  as input. It uploads the report as a run artifact.
- **Settings.** `REPORT_UCI_WEEK`, `REPORT_SUPERSTORE_WEEK` and `REPORT_OUT_DIR`.
- **No database.** The report reads committed snapshots only.

### Decision app

| Page | What it answers |
|---|---|
| Executive overview | Profitability KPIs with the bootstrap CI, monthly revenue by year, margin by discount level, the recommendation, and the demand outlook |
| Discount simulator | Choose a cap, the demand lost and the sub-categories. Shows live revenue, profit and margin; a profit bridge; a sensitivity curve against the recommended cap; and the no-regret check |
| Demand forecast | Pick a 30/60/90-day horizon to see 80% and 95% bands, model comparison and validation design |
| Anomalies | Severity markers on each series, with a table of what moved with each flag |
| Weekly report | Preview and download for any historical week |
| Data & methods | Sources, ingestion log and limitations |

Every page reads precomputed snapshots in `results/` (`python -m retailpulse.snapshot`), so the app needs no
database. Tests render every page with the database unreachable.

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
  subgraph A["Superstore · synthetic · full rebuild"]
    SRC[Sample Superstore .xls] --> PY[pipeline.py<br/>validate · profile · dedupe · rules]
    PY --> MART[(PostgreSQL mart<br/>star schema · 7 DQ checks)]
    MART --> V[12 SQL views]
    V --> ST[analysis.py<br/>bootstrap · OLS · Spearman]
    V --> FC[forecast.py<br/>monthly, 12-mo holdout]
    V --> SC[scenarios.py<br/>discount caps · sensitivity]
  end
  subgraph B["Online Retail II · real · incremental"]
    UCI[UCI .xlsx<br/>SHA-256 checked] --> ING[ingest.py<br/>watermark · 1 txn/batch]
    ING --> UL[(uci.lines<br/>unique key · ingest_log)]
    UL --> DS[uci.daily_sales view]
    DS --> FD[forecast_daily.py<br/>30/60/90 d · rolling origin]
  end
  V & DS --> AN[anomalies.py<br/>calibrated robust z]
  V --> EX[Tableau extracts] --> TAB[Tableau Public<br/>Executive Overview]
  V & DS --> SN[snapshot.py<br/>results/snapshots/*.csv]
  ST & FC & SC & FD & AN --> RES[results/*.json]
  SN & RES --> APP[Streamlit app<br/>6 pages · no DB needed]
  SN & RES --> REP[report.py<br/>weekly HTML · GitHub Actions cron]
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

**Executive Overview** ([`tableau/RetailPulse.twbx`](tableau/RetailPulse.twbx), 1400×860, no scrolling) reads `data/tableau/sales_wide.csv` (10,192 lines).

| Element | How it is built |
|---|---|
| Controls | **Year** and **Metric** (Revenue / Profit / Profit Margin / Orders) parameters, **Top N** parameter (3–17), **Region** filter applied as a context filter to every sheet |
| 4 KPI cards | Revenue, profit, margin and orders for the selected year, each with change vs the prior year and a monthly sparkline |
| Trend | Selected metric by month, selected year vs prior year |
| Top N ranking | Native Top N filter driven by the parameter; bars turn orange when the sub-category lost money that year |
| Heatmap | Profit margin by region × segment on a diverging scale centred on 0% |
| Insights | Three sentences built from calculated fields, so every number updates with the filters: growth vs margin, deep-discount revenue and profit, count of loss-making sub-categories |

Key calculations: margin as `SUM([profit]) / SUM([sales])` (a ratio of sums), current- vs prior-year measures keyed to the Year parameter, a metric switch via `CASE [Metric]`, and a `{FIXED [sub_category] : …}` LOD to count loss-making sub-categories.

**Checked against PostgreSQL:** for 2026 (all regions) the dashboard shows revenue $745,568, profit $95,926, margin 12.9% (−0.6 pp), 1,723 orders (+28.6%), 14.5% of revenue at discounts above 20% losing $47.8K, and 4 of 17 sub-categories unprofitable. All of these match the SQL views; the same checks were repeated for 2025 and for the West region.

[`tableau/calculated_fields.md`](tableau/calculated_fields.md), [`field_dictionary.md`](tableau/field_dictionary.md) and [`dashboard_spec.md`](tableau/dashboard_spec.md) are the original design spec (six dashboards). Only the Executive Overview has been built; the other five are future work.

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
createdb retailpulse_test && .venv/bin/python -m pytest -q   # 54 tests against a real Postgres
# or: docker compose up                     # Postgres + pipeline in containers

# individual steps
.venv/bin/python -m retailpulse.ingest --days 7     # next week of Online Retail II (simulated feed)
.venv/bin/python -m retailpulse.forecast_daily      # 30/60/90-day forecast + backtest (~15 s)
.venv/bin/python -m retailpulse.anomalies
.venv/bin/python -m retailpulse.snapshot            # refresh the app/report snapshots
.venv/bin/python -m retailpulse.report              # weekly HTML report -> reports/
.venv/bin/streamlit run streamlit_app.py            # decision app on http://localhost:8501
```

`python -m retailpulse` runs everything in order. That includes the Online Retail II download (44 MB, checksum-verified)
and the catch-up ingestion, about 30 seconds.

## Deployment

**Streamlit Community Cloud** (the app reads committed snapshots, so it needs no database and no secrets):

1. Push this repository to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), choose **Create app**, then this repo, branch `main` and main file
   `streamlit_app.py`.
3. Deploy. `requirements.txt` is installed automatically, and `.streamlit/config.toml` sets the theme.

To refresh what the app shows, re-run the pipeline locally, run `python -m retailpulse.snapshot`, then commit
`results/`.

**Weekly report:** this is already scheduled in `.github/workflows/report.yml`. To change the time, edit its `cron`
line. To run it for a chosen week, use **Actions → weekly-report → Run workflow**.

**Tests** use hand-built lines that reproduce every source quirk (a duplicate, a reused product ID, a multi-customer order, a return, discounted loss lines) and run them through the real pipeline and SQL:

- schema validation and business rules
- KPI, cohort, discount-band and unprofitable-product values checked against hand calculations
- the margin bridge reconciles to the margin change
- bootstrap and seasonality maths
- the seasonal-naive forecast and its scoring
- Tableau formula references, the field dictionary, and the generated workbook
- discount-cap arithmetic and the no-regret rule (`test_scenarios.py`)
- the Online Retail II reader and ingestion: duplicates, reruns, rejects, failed-batch rollback, watermark, revenue
  rules
- the daily forecast: no leakage past the origin, the closure calendar, naive and score maths
- anomalies: a spike flagged without leaking into other years, the noise-only false-flag rate, a trailing-only
  daily baseline
- the weekly report: week selection, the cancellation rule, no later forecast on back-dated reports
- every app page renders with the database unreachable

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
- **Modeled scenarios.** The cap results assume fixed unit cost, a uniform demand loss and no basket, halo or competitor effects. They size an opportunity; a controlled test measures it.
- **Real data, historical and revenue-only.** Online Retail II ends in December 2011 and has no cost. Ingestion replays it as a simulated feed, and nothing about its profit is claimed.
- **Two separate sources.** Superstore and Online Retail II are never combined into one metric; every chart and card is labelled with its source.
- **Small time series.** 48 monthly points limit the forecast.

## Future improvements

- Add prices and promotions as forecast inputs, and evaluate over more than one year-end.
- Build the remaining dashboards from `dashboard_spec.md` (profitability and revenue leakage, customer and product intelligence).
- Re-run the pipeline on a real retailer's data with a cost feed (the schema and tests are dataset-agnostic past the loader).
- Run the 20% cap as a randomized experiment, and replace the uniform demand-loss assumption with a measured price response.
- Add a Tableau Hyper extract (`tableauhyperapi`) for faster workbooks.

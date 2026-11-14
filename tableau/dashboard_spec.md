# RetailPulse: six-dashboard specification

Field names are from `field_dictionary.md`, calculations from `calculated_fields.md`. Canvas: **1366 × 900 fixed** on every dashboard, so layouts don't reflow between screens.

## Design system

| Token | Value | Use |
|---|---|---|
| Navy (header, nav rail) | `#0F1F3D` | Top bar and left navigation |
| Page | `#F5F6F8` | Dashboard background |
| Card | `#FFFFFF`, 1px `#E3E6EB` border | Every chart and KPI sits on a card |
| Ink | `#1B2433` | Titles and numbers |
| Muted ink | `#5B6475` | Axis labels, captions |
| Series 1 / 2 / 3 | `#2A78D6` / `#EB6834` / `#1BAF7A` | Categorical, in this fixed order (Furniture, Office Supplies, Technology); validated for colour-blind separation |
| Diverging | `#2A78D6` ← `#D9DCE1` → `#EB6834` | Margin vs company: above (blue), at (grey), below (orange) |
| Loss | `#EB6834` + a "▼" glyph | Never colour alone |

**Typography:** Tableau Book for body text, Tableau Semibold for titles and KPI values.

| Element | Size |
|---|---|
| KPI value | 26 pt |
| Sheet title | 12 pt |
| Axis label | 9 pt |

**Gridlines:** horizontal only, `#EEF0F3`. No borders on the panes.

**Number formats:**

| Measure | Format |
|---|---|
| Revenue and profit | `$#,##0,K` on axes; `$#,##0` in tooltips |
| Margin and growth | `0.0%`, with a ▲/▼ prefix on growth |

**Navigation:** a 64px left rail with six navigation buttons (Tableau *Navigation* objects), with the active page filled navy. The header shows the page title, a one-line subtitle stating the question the page answers, and a "Data: Tableau Sample Superstore (synthetic)" badge.

---

## 1. Executive Command Center

*What happened? How are revenue, profit and margin trending, and where does revenue come from?*

```
┌────┬──────────────────────────────────────────────────────────────────────────┐
│NAV │ Executive Command Center      [Year ▾] [Region ▾] [Segment ▾]   synthetic│
│ ■  ├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬───────┤
│ □  │ Revenue  │ Profit   │ Margin   │ Rev YoY  │ Prof YoY │ Orders   │ AOV   │
│ □  │ $745.6K  │ $95.9K   │ 12.9%    │ ▲21.4%   │ ▲16.0%   │ 1,723    │ $433  │
│ □  │ spark    │ spark    │ spark    │          │          │          │       │
│ □  ├──────────┴──────────┴──────────┴──────────┼──────────┴──────────┴───────┤
│ □  │ Monthly revenue (bars) + rolling 3M (line)│ Revenue & margin by category │
│    │                                           │ (bar = revenue, label=margin)│
│    ├───────────────────────────────────────────┼──────────────────────────────┤
│    │ Rolling 12-month margin (line, ref = co.) │ Top 5 sub-categories (profit)│
└────┴───────────────────────────────────────────┴──────────────────────────────┘
```

| Sheet | Build | Detail |
|---|---|---|
| KPI cards (×7) | Text marks | `Revenue CY`, `Profit CY`, `Profit Margin`, `Revenue YoY`, `Profit YoY`, `Orders`, `AOV`. Growth is coloured by sign and carries a ▲/▼ glyph. Each card has a 12-month sparkline (an area mark under the value) |
| Monthly revenue | Columns: MONTH(`order_date`) continuous | Bars = `Revenue`. Dual-mark line = `Rolling 3M Revenue`, on a shared axis (same unit, so not a dual-axis chart) |
| Category mix | Rows: `category` | Bars = `Revenue`. Label = `Profit Margin`. Colour = series slots 1–3 |
| Rolling margin | Line | `margin_rolling_12m_pct` from `monthly_trends.csv`. Reference line = company margin |
| Top sub-categories | Bars | `Total Profit` by `sub_category`, top 5 by an index filter |

**Interactions**

- The Year, Region and Segment filters apply to all sheets that use `sales_wide`.
- Clicking a category bar filters the trend sheets (a filter action).

**Story** (numbers from `results/insights.json`)

- **What happened:** revenue grew 21.4% in the latest year, profit grew 16.0%, and margin moved −0.6pp.
- **Why it matters:** the margin dip alone is not statistically distinguishable from noise (bootstrap 95% CI −5.6 to +4.8pp). That is why page 3 looks *inside* the total.

## 2. Sales Performance

*Where does revenue come from, and which products carry it?*

```
┌────┬──────────────────────────────────────────────────────────────────────────┐
│NAV │ Sales Performance            [Metric: Revenue|Profit|Margin]  [Top N: 10]│
│    ├─────────────────────────────────────┬────────────────────────────────────┤
│    │ Filled map: state × Selected Metric │ Region bars (click = parameter act)│
│    │ (diverging when Metric = Margin)    │ Central / East / South / West      │
│    ├─────────────────────────────────────┼────────────────────────────────────┤
│    │ Category ▸ Sub-category drill       │ Top N products │ Bottom N products │
│    │ (hierarchy, + / − to drill)         │ (Product Rank) │ (Product Rank)    │
│    ├─────────────────────────────────────┴────────────────────────────────────┤
│    │ Pareto: products by revenue (bars) + Running Revenue Share (line, 80% ref)│
└────┴──────────────────────────────────────────────────────────────────────────┘
```

| Sheet | Build | Detail |
|---|---|---|
| Map | Filled map | `state` geographic role (State/Province, with Country). Colour = `Selected Metric`. When Metric = Profit Margin, use the diverging palette centred on `Company Margin` |
| Region bars | Bars | `Selected Metric` by `region`. A *parameter action* sets `Selected Region`. Other sheets colour by `Is Selected Region` (selected = navy, others = light grey) |
| Hierarchy | Hierarchy `category` → `sub_category` → `product_name` | Drill-down with the + control |
| Top/Bottom N | Bars | Filter on `Show Top N` / `Show Bottom N`, computed along `product_name` |
| Pareto | Bars + line | Bars = `Revenue` sorted descending. Line = `Running Revenue Share`. Constant reference line at 80% |

**Custom tooltip:** product, category, revenue, profit, margin, and units, plus the line *"Rank {Product Rank} of N on {Metric}"*.

**Story**

- West and East lead on revenue.
- 304 products lose money in total. The Pareto shows how few products carry most of the revenue.

## 3. Profitability Intelligence

*Why might profit be lagging revenue? Is discounting associated with lower margin?*

```
┌────┬──────────────────────────────────────────────────────────────────────────┐
│NAV │ Profitability Intelligence                       [Discount Cap: 20% ▾]   │
│    ├────────────────────────────────────┬─────────────────────────────────────┤
│    │ Margin bridge (latest year):       │ Discount vs margin                  │
│    │ prev margin → mix → rate → current │ x = discount level, y = margin,     │
│    │ (waterfall from margin_bridge.csv) │ size = revenue; ref line at 0 and   │
│    │                                    │ at the Discount Cap parameter       │
│    ├────────────────────────────────────┼─────────────────────────────────────┤
│    │ Sub-category margin YoY            │ Unprofitable products (table, red ▼)│
│    │ (dot plot prev → current, sorted)  │ Product Lifetime Profit < 0         │
│    ├────────────────────────────────────┴─────────────────────────────────────┤
│    │ Region × category margin heatmap (Margin vs Company, diverging)          │
└────┴──────────────────────────────────────────────────────────────────────────┘
```

| Sheet | Build | Detail |
|---|---|---|
| Margin bridge | Waterfall: Gantt bars with size = −value | Steps: previous margin, mix effect, rate effect, current margin. Data: `margin_bridge.csv`, summed by year. The effects reconcile exactly to the margin change |
| Discount scatter | Circles | Columns `discount`, Rows `Profit Margin`, size `Revenue`. Reference lines at 0% margin and at `Discount Cap`. Colour = `Above Discount Cap` |
| Sub-category YoY | Dot plot | Two dots per sub-category (previous year grey, latest blue), connected by a line, sorted by change |
| Unprofitable products | Text table | Filter `Unprofitable Product` = true. Columns: profit, revenue, discount rate. Conditional formatting: `Margin Status` |
| Heatmap | Square marks | `region` × `category`, colour = `Margin vs Company` (diverging) |

**What-if:** a KPI card shows `Profit on Capped Lines`, the profit or loss on lines above the chosen cap.

**Story**

- **Why it might have happened:** the three sub-categories with the largest margin falls deepened their discounts (Machines +8.2pp, Binders +7.4pp, Tables +5.1pp). Across all 17 sub-categories, discount change and margin change move together (Spearman ρ −0.66, p 0.004).
- **Why it matters:** with sub-category, region and segment held fixed, each extra 10 points of discount goes with about 20pp lower line margin. Every discount level from 30% up is loss-making on average.
- **Caveat:** this is an association, and the dataset is synthetic.

## 4. Customer Intelligence

*Who drives revenue, and do customers come back?*

```
┌────┬──────────────────────────────────────────────────────────────────────────┐
│NAV │ Customer Intelligence                                 [Segment ▾]        │
│    ├──────────────────────────────┬───────────────────────────────────────────┤
│    │ Revenue & margin by segment  │ RFM segments: customers vs revenue share  │
│    │ (Consumer/Corporate/Home Off)│ (bars, from customer_rfm.csv)             │
│    ├──────────────────────────────┴───────────────────────────────────────────┤
│    │ Cohort retention heatmap: Cohort Quarter × Quarters Since First → Retention│
│    ├──────────────────────────────┬───────────────────────────────────────────┤
│    │ Orders per customer histogram│ High-value customers (top 20 by lifetime  │
│    │ (Customer Orders bins)       │ revenue, with margin)                     │
└────┴──────────────────────────────┴───────────────────────────────────────────┘
```

| Sheet | Build | Detail |
|---|---|---|
| Segment | Bars | `Revenue` by `segment`. Label = `Profit Margin` |
| RFM | Bars | Customer count and revenue share by `rfm_segment` |
| Cohort heatmap | Squares | Rows `Cohort Quarter` (LOD), Columns `Quarters Since First`. Colour = `Retention`, sequential blue, one hue from light to dark |
| Histogram | Bars | Bins of `Customer Orders`. Colour = `Repeat Customer` |
| High-value | Bars | Top 20 `customer_name` by `Customer Lifetime Revenue` |

**Interaction:** selecting a segment highlights it across the sheets (a highlight action).

## 5. Forecasting & Trends

*What should we expect next, and how much should we trust it?*

```
┌────┬──────────────────────────────────────────────────────────────────────────┐
│NAV │ Forecasting & Trends                          [Method: holdout ▾]        │
│    ├──────────────────────────────────────────────────────────────────────────┤
│    │ Actual monthly revenue + next-12-month forecast with 80% / 95% bands     │
│    ├────────────────────────────────────┬─────────────────────────────────────┤
│    │ Holdout: actual vs each method     │ Holdout accuracy table              │
│    │ (latest 12 months)                 │ MAE · MAPE · annual error · coverage│
│    ├────────────────────────────────────┴─────────────────────────────────────┤
│    │ Seasonality index by calendar month (mean with min–max range)            │
└────┴──────────────────────────────────────────────────────────────────────────┘
```

| Sheet | Build | Detail |
|---|---|---|
| Forecast | Data: `forecast.csv` | Line = `revenue` where series = actual. Line = `forecast` where series starts `forecast_`. Bands = area between `lo95`–`hi95` (light) and `lo80`–`hi80` (darker) |
| Holdout | Lines | `actual` vs `forecast` for each `holdout_*` series. A parameter picks which method is shown |
| Accuracy table | Text table | From `results/forecast.json` |

| Method | MAPE | Annual error | 95% coverage |
|---|---|---|---|
| Holt-Winters | 23.3% | −20.1% | 91.7% |
| SARIMA | 28.2% | +5.9% | 100% |
| Seasonal naive | 24.4% | −17.7% | 66.7% |

| Seasonality sheet | Detail |
|---|---|
| Seasonality | `seasonality.csv`: bar = mean index, with a min–max range bar behind it |

**Story:** Sep, Nov and Dec run 63–82% above an average month. Monthly forecasts are about ±23% accurate, which is good enough for seasonal planning but not for a precise budget.

## 6. Executive Insights

*What should the business do next?*

```
┌────┬──────────────────────────────────────────────────────────────────────────┐
│NAV │ Executive Insights                                                       │
│    ├────────────────────────────────────┬─────────────────────────────────────┤
│    │ What happened                      │ Why it might have happened          │
│    │ finding · evidence type · CI       │ finding · association caveat        │
│    ├────────────────────────────────────┼─────────────────────────────────────┤
│    │ Why it matters                     │ Where to focus                      │
│    ├────────────────────────────────────┴─────────────────────────────────────┤
│    │ What to expect next  ·  Limitations: synthetic sample, no separate cost   │
└────┴──────────────────────────────────────────────────────────────────────────┘
```

Each panel is a text sheet on `insights.csv` (fields: `area`, `type`, `finding`, `uncertainty`, `action`), filtered to one `area`. A small "evidence type" pill (Descriptive / Association / Forecast) sits beside each finding. The text is generated from the result files, so re-running the pipeline updates the page.

---

## Feature checklist (where each required Tableau feature is used)

| Feature | Where |
|---|---|
| Calculated fields | All pages (37 in `calculated_fields.md`) |
| LOD expressions | `Latest Year`, `Company Margin`, `Product Lifetime Profit`, `Customer First Order`, `Cohort Size`, `Customer Orders`, `Customer Lifetime Revenue` |
| Table calculations | `Revenue YoY (table calc)`, `Rolling 3M Revenue`, `Running Revenue Share`, `Product Rank`, `Show Top/Bottom N` |
| Parameters | `Metric`, `Top N`, `Discount Cap`, `Selected Region` |
| Parameter actions | Region bar → `Selected Region` (page 2) |
| Dashboard actions | Category → trend filter (1); segment highlight (4); product → page 3 detail (go-to-sheet URL action) |
| Drill-down | Category → Sub-category → Product hierarchy (2) |
| Dynamic filters | Year / Region / Segment, applied to all sheets using this data source |
| Custom tooltips | Product and state tooltips (2, 3) |
| Reference lines | 80% Pareto, 0% margin, discount cap, company margin |
| Conditional formatting | `Margin Status`, diverging `Margin vs Company`, ▲/▼ growth |
| Highlighting | `Is Selected Region`, segment highlight |

## Assembly (Tableau Public, about 2–3 hours)

1. Run `python -m retailpulse`, so that `data/tableau/*.csv` exist.
2. Open `tableau/RetailPulse.twb` in Tableau Public. The parameters and all 37 calculated fields are already defined on the "Sales lines" data source.
   - If Tableau asks for the file, point it at `data/tableau/sales_wide.csv`.
3. Add text-file data sources for:
   - `forecast.csv` (included)
   - `margin_bridge.csv`, `customer_rfm.csv`, `seasonality.csv` and `insights.csv`
4. Build each sheet listed above. Keep the sheet names as written in this spec.
5. Create six dashboards at 1366 × 900, using the layout grids above:
   - a vertical container for the navigation rail
   - a horizontal container for the KPI row
   - tiled cards with 12px padding
6. Add the actions under *Dashboard → Actions*: the parameter action, the filter action, and the highlight action.
7. Apply the design tokens:
   - *Format → Workbook* for fonts
   - *Format → Shading* for card colours
   - *Format → Lines* for gridlines
8. Publish:
   - Use *File → Save to Tableau Public*.
   - Then put the public URL in the README.

# Calculated fields and parameters

Generated from `retailpulse/tableau.py` (the single source of truth). Data source: `data/tableau/sales_wide.csv` (one row per order line).

## Parameters

| Parameter | Type | Default | Values | Purpose |
|---|---|---|---|---|
| Metric | string | `"Revenue"` | `"Revenue"`, `"Profit"`, `"Profit Margin"` | Switches ranked bars and maps between revenue, profit and margin |
| Top N | integer | `10` | `5`, `10`, `15`, `20`, `25` | How many products the top/bottom lists show |
| Discount Cap | real | `0.2` | `0.1`, `0.2`, `0.3`, `0.4` | Policy threshold used to flag lines and price the what-if |
| Selected Region | string | `"All"` | `"All"`, `"Central"`, `"East"`, `"South"`, `"West"` | Set by a parameter action when a region is clicked; highlights it across sheets |

## Calculated fields

| Field | Kind | Formula | Purpose | Dashboards |
|---|---|---|---|---|
| Revenue | aggregate | `SUM([sales])` | Net revenue after discounts | 1-6 |
| Total Profit | aggregate | `SUM([profit])` | Recorded profit | 1-6 |
| Profit Margin | aggregate | `SUM([profit]) / SUM([sales])` | Ratio of sums, never the average of line margins | 1-4 |
| Orders | aggregate | `COUNTD([order_id])` | Distinct orders | 1, 2 |
| AOV | aggregate | `SUM([sales]) / COUNTD([order_id])` | Average order value | 1, 4 |
| Discount Rate | aggregate | `SUM([discount_amount]) / SUM([gross_sales])` | Revenue-weighted discount depth | 3 |
| Latest Year | LOD | `{FIXED : MAX(YEAR([order_date]))}` | Most recent year in the data, so KPI cards never hard-code a year | 1 |
| Revenue CY | aggregate | `SUM(IF YEAR([order_date]) = [Latest Year] THEN [sales] END)` | Revenue in the latest year | 1 |
| Revenue PY | aggregate | `SUM(IF YEAR([order_date]) = [Latest Year] - 1 THEN [sales] END)` | Revenue in the year before | 1 |
| Profit CY | aggregate | `SUM(IF YEAR([order_date]) = [Latest Year] THEN [profit] END)` | Profit in the latest year | 1 |
| Profit PY | aggregate | `SUM(IF YEAR([order_date]) = [Latest Year] - 1 THEN [profit] END)` | Profit in the year before | 1 |
| Revenue YoY | aggregate | `([Revenue CY] - [Revenue PY]) / [Revenue PY]` | KPI card growth | 1 |
| Profit YoY | aggregate | `([Profit CY] - [Profit PY]) / [Profit PY]` | KPI card growth | 1 |
| Revenue YoY (table calc) | table calc | `(SUM([sales]) - LOOKUP(SUM([sales]), -1)) / ABS(LOOKUP(SUM([sales]), -1))` | Growth along any date axis (compute using Year of order_date) | 1, 2 |
| Rolling 3M Revenue | table calc | `WINDOW_AVG(SUM([sales]), -2, 0)` | Smooths the monthly trend line | 1, 2, 5 |
| Running Revenue Share | table calc | `RUNNING_SUM(SUM([sales])) / TOTAL(SUM([sales]))` | Pareto curve of products sorted by revenue | 2 |
| Selected Metric | aggregate | `CASE [Metric] WHEN "Revenue" THEN SUM([sales]) WHEN "Profit" THEN SUM([profit]) WHEN "Profit Margin" THEN SUM([profit]) / SUM([sales]) END` | Measure chosen with the Metric parameter | 2, 3 |
| Product Rank | table calc | `RANK_UNIQUE([Selected Metric], 'desc')` | Rank of each product on the selected metric | 2, 3 |
| Show Top N | table calc | `[Product Rank] <= [Top N]` | Filter for top-N lists | 2 |
| Show Bottom N | table calc | `[Product Rank] > WINDOW_MAX([Product Rank]) - [Top N]` | Filter for bottom-N lists | 2, 3 |
| Company Margin | LOD | `{FIXED : SUM([profit]) / SUM([sales])}` | Benchmark for reference lines and colour rules | 3 |
| Margin vs Company | aggregate | `[Profit Margin] - MIN([Company Margin])` | Diverging colour for regions and categories | 2, 3 |
| Margin Status | aggregate | `IF [Profit Margin] < 0 THEN "Loss" ELSEIF [Profit Margin] < MIN([Company Margin]) THEN "Below company" ELSE "At or above company" END` | Conditional formatting class | 3 |
| Product Lifetime Profit | LOD | `{FIXED [product_id], [product_name] : SUM([profit])}` | Product profit regardless of view filters | 3 |
| Unprofitable Product | basic | `[Product Lifetime Profit] < 0` | Flags the products that lose money in total | 3 |
| Customer First Order | LOD | `{FIXED [customer_id] : MIN([order_date])}` | Acquisition date per customer | 4 |
| Cohort Quarter | basic | `DATETRUNC('quarter', [Customer First Order])` | Acquisition cohort | 4 |
| Quarters Since First | basic | `DATEDIFF('quarter', [Cohort Quarter], DATETRUNC('quarter', [order_date]))` | Cohort age | 4 |
| Cohort Size | LOD | `{FIXED [Cohort Quarter] : COUNTD([customer_id])}` | Customers acquired in the cohort | 4 |
| Retention | aggregate | `COUNTD([customer_id]) / MIN([Cohort Size])` | Share of a cohort ordering in a later quarter | 4 |
| Customer Orders | LOD | `{FIXED [customer_id] : COUNTD([order_id])}` | Lifetime orders per customer (histogram bins) | 4 |
| Customer Lifetime Revenue | LOD | `{FIXED [customer_id] : SUM([sales])}` | High-value customer analysis | 4 |
| Repeat Customer | basic | `[Customer Orders] > 1` | Repeat vs one-time | 4 |
| Discount Band | basic | `IF [discount] = 0 THEN "0%" ELSEIF [discount] <= 0.2 THEN "1-20%" ELSEIF [discount] <= 0.4 THEN "21-40%" ELSE "41-80%" END` | Same bands as analytics.discount_bands | 3 |
| Above Discount Cap | basic | `[discount] > [Discount Cap]` | Lines a cap at the chosen level would affect | 3 |
| Profit on Capped Lines | aggregate | `SUM(IF [discount] > [Discount Cap] THEN [profit] END)` | Profit currently earned (or lost) above the cap | 3 |
| Is Selected Region | basic | `[Selected Region] = "All" OR [region] = [Selected Region]` | Highlight driven by the region parameter action | 2, 3 |

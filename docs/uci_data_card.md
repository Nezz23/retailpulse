# Data card: UCI Online Retail II

**Real** transactions from a UK-based online retailer of gifts and homewares, most of whose customers are
wholesalers. This is RetailPulse's second source. It sits **separate from Superstore** (which is synthetic), and the
two are never mixed in one metric.

| | |
|---|---|
| Source | Chen, D. (2012). *Online Retail II*. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D |
| License | CC BY 4.0 |
| File | `online_retail_ii.zip` (one `.xlsx`, one sheet per year) · SHA-256 `572e3627…e408e67bfb`, verified on every read |
| Coverage | 2009-12-01 07:45 to 2011-12-09 12:50. **The last day is partial.** |
| Rows | 1,067,371 invoice lines, 8 columns |
| **Not in the data** | Cost, margin, profit, discounts, returns reasons. **No profitability is derived from this source.** |

## What profiling found (`retailpulse/uci.py`)

| Issue | Count | Handling |
|---|---|---|
| Exact duplicate lines (no line number exists to tell them apart) | 34,335 | Rejected by a `UNIQUE NULLS NOT DISTINCT` key over all 8 columns; the count of rejected rows is logged per batch |
| Cancellations (invoice starts with `C`, negative quantity) | 19,494 | Kept in the data, and netted against sales in revenue |
| Bad-debt adjustments (invoice starts with `A`) | 6 | Excluded from revenue |
| Lines with quantity ≤ 0 | 22,950 | Mostly cancellations; the rest are stock write-offs with price 0 |
| Lines with price ≤ 0 | 6,207 | Excluded from revenue (write-offs, samples) |
| Non-product stock codes: `POST`, `DOT`, `M`, `C2`, `D`, `BANK CHARGES`, `AMAZONFEE`, … | ≈5,900 | Excluded from product revenue; product codes start with 5 digits |
| Missing customer ID | 243,007 | Kept for revenue; excluded from any customer-level metric |
| Countries | 43 | 91.9% of lines are UK |

## Calendar

- **Trading days:** 604 of the 739 calendar days have sales.
- **Saturdays:** the shop is effectively closed (one Saturday in two years has sales).
- **Closures:** about ten days at Christmas, plus UK bank holidays.
- **Gaps are zeros.** A forecast has to model them as closed days, not as missing data, and has to drop the partial last day.

## Simulated ingestion

The data stops in 2011. Incremental loading **replays** it in date order, one batch at a time, so that the
duplicate-prevention, validation and logging logic gets exercised. It is not a live feed from a running store.

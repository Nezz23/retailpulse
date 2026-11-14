"""Single source of truth for the Tableau layer: parameters and calculated fields (incl. LOD and table
calculations). Writes tableau/calculated_fields.md and a starter workbook tableau/RetailPulse.twb that
connects to data/tableau/sales_wide.csv and forecast.csv with every calculation and parameter defined.
The workbook XML is generated, so it must be opened in Tableau to be verified (see README)."""
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pandas as pd

from . import config

TABLEAU_DOCS = config.ROOT / "tableau"


@dataclass(frozen=True)
class Param:
    name: str
    datatype: str          # string | integer | real
    default: str           # Tableau literal, e.g. '"Revenue"' or '10'
    members: tuple[str, ...] = ()
    purpose: str = ""


@dataclass(frozen=True)
class Calc:
    name: str
    formula: str
    datatype: str          # string | integer | real | boolean | date
    role: str              # measure | dimension
    kind: str              # basic | aggregate | LOD | table calc
    purpose: str
    dashboards: str


PARAMS = [
    Param("Metric", "string", '"Revenue"', ('"Revenue"', '"Profit"', '"Profit Margin"'),
          "Switches ranked bars and maps between revenue, profit and margin"),
    Param("Top N", "integer", "10", ("5", "10", "15", "20", "25"), "How many products the top/bottom lists show"),
    Param("Discount Cap", "real", "0.2", ("0.1", "0.2", "0.3", "0.4"),
          "Policy threshold used to flag lines and price the what-if"),
    Param("Selected Region", "string", '"All"', ('"All"', '"Central"', '"East"', '"South"', '"West"'),
          "Set by a parameter action when a region is clicked; highlights it across sheets"),
]

CALCS = [
    # core KPIs
    Calc("Revenue", "SUM([sales])", "real", "measure", "aggregate", "Net revenue after discounts", "1-6"),
    Calc("Total Profit", "SUM([profit])", "real", "measure", "aggregate", "Recorded profit", "1-6"),
    Calc("Profit Margin", "SUM([profit]) / SUM([sales])", "real", "measure", "aggregate",
         "Ratio of sums, never the average of line margins", "1-4"),
    Calc("Orders", "COUNTD([order_id])", "integer", "measure", "aggregate", "Distinct orders", "1, 2"),
    Calc("AOV", "SUM([sales]) / COUNTD([order_id])", "real", "measure", "aggregate", "Average order value", "1, 4"),
    Calc("Discount Rate", "SUM([discount_amount]) / SUM([gross_sales])", "real", "measure", "aggregate",
         "Revenue-weighted discount depth", "3"),
    # latest-year KPI cards (LOD finds the latest year once for the whole data source)
    Calc("Latest Year", "{FIXED : MAX(YEAR([order_date]))}", "integer", "dimension", "LOD",
         "Most recent year in the data, so KPI cards never hard-code a year", "1"),
    Calc("Revenue CY", "SUM(IF YEAR([order_date]) = [Latest Year] THEN [sales] END)", "real", "measure", "aggregate",
         "Revenue in the latest year", "1"),
    Calc("Revenue PY", "SUM(IF YEAR([order_date]) = [Latest Year] - 1 THEN [sales] END)", "real", "measure",
         "aggregate", "Revenue in the year before", "1"),
    Calc("Profit CY", "SUM(IF YEAR([order_date]) = [Latest Year] THEN [profit] END)", "real", "measure", "aggregate",
         "Profit in the latest year", "1"),
    Calc("Profit PY", "SUM(IF YEAR([order_date]) = [Latest Year] - 1 THEN [profit] END)", "real", "measure",
         "aggregate", "Profit in the year before", "1"),
    Calc("Revenue YoY", "([Revenue CY] - [Revenue PY]) / [Revenue PY]", "real", "measure", "aggregate",
         "KPI card growth", "1"),
    Calc("Profit YoY", "([Profit CY] - [Profit PY]) / [Profit PY]", "real", "measure", "aggregate",
         "KPI card growth", "1"),
    # table calculations
    Calc("Revenue YoY (table calc)", "(SUM([sales]) - LOOKUP(SUM([sales]), -1)) / ABS(LOOKUP(SUM([sales]), -1))",
         "real", "measure", "table calc", "Growth along any date axis (compute using Year of order_date)", "1, 2"),
    Calc("Rolling 3M Revenue", "WINDOW_AVG(SUM([sales]), -2, 0)", "real", "measure", "table calc",
         "Smooths the monthly trend line", "1, 2, 5"),
    Calc("Running Revenue Share", "RUNNING_SUM(SUM([sales])) / TOTAL(SUM([sales]))", "real", "measure",
         "table calc", "Pareto curve of products sorted by revenue", "2"),
    Calc("Selected Metric", 'CASE [Metric] WHEN "Revenue" THEN SUM([sales]) WHEN "Profit" THEN SUM([profit]) '
         'WHEN "Profit Margin" THEN SUM([profit]) / SUM([sales]) END', "real", "measure", "aggregate",
         "Measure chosen with the Metric parameter", "2, 3"),
    Calc("Product Rank", "RANK_UNIQUE([Selected Metric], 'desc')", "integer", "measure", "table calc",
         "Rank of each product on the selected metric", "2, 3"),
    Calc("Show Top N", "[Product Rank] <= [Top N]", "boolean", "measure", "table calc",
         "Filter for top-N lists", "2"),
    Calc("Show Bottom N", "[Product Rank] > WINDOW_MAX([Product Rank]) - [Top N]", "boolean", "measure",
         "table calc", "Filter for bottom-N lists", "2, 3"),
    # LOD expressions
    Calc("Company Margin", "{FIXED : SUM([profit]) / SUM([sales])}", "real", "measure", "LOD",
         "Benchmark for reference lines and colour rules", "3"),
    Calc("Margin vs Company", "[Profit Margin] - MIN([Company Margin])", "real", "measure", "aggregate",
         "Diverging colour for regions and categories", "2, 3"),
    Calc("Margin Status", 'IF [Profit Margin] < 0 THEN "Loss" ELSEIF [Profit Margin] < MIN([Company Margin]) '
         'THEN "Below company" ELSE "At or above company" END', "string", "dimension", "aggregate",
         "Conditional formatting class", "3"),
    Calc("Product Lifetime Profit", "{FIXED [product_id], [product_name] : SUM([profit])}", "real", "measure", "LOD",
         "Product profit regardless of view filters", "3"),
    Calc("Unprofitable Product", "[Product Lifetime Profit] < 0", "boolean", "dimension", "basic",
         "Flags the products that lose money in total", "3"),
    Calc("Customer First Order", "{FIXED [customer_id] : MIN([order_date])}", "date", "dimension", "LOD",
         "Acquisition date per customer", "4"),
    Calc("Cohort Quarter", "DATETRUNC('quarter', [Customer First Order])", "date", "dimension", "basic",
         "Acquisition cohort", "4"),
    Calc("Quarters Since First", "DATEDIFF('quarter', [Cohort Quarter], DATETRUNC('quarter', [order_date]))",
         "integer", "dimension", "basic", "Cohort age", "4"),
    Calc("Cohort Size", "{FIXED [Cohort Quarter] : COUNTD([customer_id])}", "integer", "measure", "LOD",
         "Customers acquired in the cohort", "4"),
    Calc("Retention", "COUNTD([customer_id]) / MIN([Cohort Size])", "real", "measure", "aggregate",
         "Share of a cohort ordering in a later quarter", "4"),
    Calc("Customer Orders", "{FIXED [customer_id] : COUNTD([order_id])}", "integer", "dimension", "LOD",
         "Lifetime orders per customer (histogram bins)", "4"),
    Calc("Customer Lifetime Revenue", "{FIXED [customer_id] : SUM([sales])}", "real", "measure", "LOD",
         "High-value customer analysis", "4"),
    Calc("Repeat Customer", "[Customer Orders] > 1", "boolean", "dimension", "basic", "Repeat vs one-time", "4"),
    # discounts and interactivity
    Calc("Discount Band", 'IF [discount] = 0 THEN "0%" ELSEIF [discount] <= 0.2 THEN "1-20%" '
         'ELSEIF [discount] <= 0.4 THEN "21-40%" ELSE "41-80%" END', "string", "dimension", "basic",
         "Same bands as analytics.discount_bands", "3"),
    Calc("Above Discount Cap", "[discount] > [Discount Cap]", "boolean", "dimension", "basic",
         "Lines a cap at the chosen level would affect", "3"),
    Calc("Profit on Capped Lines", "SUM(IF [discount] > [Discount Cap] THEN [profit] END)", "real", "measure",
         "aggregate", "Profit currently earned (or lost) above the cap", "3"),
    Calc("Is Selected Region", '[Selected Region] = "All" OR [region] = [Selected Region]', "boolean",
         "dimension", "basic", "Highlight driven by the region parameter action", "2, 3"),
]

FIELD_REF = re.compile(r"\[([^\]]+)\]")


def referenced_fields(formula: str) -> set[str]:
    return set(FIELD_REF.findall(formula))


def unknown_references(columns: list[str]) -> dict[str, set[str]]:
    """Fields a formula uses that are neither a source column, a calc, nor a parameter (should be empty)."""
    known = set(columns) | {c.name for c in CALCS} | {p.name for p in PARAMS}
    return {c.name: missing for c in CALCS if (missing := referenced_fields(c.formula) - known)}


def write_markdown(path: Path = TABLEAU_DOCS / "calculated_fields.md") -> None:
    lines = ["# Calculated fields and parameters", "",
             "Generated from `retailpulse/tableau.py` (the single source of truth). Data source: "
             "`data/tableau/sales_wide.csv` (one row per order line).", "", "## Parameters", "",
             "| Parameter | Type | Default | Values | Purpose |", "|---|---|---|---|---|"]
    lines += [f"| {p.name} | {p.datatype} | `{p.default}` | {', '.join(f'`{m}`' for m in p.members)} | {p.purpose} |"
              for p in PARAMS]
    lines += ["", "## Calculated fields", "", "| Field | Kind | Formula | Purpose | Dashboards |",
              "|---|---|---|---|---|"]
    lines += [f"| {c.name} | {c.kind} | `{c.formula.replace('|', '¦')}` | {c.purpose} | {c.dashboards} |"
              for c in CALCS]
    path.write_text("\n".join(lines) + "\n")


# ---- starter workbook ---------------------------------------------------------------------------------

def case_collisions(columns: list[str]) -> set[str]:
    """Tableau field names are case-insensitive, so a calc may not share a column's name in any case."""
    lower = {x.lower() for x in columns}
    return {c.name for c in CALCS if c.name.lower() in lower}


TYPE_MAP = {"int64": "integer", "float64": "real", "bool": "boolean", "object": "string", "str": "string"}


def _csv_columns(csv: Path) -> list[tuple[str, str]]:
    df = pd.read_csv(csv, nrows=500)
    out = []
    for col, dtype in df.dtypes.items():
        t = TYPE_MAP.get(str(dtype), "string")
        if col.endswith("date") or col == "month":
            t = "date"
        out.append((col, t))
    return out


def _param_xml(i: int, p: Param) -> str:
    members = "".join(f"<member value={quoteattr(m)} />" for m in p.members)
    return (f"<column caption={quoteattr(p.name)} datatype='{p.datatype}' name='[Parameter {i}]' "
            f"param-domain-type='list' role='measure' type='{'nominal' if p.datatype == 'string' else 'quantitative'}' "
            f"value={quoteattr(p.default)}><calculation class='tableau' formula={quoteattr(p.default)} />"
            f"<members>{members}</members></column>")


def _calc_xml(i: int, c: Calc, param_ids: dict[str, str]) -> str:
    formula = c.formula
    for name, pid in param_ids.items():
        formula = formula.replace(f"[{name}]", f"[Parameters].[{pid}]")
    ctype = "quantitative" if c.role == "measure" and c.datatype in ("real", "integer") else "nominal"
    if c.datatype == "date":
        ctype = "ordinal"
    return (f"<column caption={quoteattr(c.name)} datatype='{c.datatype}' name='[Calculation_{i:04d}]' "
            f"role='{c.role}' type='{ctype}'><calculation class='tableau' formula={quoteattr(formula)} /></column>")


def _textscan_datasource(name: str, caption: str, csv: Path, extra: str = "") -> str:
    cols = "".join(f"<column datatype='{t}' name={quoteattr(c)} ordinal='{i}' />"
                   for i, (c, t) in enumerate(_csv_columns(csv)))
    return (f"<datasource caption={quoteattr(caption)} inline='true' name='{name}' version='18.1'>"
            f"<connection class='federated'><named-connections>"
            f"<named-connection caption={quoteattr(csv.stem)} name='textscan.{name}'>"
            f"<connection class='textscan' directory='../data/tableau' filename={quoteattr(csv.name)} password='' server='' />"
            f"</named-connection></named-connections>"
            f"<relation connection='textscan.{name}' name={quoteattr(csv.name)} table='[{csv.stem}#csv]' type='table'>"
            f"<columns character-set='UTF-8' header='yes' locale='en_US' separator=','>{cols}</columns>"
            f"</relation></connection>{extra}</datasource>")


def write_workbook(path: Path = TABLEAU_DOCS / "RetailPulse.twb") -> None:
    param_ids = {p.name: f"Parameter {i}" for i, p in enumerate(PARAMS, 1)}
    params = "".join(_param_xml(i, p) for i, p in enumerate(PARAMS, 1))
    calc_ids = {c.name: f"Calculation_{i:04d}" for i, c in enumerate(CALCS, 1)}
    calcs = []
    for i, c in enumerate(CALCS, 1):
        formula = c.formula
        for name, cid in calc_ids.items():
            formula = formula.replace(f"[{name}]", f"[{cid}]")
        calcs.append(_calc_xml(i, Calc(c.name, formula, c.datatype, c.role, c.kind, c.purpose, c.dashboards),
                               param_ids))
    xml = ("<?xml version='1.0' encoding='utf-8' ?>\n"
           "<workbook source-platform='mac' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>"
           "<datasources>"
           f"<datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>{params}</datasource>"
           + _textscan_datasource("federated.sales_wide", "Sales lines", config.TABLEAU_DIR / "sales_wide.csv",
                                  "".join(calcs))
           + _textscan_datasource("federated.forecast", "Forecast", config.TABLEAU_DIR / "forecast.csv")
           + "</datasources></workbook>\n")
    path.write_text(xml)


def run() -> None:
    TABLEAU_DOCS.mkdir(exist_ok=True)
    write_markdown()
    write_workbook()


if __name__ == "__main__":
    cols = list(pd.read_csv(config.TABLEAU_DIR / "sales_wide.csv", nrows=1).columns)
    assert not (bad := unknown_references(cols)), bad
    assert not (clash := case_collisions(cols)), clash
    run()
    print(f"{len(PARAMS)} parameters, {len(CALCS)} calculated fields -> {TABLEAU_DOCS}")

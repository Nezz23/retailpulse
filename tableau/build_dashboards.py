"""Build the three RetailPulse dashboards inside a Tableau-saved workbook.

Tableau Public cannot open workbooks written from scratch, so this edits a .twb that Tableau itself saved
(the connection to data/tableau/sales_wide.csv): it adds parameters, calculated fields, worksheets and
three dashboards that share one header, one set of controls and navigation buttons, and removes the
first-draft sheets and fields. Run:  python tableau/build_dashboards.py <path/to/workbook.twb>
"""
import re
import sys
import uuid
from xml.sax.saxutils import quoteattr

DS = "federated.1v3zil81ekgd7u15t28b419jxmj6"
path = sys.argv[1]
s = open(path, encoding="utf-8").read()
_ds = s[s.index("<datasource caption='retailpulse_sales'"):]
_ds = _ds[:_ds.index("<layout dim-ordering")]
# existing named calculated fields (Discount Band, Profitability) by internal name
EXISTING = {m.group(2): m.group(0) for m in re.finditer(
    r"<column caption='([^']*)'[^>]*name='\[(Calculation_\d+)\]'[^>]*>\s*<calculation[^>]*/>\s*</column>", _ds)}

# one visual identity for all three dashboards
NAVY, BLUE, ORANGE, GREY, INK, MUTED = "#0f1f3d", "#2a78d6", "#eb6834", "#b8bec9", "#1f2937", "#6b7280"
GREEN, RED, LIGHT_BLUE, BG, LINE = "#1a7f37", "#c62828", "#9ec5f0", "#f5f7fa", "#e3e6ec"

# ---- parameters ------------------------------------------------------------------------------------------
YEAR, METRIC, TOPN = "[Parameters].[Selected Year]", "[Parameters].[Metric]", "[Parameters].[Top N]"
PARAMS = f"""<datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>
      <aliases enabled='yes' />
      <column caption='Year' datatype='string' name='[Selected Year]' param-domain-type='list' role='measure' type='nominal' value='&quot;2026&quot;'>
        <calculation class='tableau' formula='&quot;2026&quot;' />
        <members><member value='&quot;2023&quot;' /><member value='&quot;2024&quot;' /><member value='&quot;2025&quot;' /><member value='&quot;2026&quot;' /></members>
      </column>
      <column caption='Metric' datatype='string' name='[Metric]' param-domain-type='list' role='measure' type='nominal' value='&quot;Revenue&quot;'>
        <calculation class='tableau' formula='&quot;Revenue&quot;' />
        <members><member value='&quot;Revenue&quot;' /><member value='&quot;Profit&quot;' /><member value='&quot;Profit Margin&quot;' /><member value='&quot;Orders&quot;' /></members>
      </column>
      <column caption='Top N' datatype='integer' name='[Top N]' param-domain-type='range' role='measure' type='quantitative' value='8'>
        <calculation class='tableau' formula='8' />
        <range granularity='1' max='17' min='3' />
      </column>
    </datasource>"""

# ---- calculated fields: id -> (caption, formula, datatype, role, type, default-format) ----------------------
C = {}


def calc(n, caption, formula, datatype="real", role="measure", typ="quantitative", fmt=None):
    name = f"Calculation_77000000000000{n:02d}"
    C[name] = (caption, formula, datatype, role, typ, fmt)
    return f"[{name}]"


def dim(n, caption, formula, datatype="string"):
    return calc(n, caption, formula, datatype, "dimension", "nominal")


def text(n, caption, formula):
    return calc(n, caption, formula, "string", "measure", "nominal")


Y = f"INT({YEAR})"  # the Year parameter is text so it displays without a thousands separator
CY, PY = f"YEAR([order_date]) = {Y}", f"YEAR([order_date]) = {Y} - 1"
USD, PCT, INT_ = 'c"$"#,##0', "p0.0%", "n#,##0"


def year_sum(n, caption, expr, cond=CY, fmt=USD):
    return calc(n, caption, f"SUM(IF {cond} THEN {expr} END)", fmt=fmt)


DISC_BAND = "[Calculation_4972470664826900]"      # existing 'Discount Band'
PROFITABILITY = "[Calculation_4972470665723932]"  # existing 'Profitability' (aggregate, so it follows the year filter)

MARGIN = calc(1, "Profit Margin", "SUM([profit]) / SUM([sales])", fmt=PCT)
IN_YEAR = dim(2, "In Selected Year", CY, "boolean")
PERIOD = dim(3, "Period", f"IF {CY} THEN 'Selected year' ELSEIF {PY} THEN 'Prior year' END")
REV_CY = year_sum(4, "Revenue (selected year)", "[sales]")
REV_PY = year_sum(5, "Revenue (prior year)", "[sales]", PY)
PRO_CY = year_sum(6, "Profit (selected year)", "[profit]")
PRO_PY = year_sum(7, "Profit (prior year)", "[profit]", PY)
ORD_CY = calc(8, "Orders (selected year)", f"COUNTD(IF {CY} THEN [order_id] END)", "integer", fmt=INT_)
ORD_PY = calc(9, "Orders (prior year)", f"COUNTD(IF {PY} THEN [order_id] END)", "integer", fmt=INT_)
MAR_CY = calc(10, "Margin (selected year)", f"{PRO_CY} / {REV_CY}", fmt=PCT)
MAR_PY = calc(11, "Margin (prior year)", f"{PRO_PY} / {REV_PY}", fmt=PCT)


def delta(n, caption, cy, py, pct=True, good_up=True):
    """Three text fields so a card can colour the change: favourable (green), unfavourable (red), no prior year."""
    change = f"({cy} - {py}) / ABS({py}) * 100" if pct else f"({cy} - {py}) * 100"
    unit = "%" if pct else " pp"
    body = (f"(IF {change} >= 0 THEN '▲ +' ELSE '▼ ' END) + STR(ROUND({change}, 1)) + '{unit} vs ' + STR({Y} - 1)")
    good = f"{change} >= 0" if good_up else f"{change} < 0"
    return (text(n, f"{caption} (favourable)", f"IF NOT ISNULL({py}) AND {good} THEN {body} ELSE '' END"),
            text(n + 1, f"{caption} (unfavourable)", f"IF NOT ISNULL({py}) AND NOT ({good}) THEN {body} ELSE '' END"),
            text(n + 2, f"{caption} (no prior year)", f"IF ISNULL({py}) THEN 'no prior-year data' ELSE '' END"))


METRIC_V = calc(16, "Selected Metric", "CASE [Parameters].[Metric] WHEN 'Revenue' THEN SUM([sales]) "
                "WHEN 'Profit' THEN SUM([profit]) WHEN 'Profit Margin' THEN SUM([profit]) / SUM([sales]) * 100 "
                "WHEN 'Orders' THEN COUNTD([order_id]) END", fmt=INT_)
METRIC_CY = calc(17, "Selected Metric (selected year)",
                 f"CASE {METRIC} WHEN 'Revenue' THEN {REV_CY} WHEN 'Profit' THEN {PRO_CY} "
                 f"WHEN 'Profit Margin' THEN {MAR_CY} * 100 WHEN 'Orders' THEN {ORD_CY} END", fmt=INT_)


def metric_label(n, caption, value):
    return text(n, caption, f"CASE {METRIC} WHEN 'Revenue' THEN '$' + STR(ROUND({value} / 1000, 1)) + 'K' "
                            f"WHEN 'Profit' THEN '$' + STR(ROUND({value} / 1000, 1)) + 'K' "
                            f"WHEN 'Profit Margin' THEN STR(ROUND({value}, 1)) + '%' ELSE STR({value}) END")


METRIC_LBL = metric_label(18, "Selected Metric label", METRIC_V)
METRIC_CY_LBL = metric_label(19, "Selected Metric label (selected year)", METRIC_CY)
DEEP_REV = year_sum(20, "Revenue at >20% discount", "[sales]", f"{CY} AND [discount] > 0.2")
DEEP_PRO = year_sum(21, "Profit at >20% discount", "[profit]", f"{CY} AND [discount] > 0.2")
SUBCAT_PROFIT = calc(22, "Sub-Category Profit (selected year)",
                     f"{{FIXED [sub_category] : SUM(IF {CY} THEN [profit] END)}}", fmt=USD)
LOSS_SUBCATS = calc(23, "Loss-making Sub-Categories", f"COUNTD(IF {SUBCAT_PROFIT} < 0 THEN [sub_category] END)", "integer")
ALL_SUBCATS = calc(24, "Sub-Categories", "COUNTD([sub_category])", "integer")
PROFITABLE_CY = text(28, "Profitability (selected year)", f"IF {PRO_CY} < 0 THEN 'Unprofitable' ELSE 'Profitable' END")

# executive insights
INSIGHT_1 = text(25, "Insight: growth vs margin",
                 f"'Revenue ' + (IF {REV_CY} >= {REV_PY} THEN 'grew ' ELSE 'fell ' END) "
                 f"+ STR(ROUND(ABS({REV_CY} - {REV_PY}) / {REV_PY} * 100, 1)) + '% vs ' + STR({Y} - 1) "
                 f"+ ', while profit margin ' + (IF {MAR_CY} >= {MAR_PY} THEN 'rose ' ELSE 'slipped ' END) "
                 f"+ STR(ROUND(ABS({MAR_CY} - {MAR_PY}) * 100, 1)) + ' pp to ' + STR(ROUND({MAR_CY} * 100, 1)) + '%.'")
INSIGHT_2 = text(26, "Insight: deep discounts",
                 f"'Lines discounted above 20% were ' + STR(ROUND({DEEP_REV} / {REV_CY} * 100, 1)) "
                 f"+ '% of revenue and ' + (IF {DEEP_PRO} < 0 THEN 'lost $' ELSE 'earned $' END) "
                 f"+ STR(ROUND(ABS({DEEP_PRO}) / 1000, 1)) + 'K.'")
INSIGHT_3 = text(27, "Insight: loss-making sub-categories",
                 f"STR({LOSS_SUBCATS}) + ' of ' + STR({ALL_SUBCATS}) + ' sub-categories lost money in ' + STR({Y}) + '.'")
REV_D, PRO_D, MAR_D, ORD_D = (delta(30, "Revenue change", REV_CY, REV_PY), delta(33, "Profit change", PRO_CY, PRO_PY),
                              delta(36, "Margin change", MAR_CY, MAR_PY, pct=False),
                              delta(39, "Orders change", ORD_CY, ORD_PY))

# ---- profitability & revenue leakage ----------------------------------------------------------------------
DISC_CY = year_sum(42, "Discount given (selected year)", "[discount_amount]")
DISC_PY = year_sum(43, "Discount given (prior year)", "[discount_amount]", PY)
GROSS_CY = year_sum(44, "List-price sales (selected year)", "[gross_sales]")
GROSS_PY = year_sum(45, "List-price sales (prior year)", "[gross_sales]", PY)
DRATE_CY = calc(46, "Discount rate (selected year)", f"{DISC_CY} / {GROSS_CY}", fmt=PCT)
DRATE_PY = calc(47, "Discount rate (prior year)", f"{DISC_PY} / {GROSS_PY}", fmt=PCT)
LOSS_CY = calc(48, "Profit lost on loss-making lines (selected year)", f"-SUM(IF {CY} AND [profit] < 0 THEN [profit] END)", fmt=USD)
LOSS_PY = calc(49, "Profit lost on loss-making lines (prior year)", f"-SUM(IF {PY} AND [profit] < 0 THEN [profit] END)", fmt=USD)
DEEP_REV_PY = year_sum(50, "Revenue at >20% discount (prior year)", "[sales]", f"{PY} AND [discount] > 0.2")
DSHARE_CY = calc(51, "Revenue share at >20% discount (selected year)", f"{DEEP_REV} / {REV_CY}", fmt=PCT)
DSHARE_PY = calc(52, "Revenue share at >20% discount (prior year)", f"{DEEP_REV_PY} / {REV_PY}", fmt=PCT)
DRATE = calc(53, "Discount Rate", "SUM([discount_amount]) / SUM([gross_sales])", fmt="p0%")
LOSS_AMT = calc(54, "Profit lost on loss-making lines", "-SUM(IF [profit] < 0 THEN [profit] END)", fmt=USD)
DSHARE = calc(55, "Revenue share at >20% discount", "SUM(IF [discount] > 0.2 THEN [sales] END) / SUM([sales])", fmt=PCT)
MAR_CHG = calc(56, "Margin change (pp)", f"({MAR_CY} - {MAR_PY}) * 100", fmt='n+0.0" pp";-0.0" pp"')
MAR_DIR = text(57, "Margin direction", f"IF {MAR_CHG} < 0 THEN 'Margin fell' ELSE 'Margin rose' END")
MIN_SUBCAT = calc(58, "Lowest sub-category profit", f"{{FIXED : MIN({SUBCAT_PROFIT})}}", fmt=USD)
WORST_SUBCAT = text(59, "Biggest loss-making sub-category", f"MIN(IF {SUBCAT_PROFIT} = {MIN_SUBCAT} THEN [sub_category] END)")
L_INS_1 = text(60, "Insight: discount spend",
               f"'Discounts gave away $' + STR(ROUND({DISC_CY} / 1000, 1)) + 'K in ' + STR({Y}) + ', ' "
               f"+ STR(ROUND({DRATE_CY} * 100, 1)) + '% of list price (' "
               f"+ (IF {DRATE_CY} >= {DRATE_PY} THEN '+' ELSE '' END) + STR(ROUND(({DRATE_CY} - {DRATE_PY}) * 100, 1)) "
               f"+ ' pp vs ' + STR({Y} - 1) + ').'")
L_INS_2 = text(61, "Insight: loss-making lines",
               f"'Loss-making lines cost $' + STR(ROUND({LOSS_CY} / 1000, 1)) + 'K of profit; ' + {WORST_SUBCAT} "
               f"+ (IF MIN({MIN_SUBCAT}) < 0 THEN ' lost the most ($' + STR(ROUND(-MIN({MIN_SUBCAT}) / 1000, 1)) + 'K).' "
               f"ELSE ' was the weakest sub-category but still profitable.' END)")
L_INS_3 = text(62, "Insight: deep-discount margin",
               f"'Lines discounted above 20% ran a ' + STR(ROUND({DEEP_PRO} / {DEEP_REV} * 100, 1)) "
               f"+ '% margin, vs ' + STR(ROUND(({PRO_CY} - {DEEP_PRO}) / ({REV_CY} - {DEEP_REV}) * 100, 1)) "
               f"+ '% on all other lines.'")
MARGIN_D, DRATE_D, LOSS_D, DSHARE_D = (delta(63, "Margin change", MAR_CY, MAR_PY, pct=False),
                                       delta(66, "Discount rate change", DRATE_CY, DRATE_PY, pct=False, good_up=False),
                                       delta(69, "Loss-line change", LOSS_CY, LOSS_PY, good_up=False),
                                       delta(72, "Deep-discount share change", DSHARE_CY, DSHARE_PY, pct=False, good_up=False))

# ---- customer & product intelligence ----------------------------------------------------------------------
FIRST_YEAR = calc(75, "First Purchase Year", "{FIXED [customer_id] : MIN(YEAR([order_date]))}", "integer", "dimension", "ordinal")
COHORT = dim(76, "Cohort (first purchase year)", f"STR({FIRST_YEAR})")
YEARS_SINCE = dim(77, "Years since first purchase", f"STR(YEAR([order_date]) - {FIRST_YEAR})")
COHORT_SIZE = calc(78, "Cohort size", f"{{FIXED {COHORT} : COUNTD([customer_id])}}", "integer")
RETENTION = calc(79, "Share of cohort active", f"COUNTD([customer_id]) / MIN({COHORT_SIZE})", fmt="p0%")
CUST_TYPE = dim(80, "Customer type", f"IF {FIRST_YEAR} < YEAR([order_date]) THEN 'Returning' ELSE 'New' END")
CUST_CY = calc(81, "Customers (selected year)", f"COUNTD(IF {CY} THEN [customer_id] END)", "integer", fmt=INT_)
CUST_PY = calc(82, "Customers (prior year)", f"COUNTD(IF {PY} THEN [customer_id] END)", "integer", fmt=INT_)
RET_CY = calc(83, "Returning customers (selected year)",
              f"COUNTD(IF {CY} AND {FIRST_YEAR} < {Y} THEN [customer_id] END) / {CUST_CY}", fmt=PCT)
RET_PY = calc(84, "Returning customers (prior year)",
              f"COUNTD(IF {PY} AND {FIRST_YEAR} < {Y} - 1 THEN [customer_id] END) / {CUST_PY}", fmt=PCT)
RPC_CY = calc(85, "Revenue per customer (selected year)", f"{REV_CY} / {CUST_CY}", fmt=USD)
RPC_PY = calc(86, "Revenue per customer (prior year)", f"{REV_PY} / {CUST_PY}", fmt=USD)
AOV_CY = calc(87, "Average order value (selected year)", f"{REV_CY} / {ORD_CY}", fmt=USD)
AOV_PY = calc(88, "Average order value (prior year)", f"{REV_PY} / {ORD_PY}", fmt=USD)
RET_M = calc(89, "Returning-customer share",
             f"COUNTD(IF {FIRST_YEAR} < YEAR([order_date]) THEN [customer_id] END) / COUNTD([customer_id])", fmt=PCT)
RPC_M = calc(90, "Revenue per customer", "SUM([sales]) / COUNTD([customer_id])", fmt=USD)
AOV_M = calc(91, "Average order value", "SUM([sales]) / COUNTD([order_id])", fmt=USD)
RET_REV = calc(92, "Revenue from returning customers (selected year)",
               f"SUM(IF {CY} AND {FIRST_YEAR} < {Y} THEN [sales] END) / {REV_CY}", fmt=PCT)
SEG_MAR = calc(93, "Segment margin (selected year)",
               f"{{FIXED [segment] : SUM(IF {CY} THEN [profit] END) / SUM(IF {CY} THEN [sales] END)}}", fmt=PCT)
SEG_MAX = calc(94, "Highest segment margin", f"{{FIXED : MAX({SEG_MAR})}}", fmt=PCT)
SEG_MIN = calc(95, "Lowest segment margin", f"{{FIXED : MIN({SEG_MAR})}}", fmt=PCT)
C_INS_1 = text(96, "Insight: customers",
               f"STR({CUST_CY}) + ' customers bought in ' + STR({Y}) + '; ' + STR(ROUND({RET_CY} * 100, 1)) "
               f"+ '% were returning customers and generated ' + STR(ROUND({RET_REV} * 100, 1)) + '% of revenue.'")
C_INS_2 = text(97, "Insight: order value",
               f"'Average order value was $' + STR(ROUND({AOV_CY}, 0)) + ', ' "
               f"+ (IF {AOV_CY} >= {AOV_PY} THEN 'up ' ELSE 'down ' END) "
               f"+ STR(ROUND(ABS({AOV_CY} - {AOV_PY}) / {AOV_PY} * 100, 1)) + '% vs ' + STR({Y} - 1) + '.'")
C_INS_3 = text(98, "Insight: segment margins",
               f"MIN(IF {SEG_MAR} = {SEG_MAX} THEN [segment] END) + ' had the highest margin (' "
               f"+ STR(ROUND(MIN({SEG_MAX}) * 100, 1)) + '%), ' + MIN(IF {SEG_MAR} = {SEG_MIN} THEN [segment] END) "
               f"+ ' the lowest (' + STR(ROUND(MIN({SEG_MIN}) * 100, 1)) + '%).'")
CUST_D, RET_D, RPC_D, AOV_D = (delta(99, "Customer change", CUST_CY, CUST_PY),
                               delta(102, "Returning share change", RET_CY, RET_PY, pct=False),
                               delta(105, "Revenue per customer change", RPC_CY, RPC_PY),
                               delta(108, "Order value change", AOV_CY, AOV_PY))

# first-draft fields and sheets this build replaces
DEAD = ["Profit Margin %", "Latest Year", "Revenue CY", "Revenue PY", "Profit CY", "Profit PY", "Orders CY",
        "Orders PY", "Revenue (latest year)", "Profit (latest year)", "Orders (latest year)", "KPI Revenue",
        "KPI Revenue YoY", "KPI Profit", "KPI Profit YoY", "KPI Margin", "KPI Margin YoY", "KPI Orders", "KPI Orders YoY"]
UNNAMED = ["Calculation_4972470661894149", "Calculation_4972470662049802", "Calculation_4972470662107147"]
OLD_SHEETS = ["Key Metrics 2026", "Revenue Trend", "Margin by Sub-Category", "Discount vs Margin", "Profit by State"]


# ---- helpers ----------------------------------------------------------------------------------------------
def q(x):
    return quoteattr(x)


def calc_column(name, spec):
    caption, formula, datatype, role, typ, fmt = spec
    f = f" default-format={q(fmt)}" if fmt else ""
    return (f"<column caption={q(caption)} datatype='{datatype}'{f} name='[{name}]' role='{role}' type='{typ}'>"
            f"<calculation class='tableau' formula={q(formula)} /></column>")


def ref(inst):
    return f"[{DS}].[{inst}]"


def uid():
    return "{" + str(uuid.uuid4()).upper() + "}"


def run(text_, size=10, color=INK, bold=False, font="Tableau Book"):
    b = " bold='true'" if bold else ""
    return f"<run{b} fontcolor='{color}' fontname='{font}' fontsize='{size}'>{text_}</run>"


def field_run(inst_, size=10, color=INK, bold=False, font="Tableau Book"):
    b = " bold='true'" if bold else ""
    return f"<run{b} fontcolor='{color}' fontname='{font}' fontsize='{size}'><![CDATA[<{ref(inst_)}>]]></run>"


def param_run(name, size=10, color=INK, bold=False):
    b = " bold='true'" if bold else ""
    return f"<run{b} fontcolor='{color}' fontsize='{size}'><![CDATA[<[Parameters].[{name}]>]]></run>"


NL = "<run>Æ&#10;</run>"
PARAM_DEPS = "<datasource-dependencies datasource='Parameters'>" + "".join(
    re.findall(r"<column caption=.*?</column>", PARAMS, re.S)) + "</datasource-dependencies>"


def title(*parts, size=12):
    """parts: plain strings, or ('p', name) for a parameter value."""
    return [param_run(p[1], size, INK, True) if isinstance(p, tuple) else run(p, size, INK, True) for p in parts]


def worksheet(name, title_runs, deps, instances, rows="", cols="", mark="Automatic", encodings="",
              tooltip="", label="", filters=(), styles="", pane_style="", sort=None):
    region_filter = (f"<filter class='categorical' column='{ref('none:region:nk')}' context='true' filter-group='2'>"
                     "<groupfilter function='level-members' level='[none:region:nk]' user:ui-enumeration='all' "
                     "user:ui-marker='enumerate' /></filter>")
    slices = [ref("none:region:nk")] + [f for f, _ in filters]
    fxml = region_filter + "".join(x for _, x in filters)
    sort_xml = ""
    if sort:
        dim_, measure, direction, shelf = sort
        sort_xml = (f"<shelf-sorts><shelf-sort-v2 dimension-to-sort='{ref(dim_)}' direction='{direction}' "
                    f"is-on-innermost-dimension='true' measure-to-sort-by='{ref(measure)}' shelf='{shelf}' /></shelf-sorts>")
    ttl = f"<layout-options><title><formatted-text>{''.join(title_runs)}</formatted-text></title></layout-options>"
    tip = f"<customized-tooltip><formatted-text>{tooltip}</formatted-text></customized-tooltip>" if tooltip else ""
    lab = f"<customized-label><formatted-text>{label}</formatted-text></customized-label>" if label else ""
    enc = f"<encodings>{encodings}</encodings>" if encodings else ""
    pstyle = f"<style><style-rule element='mark'>{pane_style}</style-rule></style>" if pane_style else ""
    return (f"<worksheet name={q(name)}>{ttl}<table><view><datasources>"
            f"<datasource caption='retailpulse_sales' name='{DS}' /><datasource name='Parameters' /></datasources>"
            f"{PARAM_DEPS}<datasource-dependencies datasource='{DS}'>{''.join(deps)}{''.join(instances)}"
            f"</datasource-dependencies>{fxml}{sort_xml}<slices>{''.join(f'<column>{x}</column>' for x in slices)}</slices>"
            f"<aggregation value='true' /></view><style>{styles}</style><panes>"
            f"<pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view>"
            f"<mark class='{mark}' />{enc}{tip}{lab}{pstyle}</pane></panes>"
            f"<rows>{rows}</rows><cols>{cols}</cols></table><simple-id uuid='{uid()}' /></worksheet>")


BASE = {c: f"<column caption={q(cap)} datatype='{dt}' name='[{c}]' role='{role}' type='{typ}' />" for c, cap, dt, role, typ in [
    ("order_date", "Order Date", "date", "dimension", "ordinal"),
    ("order_id", "Order Id", "string", "dimension", "nominal"),
    ("customer_id", "Customer Id", "string", "dimension", "nominal"),
    ("product_name", "Product Name", "string", "dimension", "nominal"),
    ("sales", "Sales", "real", "measure", "quantitative"),
    ("profit", "Profit", "real", "measure", "quantitative"),
    ("discount", "Discount", "real", "measure", "quantitative"),
    ("discount_amount", "Discount Amount", "real", "measure", "quantitative"),
    ("gross_sales", "Gross Sales", "real", "measure", "quantitative"),
    ("region", "Region", "string", "dimension", "nominal"),
    ("segment", "Segment", "string", "dimension", "nominal"),
    ("state", "State", "string", "dimension", "nominal"),
    ("sub_category", "Sub Category", "string", "dimension", "nominal")]}
BASE["sales"] = BASE["sales"].replace("datatype='real'", "datatype='real' default-format='c&quot;$&quot;#,##0'")
BASE["profit"] = BASE["profit"].replace("datatype='real'", "datatype='real' default-format='c&quot;$&quot;#,##0'")


def deps_for(*fields):
    """Column XML for the given fields plus everything their formulas reference, transitively."""
    out, seen, todo = [], set(), [f.strip("[]") for f in fields] + ["region"]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        if f in BASE:
            out.append(BASE[f])
        elif f in C:
            out.append(calc_column(f, C[f]))
            todo += [x for x in re.findall(r"\[([A-Za-z_0-9]+)\]", C[f][1]) if x in C or x in BASE]
        elif f in EXISTING:
            out.append(EXISTING[f])
            todo += [x for x in re.findall(r"\[([a-z_]+)\]", EXISTING[f]) if x in BASE]
    return out


def inst(col, deriv, kind):
    pre = {"None": "none", "Sum": "sum", "User": "usr", "CountD": "ctd", "Month-Trunc": "tmn", "Month": "mn"}[deriv]
    typ = {"nk": "nominal", "ok": "ordinal", "qk": "quantitative"}[kind]
    c = col.strip("[]")
    return (f"{pre}:{c}:{kind}",
            f"<column-instance column='[{c}]' derivation='{deriv}' name='[{pre}:{c}:{kind}]' pivot='key' type='{typ}' />")


def bool_filter(col):
    name, xml = inst(col, "None", "nk")
    return ref(name), (f"<filter class='categorical' column='{ref(name)}'><groupfilter function='member' "
                       f"level='[{name}]' member='true' user:ui-domain='database' user:ui-enumeration='inclusive' "
                       f"user:ui-marker='enumerate' /></filter>"), xml


def top_filter(dim_name, expr, direction="DESC"):
    """Native Top N: N comes from the Top N parameter; ASC ranks from the bottom."""
    return (ref(dim_name), f"<filter class='categorical' column='{ref(dim_name)}'>"
            f"<groupfilter count='{TOPN}' end='top' function='end' units='records' user:ui-marker='end' user:ui-top-by-field='true'>"
            f"<groupfilter direction='{direction}' expression='{expr}' function='order' user:ui-marker='order'>"
            f"<groupfilter function='level-members' level='[{dim_name}]' user:ui-enumeration='all' user:ui-marker='enumerate' />"
            f"</groupfilter></groupfilter></filter>")


def hide_axes(*fields_scopes):
    return "<style-rule element='axis'>" + "".join(
        f"<format attr='display' class='0' field='{ref(f)}' scope='{sc}' value='false' />" for f, sc in fields_scopes
    ) + "</style-rule>"


def axis_titles(*fields_scopes):
    return "<style-rule element='axis'>" + "".join(
        f"<format attr='title' class='0' field='{ref(f)}' scope='{sc}' value={q(t)} />" for f, sc, t in fields_scopes
    ) + "</style-rule>"


NO_GRID = ("<style-rule element='gridline'><format attr='line-visibility' scope='rows' value='off' />"
           "<format attr='line-visibility' scope='cols' value='off' /></style-rule>"
           "<style-rule element='zeroline'><format attr='line-visibility' scope='rows' value='off' />"
           "<format attr='line-visibility' scope='cols' value='off' /></style-rule>")
ROW_GRID_ONLY = "<style-rule element='gridline'><format attr='line-visibility' scope='cols' value='off' /></style-rule>"
NO_FIELD_LABELS = ("<style-rule element='worksheet'><format attr='display-field-labels' scope='rows' value='false' />"
                   "<format attr='display-field-labels' scope='cols' value='false' /></style-rule>")
REGION_INST = inst("[region]", "None", "nk")[1]
MONTH_NAME, MONTH_XML = inst("[order_date]", "Month", "ok")
SHORT_MONTHS = f"<style-rule element='header'><format attr='text-format' field='{ref(MONTH_NAME)}' value='iLLL' /></style-rule>"
IN_YEAR_FILTER, IN_YEAR_XML = bool_filter(IN_YEAR)[0], bool_filter(IN_YEAR)[2]

sheets = {}


# ---- reusable sheet builders ------------------------------------------------------------------------------
def kpi_card(name, label, value, change):
    good, bad, none = change
    v_name, v_xml = inst(value, "User", "qk")
    parts = [inst(c, "User", "nk") for c in (good, bad, none)]
    lab = (run(label.upper(), 9, MUTED, font="Tableau Semibold") + NL + field_run(v_name, 17, NAVY, True, "Tableau Bold")
           + NL + field_run(parts[0][0], 9, GREEN, True) + field_run(parts[1][0], 9, RED, True)
           + field_run(parts[2][0], 9, MUTED))
    tip = (run(f"{label} in ", 9, MUTED) + param_run("Selected Year", 9, MUTED) + NL + field_run(v_name, 11, INK, True)
           + NL + field_run(parts[0][0], 9, GREEN) + field_run(parts[1][0], 9, RED) + field_run(parts[2][0], 9, MUTED))
    sheets[name] = worksheet(
        name, [run(label, 10)], deps_for(value, good, bad, none), [REGION_INST, v_xml] + [x for _, x in parts],
        mark="Text", encodings=f"<text column='{ref(v_name)}' />" + "".join(f"<text column='{ref(n)}' />" for n, _ in parts),
        label=lab, tooltip=tip,
        styles="<style-rule element='cell'><format attr='text-align' value='center' /></style-rule>"
               "<style-rule element='mark'><format attr='mark-labels-show' value='true' /></style-rule>")


def sparkline(name, measure, deriv="User"):
    m_inst, m_xml = inst(measure, deriv, "qk")
    t_name, t_xml = inst("[order_date]", "Month-Trunc", "qk")
    sheets[name] = worksheet(
        name, [run(name, 9)], deps_for(measure, IN_YEAR, "order_date"), [REGION_INST, IN_YEAR_XML, t_xml, m_xml],
        rows=ref(m_inst), cols=ref(t_name), mark="Area", filters=[(IN_YEAR_FILTER, bool_filter(IN_YEAR)[1])],
        tooltip=field_run(t_name, 9, MUTED) + NL + field_run(m_inst, 10, INK, True),
        styles=hide_axes((m_inst, "rows"), (t_name, "cols")) + NO_GRID,
        pane_style=f"<format attr='mark-color' value='{BLUE}' /><format attr='mark-transparency' value='70' />")


def ranked_bars(name, title_runs, dim_col, value, label, color, extra_tip=(), top=None, direction="DESC",
                year_filter=False, label_on_bar=False):
    d_name, d_xml = inst(dim_col, "None", "nk")
    v_name, v_xml = inst(value, "User", "qk")
    l_name, l_xml = inst(label, "User", "nk")
    c_name, c_xml = inst(color, "User", "nk")
    extra = [inst(e, "User", "qk") for e in extra_tip]
    filters = [top_filter(d_name, value.strip("[]").join("[]"), direction)] if top else []
    instances = [REGION_INST, d_xml, v_xml, l_xml, c_xml] + [x for _, x in extra]
    deps = [dim_col, value, label, color, *extra_tip]
    if year_filter:
        filters.append((IN_YEAR_FILTER, bool_filter(IN_YEAR)[1]))
        instances.append(IN_YEAR_XML)
        deps.append(IN_YEAR)
    tip = field_run(d_name, 11, INK, True) + NL + field_run(l_name, 10, INK, True) + NL + field_run(c_name, 9, MUTED)
    for (e_name, _), e in zip(extra, extra_tip):
        tip += NL + run(C[e.strip("[]")][0] + ": ", 9, MUTED) + field_run(e_name, 9, INK)
    rows = ref(d_name) if label_on_bar else f"({ref(d_name)} / {ref(l_name)})"
    enc = f"<color column='{ref(c_name)}' />" + "".join(f"<lod column='{ref(n)}' />" for n, _ in extra)
    enc += f"<text column='{ref(l_name)}' />" if label_on_bar else f"<lod column='{ref(l_name)}' />"
    sheets[name] = worksheet(
        name, title_runs, deps_for(*deps), instances, rows=rows, cols=ref(v_name), mark="Bar", encodings=enc,
        filters=filters, tooltip=tip,
        styles=NO_GRID + hide_axes((v_name, "cols")) + NO_FIELD_LABELS
               + f"<style-rule element='header'><format attr='font-size' field='{ref(d_name)}' value='9' /></style-rule>",
        pane_style="<format attr='size' value='0.6' />" + ("<format attr='mark-labels-show' value='true' />" if label_on_bar else ""),
        sort=(d_name, v_name, direction, "rows"))


def insights(name, heading, fields, footnote):
    names = [inst(c, "User", "nk") for c in fields]
    lab = (run(heading, 12, INK, True) + NL
           + "".join(NL + run("•  ", 10, BLUE, True) + field_run(n, 10, INK) + NL for n, _ in names)
           + NL + run(footnote, 8, MUTED))
    sheets[name] = worksheet(
        name, [run(heading, 10)], deps_for(*fields), [REGION_INST] + [x for _, x in names], mark="Text",
        encodings="".join(f"<text column='{ref(n)}' />" for n, _ in names), label=lab,
        styles="<style-rule element='cell'><format attr='text-align' value='left' />"
               "<format attr='vertical-align' value='top' /></style-rule>"
               "<style-rule element='mark'><format attr='mark-labels-show' value='true' /></style-rule>")


# ---- 1. Executive Overview sheets -------------------------------------------------------------------------
kpi_card("KPI Revenue", "Revenue", REV_CY, REV_D)
kpi_card("KPI Profit", "Profit", PRO_CY, PRO_D)
kpi_card("KPI Margin", "Profit margin", MAR_CY, MAR_D)
kpi_card("KPI Orders", "Orders", ORD_CY, ORD_D)
sparkline("Spark Revenue", "[sales]", "Sum")
sparkline("Spark Profit", "[profit]", "Sum")
sparkline("Spark Margin", MARGIN)
sparkline("Spark Orders", "[order_id]", "CountD")

p_name, p_xml = inst(PERIOD, "None", "nk")
mv_name, mv_xml = inst(METRIC_V, "User", "qk")
ml_name, ml_xml = inst(METRIC_LBL, "User", "nk")
period_not_null = (ref(p_name), f"<filter class='categorical' column='{ref(p_name)}'><groupfilter function='union' user:op='manual'>"
                   f"<groupfilter function='member' level='[{p_name}]' member='&quot;Selected year&quot;' />"
                   f"<groupfilter function='member' level='[{p_name}]' member='&quot;Prior year&quot;' /></groupfilter></filter>")
sheets["Trend vs Prior Year"] = worksheet(
    "Trend vs Prior Year", title(("p", "Metric"), " by month: ", ("p", "Selected Year"), " vs prior year"),
    deps_for(PERIOD, METRIC_V, METRIC_LBL, "order_date"), [REGION_INST, p_xml, MONTH_XML, mv_xml, ml_xml],
    rows=ref(mv_name), cols=ref(MONTH_NAME), mark="Line",
    encodings=f"<color column='{ref(p_name)}' /><lod column='{ref(ml_name)}' />", filters=[period_not_null],
    tooltip=field_run(p_name, 9, MUTED) + run(" ", 9, MUTED) + field_run(MONTH_NAME, 9, MUTED) + NL
            + param_run("Metric", 9, MUTED) + run(": ", 9, MUTED) + field_run(ml_name, 11, INK, True),
    styles=ROW_GRID_ONLY + NO_FIELD_LABELS + SHORT_MONTHS
           + axis_titles((mv_name, "rows", ""), (MONTH_NAME, "cols", "")),
    pane_style="<format attr='size' value='1.5' />")
ranked_bars("Top N Sub-Categories",
            title("Top ", ("p", "Top N"), " sub-categories by ", ("p", "Metric"), ", ", ("p", "Selected Year")),
            "[sub_category]", METRIC_CY, METRIC_CY_LBL, PROFITABLE_CY, extra_tip=[PRO_CY], top=True)

sg_name, sg_xml = inst("[segment]", "None", "nk")
mg_name, mg_xml = inst(MARGIN, "User", "qk")
s_name, s_xml = inst("[sales]", "Sum", "qk")
sheets["Margin Heatmap"] = worksheet(
    "Margin Heatmap", title("Profit margin by region and segment, ", ("p", "Selected Year")),
    deps_for(MARGIN, IN_YEAR, "segment", "sales"), [REGION_INST, sg_xml, mg_xml, s_xml, IN_YEAR_XML],
    rows=ref("none:region:nk"), cols=ref(sg_name), mark="Square",
    encodings=f"<color column='{ref(mg_name)}' /><text column='{ref(mg_name)}' /><lod column='{ref(s_name)}' />",
    filters=[(IN_YEAR_FILTER, bool_filter(IN_YEAR)[1])],
    tooltip=field_run("none:region:nk", 10, INK, True) + run(" · ", 10, INK) + field_run(sg_name, 10, INK, True) + NL
            + run("Margin: ", 9, MUTED) + field_run(mg_name, 10, INK, True) + NL + run("Revenue: ", 9, MUTED)
            + field_run(s_name, 10, INK),
    styles=NO_FIELD_LABELS, pane_style="<format attr='mark-labels-show' value='true' />")
insights("Insights", "What the data says", [INSIGHT_1, INSIGHT_2, INSIGHT_3],
         "Associations in synthetic sample data, not proof of cause.")

# ---- 2. Profitability & Revenue Leakage sheets ------------------------------------------------------------
kpi_card("KPI Leak Margin", "Profit margin", MAR_CY, MARGIN_D)
kpi_card("KPI Discount Rate", "Discount rate", DRATE_CY, DRATE_D)
kpi_card("KPI Loss Lines", "Lost on loss-making lines", LOSS_CY, LOSS_D)
kpi_card("KPI Deep Discount", "Revenue at >20% discount", DSHARE_CY, DSHARE_D)
sparkline("Spark Leak Margin", MARGIN)
sparkline("Spark Discount Rate", DRATE)
sparkline("Spark Loss Lines", LOSS_AMT)
sparkline("Spark Deep Discount", DSHARE)

b_name, b_xml = inst(DISC_BAND, "None", "nk")
pf_name, pf_xml = inst(PROFITABILITY, "User", "nk")
sheets["Margin by Discount Band"] = worksheet(
    "Margin by Discount Band", title("Profit margin by discount band, ", ("p", "Selected Year")),
    deps_for(DISC_BAND, MARGIN, PROFITABILITY, IN_YEAR, "sales"),
    [REGION_INST, b_xml, mg_xml, pf_xml, s_xml, IN_YEAR_XML], rows=ref(mg_name), cols=ref(b_name), mark="Bar",
    encodings=f"<color column='{ref(pf_name)}' /><text column='{ref(mg_name)}' /><lod column='{ref(s_name)}' />",
    filters=[(IN_YEAR_FILTER, bool_filter(IN_YEAR)[1])],
    tooltip=run("Discount ", 9, MUTED) + field_run(b_name, 11, INK, True) + NL + run("Margin: ", 9, MUTED)
            + field_run(mg_name, 10, INK, True) + NL + run("Revenue: ", 9, MUTED) + field_run(s_name, 10, INK),
    styles=ROW_GRID_ONLY + NO_FIELD_LABELS + axis_titles((mg_name, "rows", "Profit margin")),
    pane_style="<format attr='mark-labels-show' value='true' /><format attr='size' value='0.7' />")

sc_name, sc_xml = inst("[sub_category]", "None", "nk")
dr_name, dr_xml = inst(DRATE, "User", "qk")
sheets["Discount vs Margin Scatter"] = worksheet(
    "Discount vs Margin Scatter", title("Discount depth vs margin by sub-category, ", ("p", "Selected Year")),
    deps_for(DRATE, MARGIN, PROFITABILITY, IN_YEAR, "sales", "sub_category"),
    [REGION_INST, sc_xml, dr_xml, mg_xml, pf_xml, s_xml, IN_YEAR_XML], rows=ref(mg_name), cols=ref(dr_name),
    mark="Circle",
    encodings=(f"<color column='{ref(pf_name)}' /><size column='{ref(s_name)}' /><text column='{ref(sc_name)}' />"),
    filters=[(IN_YEAR_FILTER, bool_filter(IN_YEAR)[1])],
    tooltip=field_run(sc_name, 11, INK, True) + NL + run("Discount rate: ", 9, MUTED) + field_run(dr_name, 10, INK, True)
            + NL + run("Margin: ", 9, MUTED) + field_run(mg_name, 10, INK, True) + NL + run("Revenue: ", 9, MUTED)
            + field_run(s_name, 10, INK),
    styles=axis_titles((mg_name, "rows", "Profit margin"), (dr_name, "cols", "Discount rate (share of list price)")),
    pane_style="<format attr='mark-labels-show' value='true' /><format attr='mark-transparency' value='200' />")

chg_name, chg_xml = inst(MAR_CHG, "User", "qk")
dir_name, dir_xml = inst(MAR_DIR, "User", "nk")
sheets["Margin Change by Sub-Category"] = worksheet(
    "Margin Change by Sub-Category", title("Margin change vs prior year by sub-category, ", ("p", "Selected Year")),
    deps_for(MAR_CHG, MAR_DIR, MAR_CY, MAR_PY, "sub_category"), [REGION_INST, sc_xml, chg_xml, dir_xml],
    rows=ref(sc_name), cols=ref(chg_name), mark="Bar",
    encodings=f"<color column='{ref(dir_name)}' /><text column='{ref(chg_name)}' />",
    tooltip=field_run(sc_name, 11, INK, True) + NL + run("Margin change: ", 9, MUTED) + field_run(chg_name, 10, INK, True),
    styles=NO_GRID + hide_axes((chg_name, "cols")) + NO_FIELD_LABELS
           + f"<style-rule element='header'><format attr='font-size' field='{ref(sc_name)}' value='9' /></style-rule>",
    pane_style="<format attr='mark-labels-show' value='true' /><format attr='size' value='0.6' />",
    sort=(sc_name, chg_name, "ASC", "rows"))

ST_LABEL = text(111, "Profit label", "'$' + STR(ROUND(SUM([profit]) / 1000, 1)) + 'K'")
ranked_bars("Bottom N States",
            title("Bottom ", ("p", "Top N"), " states by profit, ", ("p", "Selected Year")),
            "[state]", "[profit]", ST_LABEL, PROFITABILITY, top=True, direction="ASC", year_filter=True)
# profit is a plain SUM, not a calc, so the Top N expression and the bar column use the Sum instance
sheets["Bottom N States"] = (sheets["Bottom N States"]
                             .replace("expression='[profit]'", "expression='SUM([profit])'")
                             .replace("[usr:profit:qk]", "[sum:profit:qk]").replace("derivation='User' name='[sum:profit:qk]'",
                                                                                     "derivation='Sum' name='[sum:profit:qk]'"))
insights("Leakage Insights", "Where profit leaks", [L_INS_1, L_INS_2, L_INS_3],
         "Associations in synthetic sample data, not proof that discounts cause the losses.")

# ---- 3. Customer & Product Intelligence sheets ------------------------------------------------------------
kpi_card("KPI Customers", "Customers", CUST_CY, CUST_D)
kpi_card("KPI Returning", "Returning customers", RET_CY, RET_D)
kpi_card("KPI Revenue per Customer", "Revenue per customer", RPC_CY, RPC_D)
kpi_card("KPI Order Value", "Average order value", AOV_CY, AOV_D)
sparkline("Spark Customers", "[customer_id]", "CountD")
sparkline("Spark Returning", RET_M)
sparkline("Spark Revenue per Customer", RPC_M)
sparkline("Spark Order Value", AOV_M)

ranked_bars("Top N Products",
            title("Top ", ("p", "Top N"), " products by ", ("p", "Metric"), ", ", ("p", "Selected Year")),
            "[product_name]", METRIC_CY, METRIC_CY_LBL, PROFITABLE_CY, extra_tip=[PRO_CY], top=True)
ranked_bars("Segment Performance", title(("p", "Metric"), " by segment, ", ("p", "Selected Year")),
            "[segment]", METRIC_CY, METRIC_CY_LBL, PROFITABLE_CY, extra_tip=[PRO_CY, MAR_CY], label_on_bar=True)

ct_name, ct_xml = inst(CUST_TYPE, "None", "nk")
ss_name = "sum:sales:qk"
sheets["New vs Returning Revenue"] = worksheet(
    "New vs Returning Revenue", title("Revenue from new vs returning customers, ", ("p", "Selected Year")),
    deps_for(CUST_TYPE, IN_YEAR, "sales", "order_date"), [REGION_INST, ct_xml, MONTH_XML, s_xml, IN_YEAR_XML],
    rows=ref(ss_name), cols=ref(MONTH_NAME), mark="Bar", encodings=f"<color column='{ref(ct_name)}' />",
    filters=[(IN_YEAR_FILTER, bool_filter(IN_YEAR)[1])],
    tooltip=field_run(ct_name, 10, INK, True) + run(" customers, ", 10, INK) + field_run(MONTH_NAME, 10, INK) + NL
            + run("Revenue: ", 9, MUTED) + field_run(ss_name, 10, INK, True),
    styles=ROW_GRID_ONLY + NO_FIELD_LABELS + SHORT_MONTHS + axis_titles((ss_name, "rows", "Revenue")),
    pane_style="<format attr='size' value='0.7' />")

co_name, co_xml = inst(COHORT, "None", "nk")
ys_name, ys_xml = inst(YEARS_SINCE, "None", "nk")
rt_name, rt_xml = inst(RETENTION, "User", "qk")
cc_name, cc_xml = inst("[customer_id]", "CountD", "qk")
sheets["Cohort Retention"] = worksheet(
    "Cohort Retention", title("Share of each first-purchase cohort buying again, by years since first order", size=11),
    deps_for(COHORT, YEARS_SINCE, RETENTION, "customer_id"), [REGION_INST, co_xml, ys_xml, rt_xml, cc_xml],
    rows=ref(co_name), cols=ref(ys_name), mark="Square",
    encodings=f"<color column='{ref(rt_name)}' /><text column='{ref(rt_name)}' /><lod column='{ref(cc_name)}' />",
    tooltip=run("Cohort ", 9, MUTED) + field_run(co_name, 10, INK, True) + run(", year +", 9, MUTED)
            + field_run(ys_name, 10, INK, True) + NL + field_run(rt_name, 10, INK, True) + run(" of the cohort bought (", 9, MUTED)
            + field_run(cc_name, 9, INK) + run(" customers)", 9, MUTED),
    styles="<style-rule element='worksheet'><format attr='display-field-labels' scope='rows' value='true' />"
           "<format attr='display-field-labels' scope='cols' value='true' /></style-rule>",
    pane_style="<format attr='mark-labels-show' value='true' />")
insights("Customer Insights", "Who buys, and who comes back", [C_INS_1, C_INS_2, C_INS_3],
         "Customers are attributed by Customer ID; 'returning' means a first order in an earlier year.")

# ---- dashboards -------------------------------------------------------------------------------------------
DASHBOARDS = ["Executive Overview", "Profitability & Revenue Leakage", "Customer & Product Intelligence"]
NAV_LABELS = ["Executive", "Profitability", "Customers"]
WINDOW_ID = {d: uid() for d in DASHBOARDS}
_ids = iter(range(200, 10000))


def zstyle(border=True, margin=4):
    if border:
        return (f"<zone-style><format attr='border-color' value='{LINE}' /><format attr='border-style' value='solid' />"
                f"<format attr='border-width' value='1' /><format attr='margin' value='{margin}' />"
                "<format attr='padding' value='2' /><format attr='background-color' value='#ffffff' /></zone-style>")
    return f"<zone-style><format attr='margin' value='{margin}' /></zone-style>"


def z(x, y, w, h, attrs, border=False, show_title=True, margin=4):
    t = "" if show_title else " show-title='false'"
    return f"<zone h='{h}' id='{next(_ids)}' w='{w}' x='{x}' y='{y}' {attrs}{t}>{zstyle(border, margin)}</zone>"


def card(x, y, w, h, top_sheet, bottom, bottom_h, legend=False):
    """A bordered vertical container: a sheet plus either its sparkline or its colour legend."""
    top = z(x, y, w, h - bottom_h, f"name={q(top_sheet)}", show_title=not top_sheet.startswith("KPI"), margin=0)
    if legend:
        sheet, field = bottom
        bot = z(x, y + h - bottom_h, w, bottom_h,
                f"leg-item-layout='horz' name={q(sheet)} pane-specification-id='0' param={q(ref(field))} type-v2='color'",
                show_title=False, margin=0)
    else:
        bot = z(x, y + h - bottom_h, w, bottom_h, f"name={q(bottom)}", show_title=False, margin=0)
    return (f"<zone h='{h}' id='{next(_ids)}' param='vert' type-v2='layout-flow' w='{w}' x='{x}' y='{y}'>"
            f"{top}{bot}{zstyle(True)}</zone>")


def nav_buttons(current, x0, w_each):
    out = []
    for i, (dash, label) in enumerate(zip(DASHBOARDS, NAV_LABELS)):
        active = dash == current
        out.append(
            f"<zone h='8000' id='{next(_ids)}' type-v2='dashboard-object' w='{w_each}' x='{x0 + i * w_each}' y='0'>"
            f"<button action={q(f'tabdoc:goto-sheet window-id=&quot;{WINDOW_ID[dash]}&quot;'.replace('&quot;', chr(34)))} "
            "button-type='text'><button-visual-state>"
            f"<caption>{label}</caption>"
            f"<button-caption-font-style fontcolor='{'#ffffff' if active else NAVY}' fontname='Tableau Semibold' fontsize='10' />"
            f"<format attr='background-color' value='{NAVY if active else LINE}' />"
            f"</button-visual-state></button><zone-style><format attr='margin' value='14' /></zone-style></zone>")
    return "".join(out)


def header(dash, subtitle, controls, insight_sheet):
    """Title, navigation and controls: identical position and style on every dashboard."""
    head = (f"<zone h='8000' id='{next(_ids)}' type-v2='text' w='33000' x='0' y='0'><formatted-text>"
            + run("RetailPulse", 15, NAVY, True, "Tableau Bold") + run("  ·  " + dash, 13, INK)
            + NL + run(subtitle, 9, MUTED) + "</formatted-text><zone-style><format attr='margin' value='6' /></zone-style></zone>")
    nav = nav_buttons(dash, 33000, 8000)
    x, w = 57000, 43000 // len(controls)
    ctrl = []
    for c in controls:
        if c == "region":
            attrs = f"mode='checkdropdown' name={q(insight_sheet)} param={q(ref('none:region:nk'))} type-v2='filter'"
        else:
            attrs = f"mode='{'slider' if c == TOPN else 'compact'}' param={q(c)} type-v2='paramctrl'"
        ctrl.append(z(x, 0, w, 8000, attrs))
        x += w
    return head + nav + "".join(ctrl)


def dashboard(name, subtitle, controls, insight_sheet, kpis, body):
    kpi_xml = "".join(card(i * 25000, 8000, 25000, 16000, k, sp, 5000) for i, (k, sp) in enumerate(kpis))
    return (f"<dashboard enable-sort-zone-taborder='true' name={q(name)}>"
            f"<style><style-rule element='table'><format attr='background-color' value='{BG}' /></style-rule></style>"
            "<size maxheight='860' maxwidth='1400' minheight='860' minwidth='1400' sizing-mode='fixed' />"
            "<zones><zone h='100000' id='4' type-v2='layout-basic' w='100000' x='0' y='0'>"
            + header(name, subtitle, controls, insight_sheet) + kpi_xml + "".join(body)
            + f"</zone></zones><simple-id uuid='{uid()}' /></dashboard>")


def plain(x, y, w, h, sheet, show_title=True):
    return z(x, y, w, h, f"name={q(sheet)}", border=True, show_title=show_title)


PROF_CY_FIELD = inst(PROFITABLE_CY, "User", "nk")[0]
PROF_FIELD = inst(PROFITABILITY, "User", "nk")[0]
dash_xml = [
    dashboard("Executive Overview", "Sample Superstore (synthetic) · one view of growth and profitability",
              [YEAR, "region", METRIC, TOPN], "Insights",
              [("KPI Revenue", "Spark Revenue"), ("KPI Profit", "Spark Profit"), ("KPI Margin", "Spark Margin"),
               ("KPI Orders", "Spark Orders")],
              [card(0, 24000, 58000, 40000, "Trend vs Prior Year", ("Trend vs Prior Year", p_name), 3500, True),
               card(58000, 24000, 42000, 40000, "Top N Sub-Categories", ("Top N Sub-Categories", PROF_CY_FIELD), 3500, True),
               card(0, 64000, 42000, 36000, "Margin Heatmap", ("Margin Heatmap", mg_name), 4500, True),
               plain(42000, 64000, 58000, 36000, "Insights", show_title=False)]),
    dashboard("Profitability & Revenue Leakage", "Where discounts and loss-making lines erode margin",
              [YEAR, "region", TOPN], "Leakage Insights",
              [("KPI Leak Margin", "Spark Leak Margin"), ("KPI Discount Rate", "Spark Discount Rate"),
               ("KPI Loss Lines", "Spark Loss Lines"), ("KPI Deep Discount", "Spark Deep Discount")],
              [card(0, 24000, 38000, 40000, "Margin by Discount Band", ("Margin by Discount Band", PROF_FIELD), 3500, True),
               card(38000, 24000, 62000, 40000, "Discount vs Margin Scatter", ("Discount vs Margin Scatter", PROF_FIELD), 3500, True),
               card(0, 64000, 34000, 36000, "Margin Change by Sub-Category",
                    ("Margin Change by Sub-Category", dir_name), 3500, True),
               card(34000, 64000, 32000, 36000, "Bottom N States", ("Bottom N States", PROF_FIELD), 3500, True),
               plain(66000, 64000, 34000, 36000, "Leakage Insights", show_title=False)]),
    dashboard("Customer & Product Intelligence", "Who buys, what sells, and who comes back",
              [YEAR, "region", METRIC, TOPN], "Customer Insights",
              [("KPI Customers", "Spark Customers"), ("KPI Returning", "Spark Returning"),
               ("KPI Revenue per Customer", "Spark Revenue per Customer"), ("KPI Order Value", "Spark Order Value")],
              [card(0, 24000, 58000, 40000, "Top N Products", ("Top N Products", PROF_CY_FIELD), 3500, True),
               card(58000, 24000, 42000, 40000, "Segment Performance", ("Segment Performance", PROF_CY_FIELD), 3500, True),
               card(0, 64000, 36000, 36000, "New vs Returning Revenue", ("New vs Returning Revenue", ct_name), 3500, True),
               card(36000, 64000, 32000, 36000, "Cohort Retention", ("Cohort Retention", rt_name), 4500, True),
               plain(68000, 64000, 32000, 36000, "Customer Insights", show_title=False)]),
]

DASH_SHEETS = {d: sorted(set(re.findall(r"name='([^']+)'", x)) & set(sheets)) for d, x in zip(DASHBOARDS, dash_xml)}


def window(name, cls="worksheet"):
    if cls == "dashboard":
        vps = "".join(f"<viewpoint name={q(n)}><zoom type='entire-view' /></viewpoint>" for n in DASH_SHEETS[name])
        return (f"<window class='dashboard' name={q(name)}><viewpoints>{vps}</viewpoints><active id='-1' />"
                f"<simple-id uuid='{WINDOW_ID[name]}' /></window>")
    return (f"<window class='worksheet' hidden='true' name={q(name)}><cards><edge name='left'><strip size='160'>"
            "<card type='pages' /><card type='filters' /><card type='marks' /></strip></edge><edge name='top'>"
            "<strip size='2147483647'><card type='columns' /></strip><strip size='2147483647'><card type='rows' /></strip>"
            f"<strip size='31'><card type='title' /></strip></edge></cards><simple-id uuid='{uid()}' /></window>")


# ---- apply ------------------------------------------------------------------------------------------------
def cut(pattern):
    global s
    s, n = re.subn(pattern, "", s, flags=re.S)
    return n


for nm in OLD_SHEETS:
    cut(rf"\n?\s*<worksheet name={re.escape(q(nm))}>.*?</worksheet>")
    cut(rf"\n?\s*<window class='worksheet'[^>]*name={re.escape(q(nm))}>.*?</window>")
cut(r"\n?\s*<dashboard [^>]*name='RetailPulse Overview'>.*?</dashboard>")
cut(r"\n?\s*<window class='dashboard'[^>]*name='RetailPulse Overview'>.*?</window>")
cut(r"\n?\s*<thumbnails>.*?</thumbnails>")
cut(r"<actions>.*?</actions>\s*")
for cap in DEAD:
    cut(rf"\n?\s*<column caption='{re.escape(cap)}'[^>]*name='\[Calculation_\d+\]'[^>]*>\s*<calculation[^>]*/>\s*</column>")
for old in UNNAMED:
    cut(rf"\n?\s*<column caption='[^']*' datatype='[a-z]+' name='\[{old}\]'[^>]*>\s*<calculation[^>]*/>\s*</column>")
assert not any(u in s for u in UNNAMED), "a removed field is still referenced"

# calculated fields + the column-instances that colour maps bind to, before <drill-paths>
COLOURED = [(PERIOD, "None", "nk"), (PROFITABLE_CY, "User", "nk"), (PROFITABILITY, "User", "nk"),
            (MARGIN, "User", "qk"), (MAR_DIR, "User", "nk"), (CUST_TYPE, "None", "nk"), (RETENTION, "User", "qk")]
ds_start = s.index("<datasource caption='retailpulse_sales'")
dp = s.index("<drill-paths>", ds_start)
s = s[:dp] + "".join(calc_column(k, v) for k, v in C.items()) + "".join(inst(*c)[1] for c in COLOURED) + s[dp:]
s = s.replace("<datasources>", "<datasources>" + PARAMS, 1)
ds_start = s.index("<datasource caption='retailpulse_sales'")
lay_end = s.index("/>", s.index("<layout dim-ordering", ds_start)) + 2
cut_style = re.match(r"\s*<style>.*?</style>", s[lay_end:], re.S)
if cut_style:
    s = s[:lay_end] + s[lay_end + cut_style.end():]


def palette(field, pairs):
    return (f"<encoding attr='color' field='[{field}]' type='palette'>"
            + "".join(f"<map to='{c}'><bucket>&quot;{v}&quot;</bucket></map>" for v, c in pairs) + "</encoding>")


s = s[:lay_end] + (
    "<style><style-rule element='mark'>"
    + palette(p_name, [("Selected year", NAVY), ("Prior year", GREY)])
    + palette(PROF_CY_FIELD, [("Profitable", BLUE), ("Unprofitable", ORANGE)])
    + palette(PROF_FIELD, [("Profitable", BLUE), ("Unprofitable", ORANGE)])
    + palette(dir_name, [("Margin rose", BLUE), ("Margin fell", ORANGE)])
    + palette(ct_name, [("Returning", NAVY), ("New", LIGHT_BLUE)])
    + f"<encoding attr='color' center='0.0' field='[{mg_name}]' max='0.25' min='-0.25' palette='orange_blue_diverging_10_0' type='interpolated' />"
    + "</style-rule></style>") + s[lay_end:]
s = s.replace("</worksheets>", "".join(sheets.values()) + "</worksheets>", 1)
s = s.replace("</dashboards>", "".join(dash_xml) + "</dashboards>", 1) if "</dashboards>" in s else \
    s.replace("</worksheets>", "</worksheets><dashboards>" + "".join(dash_xml) + "</dashboards>", 1)
s = re.sub(r"<window class='(worksheet|dashboard)' maximized='true'", r"<window class='\1'", s)
s = s.replace("</windows>", "".join(window(n) for n in sheets)
              + "".join(window(d, "dashboard") for d in DASHBOARDS) + "</windows>", 1)
s = s.replace(f"<window class='dashboard' name={q(DASHBOARDS[0])}>",
              f"<window class='dashboard' maximized='true' name={q(DASHBOARDS[0])}>")
open(path, "w", encoding="utf-8").write(s)
print(f"{len(C)} calcs, {len(sheets)} sheets, {len(DASHBOARDS)} dashboards")

"""UCI Online Retail II: real transactions from a UK online gift retailer, 2009-12-01 to 2011-12-09.

A second, separate source next to Superstore. It has revenue but no cost, so nothing profit-related is derived
from it. License CC BY 4.0: Chen, D. (2012), https://doi.org/10.24432/C5CG6D"""
import hashlib
import logging
import urllib.request
import zipfile

import pandas as pd

from . import config
from .pipeline import SchemaError

log = logging.getLogger("retailpulse.uci")

SOURCE_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
RAW_ZIP = config.DATA_DIR / "raw" / "uci" / "online_retail_ii.zip"
COLUMNS = {"Invoice": "invoice", "StockCode": "stock_code", "Description": "description", "Quantity": "quantity",
           "InvoiceDate": "invoice_ts", "Price": "price", "Customer ID": "customer_id", "Country": "country"}


def download() -> None:
    RAW_ZIP.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s", SOURCE_URL)
    urllib.request.urlretrieve(SOURCE_URL, RAW_ZIP)


def read(path=None) -> pd.DataFrame:
    """Both yearly sheets of the workbook inside the zip, checksum-verified. Text columns stay text."""
    path = path or RAW_ZIP
    if path == RAW_ZIP and not path.exists():
        download()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path == RAW_ZIP and digest != SHA256:
        raise SchemaError(f"{path.name} checksum {digest} does not match the published file")
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        sheets = pd.read_excel(f, sheet_name=None, dtype={"Invoice": str, "StockCode": str, "Description": str})
    return pd.concat(sheets.values(), ignore_index=True)


def validate(df: pd.DataFrame) -> None:
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise SchemaError(f"Online Retail II is missing columns: {sorted(missing)}")
    for col in ("Quantity", "Price"):
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise SchemaError(f"{col} must be numeric, got {df[col].dtype}")
    if not pd.api.types.is_datetime64_any_dtype(df["InvoiceDate"]):
        raise SchemaError(f"InvoiceDate must be a timestamp, got {df['InvoiceDate'].dtype}")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Snake-case columns, trimmed text, customer IDs as text. Duplicates are left for the database key to reject,
    so the count of rejected rows is reported by the load, in one place."""
    out = df.rename(columns=COLUMNS)[list(COLUMNS.values())].copy()
    for col in ("invoice", "stock_code", "description", "country"):
        out[col] = out[col].str.strip()
    out["customer_id"] = out["customer_id"].astype("Int64").astype("string")
    return out

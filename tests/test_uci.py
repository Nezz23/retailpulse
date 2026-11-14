import zipfile

import pandas as pd
import pytest

from retailpulse import uci
from retailpulse.pipeline import SchemaError


def workbook_zip(tmp_path, sheets: dict[str, pd.DataFrame]):
    """The published layout: one .xlsx with a sheet per year, inside a zip."""
    xlsx = tmp_path / "online_retail_II.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    path = tmp_path / "online_retail_ii.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.write(xlsx, xlsx.name)
    return path


def raw(rows):
    return pd.DataFrame(rows, columns=list(uci.COLUMNS)).assign(InvoiceDate=lambda d: pd.to_datetime(d["InvoiceDate"]))


Y1 = raw([("489434", "85048", " LED CUSHION ", 12, "2009-12-01 07:45", 6.95, 13085.0, "United Kingdom")])
Y2 = raw([("C539000", "22423", "CAKESTAND", -1, "2010-12-15 10:00", 12.75, None, "France")])


def test_both_yearly_sheets_are_read_and_normalized(tmp_path):
    df = uci.read(workbook_zip(tmp_path, {"Year 2009-2010": Y1, "Year 2010-2011": Y2}))
    uci.validate(df)
    out = uci.normalize(df)
    assert list(out["invoice"]) == ["489434", "C539000"]
    assert out.loc[0, "description"] == "LED CUSHION"
    assert out.loc[0, "customer_id"] == "13085" and pd.isna(out.loc[1, "customer_id"])


def test_missing_column_is_rejected():
    with pytest.raises(SchemaError, match="Price"):
        uci.validate(Y1.drop(columns="Price"))

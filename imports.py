"""Bounded, in-memory readers and explicit mapping for financial uploads."""
import csv
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from finance import CATEGORIES, CASH_COLUMNS, validate_ledger, validate_cash

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 30
DATE_FORMATS = {"YYYY-MM": "%Y-%m", "YYYY-MM-DD": "%Y-%m-%d", "DD/MM/YYYY": "%d/%m/%Y", "MM/DD/YYYY": "%m/%d/%Y"}


def _check_file(data, name):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Choose a nonempty file of at most 5 MB.")
    extension = Path(name).suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        raise ValueError("Only CSV and .xlsx files are supported.")
    if extension == ".xlsx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                    raise ValueError("The expanded workbook is too large (50 MB maximum).")
                if len(archive.infolist()) > 1000:
                    raise ValueError("The workbook contains too many internal files.")
                if any("vbaproject" in i.filename.lower() for i in archive.infolist()):
                    raise ValueError("Macro-containing workbooks are not supported.")
        except zipfile.BadZipFile:
            raise ValueError("The file is not a readable .xlsx workbook.") from None
    return extension


def sheet_names(data, name):
    if _check_file(data, name) == ".csv":
        return ["CSV"]
    from openpyxl import load_workbook
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            names = workbook.sheetnames
            if len(names) > 20:
                raise ValueError("Use a workbook with at most 20 sheets.")
            return names
        finally:
            workbook.close()
    except ValueError:
        raise
    except Exception:
        raise ValueError("The workbook could not be read. Upload an unencrypted .xlsx file.") from None


def read_table(data, name, sheet=None):
    extension = _check_file(data, name)
    if extension == ".csv":
        try:
            text = data.decode("utf-8-sig")
            reader = csv.reader(StringIO(text), strict=True)
            rows = []
            for row in reader:
                if len(row) > MAX_COLUMNS or len(rows) > MAX_ROWS:
                    raise ValueError("Use at most 10,000 data rows and 30 columns.")
                rows.append(row)
        except (UnicodeError, csv.Error):
            raise ValueError("Use a UTF-8, comma-separated CSV with a single header row.") from None
    else:
        from openpyxl import load_workbook
        try:
            workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
            try:
                worksheet = workbook[sheet or workbook.sheetnames[0]]
                if worksheet.max_row > MAX_ROWS + 1 or worksheet.max_column > MAX_COLUMNS:
                    raise ValueError("Use at most 10,000 data rows and 30 columns; remove excess formatted rows/columns.")
                rows = []
                for cells in worksheet.iter_rows():
                    if len(rows) > MAX_ROWS or len(cells) > MAX_COLUMNS:
                        raise ValueError("Use at most 10,000 data rows and 30 columns.")
                    if any(c.data_type == "f" for c in cells):
                        raise ValueError("Excel formulas are not imported. Paste values into a clean sheet first.")
                    rows.append([c.value for c in cells])
            finally:
                workbook.close()
        except ValueError:
            raise
        except Exception:
            raise ValueError("The selected workbook sheet could not be read.") from None
    if len(rows) < 2:
        raise ValueError("Include a header and at least one data row.")
    headers = [str(v).strip() if v is not None else "" for v in rows[0]]
    if not all(headers) or len(headers) != len(set(headers)) or any(len(h)>80 or any(ord(c)<32 for c in h) for h in headers):
        raise ValueError("Column headings must be unique, nonempty labels of at most 80 characters with no control characters, including after trimming spaces.")
    if any(len(row) != len(headers) for row in rows[1:]):
        raise ValueError("Each row must contain the same number of columns as the header.")
    return pd.DataFrame(rows[1:], columns=headers)


def _dates(series, date_format):
    if date_format not in DATE_FORMATS:
        raise ValueError("Choose a supported date format.")
    parsed = []
    for value in series:
        try:
            if isinstance(value, (datetime, date, pd.Timestamp)):
                stamp = pd.Timestamp(value)
            else:
                stamp = pd.Timestamp(datetime.strptime(str(value).strip(), DATE_FORMATS[date_format]))
            if pd.isna(stamp) or stamp.tzinfo is not None or not 2000 <= stamp.year <= 2100:
                raise ValueError
            parsed.append(stamp.to_period("M").to_timestamp())
        except (ValueError, TypeError, OverflowError):
            raise ValueError("A date is missing or does not match the selected format. Use dates between 2000 and 2100; Excel date cells are also supported.") from None
    return pd.Series(parsed, index=series.index, dtype="datetime64[ns]")


def _text(series, field):
    if series.isna().any():
        raise ValueError(f"{field} contains missing values.")
    result = series.astype(str).str.strip()
    if result.eq("").any() or result.str.len().gt(80).any() or result.str.contains(r"[\x00-\x1f]", regex=True).any():
        raise ValueError(f"{field} must contain nonempty labels of at most 80 characters, with no control characters.")
    if result.str.startswith(("=", "+", "-", "@")).any():
        raise ValueError(f"{field} labels cannot start with spreadsheet formula characters (=, +, - or @).")
    return result


def _amounts(series):
    # No guessed separators, currency symbols, scaling or sign reversal.
    if series.map(lambda v: isinstance(v, (bool, np.bool_))).any():
        raise ValueError("Amounts must be numbers, not Boolean values.")
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any() or not np.isfinite(values).all():
        raise ValueError("Amounts must be finite plain numbers, without currency symbols or thousands separators.")
    if not np.allclose(values, values.round(2), atol=1e-7, rtol=0):
        raise ValueError("Amounts must have no more than two decimal places.")
    return values.round(2).astype(float)


def _mapping(frame, mapping, fields, currency_column, confirmed_gbp):
    selected = [mapping.get(f) for f in fields]
    if any(c not in frame.columns for c in selected) or len(set(selected)) != len(selected):
        raise ValueError("Map each required field to a different source column.")
    if currency_column:
        if currency_column not in frame.columns or currency_column in selected:
            raise ValueError("Map currency to a separate source column.")
        if not _text(frame[currency_column], "Currency").str.upper().eq("GBP").all():
            raise ValueError("Only GBP is supported. Mixed or non-GBP currencies cannot be analysed together; no currency conversion is performed.")
    elif not confirmed_gbp:
        raise ValueError("Confirm that every amount is in GBP, or map a currency column containing GBP.")


def ledger_from_table(frame, mapping, layout, date_format, category_map, scenario_map=None,
                      currency_column=None, confirmed_gbp=False, fill_unused=False):
    fields = ["month", "business_unit", "category"] + (["scenario", "amount_gbp"] if layout == "Long" else ["actual", "budget"])
    _mapping(frame, mapping, fields, currency_column, confirmed_gbp)
    base = pd.DataFrame({"month":_dates(frame[mapping["month"]],date_format),
                         "business_unit":_text(frame[mapping["business_unit"]],"Business unit"),
                         "source_category":_text(frame[mapping["category"]],"Account category")})
    if layout == "Long":
        base["scenario"] = _text(frame[mapping["scenario"]],"Scenario").map(scenario_map or {})
        base["amount_gbp"] = _amounts(frame[mapping["amount_gbp"]])
    elif layout == "Wide":
        base["Actual"] = _amounts(frame[mapping["actual"]])
        base["Budget"] = _amounts(frame[mapping["budget"]])
        base = base.melt(id_vars=["month","business_unit","source_category"], value_vars=["Actual","Budget"],var_name="scenario",value_name="amount_gbp")
    else:
        raise ValueError("Choose Long or Wide layout.")
    base["category"] = base.source_category.map(category_map)
    if base.category.isna().any() or not set(base.category).issubset(CATEGORIES):
        raise ValueError("Map every source account to a supported category.")
    if base.scenario.isna().any() or not set(base.scenario).issubset({"Actual","Budget"}):
        raise ValueError("Map every scenario to Actual or Budget.")
    if base.duplicated(["month","business_unit","source_category","scenario"]).any():
        raise ValueError("Duplicate month/unit/source-account/scenario rows. Upload monthly account totals, not duplicate records or transaction lines.")
    if (base.amount_gbp < 0).any():
        raise ValueError("Use nonnegative revenue and cost totals. Negative amounts are not automatically reversed or netted.")
    # Multiple distinct source accounts may intentionally map to one P&L category.
    result = base.groupby(["month","business_unit","category","scenario"],as_index=False).amount_gbp.sum()
    absent = set(CATEGORIES) - set(result.category)
    if fill_unused and absent:
        keys = result[["month","business_unit"]].drop_duplicates()
        zero = [{"month":r.month,"business_unit":r.business_unit,"category":c,"scenario":s,"amount_gbp":0.0}
                for r in keys.itertuples() for c in sorted(absent) for s in ["Actual","Budget"]]
        result = pd.concat([result,pd.DataFrame(zero)],ignore_index=True)
    validate_ledger(result)
    return result.sort_values(["month","business_unit","category","scenario"]).reset_index(drop=True)


def cash_from_table(frame, mapping, date_format, ledger, currency_column=None, confirmed_gbp=False):
    _mapping(frame,mapping,["month","business_unit",*CASH_COLUMNS],currency_column,confirmed_gbp)
    result = pd.DataFrame({"month":_dates(frame[mapping["month"]],date_format),
                           "business_unit":_text(frame[mapping["business_unit"]],"Business unit")})
    for column in CASH_COLUMNS:
        result[column] = _amounts(frame[mapping[column]])
    validate_cash(result,ledger)
    return result.sort_values(["month","business_unit"]).reset_index(drop=True)


def export_csv(frame):
    """Prevent formula execution from uploaded text labels in spreadsheet exports."""
    safe = frame.copy()
    for column in safe.select_dtypes(include=["object","string"]).columns:
        safe[column] = safe[column].map(lambda v: "'"+v if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")) else v)
    return safe.to_csv(index=False).encode("utf-8")

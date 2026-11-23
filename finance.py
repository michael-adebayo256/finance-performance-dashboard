"""Testable management-accounting calculations; amounts are positive magnitudes."""
from pathlib import Path
import numpy as np
import pandas as pd

CATEGORIES = ["Revenue", "Direct costs", "People", "Sales & marketing", "Administration"]
COSTS = CATEGORIES[1:]
UNITS = ["Consulting", "Managed services", "Training"]
CASH_COLUMNS = ["opening_cash_gbp", "customer_receipts_gbp", "operating_payments_gbp",
                "capital_spend_gbp", "financing_inflow_gbp", "closing_cash_gbp"]


def validate_ledger(ledger):
    required = {"month", "business_unit", "category", "scenario", "amount_gbp"}
    if not required.issubset(ledger.columns):
        raise ValueError("Management accounts are missing required columns.")
    if ledger.empty or ledger[list(required)].isna().any().any():
        raise ValueError("Management accounts must contain records with no missing required values.")
    if not pd.api.types.is_datetime64_any_dtype(ledger.month):
        raise ValueError("Month must contain validated dates.")
    if (ledger.month.dt.day != 1).any():
        raise ValueError("Dates must be normalised to month starts.")
    months = sorted(ledger.month.unique())
    if len(months) > 120 or len(pd.date_range(months[0], months[-1], freq="MS")) != len(months):
        raise ValueError("Reporting months must be consecutive, with at most 120 months.")
    if not set(ledger.category).issubset(CATEGORIES) or set(ledger.scenario) != {"Actual", "Budget"}:
        raise ValueError("Use the five supported account categories and both Actual and Budget scenarios.")
    if (ledger.amount_gbp < 0).any() or not np.isfinite(ledger.amount_gbp).all():
        raise ValueError("Ledger amounts must be finite, nonnegative magnitudes.")
    if (ledger.amount_gbp > 1e12).any():
        raise ValueError("An amount exceeds the supported maximum of £1 trillion per record.")
    if ledger.duplicated(["month", "business_unit", "category", "scenario"]).any():
        raise ValueError("Duplicate ledger records.")
    if ledger.business_unit.nunique() > 50:
        raise ValueError("At most 50 business units are supported.")
    expected = pd.MultiIndex.from_product([months, sorted(ledger.business_unit.unique()), CATEGORIES, ["Actual", "Budget"]])
    observed = pd.MultiIndex.from_frame(ledger[["month", "business_unit", "category", "scenario"]])
    missing = expected.difference(observed)
    if len(missing):
        raise ValueError(f"Every month/unit/category must have actual and budget records. {len(missing)} combinations are missing; add explicit zero rows where appropriate.")


def validate_cash(cash, ledger):
    if not {"month", "business_unit", *CASH_COLUMNS}.issubset(cash.columns):
        raise ValueError("Cash data are missing required columns.")
    if cash.empty or cash[["month", "business_unit", *CASH_COLUMNS]].isna().any().any():
        raise ValueError("Cash data must contain records with no missing required values.")
    if cash.duplicated(["month", "business_unit"]).any():
        raise ValueError("Duplicate cash records.")
    if not np.isfinite(cash[CASH_COLUMNS]).all().all():
        raise ValueError("Cash data must be finite.")
    if (cash[CASH_COLUMNS].abs() > 1e12).any().any():
        raise ValueError("Cash amounts exceed the supported range.")
    flows = ["customer_receipts_gbp", "operating_payments_gbp", "capital_spend_gbp", "financing_inflow_gbp"]
    if (cash[flows] < 0).any().any():
        raise ValueError("Cash receipts, payments, capital spend and financing inflow must be nonnegative magnitudes. Opening/closing balances may be negative.")
    expected_keys = set(map(tuple, ledger[["month", "business_unit"]].drop_duplicates().to_numpy()))
    if expected_keys != set(map(tuple, cash[["month", "business_unit"]].to_numpy())):
        raise ValueError("Cash and ledger periods/units must match completely.")
    check = cash.opening_cash_gbp + cash.customer_receipts_gbp - cash.operating_payments_gbp - cash.capital_spend_gbp + cash.financing_inflow_gbp
    if not np.allclose(check, cash.closing_cash_gbp, atol=.011, rtol=0):
        raise ValueError("Cash bridge does not reconcile. Check opening + receipts − payments − capital spend + financing inflow = closing (tolerance £0.01).")
    for _, group in cash.sort_values("month").groupby("business_unit"):
        if not np.allclose(group.opening_cash_gbp.iloc[1:], group.closing_cash_gbp.iloc[:-1], atol=.011, rtol=0):
            raise ValueError("Monthly opening cash does not match prior closing cash.")


def load_data(directory):
    directory = Path(directory)
    ledger = pd.read_csv(directory / "management_accounts.csv", parse_dates=["month"])
    cash = pd.read_csv(directory / "cash_movements.csv", parse_dates=["month"])
    validate_ledger(ledger)
    validate_cash(cash, ledger)
    return ledger, cash


def percent(numerator, denominator):
    """A zero budget has no meaningful variance percentage."""
    return numerator / denominator * 100 if denominator else None


def pnl(ledger):
    result = ledger.pivot_table(index="category", columns="scenario", values="amount_gbp", aggfunc="sum").reindex(CATEGORIES).fillna(0)
    for scenario in ["Actual", "Budget"]:
        if scenario not in result:
            result[scenario] = 0.0
    result.loc["Gross profit"] = result.loc["Revenue"] - result.loc["Direct costs"]
    result.loc["Operating costs"] = result.loc[["People", "Sales & marketing", "Administration"]].sum()
    result.loc["Operating profit"] = result.loc["Gross profit"] - result.loc["Operating costs"]
    result = result.reindex(["Revenue", "Direct costs", "Gross profit", "People", "Sales & marketing", "Administration", "Operating costs", "Operating profit"])
    result["Variance £"] = result.Actual - result.Budget
    result["Variance %"] = result["Variance £"].div(result.Budget.replace(0, np.nan)) * 100
    result["Profit impact £"] = result["Variance £"] * np.where(result.index.isin(COSTS + ["Operating costs"]), -1, 1)
    result["Assessment"] = np.select([result["Profit impact £"] > .005, result["Profit impact £"] < -.005], ["Favourable", "Adverse"], default="On budget")
    return result


def monthly_summary(ledger):
    rows = []
    for month, group in ledger.groupby("month", sort=True):
        statement = pnl(group)
        row = {"month": month}
        for scenario in ["Actual", "Budget"]:
            row[f"{scenario} revenue"] = statement.loc["Revenue", scenario]
            row[f"{scenario} operating profit"] = statement.loc["Operating profit", scenario]
            row[f"{scenario} margin %"] = percent(statement.loc["Operating profit", scenario], statement.loc["Revenue", scenario])
        rows.append(row)
    return pd.DataFrame(rows)


def profit_bridge(statement):
    """Budget profit plus revenue/cost impacts equals actual profit."""
    labels = ["Budget profit", *CATEGORIES, "Actual profit"]
    values = [statement.loc["Operating profit", "Budget"]]
    values += [statement.loc[c, "Profit impact £"] for c in CATEGORIES]
    values += [statement.loc["Operating profit", "Actual"]]
    return labels, values


def cash_summary(cash):
    monthly = cash.groupby("month", sort=True)[CASH_COLUMNS].sum()
    return {
        "Opening cash": monthly.opening_cash_gbp.iloc[0],
        "Customer receipts": monthly.customer_receipts_gbp.sum(),
        "Operating payments": monthly.operating_payments_gbp.sum(),
        "Capital spend": monthly.capital_spend_gbp.sum(),
        "Financing inflow": monthly.financing_inflow_gbp.sum(),
        "Closing cash": monthly.closing_cash_gbp.iloc[-1],
    }, monthly

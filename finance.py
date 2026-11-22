"""Testable management-accounting calculations; amounts are positive magnitudes."""
from pathlib import Path
import numpy as np
import pandas as pd

CATEGORIES = ["Revenue", "Direct costs", "People", "Sales & marketing", "Administration"]
COSTS = CATEGORIES[1:]
UNITS = ["Consulting", "Managed services", "Training"]
CASH_COLUMNS = ["opening_cash_gbp", "customer_receipts_gbp", "operating_payments_gbp",
                "capital_spend_gbp", "financing_inflow_gbp", "closing_cash_gbp"]


def load_data(directory):
    directory = Path(directory)
    ledger = pd.read_csv(directory / "management_accounts.csv", parse_dates=["month"])
    cash = pd.read_csv(directory / "cash_movements.csv", parse_dates=["month"])
    required = {"month", "business_unit", "category", "scenario", "amount_gbp"}
    if not required.issubset(ledger.columns):
        raise ValueError("Management accounts are missing required columns.")
    if not {"month", "business_unit", *CASH_COLUMNS}.issubset(cash.columns):
        raise ValueError("Cash data are missing required columns.")
    if ledger[list(required)].isna().any().any() or cash.isna().any().any():
        raise ValueError("The dataset contains missing values.")
    if not set(ledger.category).issubset(CATEGORIES) or set(ledger.scenario) != {"Actual", "Budget"}:
        raise ValueError("Unexpected category or scenario.")
    if (ledger.amount_gbp < 0).any() or not np.isfinite(ledger.amount_gbp).all():
        raise ValueError("Ledger amounts must be finite, nonnegative magnitudes.")
    if ledger.duplicated(["month", "business_unit", "category", "scenario"]).any():
        raise ValueError("Duplicate ledger records.")
    if cash.duplicated(["month", "business_unit"]).any():
        raise ValueError("Duplicate cash records.")
    expected = pd.MultiIndex.from_product([sorted(ledger.month.unique()), sorted(ledger.business_unit.unique()),
                                          CATEGORIES, ["Actual", "Budget"]])
    observed = pd.MultiIndex.from_frame(ledger[["month", "business_unit", "category", "scenario"]])
    if len(expected.difference(observed)) or len(observed.difference(expected)):
        raise ValueError("Every month/unit/category must have actual and budget records.")
    if not np.isfinite(cash[CASH_COLUMNS]).all().all():
        raise ValueError("Cash data must be finite.")
    expected_keys = set(map(tuple, ledger[["month", "business_unit"]].drop_duplicates().to_numpy()))
    if expected_keys != set(map(tuple, cash[["month", "business_unit"]].to_numpy())):
        raise ValueError("Cash and ledger periods/units must match.")
    check = cash.opening_cash_gbp + cash.customer_receipts_gbp - cash.operating_payments_gbp - cash.capital_spend_gbp + cash.financing_inflow_gbp
    if not np.allclose(check, cash.closing_cash_gbp, atol=.011, rtol=0):
        raise ValueError("Cash bridge does not reconcile.")
    for _, group in cash.sort_values("month").groupby("business_unit"):
        if not np.allclose(group.opening_cash_gbp.iloc[1:], group.closing_cash_gbp.iloc[:-1], atol=.011, rtol=0):
            raise ValueError("Monthly opening cash does not match prior closing cash.")
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

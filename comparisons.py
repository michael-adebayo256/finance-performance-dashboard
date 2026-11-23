"""Actual-to-actual period comparisons and explicit investigation thresholds."""
import numpy as np
import pandas as pd
from finance import CATEGORIES, COSTS, pnl, percent

COMPARISON_BASES = ["Same period last year", "Previous period (same length)"]
THRESHOLD_RULES = ["Either threshold", "Both thresholds"]


def review_flags(table, amount_threshold, percentage_threshold, rule="Either threshold",
                 amount_column="Variance £", percentage_column="Variance %"):
    """Flag nonzero changes; a missing percentage falls back to the £ test."""
    if rule not in THRESHOLD_RULES:
        raise ValueError("Unknown threshold rule.")
    if not np.isfinite([amount_threshold, percentage_threshold]).all() or min(amount_threshold, percentage_threshold) < 0:
        raise ValueError("Review thresholds must be finite and nonnegative.")
    result = table.copy()
    amounts = result[amount_column]
    percentages = result[percentage_column]
    nonzero = amounts.abs() > .005
    meets_amount = amounts.abs() >= amount_threshold
    available_percentage = percentages.notna() & np.isfinite(percentages)
    meets_percentage = available_percentage & (percentages.abs() >= percentage_threshold)
    if rule == "Either threshold":
        flagged = meets_amount | meets_percentage
    else:
        flagged = meets_amount & meets_percentage
    flagged = nonzero & flagged.where(available_percentage, meets_amount)
    result["Flagged for review"] = flagged.astype(bool)
    result["Review flag"] = np.select(
        [~nonzero, flagged & ~available_percentage, flagged, ~available_percentage],
        ["No change", "Review (£ only; % unavailable)", "Review", "Below £ threshold; % unavailable"],
        default="Below thresholds",
    )
    return result


def _coverage(ledger, months, units):
    expected = pd.MultiIndex.from_product([months, units, CATEGORIES], names=["month", "business_unit", "category"])
    actual = ledger[(ledger.scenario == "Actual") & ledger.month.isin(months) & ledger.business_unit.isin(units)]
    return expected.difference(pd.MultiIndex.from_frame(actual[["month", "business_unit", "category"]]))


def period_comparison(ledger, start, end, units, basis="Same period last year"):
    """Use complete, matched Actual records for the same selected business units."""
    if basis not in COMPARISON_BASES or not units:
        raise ValueError("Choose a supported comparison basis and at least one business unit.")
    units = list(dict.fromkeys(units))
    start, end = (pd.Timestamp(v).to_period("M").to_timestamp() for v in [start, end])
    if end < start:
        raise ValueError("The current period must end on or after its start.")
    current_months = pd.date_range(start, end, freq="MS")
    if len(_coverage(ledger, current_months, units)):
        raise ValueError("The current selection lacks complete Actual records for the selected units and categories.")
    shift = 12 if basis == "Same period last year" else len(current_months)
    prior_start = start - pd.DateOffset(months=shift)
    prior_end = end - pd.DateOffset(months=shift)
    prior_months = pd.date_range(prior_start, prior_end, freq="MS")
    missing = _coverage(ledger, prior_months, units)
    result = {"basis":basis, "current_start":start, "current_end":end,
              "reference_start":prior_start, "reference_end":prior_end,
              "months":len(current_months), "available":not len(missing),
              "missing_actual_records":len(missing),
              "missing_months":sorted(set(missing.get_level_values("month"))),
              "table":None, "current_margin":None, "reference_margin":None,
              "margin_change_pp":None}
    if len(missing):
        return result
    current = pnl(ledger[ledger.month.isin(current_months) & ledger.business_unit.isin(units)])
    prior = pnl(ledger[ledger.month.isin(prior_months) & ledger.business_unit.isin(units)])
    table = pd.DataFrame({"Current actual":current.Actual,"Reference actual":prior.Actual})
    table["Change £"] = table["Current actual"] - table["Reference actual"]
    # Growth from a zero or negative profit base is not represented as a percentage.
    table["Change %"] = table["Change £"] / table["Reference actual"].where(table["Reference actual"] > 0) * 100
    table["Profit impact £"] = table["Change £"] * np.where(table.index.isin(COSTS+["Operating costs"]), -1, 1)
    table["Assessment"] = np.select([table["Profit impact £"] > .005, table["Profit impact £"] < -.005], ["Favourable", "Adverse"], default="No change")
    result["table"] = table
    result["current_margin"] = percent(table.loc["Operating profit","Current actual"],table.loc["Revenue","Current actual"])
    result["reference_margin"] = percent(table.loc["Operating profit","Reference actual"],table.loc["Revenue","Reference actual"])
    if result["current_margin"] is not None and result["reference_margin"] is not None:
        result["margin_change_pp"] = result["current_margin"]-result["reference_margin"]
    return result

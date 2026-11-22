"""Generate deterministic, fictional management accounts. No real company data."""
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
SEED = 20261122
UNITS = {"Consulting": 145_000, "Managed services": 108_000, "Training": 62_000}
CATEGORIES = ["Revenue", "Direct costs", "People", "Sales & marketing", "Administration"]


def generate():
    rng = np.random.default_rng(SEED)
    ledger, cash = [], []
    opening = {unit: base * 1.8 for unit, base in UNITS.items()}
    for i, month in enumerate(pd.date_range("2025-01-01", "2026-10-01", freq="MS")):
        for unit, base in UNITS.items():
            season = 1 + .10 * np.sin((month.month - 3) * np.pi / 6)
            revenue_budget = base * (1 + .008 * i) * season
            budgets = {"Revenue": revenue_budget, "Direct costs": revenue_budget * .28,
                       "People": base * .32 * (1 + .004 * i),
                       "Sales & marketing": revenue_budget * .065,
                       "Administration": base * .085 * (1 + .003 * i)}
            # Explicit fictional operating changes create explainable demo variances.
            revenue_shift = -.075 if unit == "Training" and month.year == 2026 else .018
            actuals = {"Revenue": revenue_budget * (1 + revenue_shift + rng.normal(0, .045)),
                       "Direct costs": budgets["Direct costs"] * (1 + rng.normal(.035, .035)),
                       "People": budgets["People"] * (1 + rng.normal(.018, .015)),
                       "Sales & marketing": budgets["Sales & marketing"] * (1 + rng.normal(.06, .07)),
                       "Administration": budgets["Administration"] * (1 + rng.normal(-.015, .025))}
            for category in CATEGORIES:
                for scenario, values in [("Budget", budgets), ("Actual", actuals)]:
                    ledger.append({"month": month.date().isoformat(), "business_unit": unit,
                                   "category": category, "scenario": scenario,
                                   "amount_gbp": round(values[category], 2)})
            receipts = round(actuals["Revenue"] * rng.uniform(.91, 1.07), 2)
            payments = round(sum(actuals[c] for c in CATEGORIES[1:]) * rng.uniform(.96, 1.06), 2)
            capex = float(rng.integers(9_000, 24_000)) if month.month in (3, 9) else 0.0
            funding = 30_000.0 if unit == "Managed services" and month == pd.Timestamp("2025-01-01") else 0.0
            start = round(opening[unit], 2)
            end = round(start + receipts - payments - capex + funding, 2)
            cash.append({"month": month.date().isoformat(), "business_unit": unit,
                         "opening_cash_gbp": start, "customer_receipts_gbp": receipts,
                         "operating_payments_gbp": payments, "capital_spend_gbp": capex,
                         "financing_inflow_gbp": funding, "closing_cash_gbp": end})
            opening[unit] = end
    DATA.mkdir(exist_ok=True)
    pd.DataFrame(ledger).to_csv(DATA / "management_accounts.csv", index=False)
    pd.DataFrame(cash).to_csv(DATA / "cash_movements.csv", index=False)


if __name__ == "__main__":
    generate()
    print("Generated fictional GBP accounts for January 2025–October 2026.")

"""Independent accounting identities and edge cases for portfolio calculations."""
from pathlib import Path
import unittest
import tempfile
import pandas as pd
from finance import load_data, pnl, monthly_summary, cash_summary, profit_bridge, percent

ROOT = Path(__file__).resolve().parents[1]


class FinanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger, cls.cash = load_data(ROOT / "data")

    def test_profit_identity_and_bridge(self):
        for _, group in self.ledger.groupby(["month", "business_unit"]):
            result = pnl(group)
            for scenario in ["Actual", "Budget"]:
                expected = group.loc[(group.scenario == scenario) & (group.category == "Revenue"),"amount_gbp"].sum() - group.loc[(group.scenario == scenario) & (group.category != "Revenue"),"amount_gbp"].sum()
                self.assertAlmostEqual(result.loc["Operating profit",scenario], expected, places=6)
            _, values = profit_bridge(result)
            self.assertAlmostEqual(sum(values[:-1]), values[-1], places=6)

    def test_variance_signs_and_zero_budget(self):
        frame = pd.DataFrame([
            {"category":category,"scenario":scenario,"amount_gbp":value}
            for category in ["Revenue","Direct costs","People","Sales & marketing","Administration"]
            for scenario,value in [("Budget",0),("Actual",100)]])
        result = pnl(frame)
        self.assertEqual(result.loc["Revenue","Assessment"],"Favourable")
        self.assertEqual(result.loc["Direct costs","Assessment"],"Adverse")
        self.assertTrue(pd.isna(result.loc["Revenue","Variance %"]))
        self.assertIsNone(percent(1,0))

    def test_period_cash_uses_boundaries(self):
        selected = self.cash[self.cash.month.between("2026-03-01","2026-07-01")]
        values, monthly = cash_summary(selected)
        self.assertAlmostEqual(values["Opening cash"],selected.loc[selected.month == selected.month.min(),"opening_cash_gbp"].sum(),places=6)
        self.assertAlmostEqual(values["Closing cash"],selected.loc[selected.month == selected.month.max(),"closing_cash_gbp"].sum(),places=6)
        self.assertAlmostEqual(values["Opening cash"]+values["Customer receipts"]-values["Operating payments"]-values["Capital spend"]+values["Financing inflow"],values["Closing cash"],places=5)
        self.assertEqual(len(monthly),5)

    def test_monthly_aggregation_matches_period(self):
        monthly = monthly_summary(self.ledger)
        result = pnl(self.ledger)
        self.assertAlmostEqual(monthly["Actual operating profit"].sum(),result.loc["Operating profit","Actual"],places=6)
        self.assertEqual(len(monthly),22)

    def test_business_unit_additivity(self):
        total = sum(pnl(g).loc["Operating profit","Actual"] for _,g in self.ledger.groupby("business_unit"))
        self.assertAlmostEqual(total,pnl(self.ledger).loc["Operating profit","Actual"],places=6)

    def test_bad_cash_and_incomplete_budget_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.ledger.to_csv(path / "management_accounts.csv", index=False)
            broken = self.cash.copy()
            broken.loc[0,"closing_cash_gbp"] += 10
            broken.to_csv(path / "cash_movements.csv", index=False)
            with self.assertRaisesRegex(ValueError,"Cash bridge"):
                load_data(path)
            self.cash.to_csv(path / "cash_movements.csv", index=False)
            self.ledger.iloc[1:].to_csv(path / "management_accounts.csv", index=False)
            with self.assertRaisesRegex(ValueError,"Every month"):
                load_data(path)


if __name__ == "__main__":
    unittest.main()

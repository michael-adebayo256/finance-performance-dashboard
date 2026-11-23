from pathlib import Path
import unittest
import pandas as pd
from finance import load_data, CATEGORIES
from comparisons import period_comparison, review_flags


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger,_=load_data(Path(__file__).resolve().parents[1]/"data")

    def test_yoy_uses_same_months_and_units(self):
        units=["Consulting","Training"]
        result=period_comparison(self.ledger,"2026-03-01","2026-06-01",units)
        self.assertTrue(result["available"])
        self.assertEqual(result["reference_start"],pd.Timestamp("2025-03-01"))
        self.assertEqual(result["reference_end"],pd.Timestamp("2025-06-01"))
        actual=self.ledger[(self.ledger.scenario=="Actual") & self.ledger.business_unit.isin(units)]
        for label,begin,end in [("Current actual","2026-03-01","2026-06-01"),("Reference actual","2025-03-01","2025-06-01")]:
            frame=actual[actual.month.between(begin,end)]
            revenue=frame.loc[frame.category=="Revenue","amount_gbp"].sum()
            profit=revenue-frame.loc[frame.category!="Revenue","amount_gbp"].sum()
            self.assertAlmostEqual(result["table"].loc["Operating profit",label],profit,places=6)
        expected=(result["table"].loc["Operating profit","Current actual"]/result["table"].loc["Revenue","Current actual"]-result["table"].loc["Operating profit","Reference actual"]/result["table"].loc["Revenue","Reference actual"])*100
        self.assertAlmostEqual(result["margin_change_pp"],expected)

    def test_previous_equal_length_period_crosses_year(self):
        result=period_comparison(self.ledger,"2026-01-01","2026-03-01",["Consulting"],"Previous period (same length)")
        self.assertTrue(result["available"])
        self.assertEqual(result["months"],3)
        self.assertEqual(result["reference_start"],pd.Timestamp("2025-10-01"))
        self.assertEqual(result["reference_end"],pd.Timestamp("2025-12-01"))

    def test_partial_reference_is_unavailable_not_zero_filled(self):
        result=period_comparison(self.ledger,"2025-05-01","2025-12-01",["Training"],"Previous period (same length)")
        self.assertFalse(result["available"])
        self.assertIsNone(result["table"])
        self.assertEqual(len(result["missing_months"]),4)
        broken=self.ledger.drop(self.ledger[(self.ledger.month==pd.Timestamp("2025-01-01")) & (self.ledger.business_unit=="Training") & (self.ledger.category=="Revenue") & (self.ledger.scenario=="Actual")].index)
        result=period_comparison(broken,"2026-01-01","2026-01-01",["Training"])
        self.assertFalse(result["available"])
        self.assertEqual(result["missing_actual_records"],1)

    def test_cost_signs_and_nonpositive_reference(self):
        rows=[]
        for month,values in [("2025-01-01",[0,50,0,0,0]),("2026-01-01",[100,60,0,0,0])]:
            rows.extend({"month":pd.Timestamp(month),"business_unit":"Unit","category":c,"scenario":s,"amount_gbp":v} for c,v in zip(CATEGORIES,values) for s in ["Actual","Budget"])
        result=period_comparison(pd.DataFrame(rows),"2026-01-01","2026-01-01",["Unit"])
        table=result["table"]
        self.assertEqual(table.loc["Direct costs","Assessment"],"Adverse")
        self.assertEqual(table.loc["Operating profit","Change £"],90)
        self.assertTrue(pd.isna(table.loc["Operating profit","Change %"]))
        self.assertTrue(pd.isna(table.loc["Revenue","Change %"]))
        self.assertIsNone(result["margin_change_pp"])

    def test_threshold_rules_boundaries_and_missing_percentages(self):
        table=pd.DataFrame({"Variance £":[10000,-9999,0,10000,9999],"Variance %":[4,-5,0,float("nan"),float("nan")]})
        either=review_flags(table,10000,5,"Either threshold")
        both=review_flags(table,10000,5,"Both thresholds")
        self.assertEqual(either["Flagged for review"].tolist(),[True,True,False,True,False])
        self.assertEqual(both["Flagged for review"].tolist(),[False,False,False,True,False])
        self.assertIn("£ only",both.loc[3,"Review flag"])
        zeros=review_flags(table,0,0)
        self.assertFalse(zeros.loc[2,"Flagged for review"])
        pd.testing.assert_frame_equal(table,either[table.columns])

    def test_invalid_inputs_are_rejected(self):
        table=pd.DataFrame({"Variance £":[1],"Variance %":[1]})
        for value in [-1,float("nan"),float("inf")]:
            with self.assertRaises(ValueError):review_flags(table,value,5)
        with self.assertRaises(ValueError):period_comparison(self.ledger,"2026-01-01","2026-02-01",[])
        with self.assertRaises(ValueError):period_comparison(self.ledger,"2026-02-01","2026-01-01",["Consulting"])
        with self.assertRaises(ValueError):period_comparison(self.ledger,"2026-01-01","2026-01-01",["Unknown unit"])


if __name__=="__main__":
    unittest.main()

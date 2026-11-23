"""Import integrity, reader bounds and untrusted-input regression checks."""
from io import BytesIO
import unittest
import pandas as pd
from openpyxl import Workbook
from imports import read_table, sheet_names, ledger_from_table, cash_from_table, export_csv, MAX_BYTES
from finance import CATEGORIES, CASH_COLUMNS, pnl


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.frame=pd.DataFrame({"Period":["2026-01"]*5,"Unit":["Example unit"]*5,"Account":CATEGORIES,
                                 "Actual":[1000,250,300,50,100],"Plan":[900,200,280,60,90],"Currency":["GBP"]*5})
        self.mapping={"month":"Period","business_unit":"Unit","category":"Account","actual":"Actual","budget":"Plan"}
        self.categories={c:c for c in CATEGORIES}

    def ledger(self,frame=None,**kwargs):
        options=dict(frame=self.frame if frame is None else frame,mapping=self.mapping,layout="Wide",date_format="YYYY-MM",category_map=self.categories,currency_column="Currency")
        options.update(kwargs)
        return ledger_from_table(**options)

    def test_wide_csv_bom_and_financial_totals(self):
        raw=b"\xef\xbb\xbf"+self.frame.to_csv(index=False).encode()
        imported=self.ledger(read_table(raw,"accounts.csv"))
        statement=pnl(imported)
        self.assertEqual(len(imported),10)
        self.assertEqual(statement.loc["Operating profit","Actual"],300)
        self.assertEqual(statement.loc["Operating profit","Budget"],270)

    def test_long_layout_matches_wide(self):
        long=self.frame.melt(id_vars=["Period","Unit","Account","Currency"],value_vars=["Actual","Plan"],var_name="Case",value_name="Value")
        mapping={k:v for k,v in self.mapping.items() if k not in ["actual","budget"]}
        mapping.update(scenario="Case",amount_gbp="Value")
        result=self.ledger(long,mapping=mapping,layout="Long",scenario_map={"Actual":"Actual","Plan":"Budget"})
        pd.testing.assert_frame_equal(result,self.ledger())

    def test_distinct_accounts_aggregate_but_duplicates_fail(self):
        split=self.frame.iloc[:-1].copy()
        rows=pd.DataFrame([{"Period":"2026-01","Unit":"Example unit","Account":"Rent","Actual":60,"Plan":50,"Currency":"GBP"},
                           {"Period":"2026-01","Unit":"Example unit","Account":"Insurance","Actual":40,"Plan":40,"Currency":"GBP"}])
        result=self.ledger(pd.concat([split,rows],ignore_index=True),category_map={**self.categories,"Rent":"Administration","Insurance":"Administration"})
        self.assertEqual(pnl(result).loc["Administration","Actual"],100)
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            self.ledger(pd.concat([self.frame,self.frame.iloc[:1]],ignore_index=True))

    def test_no_silent_zero_fill(self):
        with self.assertRaisesRegex(ValueError,"Every month"):
            self.ledger(self.frame.iloc[:1])
        result=self.ledger(self.frame.iloc[:1],fill_unused=True)
        self.assertEqual(pnl(result).loc["Operating profit","Actual"],1000)
        partial=self.frame.melt(id_vars=["Period","Unit","Account","Currency"],value_vars=["Actual","Plan"],var_name="Case",value_name="Value").iloc[1:]
        with self.assertRaisesRegex(ValueError,"Every month"):
            self.ledger(partial,mapping={"month":"Period","business_unit":"Unit","category":"Account","scenario":"Case","amount_gbp":"Value"},layout="Long",scenario_map={"Actual":"Actual","Plan":"Budget"},fill_unused=True)

    def test_currency_must_be_explicit_and_uniform(self):
        for value in ["USD",""]:
            frame=self.frame.copy();frame.loc[0,"Currency"]=value
            with self.assertRaises(ValueError):self.ledger(frame)
        with self.assertRaisesRegex(ValueError,"Confirm"):
            self.ledger(currency_column=None)
        self.assertEqual(len(self.ledger(currency_column=None,confirmed_gbp=True)),10)

    def test_numbers_and_raw_negative_amounts_are_rejected(self):
        for value in [-1,float("inf"),"£1,000",None,"not a number",True,1.001]:
            with self.subTest(value=value):
                frame=self.frame.copy();frame["Actual"]=frame.Actual.astype(object);frame.loc[0,"Actual"]=value
                with self.assertRaises(ValueError):self.ledger(frame)

    def test_explicit_dates_and_missing_months(self):
        frame=self.frame.copy();frame["Period"]="03/02/2026"
        self.assertEqual(self.ledger(frame,date_format="DD/MM/YYYY").month.iloc[0],pd.Timestamp("2026-02-01"))
        self.assertEqual(self.ledger(frame,date_format="MM/DD/YYYY").month.iloc[0],pd.Timestamp("2026-03-01"))
        with self.assertRaises(ValueError):self.ledger(frame)
        other=self.frame.copy();other["Period"]="2026-03"
        with self.assertRaisesRegex(ValueError,"consecutive"):
            self.ledger(pd.concat([self.frame,other],ignore_index=True))

    def test_safe_labels_and_unique_mapping(self):
        for label in ["=1+1","+CMD","-CMD","@SUM(1)","bad\nunit",""]:
            frame=self.frame.copy();frame["Unit"]=label
            with self.assertRaises(ValueError):self.ledger(frame)
        with self.assertRaisesRegex(ValueError,"different source"):
            self.ledger(mapping={**self.mapping,"actual":"Plan"})

    def test_cash_requires_matching_keys_and_reconciliation(self):
        ledger=self.ledger()
        cash=pd.DataFrame([{"month":"2026-01","business_unit":"Example unit","opening_cash_gbp":400,
                            "customer_receipts_gbp":900,"operating_payments_gbp":650,"capital_spend_gbp":50,
                            "financing_inflow_gbp":0,"closing_cash_gbp":600,"currency":"GBP"}])
        mapping={f:f for f in ["month","business_unit",*CASH_COLUMNS]}
        result=cash_from_table(cash,mapping,"YYYY-MM",ledger,currency_column="currency")
        self.assertEqual(result.closing_cash_gbp.iloc[0],600)
        for field,value,pattern in [("closing_cash_gbp",601,"reconcile"),("business_unit","Other","match"),("operating_payments_gbp",-5,"nonnegative")]:
            broken=cash.copy();broken.loc[0,field]=value
            with self.assertRaisesRegex(ValueError,pattern):cash_from_table(broken,mapping,"YYYY-MM",ledger,currency_column="currency")

    def test_readers_reject_invalid_headers_and_sizes(self):
        for data,name in [(b"a,a\n1,2\n","x.csv"),(b"a, a\n1,2\n","x.csv"),(b"a,b\n1\n","x.csv"),(b"","x.csv"),(b"x"*(MAX_BYTES+1),"x.csv"),(b"notzip","x.xlsx"),(b"a\n1","x.exe")]:
            with self.subTest(name=name),self.assertRaises(ValueError):read_table(data,name)

    def test_excel_sheet_selection_and_formula_rejection(self):
        buffer=BytesIO()
        with pd.ExcelWriter(buffer,engine="openpyxl") as writer:
            self.frame.to_excel(writer,sheet_name="Accounts",index=False)
            pd.DataFrame({"field":[1]}).to_excel(writer,sheet_name="Other",index=False)
        self.assertEqual(sheet_names(buffer.getvalue(),"x.xlsx"),["Accounts","Other"])
        self.assertEqual(len(self.ledger(read_table(buffer.getvalue(),"x.xlsx","Accounts"))),10)
        workbook=Workbook();sheet=workbook.active;sheet.append(["value"]);sheet.append(["=1+1"])
        buffer=BytesIO();workbook.save(buffer)
        with self.assertRaisesRegex(ValueError,"formulas"):read_table(buffer.getvalue(),"x.xlsx")

    def test_spreadsheet_safe_exports_preserve_numeric_negatives(self):
        frame=pd.DataFrame({"label":["=SUM(1)","+test","@test","normal"],"amount":[-10,0,2,3]})
        text=export_csv(frame).decode()
        self.assertIn("'=SUM(1),-10",text)
        self.assertIn("normal,3",text)


if __name__=="__main__":
    unittest.main()

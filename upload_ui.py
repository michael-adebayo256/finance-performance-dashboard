"""Session-scoped upload workflow; never caches or writes user files to disk."""
from hashlib import sha256
import json
from io import BytesIO
import pandas as pd
import streamlit as st
from finance import CATEGORIES, CASH_COLUMNS, pnl
from imports import sheet_names, read_table, ledger_from_table, cash_from_table, export_csv, DATE_FORMATS

NONE = "— Select a column —"
ALIASES = {"month":["month","date","period"],"business_unit":["business_unit","business unit","department","division"],
           "category":["category","account","account category"],"scenario":["scenario","type"],
           "amount_gbp":["amount_gbp","amount","value"],"actual":["actual","actual_gbp"],"budget":["budget","budget_gbp"]}
LABELS = {"month":"Month / date","business_unit":"Business unit","category":"Account category",
          "scenario":"Scenario","amount_gbp":"Amount (£)","actual":"Actual amount (£)","budget":"Budget amount (£)"}


def clear_uploads():
    # Called as a callback before widgets are created on the next run.
    for key in list(st.session_state):
        if key.startswith("import_"):
            del st.session_state[key]
    st.session_state.upload_epoch = st.session_state.get("upload_epoch",0)+1


def _example():
    return pd.DataFrame([{"month":"2026-01","business_unit":"Example unit","category":c,
                          "actual":a,"budget":b,"currency":"GBP"}
                         for c,a,b in zip(CATEGORIES,[100000,30000,25000,5000,10000],[95000,28000,26000,4500,11000])])


def _templates():
    ledger = _example()
    cash = pd.DataFrame([{"month":"2026-01","business_unit":"Example unit","opening_cash_gbp":40000,
                          "customer_receipts_gbp":90000,"operating_payments_gbp":65000,"capital_spend_gbp":5000,
                          "financing_inflow_gbp":0,"closing_cash_gbp":60000,"currency":"GBP"}])
    columns = st.columns(3)
    columns[0].download_button("Accounts CSV template",export_csv(ledger),"finance_accounts_template.csv","text/csv",key="template_accounts")
    columns[1].download_button("Cash CSV template",export_csv(cash),"finance_cash_template.csv","text/csv",key="template_cash")
    buffer=BytesIO()
    with pd.ExcelWriter(buffer,engine="openpyxl") as writer:
        ledger.to_excel(writer,sheet_name="Accounts",index=False)
        cash.to_excel(writer,sheet_name="Cash",index=False)
    columns[2].download_button("Excel templates",buffer.getvalue(),"finance_templates.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="template_excel")


def _read(upload, prefix):
    data = upload.getvalue()
    names = sheet_names(data,upload.name)
    label = "Cash worksheet" if prefix.startswith("import_cash_") else "Accounts worksheet"
    sheet = st.radio(label,names,horizontal=len(names)<=4,key=prefix+"_sheet") if names != ["CSV"] else "CSV"
    frame = read_table(data,upload.name,sheet)
    st.caption(f"{len(frame):,} rows · {len(frame.columns)} columns. Only mapped fields enter the dashboard.")
    # A sheet change must also reset mapping widget identities, not just the data.
    return frame, sha256(data + b"\0" + sheet.encode("utf-8")).hexdigest()


def _map_columns(frame, fields, prefix):
    mapping={};columns=st.columns(2)
    options=[NONE,*frame.columns]
    for i,field in enumerate(fields):
        aliases=ALIASES.get(field,[field])
        default=next((c for c in frame.columns if c.lower() in aliases),NONE)
        mapping[field]=columns[i%2].selectbox(LABELS.get(field,field.replace("_gbp","").replace("_"," ").title()),options,index=options.index(default),key=prefix+"_"+field)
    return mapping


def _currency(frame,prefix):
    options=["No currency column",*frame.columns]
    default=next((c for c in frame.columns if c.lower() in ["currency","currency_code"]),options[0])
    column=st.selectbox("Currency column",options,index=options.index(default),key=prefix+"_currency")
    confirmed=False
    if column==options[0]:
        column=None
        confirmed=st.checkbox("I confirm every amount is in GBP (pounds), with no currency conversion needed.",key=prefix+"_gbp")
    return column,confirmed


def _value_map(frame,column,targets,label,prefix):
    if column not in frame.columns:
        return {}
    if frame[column].isna().any():
        raise ValueError(f"{label} contains missing values.")
    values=sorted(frame[column].astype(str).str.strip().unique())
    if len(values)>50:
        raise ValueError(f"{label} has more than 50 distinct labels. Use a monthly summary file.")
    if any(not value or len(value)>80 or any(ord(c)<32 for c in value) for value in values):
        raise ValueError(f"{label} labels must be nonempty, at most 80 characters and contain no control characters.")
    result={}
    for i,value in enumerate(values):
        default=next((t for t in targets if t.casefold()==value.casefold()),"— Map this label —")
        options=["— Map this label —",*targets]
        result[value]=st.selectbox(f"{label}: {value}",options,index=options.index(default),key=f"{prefix}_{i}")
    return result


def render_import():
    """Return active (ledger, optional cash), or None until preview is accepted."""
    epoch=st.session_state.get("upload_epoch",0)
    has_active="import_active" in st.session_state
    with st.expander("Upload, map and validate financial data",expanded=not has_active):
        st.markdown("#### Start with a template")
        st.write("Use monthly account totals. CSV must be UTF-8 and comma-separated; Excel must be .xlsx with one header row and values only. Maximum: 5 MB per file, 10,000 rows and 30 columns.")
        _templates()
        with st.expander("How uploaded data are handled"):
            st.write("Files are sent to this app’s server for processing. The app holds uploaded files and applied data in your Streamlit session; it does not write them to disk, a database or GitHub, or put them in a shared data cache. Downloads return the data to your browser. No uploaded content is sent to an AI service.")
            st.write("Use anonymised company-level totals you are authorised to process. This public app has no sign-in or organisation access controls. Clear uploaded data removes this app’s session references and upload controls; it is not a promise of immediate secure memory erasure. Hosting infrastructure has its own data-handling policies.")
            st.link_button("Data-handling details", "https://github.com/michael-adebayo256/finance-performance-dashboard/blob/main/DATA_HANDLING.md")
        st.button("Clear uploaded data",on_click=clear_uploads,key="clear_import")
        account_file=st.file_uploader("Management accounts file",type=["csv","xlsx"],max_upload_size=5,key=f"import_accounts_{epoch}")
        cash_file=st.file_uploader("Cash movements file (optional)",type=["csv","xlsx"],max_upload_size=5,key=f"import_cash_{epoch}",help="Cash analysis is disabled if no cash file is supplied. You may upload the same Excel workbook twice and select different sheets.")
        if account_file is None:
            st.session_state.pop("import_active",None)
            st.session_state.pop("import_preview",None)
            st.info("Upload accounts to configure the column mapping. Demo data will never be mixed with uploaded data.")
            return None
        try:
            accounts,account_hash=_read(account_file,f"import_accounts_{epoch}")
            prefix=f"import_map_{epoch}_{account_hash[:12]}"
            layout=st.radio("Accounts layout",["Wide","Long"],horizontal=True,key=prefix+"_layout",help="Wide: separate actual/budget columns. Long: scenario and amount columns.")
            fields=["month","business_unit","category"]+(["actual","budget"] if layout=="Wide" else ["scenario","amount_gbp"])
            mapping=_map_columns(accounts,fields,prefix+layout)
            dates=st.selectbox("Accounts date format",list(DATE_FORMATS),key=prefix+"_dates",help="Excel date cells are recognised directly. Dates are normalised to the first day of their month.")
            currency,confirmed=_currency(accounts,prefix)
            st.markdown("#### Map account labels")
            categories=_value_map(accounts,mapping["category"],CATEGORIES,"Source account",prefix+"_category")
            scenarios=_value_map(accounts,mapping["scenario"],["Actual","Budget"],"Source scenario",prefix+"_scenario") if layout=="Long" else {}
            fill_unused=st.checkbox("Add zero rows for categories absent from the entire file",key=prefix+"_zero",help="Explicitly supplies unused categories only. Missing actual/budget pairs or periods still fail validation.")
            st.caption("Amounts are pounds with up to two decimal places. Use positive revenue and cost magnitudes; values are not scaled, sign-reversed or converted. Distinct source accounts mapped to the same category are summed after duplicate checks.")
            cash_frame=None;cash_hash="";cash_mapping={};cash_dates="YYYY-MM";cash_currency=None;cash_confirmed=False
            if cash_file is not None:
                st.markdown("#### Cash mapping")
                cash_frame,cash_hash=_read(cash_file,f"import_cash_{epoch}")
                cash_prefix=f"import_cash_map_{epoch}_{cash_hash[:12]}"
                cash_mapping=_map_columns(cash_frame,["month","business_unit",*CASH_COLUMNS],cash_prefix)
                cash_dates=st.selectbox("Cash date format",list(DATE_FORMATS),key=cash_prefix+"_dates")
                cash_currency,cash_confirmed=_currency(cash_frame,cash_prefix)
            signature=sha256(json.dumps([account_hash,cash_hash,layout,mapping,dates,currency,confirmed,categories,scenarios,fill_unused,cash_mapping,cash_dates,cash_currency,cash_confirmed],sort_keys=True).encode()).hexdigest()
            for name in ["import_preview","import_active"]:
                if name in st.session_state and st.session_state[name]["signature"]!=signature:
                    st.session_state.pop(name)
            if st.button("Validate and preview",type="primary",key="validate_import"):
                st.session_state.pop("import_preview",None)
                st.session_state.pop("import_active",None)
                ledger=ledger_from_table(accounts,mapping,layout,dates,categories,scenarios,currency,confirmed,fill_unused)
                cash=cash_from_table(cash_frame,cash_mapping,cash_dates,ledger,cash_currency,cash_confirmed) if cash_frame is not None else None
                st.session_state.import_preview={"signature":signature,"ledger":ledger,"cash":cash}
            preview=st.session_state.get("import_preview")
            if preview:
                ledger=preview["ledger"];cash=preview["cash"]
                st.success(f"Validation passed: {len(ledger):,} account records, {ledger.business_unit.nunique()} business units, {ledger.month.nunique()} months. Cash: {'validated' if cash is not None else 'not supplied' }.")
                st.caption("Preview of normalised account records (first 20); check these before applying.")
                st.dataframe(ledger.head(20),hide_index=True,width="stretch")
                st.dataframe(pnl(ledger)[["Actual","Budget"]].style.format("£{:,.2f}"),width="stretch")
                if cash is not None:
                    st.caption("Normalised cash preview (first 10).")
                    st.dataframe(cash.head(10),hide_index=True,width="stretch")
                if st.button("Use validated data",type="primary",key="apply_import"):
                    st.session_state.import_active=preview
                    st.rerun()
        except ValueError as error:
            st.session_state.pop("import_active",None)
            st.session_state.pop("import_preview",None)
            st.error(str(error))
        except Exception:
            st.session_state.pop("import_active",None)
            st.session_state.pop("import_preview",None)
            st.error("The import could not be processed. Check the template, format and mapped fields; no uploaded data were applied.")
        active=st.session_state.get("import_active")
    return (active["ledger"],active["cash"]) if active else None

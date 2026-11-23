"""Finance Lens — fictional company management reporting portfolio dashboard."""
from pathlib import Path
from html import escape
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from finance import load_data, pnl, monthly_summary, profit_bridge, cash_summary, percent, CATEGORIES
from themes import PALETTES
from comparisons import period_comparison, review_flags, COMPARISON_BASES, THRESHOLD_RULES
from imports import export_csv
from upload_ui import render_import, clear_uploads

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title="Finance Lens | Performance & Variance", page_icon="◈", layout="wide")
# Native appearance changes trigger a rerun and stay local to the viewer.
# No process-wide theme mutation: concurrent viewers can use different modes.
mode = st.context.theme.type or "dark"


@st.fragment(run_every="1s")
def sync_appearance():
    """Native theme changes update context on the next fragment request."""
    if (st.context.theme.type or "dark") != mode:
        st.rerun()


# Do not schedule background reruns while an import form is being completed.
# Active dashboards retain automatic theme synchronisation below.
if st.session_state.get("data_source") != "Upload files":
    sync_appearance()
palette = PALETTES[mode]
TEAL, BLUE, GOLD, RED = (palette[key] for key in ("teal", "blue", "gold", "red"))
css_variables = ";".join(f"--finance-{key.replace('_', '-')}: {value}" for key, value in palette.items() if key != "template")
st.markdown("<style>:root {" + css_variables + "}</style>", unsafe_allow_html=True)
st.markdown('''<style>
.stApp {background:var(--finance-background);color:var(--finance-text);}
.block-container {max-width:1600px;padding-top:4.5rem;}
[data-testid="stSidebar"] {background:var(--finance-sidebar);border-right:1px solid var(--finance-border);}
h1,h2,h3 {letter-spacing:-.035em;}
h1 {font-size:clamp(2rem,3vw,2.9rem)!important;line-height:1.14!important;}
.eyebrow {color:var(--finance-teal);font-size:.85rem;letter-spacing:.14em;font-weight:700;}
.intro {color:var(--finance-muted);font-size:1.05rem;max-width:850px;line-height:1.6;}
.demo {display:inline-block;padding:.35rem .7rem;border:1px solid var(--finance-demo-border);border-radius:6px;color:var(--finance-gold);font-size:.85rem;}
.metric-card {padding:1.2rem;background:var(--finance-surface);border:1px solid var(--finance-border);border-radius:12px;min-height:160px;margin-bottom:.8rem;}
.metric-label {color:var(--finance-muted);font-size:.95rem;}
.metric-value {font-size:clamp(1.65rem,2.4vw,2.5rem);font-weight:700;letter-spacing:-.04em;margin:.2rem 0;}
.metric-detail {font-size:.85rem;line-height:1.5;color:var(--finance-muted);}
.good {color:var(--finance-teal);} .bad {color:var(--finance-red);}
.insight {padding:1rem 1.2rem;border-left:3px solid var(--finance-teal);background:var(--finance-insight);border-radius:5px;line-height:1.7;margin-bottom:1rem;}
[data-testid="stPlotlyChart"] {border:1px solid var(--finance-border);border-radius:12px;overflow:hidden;}
[data-testid="stDownloadButton"] button {background:var(--finance-teal);color:var(--finance-button-text);border:0;font-weight:650;}
[data-testid="stDownloadButton"] button p {color:var(--finance-button-text);}
[data-testid="stDownloadButton"] button:focus-visible {outline:3px solid var(--finance-gold);outline-offset:3px;}
[data-testid="stTabs"] [role="tab"] {font-size:.95rem;}
@media(max-width:700px) {.block-container {padding:4rem 1rem 1rem;} .metric-card {min-height:130px;}}
</style>''', unsafe_allow_html=True)


@st.cache_data
def get_data():
    return load_data(BASE / "data")


def money(value, compact=False):
    sign = "−" if value < 0 else ""
    value = abs(value)
    if compact and value >= 1_000_000:
        return f"{sign}£{value / 1_000_000:.2f}m"
    if compact and value >= 1000:
        return f"{sign}£{value / 1000:,.0f}k"
    return f"{sign}£{value:,.0f}"


def chart(fig, height=360):
    fig.update_layout(template=palette["template"], height=height, paper_bgcolor=palette["surface"], plot_bgcolor=palette["surface"],
                      font=dict(color=palette["text"], size=13), margin=dict(l=20, r=22, t=85, b=35),
                      title=dict(x=.03, y=.98, xanchor="left", yanchor="top"),
                      legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom", title_text=""), hovermode="closest")
    fig.update_xaxes(gridcolor=palette["grid"], zeroline=False)
    fig.update_yaxes(gridcolor=palette["grid"], zeroline=False)
    st.plotly_chart(fig, width="stretch", theme=None)


def card(label, value, detail, good=None):
    color = "good" if good is True else "bad" if good is False else ""
    st.markdown(f'<div class="metric-card"><div class="metric-label">{escape(label)}</div><div class="metric-value">{escape(value)}</div><div class="metric-detail {color}">{escape(detail)}</div></div>', unsafe_allow_html=True)


def download(label, frame, filename, key):
    st.download_button(label, export_csv(frame), filename, "text/csv", key=key, on_click="ignore")


with st.sidebar:
    st.markdown("### ◈ Finance Lens")
    st.caption("MANAGEMENT REPORTING")
    source = st.radio("Data source",["Synthetic demo","Upload files"],key="data_source",on_change=clear_uploads)

is_upload = source == "Upload files"
source_label = "Uploaded data · GBP · Session only" if is_upload else "Synthetic company data · Portfolio demonstration"
st.markdown('<div class="eyebrow">FINANCE LENS / PERFORMANCE & VARIANCE</div>', unsafe_allow_html=True)
st.title("The numbers. The drivers. The decisions.")
st.markdown('<p class="intro">Explore operating performance, explain the gap to budget, and follow the movement of cash.</p><span class="demo">'+source_label.upper()+'</span>', unsafe_allow_html=True)
st.write("")
if is_upload:
    imported = render_import()
    if imported is None:
        st.info("Validate the mapped records, review the preview, then choose Use validated data to open the dashboard.")
        st.stop()
    ledger,cash = imported
    dataset_id = st.session_state.import_active["signature"]
    sync_appearance()
else:
    try:
        ledger,cash = get_data()
    except (ValueError,OSError) as error:
        st.error(f"Could not load the demonstration data: {error}")
        st.stop()
    dataset_id = "demo"
export_prefix = "finance" if is_upload else "synthetic"
with st.sidebar:
    year = st.selectbox("Reporting year", sorted(ledger.month.dt.year.unique(), reverse=True),key="year_"+dataset_id)
    months = sorted(ledger.loc[ledger.month.dt.year == year, "month"].unique())
    if len(months) == 1:
        start = end = months[0]
        st.caption(f"Reporting period: {pd.Timestamp(start):%b %Y}")
    else:
        start, end = st.select_slider("Reporting period", options=months, value=(months[0], months[-1]), format_func=lambda d:pd.Timestamp(d).strftime("%b"),key="period_"+dataset_id+str(year))
    units = st.multiselect("Business units", sorted(ledger.business_unit.unique()), default=sorted(ledger.business_unit.unique()),key="units_"+dataset_id)
    with st.expander("Investigation thresholds"):
        amount_threshold = st.number_input("Pound threshold (£)",min_value=0.0,value=10000.0,step=1000.0,format="%.2f",key="review_gbp")
        percentage_threshold = st.number_input("Percentage threshold (%)",min_value=0.0,max_value=10000.0,value=5.0,step=1.0,key="review_pct")
        threshold_rule = st.radio("Flag a nonzero change meeting",THRESHOLD_RULES,key="review_rule")
        st.caption("Inclusive limits on absolute changes. If a percentage is unavailable, the pound test alone applies under either rule. These are investigation filters, not statutory materiality.")
    st.divider()
    st.markdown("**GBP · Uploaded data**" if is_upload else "**GBP · Fictional data**")
    st.caption("Using validated uploaded totals in this session. Validation does not audit their accuracy." if is_upload else "January 2025–October 2026. All values are synthetic and generated for this portfolio project.")
    st.caption("Filters apply to every tab. Opening and closing cash use the selected period’s boundaries, when cash data are supplied.")
    st.caption("Created by Michael Adebayo")
    st.divider()
    st.caption(f"Appearance: {mode.title()}. Switch in the top-right menu (⋮ → Light / Dark). Streamlit remembers your choice in this browser.")

if not units:
    st.info("Select at least one business unit in the sidebar to display the analysis.")
    st.stop()
selection = ledger[ledger.month.between(start, end) & ledger.business_unit.isin(units)].copy()
selected_cash = cash[cash.month.between(start, end) & cash.business_unit.isin(units)].copy() if cash is not None else None
statement = pnl(selection)
budget_review = review_flags(statement,amount_threshold,percentage_threshold,threshold_rule)
trend = monthly_summary(selection)
period = f"{pd.Timestamp(start):%b %Y} – {pd.Timestamp(end):%b %Y}"
st.caption(f"{period}  /  {len(units)} business unit{'s' if len(units) != 1 else ''}  /  Actual versus original budget")
revenue = statement.loc["Revenue"]
profit = statement.loc["Operating profit"]
margin = percent(profit.Actual, revenue.Actual)
budget_margin = percent(profit.Budget, revenue.Budget)
cash_values, cash_trend = cash_summary(selected_cash) if selected_cash is not None else (None,None)
columns = st.columns(4)
with columns[0]:
    card("Revenue", money(revenue.Actual, True), f"{money(revenue['Variance £'])} vs budget", bool(revenue["Profit impact £"] >= 0))
with columns[1]:
    card("Operating profit", money(profit.Actual, True), f"{money(profit['Variance £'])} vs budget", bool(profit["Profit impact £"] >= 0))
with columns[2]:
    card("Operating margin", f"{margin:.1f}%" if margin is not None else "N/A", f"{margin - budget_margin:+.1f} percentage points vs budget" if margin is not None and budget_margin is not None else "Revenue is zero; margin unavailable", bool(margin >= budget_margin) if margin is not None and budget_margin is not None else None)
with columns[3]:
    if cash_values is None:
        card("Closing cash", "Not supplied", "A separate cash file is needed.")
    else:
        card("Closing cash", money(cash_values["Closing cash"], True), f"Opening cash {money(cash_values['Opening cash'], True)}")

overview, variance, comparison_tab, cash_tab, detail, methodology = st.tabs(["Performance", "Budget variance", "Prior periods", "Cash movement", "Data & exports", "Methodology"])

with overview:
    st.subheader("Performance at a glance")
    impacts = statement.loc[CATEGORIES, "Profit impact £"]
    adverse = impacts[impacts < -.005]
    largest = adverse.idxmin() if len(adverse) else None
    gap = profit["Variance £"]
    summary = f"Operating profit is {money(abs(gap))} {'above' if gap >= 0 else 'below'} budget for {period}. "
    if largest:
        summary += f"The largest adverse category contribution is {largest.lower()} ({money(abs(impacts[largest]))}). "
    else:
        summary += "No category has an adverse profit contribution in this selection. "
    summary += f"{int(budget_review.loc[CATEGORIES, 'Flagged for review'].sum())} of 5 underlying category variances meet the current investigation thresholds. "
    summary += "This identifies an area to investigate; the aggregate data do not establish its underlying cause."
    st.markdown(f'<div class="insight">{escape(summary)}</div>', unsafe_allow_html=True)
    left, right = st.columns([1.2, 1])
    with left:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=trend.month, y=trend["Actual revenue"], name="Actual revenue", marker_color=TEAL))
        fig.add_trace(go.Scatter(x=trend.month, y=trend["Budget revenue"], name="Budget revenue", line=dict(color=GOLD, dash="dash", width=2)))
        fig.update_layout(title="Monthly revenue · actual vs budget", yaxis_tickprefix="£", xaxis_tickformat="%b %Y", xaxis_tickvals=trend.month)
        chart(fig)
    with right:
        unit_rows = []
        for unit, group in selection.groupby("business_unit"):
            unit_pnl = pnl(group)
            unit_rows.append({"Business unit":unit, "Actual":unit_pnl.loc["Operating profit", "Actual"], "Budget":unit_pnl.loc["Operating profit", "Budget"]})
        unit_data = pd.DataFrame(unit_rows)
        fig = px.bar(unit_data.melt(id_vars="Business unit", var_name="Scenario", value_name="Operating profit"), x="Business unit", y="Operating profit", color="Scenario", barmode="group", color_discrete_map={"Actual":TEAL, "Budget":BLUE}, title="Operating profit by business unit")
        fig.update_yaxes(tickprefix="£")
        chart(fig)
    fig = go.Figure()
    for scenario, color in [("Actual",TEAL),("Budget",GOLD)]:
        fig.add_trace(go.Scatter(x=trend.month, y=trend[f"{scenario} margin %"], name=f"{scenario} margin", mode="lines+markers", line=dict(color=color, dash="solid" if scenario == "Actual" else "dash")))
    fig.update_layout(title="Operating margin trend", yaxis_ticksuffix="%", xaxis_tickformat="%b %Y", xaxis_tickvals=trend.month)
    chart(fig, 300)
    st.caption("Period margin is total operating profit ÷ total revenue, rather than an average of monthly percentages.")

with variance:
    st.subheader("Explain the gap to budget")
    st.caption("Variance = Actual − Budget. For costs, spending above budget is adverse. Profit impact reverses the cost sign so positive always means favourable.")
    labels, values = profit_bridge(statement)
    fig = go.Figure(go.Waterfall(x=labels, y=values, measure=["absolute"]+["relative"]*len(CATEGORIES)+["total"], increasing=dict(marker_color=TEAL), decreasing=dict(marker_color=RED), totals=dict(marker_color=BLUE), connector=dict(line=dict(color=palette["muted"]))))
    fig.update_layout(title="Budget-to-actual operating profit bridge", yaxis_tickprefix="£")
    chart(fig, 420)
    st.caption("Each category appears once in the bridge. Gross profit and operating-cost subtotals are excluded to avoid double counting.")
    st.markdown("#### Management profit and loss")
    flagged_count = int(budget_review.loc[CATEGORIES,"Flagged for review"].sum())
    st.caption(f"{flagged_count} of 5 underlying categories flagged · £{amount_threshold:,.2f} / {percentage_threshold:g}% · {threshold_rule.lower()}. Subtotals are not included in this count. Flags never alter totals.")
    view = budget_review.drop(columns="Flagged for review").reset_index(names="Line item")
    st.dataframe(view.style.format({"Actual":"£{:,.2f}","Budget":"£{:,.2f}","Variance £":"£{:+,.2f}","Variance %":"{:+.1f}%","Profit impact £":"£{:+,.2f}"}, na_rep="N/A"), hide_index=True, width="stretch", height=340)
    pnl_export = view.assign(current_start=pd.Timestamp(start).strftime("%Y-%m"),current_end=pd.Timestamp(end).strftime("%Y-%m"),business_units="; ".join(units),threshold_gbp=amount_threshold,threshold_pct=percentage_threshold,threshold_rule=threshold_rule)
    download("Download selected P&L", pnl_export, f"{export_prefix}_pnl.csv", "pnl_download")
    st.caption("Costs are displayed as positive magnitudes. Gross profit = Revenue − Direct costs; operating profit also deducts People, Sales & marketing and Administration. No tax, interest or other income is modelled.")

with comparison_tab:
    st.subheader("Compare actual performance over time")
    basis = st.radio("Comparison basis",COMPARISON_BASES,horizontal=True,key="comparison_basis")
    comparison = period_comparison(ledger,start,end,units,basis)
    reference_label = f"{comparison['reference_start']:%b %Y} – {comparison['reference_end']:%b %Y}"
    st.caption(f"Current: {period} · Reference: {reference_label} · {comparison['months']} month(s) each · Same {len(units)} selected business unit(s). Actual-to-actual comparison; budget figures are excluded.")
    if not comparison["available"]:
        missing_labels = ", ".join(f"{pd.Timestamp(m):%b %Y}" for m in comparison["missing_months"])
        st.info(f"Reference period unavailable: {comparison['missing_actual_records']} required Actual records are missing across {missing_labels}. No partial comparison or zero-filled reference is shown. Supply complete reference data or choose another period/basis.")
    else:
        compared = review_flags(comparison["table"],amount_threshold,percentage_threshold,threshold_rule,"Change £","Change %")
        cols = st.columns(3)
        for column,line in zip(cols[:2],["Revenue","Operating profit"]):
            row = compared.loc[line]
            detail_text = f"{money(row['Change £'])} vs reference; " + (f"{row['Change %']:+.1f}%" if pd.notna(row['Change %']) else "% unavailable")
            with column:
                card(line + " · current actual",money(row["Current actual"],True),detail_text,bool(row["Profit impact £"] >= 0))
        change = comparison["margin_change_pp"]
        with cols[2]:
            card("Operating margin change",f"{change:+.1f} pp" if change is not None else "N/A","Current margin minus reference margin",bool(change >= 0) if change is not None else None)
        fig = go.Figure()
        for label,color in [("Reference actual",BLUE),("Current actual",TEAL)]:
            fig.add_trace(go.Bar(x=["Revenue","Operating profit"],y=compared.loc[["Revenue","Operating profit"],label],name=label,marker_color=color))
        fig.update_layout(title="Current and reference actuals",barmode="group",yaxis_tickprefix="£")
        chart(fig,330)
        count = int(compared.loc[CATEGORIES,"Flagged for review"].sum())
        st.caption(f"{count} of 5 underlying category changes flagged for investigation. Review thresholds: £{amount_threshold:,.2f} / {percentage_threshold:g}% · {threshold_rule.lower()}. Favourable/adverse describes profit impact, not a causal conclusion.")
        compared_view = compared.drop(columns="Flagged for review").reset_index(names="Line item")
        st.dataframe(compared_view.style.format({"Current actual":"£{:,.2f}","Reference actual":"£{:,.2f}","Change £":"£{:+,.2f}","Change %":"{:+.1f}%","Profit impact £":"£{:+,.2f}"},na_rep="N/A"),hide_index=True,width="stretch",height=340)
        comparison_export = compared_view.assign(current_start=pd.Timestamp(start).strftime("%Y-%m"),current_end=pd.Timestamp(end).strftime("%Y-%m"),reference_start=comparison["reference_start"].strftime("%Y-%m"),reference_end=comparison["reference_end"].strftime("%Y-%m"),comparison_basis=basis,business_units="; ".join(units),threshold_gbp=amount_threshold,threshold_pct=percentage_threshold,threshold_rule=threshold_rule)
        download("Download prior-period comparison",comparison_export,f"{export_prefix}_prior_period_comparison.csv","comparison_download")
        st.caption("Change = current actual − reference actual. Change % is shown only for a positive reference actual; zero or loss baselines are N/A. Where % is unavailable, only the pound threshold is used. Margin change is in percentage points and is not threshold-tested.")

with cash_tab:
    st.subheader("Follow the cash")
    if selected_cash is None:
        st.info("Cash analysis is unavailable. Upload and validate a separate cash-movements file; cash balances cannot be inferred from a P&L.")
    else:
        st.caption("Cash is a separate ledger. Receipts and payments differ from accrual revenue and costs; profit and cash are distinct measures.")
        cash_labels = list(cash_values)
        cash_y = [cash_values["Opening cash"], cash_values["Customer receipts"], -cash_values["Operating payments"], -cash_values["Capital spend"], cash_values["Financing inflow"], cash_values["Closing cash"]]
        fig = go.Figure(go.Waterfall(x=cash_labels,y=cash_y,measure=["absolute"]+["relative"]*4+["total"],increasing=dict(marker_color=TEAL),decreasing=dict(marker_color=RED),totals=dict(marker_color=BLUE)))
        fig.update_layout(title="Opening-to-closing cash bridge", yaxis_tickprefix="£")
        chart(fig, 400)
        chart(px.line(cash_trend.reset_index(), x="month", y="closing_cash_gbp", markers=True, color_discrete_sequence=[TEAL], title="Month-end cash balance", labels={"closing_cash_gbp":"Closing cash (£)","month":"Month"}).update_xaxes(tickvals=cash_trend.index,tickformat="%b %Y"), 300)
        download("Download selected cash movements", selected_cash, f"{export_prefix}_cash_movements.csv", "cash_download")
        st.info("This bridge reconciles opening and closing cash. It is a management illustration, not a statutory cash-flow statement or a forecast.")
with detail:
    st.subheader("Trace the numbers")
    st.caption("Every metric is derived from the records in the selected year, period and business units. The extra filters below affect only this table and its download.")
    categories = st.multiselect("Account categories", CATEGORIES, default=CATEGORIES)
    scenarios = st.multiselect("Scenarios", ["Actual","Budget"], default=["Actual","Budget"])
    records = selection[selection.category.isin(categories) & selection.scenario.isin(scenarios)].sort_values(["month","business_unit","category","scenario"])
    st.caption(f"{len(records):,} of {len(selection):,} selected ledger records displayed. All amounts are GBP.")
    st.dataframe(records, hide_index=True, width="stretch", column_config={"amount_gbp":st.column_config.NumberColumn("Amount (£)",format="£%.2f"),"month":st.column_config.DateColumn("Month",format="MMM YYYY")}, height=440)
    download("Download displayed ledger records", records, f"{export_prefix}_management_accounts.csv", "ledger_download")
    with st.expander("Data quality checks"):
        st.write(f"Validated {len(ledger):,} ledger rows: required fields, consecutive months, unique keys, complete actual/budget combinations and finite nonnegative amounts.")
        st.write(f"Validated {len(cash):,} cash rows: matching periods/units, reconciled cash bridges and opening-balance continuity." if cash is not None else "Cash data were not supplied; no cash values have been inferred.")
        st.write("No missing values were silently dropped or imputed.")

with methodology:
    st.subheader("Definitions & assumptions")
    st.markdown("**Current source:** Uploaded records held in this session." if is_upload else "**Current source:** Reproducible synthetic demo.")
    st.markdown('''
**Purpose.** A finance analyst tool by Michael Adebayo. Synthetic demo mode uses fictional data generated for demonstration. Upload mode uses only the mapped records you explicitly validate and apply; demo and uploaded records are never combined.

**Period and currency.** GBP throughout; uploaded data must be confirmed GBP or have a GBP currency column. Demo mode covers January 2025–October 2026; “Actual” is synthetic in that mode. Uploaded periods come from your mapped dates. Dates are normalised to months. Budget figures are treated as the supplied comparison plan, not a forecast.

**Revenue and costs.** The management ledger stores positive amounts by month, business unit, category and scenario. Uploaded account labels are explicitly mapped to the five supported categories, and distinct source-account totals in the same category are summed. Duplicate month/unit/source-account/scenario rows are rejected. Unused categories are filled with zero only with explicit approval; incomplete actual/budget pairs are rejected. Costs are subtracted when calculating profit. The simplified operating profit measure is not net income; no tax, interest, depreciation schedule or balance sheet is modelled.

**Variances.** Monetary variance is actual minus budget. Percentage variance divides that difference by budget; zero budget is shown as N/A. Revenue and profit increases are favourable; cost increases are adverse. “Favourable” describes the arithmetic comparison, not proof of a good business decision.

**Prior periods.** Compare actuals for the same selected business units against the same months one year earlier, or the immediately preceding equal-length period. Every required reference month/unit/category Actual record must be present; otherwise the reference is unavailable. No partial periods or inferred zero references are compared. Change percentages are N/A when reference actuals are zero or negative; monetary changes still display. Comparisons use only the active data source, never another viewer’s uploads or the demo as a reference for uploaded data.

**Investigation thresholds.** The sidebar pound and percentage limits are inclusive and use absolute changes. Either threshold flags a nonzero line meeting at least one limit; Both thresholds requires both where a percentage exists. If the percentage is unavailable, only the pound test applies, labelled explicitly. Zero-change lines are not flagged even with zero limits. Flags apply to both budget variances and period changes without changing totals. Counts cover the five underlying categories, excluding derived subtotals; these are user-defined investigation limits, not statutory materiality or an audit conclusion.

**Margins.** Operating margin is operating profit divided by revenue. Margin variance is expressed in percentage points. Period totals are used to calculate the period margin.

**Cash.** Opening cash + customer receipts − operating payments − capital spend + financing inflow = closing cash. Cash requires a separate validated file. Within each business unit, the next month starts with the previous month’s closing balance. The period view uses the first opening and last closing balance rather than summing balances. Business-unit balances are additive demo allocations; intercompany transfers and consolidation adjustments are not modelled.

**Interpretation.** The displayed commentary identifies the largest adverse category contribution, not a causal explanation. The data do not support customer-level, invoice-level or product-level conclusions. There is no forecasting or investment advice feature.

**Reproducibility.** `generate_data.py` uses a fixed seed for demo mode. User uploads are not bundled, cached globally, saved to disk or sent to an AI service. They are held in the current Streamlit session; use Clear uploaded data to remove application references and reset the upload controls. This is not a guarantee of immediate secure memory erasure. See the upload panel for the data-handling explanation. Reconciliation and import validation tests are included in the repository.
''')
    st.link_button("Michael Adebayo · LinkedIn", "https://www.linkedin.com/in/michael-adebayo-223b0722/")

st.divider()
st.caption(f"FINANCE LENS · Michael Adebayo · {source_label} · GBP")

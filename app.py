"""Finance Lens — fictional company management reporting portfolio dashboard."""
from pathlib import Path
from html import escape
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from finance import load_data, pnl, monthly_summary, profit_bridge, cash_summary, percent, CATEGORIES
from themes import PALETTES

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
    st.download_button(label, frame.to_csv(index=False).encode("utf-8"), filename, "text/csv", key=key)


try:
    ledger, cash = get_data()
except (ValueError, OSError) as error:
    st.error(f"Could not load the demonstration data: {error}")
    st.stop()

with st.sidebar:
    st.markdown("### ◈ Finance Lens")
    st.caption("MANAGEMENT REPORTING")
    year = st.selectbox("Reporting year", sorted(ledger.month.dt.year.unique(), reverse=True))
    months = sorted(ledger.loc[ledger.month.dt.year == year, "month"].unique())
    start, end = st.select_slider("Reporting period", options=months, value=(months[0], months[-1]), format_func=lambda d:pd.Timestamp(d).strftime("%b"))
    units = st.multiselect("Business units", sorted(ledger.business_unit.unique()), default=sorted(ledger.business_unit.unique()))
    st.divider()
    st.markdown("**GBP · Fictional data**")
    st.caption("January 2025–October 2026. All values are synthetic and generated for this portfolio project.")
    st.caption("Filters apply to every tab. Opening and closing cash use the selected period’s boundaries.")
    st.caption("Created by Michael Adebayo")
    st.divider()
    st.caption(f"Appearance: {mode.title()}. Switch in the top-right menu (⋮ → Light / Dark). Streamlit remembers your choice in this browser.")

st.markdown('<div class="eyebrow">FINANCE LENS / PERFORMANCE & VARIANCE</div>', unsafe_allow_html=True)
st.title("The numbers. The drivers. The decisions.")
st.markdown('<p class="intro">Explore operating performance, explain the gap to budget, and follow the movement of cash.</p><span class="demo">SYNTHETIC COMPANY DATA · PORTFOLIO DEMONSTRATION</span>', unsafe_allow_html=True)
st.write("")
if not units:
    st.info("Select at least one business unit in the sidebar to display the analysis.")
    st.stop()
selection = ledger[ledger.month.between(start, end) & ledger.business_unit.isin(units)].copy()
selected_cash = cash[cash.month.between(start, end) & cash.business_unit.isin(units)].copy()
statement = pnl(selection)
trend = monthly_summary(selection)
period = f"{pd.Timestamp(start):%b %Y} – {pd.Timestamp(end):%b %Y}"
st.caption(f"{period}  /  {len(units)} business unit{'s' if len(units) != 1 else ''}  /  Actual versus original budget")
revenue = statement.loc["Revenue"]
profit = statement.loc["Operating profit"]
margin = percent(profit.Actual, revenue.Actual)
budget_margin = percent(profit.Budget, revenue.Budget)
cash_values, cash_trend = cash_summary(selected_cash)
columns = st.columns(4)
with columns[0]:
    card("Revenue", money(revenue.Actual, True), f"{money(revenue['Variance £'])} vs budget", bool(revenue["Profit impact £"] >= 0))
with columns[1]:
    card("Operating profit", money(profit.Actual, True), f"{money(profit['Variance £'])} vs budget", bool(profit["Profit impact £"] >= 0))
with columns[2]:
    card("Operating margin", f"{margin:.1f}%" if margin is not None else "N/A", f"{margin - budget_margin:+.1f} percentage points vs budget" if margin is not None and budget_margin is not None else "Revenue is zero; margin unavailable", bool(margin >= budget_margin) if margin is not None and budget_margin is not None else None)
with columns[3]:
    card("Closing cash", money(cash_values["Closing cash"], True), f"Opening cash {money(cash_values['Opening cash'], True)}")

overview, variance, cash_tab, detail, methodology = st.tabs(["Performance", "Budget variance", "Cash movement", "Data & exports", "Methodology"])

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
    summary += "This identifies an area to investigate; the aggregate data do not establish its underlying cause."
    st.markdown(f'<div class="insight">{escape(summary)}</div>', unsafe_allow_html=True)
    left, right = st.columns([1.2, 1])
    with left:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=trend.month, y=trend["Actual revenue"], name="Actual revenue", marker_color=TEAL))
        fig.add_trace(go.Scatter(x=trend.month, y=trend["Budget revenue"], name="Budget revenue", line=dict(color=GOLD, dash="dash", width=2)))
        fig.update_layout(title="Monthly revenue · actual vs budget", yaxis_tickprefix="£", xaxis_tickformat="%b %Y")
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
    fig.update_layout(title="Operating margin trend", yaxis_ticksuffix="%", xaxis_tickformat="%b %Y")
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
    view = statement.reset_index(names="Line item")
    st.dataframe(view.style.format({"Actual":"£{:,.2f}","Budget":"£{:,.2f}","Variance £":"£{:+,.2f}","Variance %":"{:+.1f}%","Profit impact £":"£{:+,.2f}"}, na_rep="N/A"), hide_index=True, width="stretch", height=340)
    download("Download selected P&L", view, "synthetic_pnl.csv", "pnl_download")
    st.caption("Costs are displayed as positive magnitudes. Gross profit = Revenue − Direct costs; operating profit also deducts People, Sales & marketing and Administration. No tax, interest or other income is modelled.")

with cash_tab:
    st.subheader("Follow the cash")
    st.caption("Cash is a separate synthetic ledger. Receipts and payments differ from accrual revenue and costs; profit and cash are distinct measures.")
    cash_labels = list(cash_values)
    cash_y = [cash_values["Opening cash"], cash_values["Customer receipts"], -cash_values["Operating payments"], -cash_values["Capital spend"], cash_values["Financing inflow"], cash_values["Closing cash"]]
    fig = go.Figure(go.Waterfall(x=cash_labels,y=cash_y,measure=["absolute"]+["relative"]*4+["total"],increasing=dict(marker_color=TEAL),decreasing=dict(marker_color=RED),totals=dict(marker_color=BLUE)))
    fig.update_layout(title="Opening-to-closing cash bridge", yaxis_tickprefix="£")
    chart(fig, 400)
    chart(px.line(cash_trend.reset_index(), x="month", y="closing_cash_gbp", markers=True, color_discrete_sequence=[TEAL], title="Month-end cash balance", labels={"closing_cash_gbp":"Closing cash (£)","month":"Month"}), 300)
    download("Download selected cash movements", selected_cash, "synthetic_cash_movements.csv", "cash_download")
    st.info("This bridge reconciles opening and closing cash. It is a management illustration, not a statutory cash-flow statement or a forecast.")

with detail:
    st.subheader("Trace the numbers")
    st.caption("Every metric is derived from the records in the selected year, period and business units. The extra filters below affect only this table and its download.")
    categories = st.multiselect("Account categories", CATEGORIES, default=CATEGORIES)
    scenarios = st.multiselect("Scenarios", ["Actual","Budget"], default=["Actual","Budget"])
    records = selection[selection.category.isin(categories) & selection.scenario.isin(scenarios)].sort_values(["month","business_unit","category","scenario"])
    st.caption(f"{len(records):,} of {len(selection):,} selected ledger records displayed. All amounts are GBP.")
    st.dataframe(records, hide_index=True, width="stretch", column_config={"amount_gbp":st.column_config.NumberColumn("Amount (£)",format="£%.2f"),"month":st.column_config.DateColumn("Month",format="MMM YYYY")}, height=440)
    download("Download displayed ledger records", records, "synthetic_management_accounts.csv", "ledger_download")
    with st.expander("Data quality checks"):
        st.write(f"Validated {len(ledger):,} ledger rows and {len(cash):,} cash rows: required fields, unique keys, complete actual/budget pairs, finite amounts, cash reconciliation and opening-balance continuity.")
        st.write("No missing values were silently dropped or imputed.")

with methodology:
    st.subheader("Definitions & assumptions")
    st.markdown('''
**Purpose.** A finance analyst portfolio project by Michael Adebayo. The fictional company, business units, budget, financial results and cash movements were generated for demonstration. They are not extracted from a real employer or client.

**Period and currency.** January 2025–October 2026; GBP throughout. “Actual” labels a synthetic scenario, not genuine transactions. The budget represents a fixed original plan; it is not a revised forecast.

**Revenue and costs.** The management ledger stores positive amounts by month, business unit, category and scenario. Costs are subtracted when calculating profit. The simplified operating profit measure is not net income; no tax, interest, depreciation schedule or balance sheet is modelled.

**Variances.** Monetary variance is actual minus budget. Percentage variance divides that difference by budget; zero budget is shown as N/A. Revenue and profit increases are favourable; cost increases are adverse. “Favourable” describes the arithmetic comparison, not proof of a good business decision.

**Margins.** Operating margin is operating profit divided by revenue. Margin variance is expressed in percentage points. Period totals are used to calculate the period margin.

**Cash.** Opening cash + customer receipts − operating payments − capital spend + financing inflow = closing cash. Within each business unit, the next month starts with the previous month’s closing balance. The period view uses the first opening and last closing balance rather than summing balances. Business-unit balances are additive demo allocations; intercompany transfers and consolidation adjustments are not modelled.

**Interpretation.** The displayed commentary identifies the largest adverse category contribution, not a causal explanation. The data do not support customer-level, invoice-level or product-level conclusions. There is no forecasting or investment advice feature.

**Reproducibility.** `generate_data.py` uses a fixed seed. The two CSVs are bundled with the app; regenerating the data is optional. Reconciliation tests and financial definitions are included in the repository.
''')
    st.link_button("Michael Adebayo · LinkedIn", "https://www.linkedin.com/in/michael-adebayo-223b0722/")

st.divider()
st.caption("FINANCE LENS · Michael Adebayo · Synthetic data for portfolio demonstration · GBP")

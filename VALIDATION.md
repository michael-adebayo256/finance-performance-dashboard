# Validation — 22 November 2026

## Environment

Executed with Python 3.12.3, Streamlit 1.67.0, Pandas 3.1.1, NumPy 2.5.5 and Plotly 7.1.0. The existing local Python environment was used; dependencies were not added to or changed in the World Happiness project. Browser tooling ran from a separate temporary environment.

## Financial and dataset validation

- Six unittest cases passed: profit identities and bridge reconciliation across each month/unit; favourable/adverse signs and zero budget; period cash boundaries and bridge reconciliation; monthly-to-period agreement; unit additivity; rejection of broken cash and incomplete budget pairs.
- Schema, missingness, unique keys, complete actual/budget combinations, finite ledger/cash amounts, matching ledger/cash month-unit keys, cash bridge and balance continuity pass for 660 ledger records and 66 cash records.
- January–October 2026, all business units: actual revenue £3,617,542.98 versus £3,633,665.04 budget; actual operating profit £957,889.72 versus £1,024,518.98 budget. Operating profit variance is −£66,629.26.
- Same selection cash bridge: £1,364,611.84 opening + £3,572,876.13 receipts − £2,669,494.69 operating payments − £100,087.00 capital spend + £0.00 financing = £2,167,906.28 closing.
- These are computed results from the synthetic generator, not a real company's results.

## Streamlit execution

AppTest executed all five tabs without application exceptions and produced six nonempty Plotly chart specifications. Tested year changes, a single business-unit selection, empty account-category filters, a revenue-only detail filter and an empty business-unit selection. An empty unit selection shows an explanatory message instead of calculating misleading totals.

The standalone testing harness emitted Streamlit's expected missing ScriptRunContext warning; no application exceptions were observed in the passing run.

## Browser checks

Executed in headless Chromium against the local app on port 8602:

- Desktop viewport 1600 × 1400 and mobile viewport 390 × 844.
- All five tabs opened; the performance, variance and cash charts rendered.
- Downloaded the actual eight-line P&L CSV and independently recalculated operating profit from its revenue and four cost lines.
- Downloaded the actual ledger CSV: 300 records for January–October 2026.
- Changed reporting year to 2025 and observed 360 selected ledger records.
- At mobile width the sidebar could collapse, KPI cards stacked and the ledger download button remained visible after scrolling.
- No browser pageerror events or final Streamlit exception element were observed.
- Five real browser screenshots were saved in `screenshots/`. Desktop charts and mobile layout were visually inspected. A chart title/legend spacing issue found during inspection was corrected and browser checks repeated.

## Limits

This is a targeted smoke test, not exhaustive device/accessibility testing. A fresh dependency installation, Community Cloud build and public deployment have not been tested. No cloud credentials, user data upload or external finance integration is required. The dashboard does not contain real financial data, forecasts, a complete balance sheet or statutory accounts.

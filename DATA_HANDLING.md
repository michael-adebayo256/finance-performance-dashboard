# Data handling in Finance Lens

Last updated: 23 November 2026.

## What this application does

Upload mode accepts monthly company financial aggregates and an optional separate cash-movements file. The viewer chooses worksheets, maps columns/labels, validates a preview and explicitly applies the records. Only the normalised mapped fields enter the dashboard. The original uploaded file may still contain other columns, so remove unnecessary information before upload.

Files travel from the browser to the server running Streamlit. They are not processed exclusively on your device. The app reads uploaded bytes in memory and keeps preview/applied DataFrames in Streamlit Session State. The uploaded bytes, parsed records and financial results are not passed to a shared `st.cache_data` function, written to an application database, committed to GitHub or sent to an AI API. The only cached dataset is the bundled synthetic demo.

Downloads send CSV/XLSX output to the viewer's browser. A user-requested download can persist on that user's device. The app does not control those downloaded copies.

## Session scope and clearing

The application uses session-local state, not a shared uploaded-data collection. Another viewer starts in the synthetic demo. Clearing uploads resets uploader widget IDs and removes this app's references to previews, active records and mapping state. Switching to demo also clears imported state. Changes to files or mappings invalidate the previously applied dataset.

Streamlit and the hosting platform manage the lifecycle of upload buffers, disconnected sessions and server memory. Clearing is not a promise of immediate secure erasure, and a transient disconnect is not a reliable deletion mechanism. Browser reloads normally start a new Streamlit session; there is no durable save/recover feature in this app.

See Streamlit's [file-upload storage documentation](https://docs.streamlit.io/knowledge-base/using-streamlit/where-file-uploader-store-when-deleted) and [Session State documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state). Hosting services may process operational metadata under their own policies; the application code does not establish their full retention, backup or residency arrangements.

## Intended data and current boundaries

Use company-level totals you are authorised to process, with no customer/employee identifiers, bank details, credentials or unnecessary personal data. This is a publicly accessible portfolio app without user sign-in, organisational access controls or a contractual confidential-data service. Session isolation is not a substitute for those controls. Use the synthetic demo or anonymised aggregates for public-hosted testing.

The current release restricts file sizes, sheet/table dimensions, data formats and schema; rejects formulas/macros and invalid financial combinations; uses hardened XML parsing for XLSX; and avoids printing uploaded contents to application logs. Generic parser failures show a user-facing message, not a raw traceback containing file data. These controls are not a complete penetration test, security certification or compliance assessment.

## Contact

Contact [Michael Adebayo on LinkedIn](https://www.linkedin.com/in/michael-adebayo-223b0722/) with questions about the project or its data handling. This document describes the implemented application behaviour; it does not replace organisation-specific privacy information or hosting/provider agreements for a different production use.

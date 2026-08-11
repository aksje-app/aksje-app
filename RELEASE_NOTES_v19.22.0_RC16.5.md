# v19.22.0-rc16.5

Verified ZIP and Header Clock Hotfix.

- Replay-export worker is non-daemon and may finish after the initiating Streamlit rerun.
- Replay ZIP is written atomically and validated before COMPLETED status.
- Download payload is revalidated against SHA-256 before exposure.
- Replay status fragment uses the correct Streamlit alias and refreshes automatically.
- Single-report ZIP packages are integrity-checked before download.
- Main workspace shows the browser/PC clock immediately before the build version.
- Navigation, scheduler times, trading, score thresholds and report logic are unchanged.

# Release notes v19.22.0 RC16.2

## Scope
Avgrenset hotfix for automatisk fremdrift i Rapportsenteret.

## Endret
- Rapportsenteret bruker samme `render_shared_manual_job_progress`-komponent som Autonomi Oversikt.
- Samme dynamiske Streamlit-fragment med `run_every="5s"` brukes på begge sider.
- Samme autoritative `get_active_status()`-kilde brukes på begge sider.
- Rapportsenteret utløser ikke full app-rerun ved terminalstatus.

## Ikke endret
Rapportmotor, ZIP-eksport, tidssone, meny/CSS, score, beslutningsregler, scheduler, porteføljer og handel er uendret.

## Produksjonsstatus
Lokalt testet. Krever live Render-verifikasjon før godkjenning.

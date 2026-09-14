# RC16.31cs – Autonomy Continuity and Cash Exit

## Resultat

- De tre obligatoriske rapportjobbene reparerer alltid Autonomi, kontrollert læring og aktiv-porteføljekrav til påslått tilstand.
- Hver vellykket obligatorisk rapport kjører porteføljevurderingen. Avbrutt rapport lagrer en eksplisitt `BLOCKED_REPORT_ABORTED`-diagnose.
- Scheduler kontrollerer uavhengig når siste fullstendige autonomisyklus ble kjørt og varsler etter mer enn 24 børsdagstimer.
- Kontrollsenteret viser siste kjøring, kandidater, porteføljebeslutninger, siste kjøp, læringsstatus og neste planlagte kjøring.
- Hver porteføljebeslutning lagrer ticker, handling, årsakskode, begrunnelse, score, pris og salgsandel.
- Ukentlig tidligsignalrapport viser eksplisitt `NOT_DUE`, `ALREADY_COMPLETED`, `COMPLETED` eller `PUSHOVER_FAILED`.
- Ukentlig rapport er et heartbeat også når ingen produksjonsregel eller parameter er endret.
- Flat posisjon selges helt til kontanter etter 30 børsdager når avkastningen er høyst 1 % og score ikke er tydelig forbedret. Bedre erstatningsaksje er ikke påkrevd.
- En flat posisjon med klart forbedret score beskyttes og fortsetter til manuell/automatisk vurdering.

## Verifikasjon

- Python compileall: bestått for alle endrede produksjonsfiler.
- Målrettet pytest: 31 bestått, 1 kjent eldre inkonsistent test eksplisitt utelatt.
- Full pytest ble stoppet under innsamling av en eksisterende Streamlit-test fordi `current_user` var `None`; feilen oppstod ved import av `app.py`, før de nye testene ble kjørt.

## Endrede filer

- `app_version.py`
- `autonomous_orchestrator.py`
- `autonomous_orchestrator_ui.py`
- `exit_policy.py`
- `learning_observation_engine.py`
- `market_intelligence.py`
- `report_portfolio_intelligence.py`
- `scheduled_runner.py`
- `tests/test_rc16_31o_exit_policy.py`
- `tests/test_rc16_31cs_autonomy_continuity.py`

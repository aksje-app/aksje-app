# Akseptanse – v19.22.0 RC16.1

Hotfixen er godkjent først når en live Render-kjøring viser følgende:

1. Fremdriftsprosent, aktivt steg, siste fremdrift og heartbeat endres uten manuell nettleseroppdatering.
2. Linjen `Automatisk UI-poll: aktiv hvert 2. sekund` får nytt lesetidspunkt fortløpende.
3. Pollkilden er normalt `PROCESS_MEMORY` etter at jobben er startet.
4. Hele siden blir ikke stående nedtonet mellom oppdateringene.
5. Aktiv meny og rapportside forblir uendret under polling.
6. Terminalstatus vises uten automatisk full app-rerun.
7. Ingen endring i score-, scheduler-, portefølje- eller handelsregler.

Lokal validering er ikke produksjonsgodkjenning. Live Render-resultat kreves.

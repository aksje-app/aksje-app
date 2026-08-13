# v19.22.0-rc16.31b

RC16.31b stopper rapportflommen som oppstod da faste rapportprofiler beholdt 30-minutters skanningsvinduer og rapporttestmetadata.

## Rettet

- Morgen-, ettermiddags- og kveldsrapport kjører bare kl. 08:00, 14:00 og 22:00 Europe/Oslo.
- Eksisterende lagrede faste profiler renses automatisk for `scan_windows` og testserie-ID/del/forsøk.
- Automatisk rapporttest bygges fra en ren profil og kan ikke arve produksjonsjobbens identitet eller tidsvinduer.
- Bare den dedikerte testjobben kan presenteres som automatisk 1/4–4/4.
- En allerede sendt Pushover-kvittering behandles som idempotent leveringssuksess.
- Leveransetabellen bevarer tidligere dokumentert PDF- og Pushover-suksess selv om en senere retryrad feiler.

Paper Trading-skanneren, handler, strategier og læringsvarsler er ikke deaktivert eller endret av denne rettingen.


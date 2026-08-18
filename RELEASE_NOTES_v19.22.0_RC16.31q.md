# RC16.31q – Scheduler and Portfolio Navigation Closure

RC16.31q er bygget direkte fra RC16.31p og lukker avvik dokumentert i helgetesten 16.08.2026.

## Endringer

- De tre obligatoriske rapportene beholder operatørens helgevalg. Når helgekjøring er aktivert, inngår både lørdag og søndag.
- Rapportsenteret viser neste tidspunkt for morgen-, ettermiddags- og kveldsrapport samtidig, uavhengig av andre midlertidige jobbprofiler.
- Utløpte Pushover-leveringer terminaliseres som `EXPIRED_REPORT` og forsøkes ikke på nytt hver halvtime.
- En aktivert profil kan ikke fortsette å hete `Utkast`; den presenteres som `Analyse`.
- Porteføljeknappene mellom Oversikt, Autonom portefølje og Læringsportefølje har en eksplisitt regresjonskontrakt.
- Replay-regresjonen er selvstendig i FULL-pakken og avhenger ikke av en mappe utenfor distribusjonen.

## Uendret

Produksjonsterskel 73, kjøps-/salgsporter, risiko- og porteføljegrenser, Paper Trading-persistens, XAUUSD/UKOILUSD-mapping, AI Explainability og fail-closed produksjonshandel er uendret.


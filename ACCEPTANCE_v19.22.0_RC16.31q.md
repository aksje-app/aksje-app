# Akseptanse RC16.31q

RC16.31q kan godkjennes for deploy når:

1. APP_VERSION er `v19.22.0-rc16.31q` og PREVIOUS_APP_VERSION er `v19.22.0-rc16.31p`.
2. Faste rapporter har kun sine autoritative klokkeslett 08:00, 14:00 og 22:00 Europe/Oslo.
3. Helgevalg bevares ved innlasting; aktivert helgekjøring inkluderer lørdag og søndag.
4. De tre neste faste rapporttidene vises samtidig.
5. Utløpt Pushover-levering blir terminal og gjentas ikke.
6. Aktivert autosave-profil navngis `Analyse`, ikke `Utkast`.
7. Porteføljeknappene peker på kanoniske arbeidsflater.
8. Full aktiv testsamling har 0 feil, og historiske kontrakter er strict-xfail uten XPASS.
9. FULL, DELTA, deploynote, valideringsrapport, endringsinventar og SHA-256 følger leveransen.
10. Produksjonsklar status gis først etter live Render-verifisering av UI, PDF, JSON, logger, scheduler og Pushover.


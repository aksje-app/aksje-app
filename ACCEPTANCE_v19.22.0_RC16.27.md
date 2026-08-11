# Akseptanse – v19.22.0-rc16.27

Etter utrulling skal følgende kontrolleres på Render:

1. Versjonen viser `v19.22.0-rc16.27`.
2. En fast jobb viser alle seks markeder og 50 symboler per marked.
3. Rapportens skannekonfigurasjon viser planlagt maksimum 300, utvidet analyse 18 og evidenskontroll 15.
4. En testrapport bruker maksimalt fem NewsAPI-forespørsler; ordinær rapport maksimalt 15.
5. Døgnbudsjettet viser maksimalt 50 og reserve 10.
6. Læringskjøp i Pushover finnes med samme ticker og antall i PDF/TXT/JSON.
7. PDF-en viser score, risiko, datakvalitet og produksjonsblokkering for læringskjøp.
8. Gjentatt kjøring med samme `run_id` lager ingen ny læringshandel.
9. En pauset produksjonsportefølje sperrer produksjonskjøp, men stopper ikke den separate læringsvurderingen.
10. Rapport-ID og versjon er identiske i PDF, TXT og JSON, og ZIP-kontrollen består.

Godkjenn først etter en reell planlagt cron-kjøring uten aktiv nettleserøkt.

# Deploy – v19.22.0-rc16.34a

1. Merge PR #58 til main først etter grønn Release gate.
2. La Render bygge direkte fra main med runtime.txt / Python 3.12.13.
3. Behold eksisterende persistent storage/database; ingen state-migrering skal slette data.
4. Etter deploy: verifiser versjon v19.22.0-rc16.34a i UI.
5. Smoke-test på mobil:
   - Start -> Super Portfolio går direkte til Super Portfolio.
   - Marked=Norge + manuell ALM kan ikke returnere amerikansk ALM.
   - Super Portfolio PDF: åpne/del, kopier, print og retur går tilbake til Super Portfolio.
   - Start og Super Portfolio viser samme NAV/avkastning.
6. Ved avvik: stopp videre funksjonsendringer og bruk siste grønne main som rollback-referanse.

# Release notes v19.22.0 Investor Edition RC14

## Formål

RC14 gjennomfører en global navigasjons- og rerun-audit etter livefunnene i Rapporter og System. Målet er at lagring, refresh og andre handlinger skal beholde riktig hovedmeny og underfane uten å skrive til Streamlit-widgetnøkler etter at widgetene er opprettet.

RC14 fjerner også den automatiske helsidererenderingen fra rapportfremdriftsfragmentet. Denne helsidererenderingen kunne ved terminalstatus legge en ny komplett appvisning under den eksisterende og dermed gjenta hele siden.

## Endret

- Alle ordinære `st.rerun()`-kall går gjennom én global rutelås som lagrer synlig hovedrute, gruppe, panel, fane og underfane før rerun.
- Den globale rutelåsen forbrukes før sidefeltet og Kontrollsenterets widgeter opprettes.
- Eksplisitte navigasjonshandlinger beholder prioritet over den globale rutelåsen.
- Alternativ Kontrollsenter-meny bruker nå en applikasjonseid ventende gruppe i stedet for å endre `ai_control_center_group_v1863m` etter selectbox-opprettelse.
- Statisk audit av 292 aktive Python-filer fant 0 direkte literal-skrivinger til samme widgetnøkkel etter widgetopprettelse i samme funksjon.
- Visningstidssonen skrives gjennom den sentrale, versjonerte `reporting.ui`-konfigurasjonen.
- Lagret tidssone verifiseres ved ny lesing, og System → System/admin → Visning og tid forblir åpen etter lagring.
- Rapportfremdriftsfragmentet utfører ikke lenger automatisk full-app-rerun ved `COMPLETED`, `FAILED` eller `CANCELLED`.
- Rapportarkivet oppdateres ved neste vanlig sideoppdatering, uten å legge til en ny kopi av hele siden.
- Streamlit `1.57.0` og Starlette `1.3.1` beholdes låst for fungerende Render-kompatibilitet.

## Ikke endret

- `final_score`, kandidatvalg, rangering eller beslutningstrakt.
- Produksjons-, kjøps- eller varselterskler.
- Autonomis porteføljeregler eller Paper Trading.
- Faste schedulertider 08:00 og 22:00 Europe/Oslo.
- Pushover-, innloggings- eller Husk meg-regler.
- Produksjonshandel forblir fail-closed.
- Rapportinnhold, JSON-kontrakt eller PDF-renderer.

## Live-bekreftelse som gjenstår

RC14 er ikke produksjonsgodkjent før Render viser at hele siden bare rendres én gang ved rapportens terminalstatus, at tidssonen beholdes etter refresh/restart/deploy, og at lagring og handlinger i alle hovedmenyene beholder riktig rute.

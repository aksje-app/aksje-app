# RELEASE NOTES – v19.22.0 RC16.32c

## Super Portfolio Completion + Release Gate

RC16.32c bygger videre på RC16.32b og lukker de viktigste hullene som ble identifisert etter første Render-deploy.

### Nytt / ferdigstilt
- Automatisk Shadow-vurdering koblet til Render-scheduleren når en ny Investment Pipeline-kjøring foreligger.
- Daglig analyse/stop-overvåking, men ordinær rebalansering kun ukentlig (fredag som standard).
- Dynamisk hard stop kan utløse umiddelbar Shadow-exit uten å vente på ukentlig rebalansering.
- Dynamisk trailing stop bruker volatilitet og strammes ved større urealisert gevinst.
- Manuell exit får cooldown og aksjen følges fortsatt i egen Shadow-observasjon under cooldown.
- Korrelasjonsstraff kan nå beregnes ressurslett fra kandidatens allerede innhentede multi-horisont-avkastning, uten ekstra markedsnettverkskall.
- Automatisk Pushover ved faktiske Shadow-endringer og forverret stop-status, med delbar PDF-lenke.
- PDF kan nå både publiseres/deles og lastes ned direkte.
- Endringshistorikk, årsakskoder og «hvorfor er aksjen med?» vises i Super Portfolio.
- Forsiden får et kompakt Super Portfolio-vindu med Health, utvikling, Ranking Velocity, Challenger, Stop Pressure og siste handling/AI-råd.
- Direkteknapp åpner samme Super Portfolio-arbeidsflate.
- De to eksisterende markedsbannerne beholdes uendret. Super Portfolio-vinduet er et vanlig dashboard-vindu, ikke et tredje banner.
- Fast master-checkliste/release gate legges både i modulen og distribusjonen.

### Fortsatt eksplisitt delvis
- Ekstern Aurora/indeks-benchmark-feed er ikke koblet.
- Full scenario-basert Stress Radar er ikke bygget ennå.
- Eget Super Portfolio ressurs-panel er ikke bygget; eksisterende OOM breadcrumbs er fortsatt ressursgrunnlaget.

### Sikkerhet / produksjon
Super Portfolio er fortsatt SHADOW og påvirker ikke autoritativ Autonomy-, Paper Trading- eller scannerkjede og sender ingen ekte ordre.

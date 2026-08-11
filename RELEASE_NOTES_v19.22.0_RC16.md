# AI Aksje Analyzer Pro v19.22.0 Investor Edition RC16

RC16 samler rapportreplay, komplett arkiveksport, beslutningsspor, læringsprofil, fremdrift, rapportidentitet og sidemeny i én konsolidering.

## Hovedendringer

- Skrivebeskyttet eksport av alle fortsatt tilgjengelige rapporter, kandidatsnapshots, jobbhistorikk og Autonomi-/læringsdata.
- Eksporten kjører i en separat worker og leverer manifest, SHA-256, duplikatrapport, mangelliste, replayklassifisering og samlede replayresultater.
- Hver rapport kan lastes ned som komplett ZIP med PDF, TXT, JSON, input-snapshot, beslutningsspor, kildegrunnlag og replayresultat.
- Offline replay sammenligner lagret opprinnelig beslutning med RC16-porten uten nettverk, Pushover eller skriving til ordinære porteføljer.
- Porteføljelaget bruker faktiske lagrede score-, data-, evidens-, risiko-, likviditets- og porteføljegrenser. Hvert stopp får stabil blocker-kode og første blocker.
- Den sirkulære avhengigheten der en kandidat allerede måtte være merket som anbefalt før BUY kunne vurderes, er fjernet. Ingen terskel er senket.
- Evidensinnhenting dekker den avgrensede dypanalysen, mens antall presenterte forslag fortsatt styres separat.
- Ny installasjon bruker 15 000 som standard LEARNING_ONLY-notional. Eksisterende lagret verdi endres bare etter eksplisitt bekreftelse i UI-et.
- Rapportfremdrift og replay-eksport bruker modulnivå-fragmenter. Polling skal bare lese lagret workerstatus og ikke starte en ny full app-rendering.
- Siste CSS-lag låser desktop-sidemenyen til profesjonell 224 px-presentasjon etter full lasting og hindrer fragment-stale-visning i å dimme hele appen.
- PDF-, TXT- og beslutningsspråk skiller mellom analytisk kjøpsanbefaling, gjennomførbart kjøp og produksjonsgodkjent kjøp.
- Kvalitetsfeltene heter nå `Beslutningsjustert markedsdatakvalitet` og `Teknisk markedsdatadekning` for å fjerne 95/100–100/100-tvetydigheten.
- Nye offentlige PDF-navn inneholder uforanderlig rapport-ID. Eksisterende lagrede filnavn omskrives ikke.
- Tette kandidatdetaljer starter på ny PDF-side.

## Uendret

- Scheduler 08:00 og 22:00 Europe/Oslo.
- Sentral vedvarende minimumsscore og terskelsnapshot ved kjøringsstart.
- `final_score`, rangeringsmodell og produksjonsterskler er ikke senket.
- Ekte handel er fortsatt fail-closed.
- Paper Trading, login og Husk meg-kontrakter er ikke endret.

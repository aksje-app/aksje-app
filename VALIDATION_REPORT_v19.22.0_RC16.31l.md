# Validation Report - v19.22.0-rc16.31l

## Resultat

Lokal validering er bestått. Live Render-verifikasjon gjenstår, og utgaven skal derfor ikke omtales som produksjonsverifisert.

## Utførte kontroller

| Kontroll | Resultat |
|---|---|
| Full Python-kompilering | Bestått |
| Beslutningskjede, 9 unittest-kontroller | Bestått |
| RC16.31k kandidatfangst/skyggeterskler, 3 kontroller | Bestått |
| Full systemaudit | Bestått, 0 feil og 0 advarsler |
| 22:05 replay, 60 kandidater | Bestått |
| Gyldig kurs etter reparasjon | 60/60 |
| `PRICE_INVALID` etter reparasjon | 0/60 |
| Ordinær BUY i replay | SSAB-A.ST |
| Endelig kjøpsautorisasjon | Bestått for SSAB-A.ST |
| Manglende kurs | Fail-closed |
| Teknisk HOLD-bonus | 0 poeng |
| Ukjent sekundær transaksjon | OTHER, ikke BUY |
| INVE-A/INVE-B utstederkontroll | Bestått |
| Effektiv evidensminimum | Global Top 20 garantert |
| FULL distribusjonsvalidering | Bestått |
| DELTA distribusjonsvalidering | Bestått |
| ZIP-integritet FULL/DELTA | Bestått |

## Replaydetalj

Replaykilde: `MI-20260814-220503`, opprinnelig produsert av RC16.31k.

- Før: alle 60 hadde `price_valid=false` i porteføljelaget.
- Etter: alle 60 bruker samme kanoniske `raw.last_price`.
- SSAB-A.ST: score 76,35, risiko 41,73, datakvalitet 96,67, evidens godkjent, beslutning BUY.
- INVE-A.ST: eksisterende posisjon, HOLD.
- INVE-B.ST: samme utsteder som INVE-A.ST, HOLD når tilleggskjøp er deaktivert.
- DELL: fortsatt korrekt blokkert av evidens, oppdrag og risiko.

## Begrensninger

- Komplett pytest-suite kunne ikke kjøres fordi pytest/runtime-avhengigheter ikke finnes lokalt og ingen offline-hjulpakke er tilgjengelig.
- Ny live SEC-respons kan ikke dokumenteres fra en offline replay; korrekt kildeflyt må kontrolleres på Render.
- Økt evidensgaranti kan gi opptil lokal Top 20 per marked og må overvåkes for API-kvote og kjøretid.
- UI, PDF, JSON, logger, scheduler og Pushover må verifiseres live.

## Produksjonsstatus

Lokal release candidate: ja. Live produksjonsverifisert: nei.

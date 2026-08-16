# Godkjenningsmatrise RC16.31n

En FULL- eller DELTA-pakke kan bare bygges når alle punkter er bestått.

| Krav | Bevis |
|---|---|
| Snapshot tas etter Autonomi | Kildeinvariant og golden replay |
| Posisjonsantall er identisk overalt | Regnskapsport og PDF-tekstkontroll |
| Kontanter + markedsverdi = porteføljeverdi | Regnskapsport |
| Sum posisjonsvekter = investert andel | Regnskapsport med avrundingstoleranse |
| Alle avtalte porteføljefelt vises | Renderer-test og generert PDF |
| Faktisk portefølje skilles fra scenario | PDF-tekst og visuell kontroll |
| Manuell jobb feiler ikke ved normal låsekollisjon | Kø-/låsetest |
| Låseeier og heartbeat finnes i diagnose | Låsetest og diagnosekontrakt |
| Produksjonsterskel og beskyttede regler er uendret | Full systemaudit |
| FULL og DELTA har korrekte sjekksummer | Distribusjonsvalidering |

Live produksjonsgodkjenning krever i tillegg Render-verifikasjon av UI, PDF, JSON, logger, scheduler og Pushover.

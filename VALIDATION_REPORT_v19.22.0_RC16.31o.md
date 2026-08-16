# Valideringsrapport RC16.31o

## Resultat

- Python compileall: bestått.
- Nye exit-/utskiftingsscenarier: 7/7 bestått.
- Kjørbare historiske regresjonstester: 164/164 bestått.
- Målrettede rapport-, integritets- og PDF-regresjoner: bestått og inngår i de 164.
- Full systemaudit: 0 feil, 0 advarsler.
- FULL- og DELTA-distribusjonsvalidering: bestått.

## Scenarioer

- Stop-loss: totalsalg ved mer enn 5 % tap.
- Trailing stop: totalsalg ved 7 % fall fra registrert topp etter gevinst.
- Gevinstsikring: 25 % delrealisering ved +14 %, med 75 % restposisjon.
- Score-exit: totalsalg under score 55.
- RSI-exit: salg ved RSI minst 75 og fall fra forrige måling.
- Kapitalstagnasjon: vurdering, ikke automatisk salg.
- Utskifting: navngitt evidensklar kandidat og minst seks poeng scorefordel kreves.

## Replay og PDF

- Golden replay: MI-20260815-080526.
- Hovedrapport: 3 A4-sider, semantisk validering bestått.
- Teknisk vedlegg: 11 A4-sider, semantisk validering bestått.
- Alle tre hovedsider og kontaktark for samtlige tekniske sider er visuelt kontrollert.
- Ingen klipping, overlapping eller manglende tabellkolonner observert.
- Aktiv exitprofil er synlig i hovedrapporten.

## Miljøbegrensninger

Ti historiske testmoduler krever `pytest`, som ikke finnes i den tilgjengelige lokale runtime og ikke kunne installeres fra nettverket. Seksten tester ble derfor holdt utenfor den kjørbare unittest-serien: ti importblokkerte moduler og seks historiske tester med hardkodet gammel versjon/layout eller et kjent, urelatert scheduler-/tidsforventningsavvik. Ingen av disse er fremstilt som bestått.

## Live

Live Render-verifikasjon er ikke utført. Før produksjonsstatus må utkastkjøring, separat teknisk PDF, vedvarende parameterprofil og ett kontrollert delrealiseringsscenario bekreftes i deploymiljøet.

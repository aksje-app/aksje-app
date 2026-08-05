# Akseptanse - v19.22.0 Investor Edition RC3

## Lokal akseptanse
- Programversjon er `v19.22.0-rc3`.
- Rapporter ligger rett etter Oversikt i avansert navigasjon.
- Rapportsenteret viser seksjonene i denne rekkefølgen:
  1. Status for planlagte rapporter
  2. Handlinger
  3. Siste rapporter
  4. Historikk
  5. Planlegging og avanserte innstillinger
- Handlingene Nytt utkast, morgenanalyse, kveldsanalyse og nattanalyse finnes.
- Hurtigknappene bruker innholdstilpasset bredde og skal ikke strekkes over hele siden.
- Manglende planlagte rapporter vises øverst med en kompakt knapp for å kjøre rapporten.
- Planlegging og avanserte innstillinger er lukket som standard.
- Pushover, PDF-lagring, aktiv jobb, PDF-lenke og Top 3-varsel ligger samlet i en rammet innstillingsgruppe.
- Siste rapport, rapportarkiv, jobbkjøringer og rapporthistorikk er tilgjengelig uten å åpne jobbprofilen.
- Ingen endring i final_score, kandidatvalg, schedulerlogikk, innlogging, Paper Trading eller produksjonshandelsregler.

## Obligatorisk live Render-akseptanse
- Kontroller desktop og mobil visuelt.
- Kontroller at ingen avkrysningsbokser ligger løst på hovedsiden.
- Kontroller at knappene er kompakte og ikke fullbredde.
- Kontroller at avansert seksjon er lukket ved innlasting.
- Kjør Nytt utkast og hver tilgjengelige morgen-, kvelds- og nattjobb.
- Kontroller manglende-rapport-handlingen mot en kontrollert testjobb.
- Kontroller navigasjon Oversikt <-> Rapporter og ut/inn av Driftssenter.
- Kontroller UI, JSON og PDF for samme Top 3, final_score og beslutning.

RC3 er ikke produksjonsklar før livepunktene er dokumentert bestått.

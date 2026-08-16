# Diagnose før RC16.31g

## Bekreftet årsak

RC16.31f valgte et roterende utvalg på normalt 25 symboler per marked før live
markedsdata og grovfilter. Topplisten var derfor en rangering av utvalget, ikke
en dokumentert rangering av hele det konfigurerte investeringsuniverset.

Sektor og bransje ble først kjent etter databerikelsen. Programmet kunne derfor
heller ikke bevise sektorbredde for symboler som aldri kom inn i de 25.

Null BUY kan være korrekt for en enkelt kjøring, men var ikke etterprøvbart når
universdekning, sektorutfall og avvisningsspor manglet. Kjøpsterskelen skal derfor
ikke senkes som en tilfeldig løsning.

## RC16.31g akseptansekriterier

1. Alle symboler i det kontrollerte, pakkede universet for Norge, Sverige og USA
   går gjennom grovskann i faste rapporter.
2. Rapporten skiller tydelig mellom kontrollert applikasjonsunivers og en
   autoritativ komplett børsliste. Den får ikke hevde sistnevnte uten kildebevis.
3. Sektordekning, manglende metadata og manglende symboler vises per marked.
4. Dyr analyse velger både best totalrangering og sektorvinnere uten scorebonus.
5. Hvert symbol får et spor: grovskann, utvidet analyse, evidenskontroll og årsak
   til at det stoppet.
6. Dekningsfeil varsles; null kjøpskandidater alene er ikke en teknisk feil.
7. Rapporthistorikk beholder kompakte sammendrag, mens detaljspor har begrenset
   historikk slik at databasen ikke vokser uten grense.

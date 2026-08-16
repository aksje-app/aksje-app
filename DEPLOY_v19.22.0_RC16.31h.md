# Deploy RC16.31h

1. Behold sikkerhetskopien av database og vedvarende disk.
2. Deploy FULL, eller bruk DELTA mot nøyaktig RC16.31g-baseline.
3. Bekreft at appen viser `v19.22.0-rc16.31h`.
4. Åpne Autonomi og kontroller at kontoene vises separat.
5. For den kjente eldre profilen skal produksjonsverdiene migreres én gang. Kontroller audittypen `PARAMETERS_MIGRATED_RC16_31H`.
6. Bekreft at læringsprofilen fortsatt har sine tidligere verdier og at åpne posisjoner/handler er bevart.
7. Kontroller at Porteføljeverdi, total avkastning og prosentutvikling bruker aktiv kontos faktiske startverdi.
8. Send én ufarlig valutavarseltest og bekreft tre desimaler i kurs og grense.
9. La neste ordinære rapport- og Paper-skannerkjøring fortsette etter eksisterende tidsplan.

Ikke bruk porteføljereset for å aktivere parameterendringen. Reset er bare nødvendig dersom brukeren uttrykkelig ønsker en helt ny teoretisk konto.

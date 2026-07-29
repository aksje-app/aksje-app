# Deploy v19.14.1

## Anbefalt metode

Bruk FULL-pakken for testdeploy. Den inneholder hele programmet uten runtime-data, hemmeligheter, rapportarkiv eller lokale databaser.

1. Ta sikkerhetskopi av gjeldende deploy og vedvarende lagring.
2. Pakk ut v19.14.1 til et rent testmiljø.
3. Behold produksjonshemmeligheter i miljøvariabler; ikke kopier `.env` fra arkivet.
4. Kjør `python tools/validate_distribution.py <mappe> --profile full`.
5. Kjør `PYTHONPATH=. pytest -q` og `PYTHONPATH=. python tools/run_regression.py`.
6. Start appen og kontroller at Programversjon og Autonomi Core viser v19.14.1.
7. Kontroller at Enkel-modus starter med Norge, Sverige og USA og viser faktisk konfigurasjon før start.
8. Kjør en test uten varsling for kjernemarkedene.
9. Kontroller at bare status Kjøpskandidat kan gi ordinært teoretisk kjøp, og at PDF/JSON samsvarer.
10. Test PDF-nedlasting og retur til appen på fysisk mobil før produksjonssetting.

## Oppdateringspakke

ONLY_CHANGED_FILES er laget for eksakt v19.14.0-fullpakke. Ta sikkerhetskopi først og kjør de samme testene etter overlegg. Ved usikker grunnversjon skal FULL-pakken brukes.

## Produksjonsgodkjenning

Offline-verifikasjonen er bestått. Produksjonsgodkjenning krever én ny live kjernemarkedskjøring, én separat Utvidet Norden-kjøring, én separat Brasil-kjøring og fysisk mobiltest.

# Deploy RC16.31u

1. Deploy FULL, eller DELTA over verifisert RC16.31t.
2. Restart Render-web og cron; kontroller synlig versjon `v19.22.0-rc16.31u`.
3. Kjør en rapport med minst én læringshandel og bygg komplett ZIP.
4. Bekreft at Report Consistency Audit består for TXT/JSON/PDF.
5. Last ned «hovedrapport (kortversjon)» og «komplett rapport med teknisk vedlegg» direkte.
6. Restart webtjenesten og bekreft at begge nedlastinger fortsatt fungerer fra historikken.
7. Verifiser scheduler 08:00/14:00/22:00, Pushover-lenke og rapportarkiv.

Produksjonsklar status krever fullført live-verifikasjon i Render.

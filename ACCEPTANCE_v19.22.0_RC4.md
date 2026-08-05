# Akseptanse v19.22.0 RC4

RC4 kan godkjennes lokalt når:
- Hele pytest-pakken består uten feil.
- Python compileall og full systemaudit består.
- Top 1–3 og de fire separate kvalitetsmålene er på PDF-side 1.
- JSON og PDF har samme Top 3, final_score og beslutning.
- Alle PDF-sider er rendret og visuelt kontrollert uten klipp, overlapp eller brutte tegn.
- «Kontrollert – ingen hendelser» gir 0 evidensstraff.
- Rapportsenteret har reell, varig fremdriftsvisning.
- Menyvalg er autoritativt og gamle autentiseringstokener fjernes fra URL-er.
- «Husk meg» lagrer aldri passord eller råtoken på serveren og kan tilbakekalles.
- FULL og DELTA består distribusjonskontroll, og DELTA berører ikke runtime eller hemmeligheter.

Produksjonsgodkjenning krever i tillegg full live Render-test beskrevet i deploynotatet. Lokal validering alene er ikke produksjonsgodkjenning.

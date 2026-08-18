# RC16.31u – varig teknisk rapport og konsistent eksport

RC16.31u er bygget direkte fra RC16.31t.

- ZIP-revisjonen bruker samme offentlige presisjon for læringshandler i JSON, TXT og PDF, og støtter norsk desimalkomma.
- Antall skrives deterministisk med opptil åtte desimaler; pris vises og kontrolleres med to desimaler.
- Reelle avvik i ticker, handling, antall eller pris blokkerer fortsatt pakken.
- Komplett rapport med teknisk vedlegg lagres varig med egen token og kan lastes direkte ned fra siste rapport og historikken.
- Hovedrapporten er tydelig merket som kortversjon. ZIP er fortsatt tilgjengelig for JSON, TXT, revisjon og øvrige pakkefiler.

Ingen analyse-, terskel-, scheduler-, portefølje- eller handelsregler er endret.

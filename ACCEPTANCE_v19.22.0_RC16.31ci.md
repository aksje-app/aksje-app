# Akseptanse RC16.31ci

- [x] Webmotors, OLX og Mobiauto beholdes som hovedkilder.
- [x] Localiza Seminovos og Seminovos.com.br kan aktiveres som forhandlernettverk.
- [x] Forhandlernettverket kan slås av uten å slå av markedsplassene.
- [x] Privat, vanlig forhandler og eksplisitt dokumentert autorisert Jeep-forhandler skilles.
- [x] Ukjent selgertype merkes ukjent; programmet gjetter ikke.
- [x] Samme bil på flere nettsteder gir ett samlet treff og ett varsel.
- [x] Billigste lenke velges, mens alle alternative kilder og priser bevares.
- [x] Ny kilde for en allerede kjent bil kan utløse eget Pushover-varsel.
- [x] Kildestatus viser kanal, antall leste treff og konkret feil per kilde.
- [x] Én blokkert kilde gjør samlet resultat ufullstendig og vises tydelig.
- [x] År, km, motor, drivlinje, farge og område bruker samme strenge filter for alle kilder.
- [x] Prisfall, stille førstegangsreferanse og mislykket Pushover-retry er bevart.
- [x] Bilmodulen er fortsatt isolert fra investering, Autonomi, rapporter og læring.

## Testkvittering

- Målrettet bilmodul: 22/22 bestått.
- Python-kompilering: bestått.
- Produksjonskontroll etter deploy kreves fortsatt fordi annonsesider kan blokkere automatiske kall eller endre HTML.


# RC16.31n - Report Reconciliation Integrity

Denne utgivelsen fryser analyse-, score-, risiko- og handelsreglene. Produksjonsterskelen er fortsatt 73,0.

## Rettet

- Rapporten bruker ett autoritativt porteføljesnapshot etter at Autonomi er fullført.
- Posisjonsantallet kan ikke avvike mellom sammendrag, posisjonstabell og opprinnelsesliste.
- PDF og JSON viser startkapital, porteføljeverdi, kostpris, markedsverdi, kontanter, investert andel, kontantandel, reserve, ledig kjøpslimit, realisert/urealisert/samlet resultat og ledige posisjonsplasser.
- Hver posisjon viser antall, inngangskurs, siste kurs, kostpris, markedsverdi, porteføljevekt, resultat, eiertid, scoreutvikling og kapitalstatus.
- Rapportpublisering stoppes dersom porteføljeregnskapet ikke kan avstemmes internt.
- Faktisk portefølje og foreløpig modellportefølje merkes som separate datalag.
- Læringskontoens lukking ved promotering merkes som dette, ikke som et ordinært salgssignal.
- Manuelle rapporter venter i kø i opptil 30 minutter når rapportmotoren er opptatt.
- Rapportlåsen publiserer låseeier, kjøring, trigger, starttid og heartbeat.
- Diagnosepakken inkluderer låseeier og korrekt ekspanderte markeder.

## Uendret

- Scheduler: 08:00 og 22:00 Europe/Oslo.
- Produksjonsterskel: 73,0.
- Fail-closed handel, risiko- og porteføljegrenser.
- Paper Trading-persistens, navigasjon, prisregler, XAUUSD/UKOILUSD og Explainability.

## Avgrensning

Porteføljen er teoretisk og verdsettes i simulert kontoenhet. Valutaomregning til NOK er ikke introdusert i denne rettingen.

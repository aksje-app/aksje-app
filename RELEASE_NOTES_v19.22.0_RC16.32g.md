# v19.22.0 RC16.32g — Super Portfolio UI Feedback

## Formål
Gjøre Super Portfolio vesentlig lettere å lese og hindre at manuell vurdering kan startes flere ganger samtidig.

## UI
- Seks tettpakkede tekstblokker er erstattet med to horisontale rader à tre foldbare paneler.
- Panelene er: Hvorfor er aksjene med, Data Freshness, Event Risk, Stop Pressure, Ranking Velocity og AI WOULD DO TODAY.
- Innholdet vises som kompakte tabeller i stedet for lange tekstlinjer.
- Ingen tredje banner er lagt til; eksisterende to-banner-kontrakt er uendret.

## Manuell vurdering
- «Vurder porteføljen nå» blir deaktivert så snart en kjøring er startet.
- Knappeteksten endres til «Jobber...» mens kjøringen pågår.
- En progressbar viser at systemet arbeider og oppdaterer status gjennom hovedstegene.
- Session-state guard hindrer gjentatte samtidige klikk/kjøringer.
- Guard nullstilles også ved feil, slik at knappen ikke blir permanent låst.

## Motor
Ingen endring i ranking-, stop-, rebalanserings- eller handelsregler. Super Portfolio er fortsatt SHADOW.

# v19.22.0-rc16.15

- Startknappen er flyttet ut av det periodisk oppdaterte statusfragmentet.
- Startkontrollen bruker et eget ikke-periodisk fragment og eksplisitt `form_submit_button`.
- Et vellykket klikk viser umiddelbart kvittering med den returnerte eksport-ID-en.
- Status, prosent, rapportnavn og heartbeat poller fortsatt i et separat skrivebeskyttet fragment hvert tredje sekund.
- Statuspolling kan dermed ikke erstatte eller avbryte startknappen under klikk.
- RC16.14-funksjonene for watchdog, foreldet worker, prosessisolasjon, timeout og karantene er beholdt.

Ingen analyse-, score-, scheduler-, portefølje- eller handelsregler er endret.

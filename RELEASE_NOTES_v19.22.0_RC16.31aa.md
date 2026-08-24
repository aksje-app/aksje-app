# RC16.31aa – separat og immutable snapshotlagring

RC16.31aa er bygget direkte fra RC16.31z etter live-diagnosen `MBJ-20260818-101701-FC8F4B`.

## Rettet

- Nye markedssnapshots lagres som separate immutable dokumenter.
- Et nytt snapshot leser eller omskriver ikke lenger hele historikken.
- En lett indeks inneholder bare identitet, tidspunkt, checksum og kandidatantall.
- Eldre snapshots i samleformatet beholdes urørt og er fortsatt lesbare.
- Autonomi viser en egen fremdriftshendelse før snapshotlagringen.
- Snapshotvisninger bruker eksplisitte grenser, mens direkte oppslag og historisk replay beholdes.

Markeder, kandidatantall, markedsdata, innsiderdata, nyheter, shortdata, scoring, rangering, risikoregler og handelsfullmakt er uendret.


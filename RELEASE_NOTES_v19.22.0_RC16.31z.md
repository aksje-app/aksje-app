# RC16.31z – prosessminne gjennom hele rapportkjøringen

RC16.31z er bygget direkte fra RC16.31y.

## Rettet

- Markedskjøringene beholder ikke lenger komplette duplikater av kandidat-, evidens- og utvalgsdata ved siden av den kanoniske kandidatlisten.
- Python-sykluser og ledige Linux allocator-arenaer frigjøres etter hvert marked, før Autonomi og etter enhver rapportavslutning, også ved feil eller kontrollert avbrudd.
- Jobbdiagnostikken viser aktuell prosess-RSS, historisk topp-RSS, cgroup-forbruk, cgroup-grense og tilgjengelig minnemargin.
- Kompakte markedsauditvisninger beholder feltene rapportintegriteten trenger, uten store rå leverandørpayloads.

Ingen handelsfullmakt, produksjonsterskel eller beslutningsregel er endret.


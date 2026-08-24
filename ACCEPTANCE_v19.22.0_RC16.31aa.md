# Akseptanse RC16.31aa

- Direkte forgjenger: RC16.31z.
- Ny snapshotlagring skal ikke lese `repositories/market_snapshots.json` ved lagring.
- Eldre snapshots skal fortsatt kunne hentes ved ID.
- Snapshot-ID skal være immutable og avvise checksum-konflikt.
- Gjentatte lagringer skal bare øke en lett indeks og separate dokumenter.
- Full regresjon, auditer og distribusjonsvalidering skal være PASS.

Endelig produksjonsaksept krever live Render-kjøring forbi snapshot 59/59, lagring, Autonomi og rapport uten prosessrestart.


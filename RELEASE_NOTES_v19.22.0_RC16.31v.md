# RC16.31v – Rapportsenter navigasjonshotfix

RC16.31v er bygget direkte fra RC16.31u.

- Fjerner et ugyldig kall fra Rapportsenteret til den private app-funksjonen `_persist_ui_state_v18658`.
- Fjerner samme ugyldige kall fra den alternative Autonomi-siden.
- Beholder `set_global_navigation_state` som kanonisk rute- og URL-lagring.
- Alle tre rapportområdene og øvrige Autonomi-arbeidsflater er bevart.

Ingen rapportdata, analyse-, terskel-, scheduler-, portefølje- eller handelsregler er endret.

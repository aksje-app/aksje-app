# RC16.31i – versjonssporbarhet

Denne utgaven retter dokumentert avvik mellom programversjon, strategibinding, parameterpolicy og komponentversjoner.

- Aktiv standardbinding migreres fra `autonomy_main@1.0.0` til `autonomy_main@1.1.0`.
- Den nye bindingen peker på `v19.22.0-rc16.31i` og policy `v19.16.0`.
- Historiske beslutninger og den historiske 1.0.0-raden endres ikke.
- En egendefinert produksjonsbinding overstyres aldri av migreringen.
- Aktiv Autonomi-konto følger den nye bindingen og parameterpolicyen.
- Fallbackmetadata bruker samme sentrale kontrakt som databindingen.
- Kontrollert læring rapporterer `v19.3.1`; driftstelemetri rapporterer `v19.2.0`.

Ingen kjøps-, salgs-, score-, risiko- eller porteføljeterskler er endret.

# RC16.31y – snapshot-finalisering uten minnetopp

RC16.31y er bygget direkte fra RC16.31x.

- Hele kandidatsnapshotet begrenses, inkludert kvalitetsevidens, kvalitetsdekning og tekniske spor.
- Beslutningsinput er redusert til maksimalt 32 KiB per kandidat.
- Checksum beregnes strømmende uten en ekstra komplett JSON-streng.
- `to_dict()` unngår gjentatte dype kopier av hele snapshotet.
- Valgfri parallellstrategi hoppes kontrollert over ved utilstrekkelig minne.
- RSS-, restart- og oppryddingsdata følger nå diagnosepakken.

Ingen handelsfullmakt, produksjonsterskel eller rapporttid er endret.

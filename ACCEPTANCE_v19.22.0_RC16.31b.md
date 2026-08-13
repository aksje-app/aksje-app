# Akseptanse – v19.22.0-rc16.31b

## Obligatoriske kontroller

- [x] Diagnose dokumentert før kodeendring.
- [x] Faste rapportprofiler har kun 08:00, 14:00 og 22:00 Europe/Oslo.
- [x] Faste profiler har tomme skanningsvinduer og testseriefelter etter migrering.
- [x] Automatisk testjobb har egen stabil jobb-ID og ingen produksjonstidspunkter.
- [x] Faste rapporter kan ikke merkes automatisk 1/4–4/4 av foreldede metadata.
- [x] Duplikatkvittering bevarer `sendt` som sann leveringsstatus.
- [x] Leveransetabellen aggregerer vellykket leveringsbevis for samme planlagte spor.
- [x] Paper-skannerens uavhengige kontrakter er regresjonstestet.
- [x] Program, rapport og varsel bruker `v19.22.0-rc16.31b`.

## Testresultat

- Målrettet RC16.31b-port: 46 bestått, 4 deltester bestått.
- Historisk suite: 841 bestått, 56 eldre tester feiler. Feilene gjelder hovedsakelig hardkodede tidligere RC-versjoner, foreldet rapportsemantikk og fem tester som peker til en ikke-eksisterende midlertidig fixture.
- Ingen nye planleggings-, leverings-, testserie- eller Paper-regresjoner er registrert.


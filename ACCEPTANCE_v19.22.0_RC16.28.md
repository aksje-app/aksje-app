# Akseptanse – v19.22.0-rc16.28

1. Bekreft at app og cron viser `v19.22.0-rc16.28` fra samme commit.
2. Åpne en fast jobb, velg Norge, Sverige og USA, lagre og last siden på nytt. Kontroller at valgene og skanneantallet beholdes.
3. Opprett en ny jobb og kontroller standarden 25 per marked, 10 dybdeanalyser og 10 evidenskontroller.
4. Aktiver 30-minutters Autonomi-rapporttest under Fullt rapportsenter.
5. La minst én cron-kjøring fullføres uten å åpne webappen.
6. Pushover skal være merket TEST og vise `Læringstest: PASS`, `PARTIAL` eller `FAIL`.
7. Last ned diagnosepakken og kontroller `learning/LEARNING_ACCEPTANCE.json`, `learning/LEARNING_DIAGNOSTICS.json`, schedulerfilene og `SHA256SUMS`.
8. `PASS` godkjennes bare når `learning_observation_exists=true`, læringsposisjonen er lagret og alle læringshandler har `mode=LEARNING_ONLY`.
9. `PARTIAL` må vise minst én konkret `first_blocker_code` per avvist læringsbeslutning.
10. Kjør samme `run_id` på nytt i testmiljø og kontroller at ingen duplikatposisjon eller duplikathandel opprettes.
11. Kontroller at ordinær Autonomi-portefølje og ekte handel ikke er aktivert av testen.
12. Kontroller at komplett ZIP inneholder læringsakseptanse og at ZIP-/SHA-kontrollen består.

Live godkjenning krever minst én nettleseruavhengig cron-kjøring. Lokal status alene skal ikke markeres som produksjonsgodkjent.

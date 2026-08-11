# Akseptanse v19.22.0-rc16.30

## Lokal port

1. Alle instrumenterte moduler kompilerer.
2. Callback følger gateway, orkestrator og porteføljemotor.
3. Fremdrift ved 899 sekunder beholder leasen.
4. Stillhet over 900 sekunder tilbakekaller leasen.
5. Gammel aksept merkes `PREVIOUS_RUN`.
6. Canonical `action=BUY` og `side=BUY` består samme audit.
7. Simulert feil avslutter worker terminalt.

## Stabilisering

1. Start én manuell rapport.
2. Bekreft synlige Autonomi-delsteg etter 84 prosent.
3. Bekreft rapportaudit og læringsaksept for samme `run_id`.
4. Bekreft PDF og Pushover.
5. Bekreft terminal `COMPLETED`.

Før alle fem livepunktene er dokumentert er status
`LOCAL_PASS_LIVE_REQUIRED`.

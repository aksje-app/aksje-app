# Akseptanse RC16.31i

## Bestått lokalt

- Python-kompilering av alle endrede moduler.
- Isolert migrering fra standardbinding 1.0.0 til 1.1.0.
- Historisk 1.0.0-rad beholdt uendret som historisk implementasjon.
- Aktiv konto følger ny binding og policy.
- Egendefinert binding blir ikke overstyrt.
- Kontrollert læring og driftstelemetri samsvarer med sentral versjonskontrakt.
- Statisk sporbarhetsaudit uten gamle fallbackliteral i aktiv binding/konto.

`pytest` finnes ikke i det tilgjengelige pakkemiljøet. Releaseporten bruker derfor prosjektets kompilering, isolerte repository-scenarioer, statisk audit og distribusjonsvalidator. Dette skal ikke omtales som en full historisk pytest-kjøring.

## Etter deploy

En ny Autonomi-beslutning skal vise:

- `strategy_version_id = autonomy_main@1.1.0`
- `strategy_implementation_version = v19.22.0-rc16.31i`
- `parameter_version = v19.16.0`
- ikke-tom `strategy_config_checksum`
- `strategy_binding_verified = true`

Gamle beslutningsrader skal beholde sine opprinnelige versjoner.

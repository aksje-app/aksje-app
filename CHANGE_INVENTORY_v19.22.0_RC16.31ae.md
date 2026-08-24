# Endringsoversikt RC16.31ae

RC16.31ae bygger direkte på RC16.31ad.

## Endret

- `app_version.py`: versjonsidentitet og endringslogg.
- `requirements.txt`: alle direkte produksjonsavhengigheter er eksakt låst.
- `requirements-dev.txt`: utviklingstester bygger på produksjonslåsen.
- `render.yaml`: felles cache-fri bygging, låseverifikasjon, Python 3.12.13 og commit-autodeploy for alle tjenester.
- `tools/build_safe_distribution.py`: låseverifikatoren følger DELTA-pakken.
- `tools/validate_distribution.py`: FULL og DELTA krever og kontrollerer låsefilen.
- versjons- og regresjonstester er oppdatert til RC16.31ae.

## Nytt

- `.python-version`
- `requirements.lock`
- `tools/verify_dependency_lock.py`
- `tests/test_rc16_31ae_deterministic_deploy.py`
- release-, deploy-, akseptanse-, validerings- og byggedokumentasjon for RC16.31ae.

## Ikke endret

Analysefunksjon, datakilder, datainnhentingsomfang, score-, risiko-, portefølje- og handelsregler er uendret.

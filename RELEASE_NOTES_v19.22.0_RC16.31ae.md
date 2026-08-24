# RC16.31ae release notes

RC16.31ae bygger direkte på RC16.31ad og er en ren stabiliserings- og deployversjon.

- Hele produksjonsavhengighetsgrafen er låst til eksakte versjoner i `requirements.lock`.
- Alle tre Render-tjenester bruker samme cache-frie byggekommando og verifiserer låsen før oppstart.
- Python er eksplisitt satt til 3.12.13 for web, rapport-scheduler og Paper-scanner, identisk med den testede kjøretiden.
- Automatisk deploy ved commit er aktivert for alle tre tjenester.
- FULL- og DELTA-pakkene validerer at låsefil og låseverifikator følger distribusjonen.

Ingen funksjon, scoreterskel, risikogrense, porteføljeregel, handelsregel, datakilde eller datainnhentingsomfang er endret.

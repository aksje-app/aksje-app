# v19.22.0-rc16.34d – Render memory right-size

## Formål
Redusere webprosessens minnetopper uten å redusere kapasitet før live-målinger viser at det er trygt.

## Endringer
- Synkroniserer Render Blueprint med faktisk 15-minutters cron-kadens.
- Beholder web på Standard/2 GB under måleperioden; ingen risikabel planreduksjon i denne releasen.
- Legger eksplisitte grenser på flere Streamlit data-cacher som ellers kan vokse med bruk og tickerbredde.
- Setter de samme små analyse-cachegrensene på web som scheduler allerede bruker.
- Beholder PostgreSQL og scheduler-kapasitet uendret.

## Live beslutningsgate
Web kan først vurderes for mindre plan når målt RSS etter denne releasen holder seg med sikker margin under den aktuelle planens minnegrense under normal og tung bruk.

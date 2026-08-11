# Deploy v19.22.0 RC16.10

1. Ta backup av kode, `.env`, Streamlit-secrets og `.app_runtime`.
2. Installer fullpakken eller pakk deltafilene over eksisterende programrot.
3. Bekreft at begge TTF-filene finnes under `assets/fonts/`.
4. Installer eksisterende `requirements.txt` uten å senke eller endre produksjonsporter.
5. Start applikasjonen på nytt.
6. Kjør `python -m unittest -v tests.test_v19220_rc1610_verified_export_closure`.
7. Bygg en komplett enkelt­rapportpakke og kontroller at PDF, TXT, JSON og `REPORT_CONSISTENCY_AUDIT.json` finnes.
8. Bygg samlet ZIP fra rapportarkivet og kontroller at hver rapportmappe har en bestått audit.
9. Dersom `MI-20260805-200637` finnes i det varige arkivet, bygg den gjennom RC16.10-porten og dokumenter resultatet.

Godkjenningsstatus etter lokal installasjon er `LOCAL_PASS_LIVE_REQUIRED` frem til punkt 7–9 er kontrollert i den faktiske driftsinstansen.


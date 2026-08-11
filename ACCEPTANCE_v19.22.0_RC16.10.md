# Akseptanse v19.22.0 RC16.10

## Automatisk verifisert

- Python-kompilering av endrede kjernemoduler.
- 12/12 målrettede tester bestått.
- PDF inneholder Noto Sans som innebygd subset-font.
- PDF inneholder et ikke-tomt outline-/bokmerketre.
- Enkeltpakke inneholder PDF, TXT, JSON, audit og SHA-256.
- Samlet replay-ZIP inneholder bestått audit for hver rapport.
- Korrupt ZIP og avvikende JSON-versjon avvises.
- Tom offentlig kjøpsrangering gir ikke `st.columns(0)`.

## Live-verifisering

Status: `LOCAL_PASS_LIVE_REQUIRED`.

Etter utrulling skal en ekte arkivrapport og samlet rapport-ZIP bygges i appen. `MI-20260805-200637` skal brukes dersom den fortsatt finnes i det varige rapportarkivet.


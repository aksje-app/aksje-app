# v19.22.0-rc16.25 – Direkte PDF i mobilnettleseren

## Dokumentert årsak

RC16.24 rettet Pushover-tokenet, men den offentlige visningen kalte `st.pdf`. Funksjonen finnes i Streamlit-versjonen på Render, men kaster `StreamlitAPIException` når det valgfrie `streamlit-pdf`-tillegget ikke er installert.

## Retting

- Offentlig rapportvisning bruker ikke lenger `st.pdf`.
- PDF-en hentes fra den felles varige databasen.
- PDF-en skrives atomisk til webinstansens aktiverte statiske rapportområde.
- Mobilnettleseren videresendes til den rå `.pdf`-filen før innlogging og resten av appen.
- Direkte åpning og nedlasting vises som reserve hvis mobilnettleseren blokkerer automatisk videresending.

Ingen handels-, score-, risiko-, lærings- eller porteføljeterskler er endret.

# Deploy v19.22.0-rc16.25

1. Deploy FULL, eller DELTA kun over komplett RC16.24.
2. Kontroller at webtjenesten viser v19.22.0-rc16.25.
3. Ingen ny Python-avhengighet skal installeres; løsningen bruker ikke `streamlit-pdf`.
4. Kjør én ny umiddelbar Autonomi-rapporttest.
5. Trykk «Åpne rapport» i den nye Pushover-meldingen.
6. Nettleseren skal gå videre til en URL som ender i `.pdf`, uten innlogging.
7. Gamle meldinger er ikke en gyldig test av RC16.25.

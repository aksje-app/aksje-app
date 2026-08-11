# v19.22.0 RC16.10 – Verified Report Export Closure

- Noto Sans Regular/Bold følger distribusjonen under `assets/fonts/` og PDF-bygging stopper dersom fontene mangler.
- PDF-metadataoppdateringen kloner hele dokumentet og bevarer outline-treet. En deterministisk side-outline legges til dersom runtime ikke skrev semantiske bokmerker.
- PDF bygges alltid på nytt fra samme kanoniske eksportobjekt som TXT og JSON; eldre PDF-bytes gjenbrukes ikke.
- Den harde eksportporten kontrollerer rapport-ID, appversjon, offentlig kjøpsrangering, beslutninger, innebygd Noto Sans og PDF-bokmerker.
- Samlet rapport-/replay-ZIP kjører samme audit per rapport og avbryter hele leveransen ved første avvik.
- Rapportarkivet tåler tom offentlig kjøpsrangering og viser samlet ZIP direkte under «Rapportarkiv og nedlastinger».
- Tolv selvstendige RC16.10-tester kan kjøres uten pytest.

Den historiske problemrapporten `MI-20260805-200637` var ikke inkludert i den opplastede RC16.9-fullpakken og er derfor ikke feilaktig markert som testet. Den kan kjøres gjennom samme gate når rapport-JSON-en er tilgjengelig i installasjonens rapportarkiv.


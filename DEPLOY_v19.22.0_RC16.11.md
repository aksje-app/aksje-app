# Deploy v19.22.0 RC16.11

1. Ta backup av kode og runtime-data.
2. Pakk full- eller delta-ZIP over programroten.
3. Bekreft at `assets/fonts/` fortsatt inneholder begge Noto Sans-fontene.
4. Start applikasjonen på nytt.
5. Åpne **Rapporter** og trykk **Bygg komplett rapportpakke (ZIP)**.
6. Bekreft at prosent og aktivt steg vises innen ett sekund og fortsetter til 100 %.
7. Test deretter **Bygg samlet ZIP av alle rapporter** og bekreft separat heartbeat/progress.

Hvis enkeltpakken fortsatt viser ingen fremdrift etter 10 sekunder, hent applikasjonsloggen før nytt klikk.


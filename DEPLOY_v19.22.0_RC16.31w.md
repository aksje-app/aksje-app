# Deploy RC16.31w

1. Deploy FULL, eller DELTA over verifisert RC16.31v.
2. Restart Render web og cron; kontroller `v19.22.0-rc16.31w`.
3. Kjør en kontrollert rapport med Norge, Sverige og USA.
4. Kontroller søkelogg og kildefeil for FI, norsk SSR og amerikansk strukturert shortdata.
5. Bekreft at ingen treff under offentlig terskel vises som 0 %.
6. Kontroller svenske innsiderkjøp/salg og SEC-deduplisering.
7. Last ned full rapport med vedlegg, kort rapport og komplett ZIP.
8. Verifiser JSON, logger, scheduler og Pushover.

Produksjonsklar status krever vellykket live-kilde- og Render-verifikasjon.

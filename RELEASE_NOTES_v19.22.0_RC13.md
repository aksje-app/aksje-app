# Release notes v19.22.0 Investor Edition RC13

## Formål

RC13 retter den siste live-blokkeringen i Autonomi → Rapporter. Knappen `Nytt utkast` kunne fortsatt forsøke å endre arbeidsflateradioens Streamlit-nøkkel `autonomy_core_workspace_v1880` etter at widgeten var opprettet. RC13 gjør rapportnavigasjonen fullt totrinns: handlingskoden lagrer bare applikasjonseid rute/lease, og widgetnøkkelen settes først før radioen opprettes på neste rerun.

RC13 gjør også schedulerstatus restart-bevisst. Planlagte tidspunkt som lå før den nåværende Render-prosessen startet, og som ikke har varig kjøringshistorikk, vises ikke lenger feilaktig som «Mistet» og startes ikke automatisk i ettertid.

## Endret

- Rapporthandlinger skriver ikke lenger til `autonomy_core_workspace_v1880` i samme render som knappen ble trykket.
- Rapporter-ruten, query-parametrene og kjøringsbundet route lease beholdes gjennom rerun.
- Arbeidsflateradioen settes til Rapporter før widgeten opprettes på neste render.
- Schedulerhelse bruker varig jobbhistorikk for å bekrefte fullførte eller feilede planlagte kjøringer.
- Et tidspunkt før nåværende prosessoppstart klassifiseres som `Ikke vurdert etter omstart` når varig historikk mangler.
- Slike tidspunkt telles separat, regnes ikke som mistet og startes ikke automatisk som catch-up.
- Faktiske observerte tidspunkt uten start/fullføring beholder eksisterende «Mistet»-status og manuell catch-up.
- Starlette er fortsatt låst til `1.3.1` for kompatibilitet med Streamlit `1.57.0` på Render.

## Ikke endret

- `final_score`, kandidatvalg, rangering og beslutningstrakt.
- Produksjons- og varselterskler.
- Autonomis porteføljeregler og Paper Trading.
- Faste schedulertider 08:00 og 22:00 Europe/Oslo.
- Pushover-, innloggings- eller Husk meg-regler.
- Produksjonshandel forblir fail-closed.
- Rapportinnhold og PDF-renderer.

## Live-bekreftelse som gjenstår

RC13 er ikke produksjonsgodkjent før Render viser at `Nytt utkast` starter én ny jobb uten StreamlitAPIException, at Rapporter forblir aktiv under hele kjøringen, og at pre-start-tidspunkt vises som «Ikke vurdert» i stedet for «Mistet».

# Release notes v19.22.0 Investor Edition RC11

## Formål

RC11 er en avgrenset live-rettelse for Rapportersenterets Streamlit-navigasjon. RC10 kunne fullføre og lagre en rapport, men deretter feile med `StreamlitAPIException` fordi rapporthandlingen endret radiowidgetens Session State-nøkkel etter at widgeten var opprettet. Samme feil blokkerte `Nytt utkast` før panelet kunne starte.

## Endret

- Ny widget-sikker `pin_autonomy_workspace_route_v19220_rc11`.
- Rapporthandlinger legger ønsket rute i en engangs `ai_control_center_route_lock_v19220_rc6`.
- Kontrollsenteret bruker låsen før gruppe- og panelradioene opprettes på neste rerun.
- `Nytt utkast`, morgen-, kveld-, natt-, catch-up- og arkivhandlinger bruker RC11-rerunflyten.
- URL-ruten settes til `aa_nav=autonomy`, Autonomi-kontrollsenter og `aa_tab=reports`.
- Eldre RC9-funksjonsnavn beholdes som kompatibilitetsaliaser.
- UI-state og evidenspass bruker sentral `APP_VERSION` i stedet for hardkodet RC10-versjon.

## Ikke endret

- Rapportmotor og rapportinnhold.
- `final_score`, kandidatvalg og rangering.
- Produksjonsterskel og handelsregler.
- Autonomis porteføljeregler og Paper Trading.
- Scheduler 08:00 og 22:00 Europe/Oslo.
- Innlogging, Husk meg og Pushover.
- Bannerimplementasjonen fra RC10.

## Live-bekreftelse som gjenstår

RC11 er ikke produksjonsgodkjent før Render viser at `Nytt utkast` starter én jobb, blir på Rapporter, fullfører uten `StreamlitAPIException`, og at ny JSON/PDF kan lastes ned.

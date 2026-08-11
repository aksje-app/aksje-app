# v19.22.0-rc16.16

- `form_submit_button` er fjernet fra eksportstarten fordi den kolliderte med fragmentlivssyklusen i live-runtime.
- Startflaten bruker nå en vanlig knapp i et ikke-periodisk fragment.
- En `on_click`-callback oppretter workeren før Streamlit begynner fragmentets rerendering.
- Callbacken lagrer ny eksport-ID som umiddelbar kvittering i sesjonen.
- Startknappen har en helt ny widgetidentitet, slik at gammel frontendtilstand ikke gjenbrukes.
- Tresekunders statuspolling er fortsatt isolert i et separat skrivebeskyttet fragment.
- Watchdog, foreldet worker-gjenoppretting, 120-sekunders rapporttimeout og karantene er beholdt.

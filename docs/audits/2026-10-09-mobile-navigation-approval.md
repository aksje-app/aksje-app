# Mobilnavigasjon og godkjenning – rc16.34h

## Observerte problemer

Portefølje-knappen kunne beholde Autonomi-siden. Navigasjonsknappen og ruteleasen satte `ai_control_center_last_applied_nav_v19016` før den gamle ruteren faktisk hadde valgt arbeidsflaten. Ruterens snarvei behandlet derfor målet som allerede åpnet. Rerun-vakten kunne i tillegg erstatte den eksplisitte nye ruten med den gamle, fremdeles synlige arbeidsflaten.

Autonomis responsive CSS traff alle horisontale blokker i hovedsiden, inkludert den faste mobilmenyen. Dermed kunne seks navigasjonsknapper bli stablet over sideinnholdet. Menyens kolonnevelger håndterte også bare det eldre `column`-navnet, ikke dagens `stColumn`.

Godkjenningsknappene utførte lagringen inne i sidegjengivelsen etter innledende datahenting. Gjentatte trykk kunne avbryte sidekjøringen før handlingen ble nådd. Dette er en identifisert sårbarhet; antallet trykk og eventuell produksjonslatens er ikke målt i brukerens iPhone.

## Rettelser

- Mobilnavigasjon køer ønsket rute uten å markere den som anvendt. Den eksisterende ruteren velger arbeidsflate, og en eksplisitt rute overlever rerun-vakten.
- Godkjenn, Avvis nå og Utsett bruker Streamlit-callback før sidegjengivelsen. Den eksisterende atomiske transaksjonen lagrer parameter, status og historikk. UI viser kvittering etter fullført transaksjon og feil ved mislykket handling. Bekreftelseskravet beholdes. Ingen ny automatisk godkjenning innføres.
- Forslagsverdier vises uten avrunding fra 0,80 til et annet tall.
- Autonomi-innholdet beholder én kolonne på mobil. Mobilmenyen er unntatt fra regelen; begge Streamlit-kolonnenavn støttes. Tekstblokker får naturlig høyde og avstand.

## Kontroll

Ny test kjører Portefølje-knappen med gammel Autonomi-rute gjennom rerun-vakt, ruteleasens konsum og den faktiske ruterfunksjonen fra app.py. Den verifiserer ny arbeidsflate etter ett trykk.

Streamlit AppTest klikker den ekte bekreftelsesboksen og Godkjenn-knappen én gang: 1,5 % blir 0,8 %, forslaget forsvinner, IVERKSATT vises og én historikkpost lagres. Avvis og Utsett testes også, samt mislykket lagring uten falsk suksesskvittering.

CSS-regresjonstesten kontrollerer avgrensningen mot navigasjon og støtten for nye kolonnenavn. Den er ikke en visuell test på fysisk iPhone; mobilutseendet må også bekreftes etter deploy. Produksjonsparametre er ikke endret av disse testene.

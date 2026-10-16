# Roadmap fase 3 – faktisk betydning av HOLD / WAIT

Kontrollert mot `services/autonomy_technical_contribution_service.py` på `main`, 15.10.2026.

`HOLD`, `WAIT` og `NEUTRAL` er nøytrale observasjonssignaler i bidragstjenesten. De kan ikke gi ekstra positive tekniske poeng eller autorisere ordre. `SELL` og `AVOID` kan gi negativ scorejustering. Et teknisk venteflagg settes ved SELL/AVOID eller ved lav teknisk score med tilstrekkelig høy sikkerhet. `technical_can_authorize_execution=false` og `technical_hard_gates_unchanged=true` er eksplisitt definert.

De tre dokumenterte tapskjøpene med `HOLD / WAIT` beviser derfor ikke feil i koblingstjenesten. Neste forsøk må teste om det er fordelaktig å kreve sterkere inngangsbekreftelse. Det krever sammenlignbare kjøp og avviste vinnere med kun samtidige data. Manglende BUY-gruppe i loggene er en reell evidensbegrensning.

Anbefaling: Ikke innfør hard teknisk BUY-sperre, og ikke svekk eksisterende stop-loss. Prioriter datadekning, inngang etter kursoppgang, og målbar etterfølgende risiko/avkastning i Shadow. Ingen produksjonsparameter er endret.

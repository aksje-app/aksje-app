# Roadmap fase 3 – årsak til manglende kurstidspunkt

Kilde: `services/market_snapshot_service.py` på main, funksjonen `_price_and_timestamp`, kontrollert mot lagrede Autonomi-markedssnapshoter for VTURA.OL, AKER.OL og CMBTO.OL.

Når kandidaten har et gyldig positivt `price`, `current_price`, `last_price`, `close`, `regularMarketPrice` eller `last`, returneres tallet sammen med `item.price_timestamp` eller `item.data_timestamp`. Hvis disse feltene mangler, returneres tom streng. Kun når ingen slike prisfelt finnes og `hist.Close` finnes, hentes tid fra historikkens siste indeks.

Dette forklarer hvordan et snapshot kan ha `captured_at` og dokumentert kjøpskurs, men tom `data_timestamp`. `captured_at` er analyse-/innsamlingstidspunkt, og er **ikke** dokumentasjon på børsens kurstid. Historikkens siste indeks kan ikke brukes som prisens tid uten verifisert samsvar med valgt prisfelt.

Neste implementeringsoppgave: innfør eksplisitt `price_timestamp_status` (`VERIFIED`, `UNKNOWN`, `STALE`) samt kilde og sammenligning mot snapshot-tid, basert kun på autentiske provider-metadata. Hold `UNKNOWN` når provider-tid mangler; ikke fyll inn `captured_at`. Test før senere justering av kjøpsgater og vurder ytelse/DB-kostnad. Eksisterende historiske poster skal ikke retroaktivt påstå ferskhet.

Ingen endring av kjøpsparametere, produksjonshandel eller database i denne revisjonen.

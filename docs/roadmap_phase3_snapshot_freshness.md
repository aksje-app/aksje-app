# Roadmap fase 3 – kursferskhet ved problematiske innganger

Kontroll: Render Postgres read-only, `repositories/market_snapshots_index.json` og tilhørende snapshot-elementer. Matchet på `run_id` og ticker til tre dokumenterte kjøp: VTURA.OL (23.09.2026), AKER.OL (15.09.2026), CMBTO.OL (12.10.2026).

Alle tre kjøpssnapshotene finnes og har `captured_at` og `price`, men kandidatens `data_timestamp` er tom. Snapshot-postene har ingen egne RSI-, momentum-, trend- eller historiske kursavkastningsfelt. Dette er en sporbarhetsmangel; **det beviser ikke at kursene var foreldet**, eller at aksjene var overkjøpte.

Oppfølging: Finn opprinnelig provider-tid fra uavhengige lagrede metadata hvis tilgjengelig; dokumenter forskjell mellom hentetid, snapshot-tid og børsens kurstid; krev eksplisitt FRESH/UNKNOWN/STALE i forbedrede diagnoseeksporter. Ingen kjøp skal få oppdiktet datotid. Gjør tester på alle kandidater før en eventuell produksjonsendring, ikke bare tre utvalgte tapere. Ikke utvid historisk market scan.

Roadmap: Fase 2–3, økonomisk effekt ennå ikke validert. Ingen produksjonsregler endret.

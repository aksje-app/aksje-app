# v19.14.1 – implementasjon og verifikasjon

## Utgangspunkt

Live-kjøringen av v19.14.0 avdekket at AAPL kunne kjøpes og selges selv om kandidaten ikke var kjøpsgodkjent, at runtime-versjoner var usynkroniserte, at Enkel-modus arvet seks markeder, og at rapporten kunne vise foreldede utfall og engelske internkoder.

## Løsning

v19.14.1 legger autorisasjonen i ordrelaget, ikke bare rapportlaget. Ordinære handler buffers til en samlet integritetskontroll er bestått. Rapportlaget har en separat fail-closed kontroll som avviser enhver kombinasjon av handler og kandidatstatus som ikke kan dokumenteres.

Kandidatmodellen kanoniseres én gang. Beslutningsreduksjon og beslutningstrakt synkroniseres deretter, og PDF/JSON leser samme sluttverdier. Historiske råkopier isoleres og komprimeres.

Enkel-modus bruker en egen eksplisitt markedsprofil. Standardprofilen er Norge, Sverige og USA. Programmet viser markeder, strategi, datakvalitet, kandidatantall, produksjonsterskel og aktive ekspertregler før start.

## Avgrensning

Kontrollen bruker det faktiske live-datagrunnlaget fra v19.14.0, men ikke en ny ekstern markedsskanning. Offisielle kildeadaptere og nettverkspolicy er offline-testet. Produksjonsmiljø, kildeaksess og fysisk mobil må testes etter deploy.

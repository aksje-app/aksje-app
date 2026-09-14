# Valideringsrapport – RC16.31cg

## Omfang

Hele interne varslingskjeden er kontrollert fra markedsdata via signalberegning, tilstand, deduplisering, Pushover-formatering, rapportering, nedlasting og paper-portefølje. Eksterne liveleveranser er ikke simulert som bevis på faktisk nettlevering; dette må bekreftes med én kontrollert Render-kjøring etter deploy.

## Produksjonsnære scenarier

- ROGS: 95 → 81 gir MISTER MOMENT og negativ samlet retning, aldri AKSELERERER.
- WWI: 92 → 75 → 80 forblir under hysterese etter én bedring.
- DNO: sterkt oppsett kan ha sidelengs kortsiktig retning uten at begrepene blandes.
- Fullscan: en oppfølgingskø på 12 beholder den autoritative RS-referansen fra fullscan og kan ikke kalle 12 aksjer «markedet».
- Volum: pågående dagsvolum merkes som ufullført/ikke tidsjustert og brukes ikke negativt som om børsdagen var ferdig.
- Meldingslengde: avkorting skjer ved hele linjer, uten duplisert eller halv datafot.
- Samtidighet: bare én Fresh Trend-monitor kan sende fra samme kjøring.
- Salg: delvis gevinstsikring og navngitt erstatningskandidat er kontrollert.

## Begrensninger

- Historiske tester som eksplisitt krever gamle RC-versjoner eller fjernet UI er beholdt urørt og rapporteres separat.
- Full garanti mot alle fremtidige kombinasjoner er ikke mulig. Nye produksjonsforløp skal legges til som replay-regresjoner før en senere versjon erklæres ferdig.


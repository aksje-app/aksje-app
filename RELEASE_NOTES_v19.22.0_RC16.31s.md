# RC16.31s – Mobile Report Return Closure

RC16.31s er bygget direkte fra RC16.31r og retter mobilnavigasjonen fra offentlige rapportlenker.

## Endringer

- Automatisk `window.top.location.replace` er fjernet fra rapporttoken-siden.
- Pushover-lenken viser en mobilvennlig mellomside uten å erstatte programfanen.
- Brukeren kan laste ned PDF, åpne den eksplisitt i ny fane eller gå tilbake til AI Aksje Analyzer.
- Rapport-URL og HTML-attributter saniteres før rendering.

## Uendret

Rapporttoken, offentlig PDF-lagring, rapportinnhold, scheduler, produksjonsterskel 73, porteføljeregler og fail-closed handel er uendret.


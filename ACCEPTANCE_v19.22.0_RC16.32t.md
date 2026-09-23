# Godkjenning RC16.32t

- Verifiser VEI.OL med offentlig melding og vedlegg; vis ansattprogram og personlige aksjeantall uten kjøpsboost.
- Verifiser at feil summering, tvetydige kolonner og vedlegg fra ukjent vert gir null bekreftede kjøp.
- Sjekk at Superporteføljen kontrollerer eide navn og maksimalt fem finalister per marked, samt at bredskanningens ytelse ikke påvirkes av kontroll for hele universet.
- Kjør `PYTHONPATH=/tmp/aurora-test-deps:. python -m pytest -q tests/test_rc16_32t_insider_programme.py tests/test_mobile_pdf_return_link.py tests/test_rc16_32q_priority_reporting.py`.

Live datatilgang på Render og gjenfinning av den virkelige VEI-meldingen må verifiseres etter utrulling.

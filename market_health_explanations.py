"""Plain-language explanations for all 14 Shadow market gauges.

Explanations and display bands are indicative only; never trade signals.
"""
GAUGE_GUIDE = {
"vix": ("Forventede børssvingninger", "Høyere tall betyr at opsjonsmarkedet priser større svingninger neste 30 dager.", "Lavere er vanligvis roligere, men lav VIX garanterer ikke trygghet."),
"trend": ("Indeksens langsiktige kursretning", "Positivt tall betyr at S&P 500 er over sitt eget 200-dagerssnitt.", "Negativt tall antyder svakere trend. Se også markedsbredde."),
"breadth": ("Hvor mange aksjer deltar i oppgangen?", "55 % betyr at 55 av 100 aksjer med godkjent historikk er over eget 200-dagerssnitt.", "Høyere bredde betyr mer utbredt positiv trend, men ikke automatisk lav risiko."),
"credit": ("Stress i selskapsobligasjoner", "Viser ekstrarenten selskaper med svakere kreditt får betale.", "Brå økning tyder ofte på større finansieringsbekymring."),
"curve": ("Forskjell mellom lange og korte renter", "10-årsrenten minus 2-årsrenten. Negativt tall betyr invertert rentekurve.", "Kan varsle konjunktursvakhet, men sier ikke når et fall kommer."),
"cape": ("Hvor dyrt er aksjemarkedet?", "Prisnivå sammenlignet med ti års inflasjonsjustert inntjening.", "Høy verdi betyr dyrere prising historisk, ikke at et fall er nært."),
"equity_yield": ("Utbytter og tilbakekjøp", "Anslått andel av indeksverdien distribuert til aksjonærene i året.", "Ikke det samme som forventet avkastning. Årlige data oppdateres langsommere."),
"us10y": ("Amerikansk tiårsrente", "Renten på amerikanske statsobligasjoner med omtrent ti års løpetid.", "Sterk renteoppgang kan presse aksjeprising; effekten avhenger av årsaken."),
"us30y": ("Amerikansk trettiårsrente", "Lang amerikansk statsrente og et mål på langsiktige finansieringsvilkår.", "Se sammen med tiårsrenten; disse er ikke to uavhengige signaler."),
"brent": ("Oljepris per fat", "Prisen på referanseoljen Brent i amerikanske dollar per fat.", "Høyere pris kan hjelpe energiselskaper og samtidig øke inflasjonspress."),
"ttf": ("Europeisk gasspris", "Europeisk referansepris for naturgass, normalt EUR per MWh.", "Kontraktstype og sesong betyr mye; høy pris er ikke alene et børssignal."),
"gold": ("Gullpris", "Gullpris per troy ounce i amerikanske dollar.", "Høy gullpris er et prisnivå, ikke en måling av børsfrykt."),
"dxy": ("Hvor sterk er dollaren?", "Dollarindeks mot en valutakurv der euro har størst vekt.", "En sterk dollar kan stramme finansielle vilkår, men er ikke alltid negativ."),
"eurusd": ("Dollar per euro", "Antall amerikanske dollar som én euro kjøper.", "Fall betyr sterkere dollar mot euro. Overlapper med DXY."),
}

def explain(key, value=None):
    title, meaning, caution = GAUGE_GUIDE[key]
    return {"question": title, "meaning": meaning, "caution": caution, "note": "Fargene er foreløpige nivåsoner, ikke validert risiko eller kjøp/salg."}

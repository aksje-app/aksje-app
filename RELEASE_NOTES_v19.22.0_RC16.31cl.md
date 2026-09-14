# RC16.31cl – fremdrift, modulstyring og automatisk markedshvile

Jeep Commander 2.2 viser nå varig teststatus for API, OLX, Webmotors og Pushover. DataForSEO-feil forsvinner ikke lenger ved automatisk sideoppdatering. Test og manuelt søk viser prosentvis fremdrift gjennom kildeinnhenting, DataForSEO, tolking, filtrering, rangering, historikk og varsling.

Søke- og testknappene blir utilgjengelige mens en jobb kjører. Modulen har separate tilstander Aktiv, Pauset og Stoppet, i tillegg til direkte handlingsknapper. Pause stanser automatiske søk og beholder historikken; Stoppet blokkerer også manuelle søk og Pushover. En stopp lagret fra en annen aktiv sesjon blir kontrollert mellom kildene.

Automatiske bilsøk har som standard nattpause 01:00–06:00 etter Fortaleza-tid. Start og slutt kan endres. Manuelle søk er fortsatt mulig i nattpausen så lenge modulen ikke er Stoppet. Antall sparte nattkontroller og neste kontrolltid lagres.

Aksjeskanneren brukte allerede markedskalender for hovedskanningen. Denne versjonen utvider samme regel til Fresh Trend-kandidatoppfølgingen: ingen kostbar kurs-/nyhetsoppdatering eller Pushover når alle kandidatenes markeder er stengt. Helger, børshelligdager, markedsspesifikke åpningstider og sommertid håndteres per marked. Rapporter, valutavarsler og vedlikehold fortsetter uavhengig.

System/admin viser markedets status, lokal børstid, neste åpning, antall hoppede lukkede kontroller og estimerte fulle scannerkjøringer spart.

Produksjonsbevis for virkelige DataForSEO-resultater må fortsatt utføres etter deploy med Render-hemmelighetene. Automatiseringen er låst inntil både OLX og Webmotors er godkjent.

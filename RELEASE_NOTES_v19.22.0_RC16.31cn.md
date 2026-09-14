# RC16.31cn – DataForSEO-diagnose

- Viser organiske resultater, godkjente enkeltannonser og forkastede resultater per markedsplass.
- Viser konkret forkastelsesårsak, tittel, domene og URL for hvert resultat.
- Skiller API-feil, null organiske resultater og resultater som annonsefilteret forkastet.
- Ny knapp laster ned en sikker diagnose-ZIP med `LES_MEG.txt` og `dataforseo_diagnose.json`.
- ZIP-en inkluderer markedsplassstatus, API-taskstatus, kostnad, resultatmetadata og filterbeslutninger.
- API-login, API-passord, autentiseringsheadere og øvrig autentisering tas ikke med.
- DataForSEO-testen er fortsatt stille og sender ingen Pushover.

Diagnosen endrer ikke godkjenningsfilteret i denne versjonen. Den skal først vise det faktiske produksjonssvaret slik at eventuell URL-regel eller søkefrase kan rettes på dokumentert grunnlag.

# Validering v19.22.0-rc16.21

Målrettede tester dekker:

- autoritativ cron etter prosessoppstart;
- avvisning av vilkårlig gammel tidsluke;
- restart-aware webstatus uendret;
- checksum-verifisert Paper-bro;
- uendret kandidat-score og porteføljehandling;
- avvisning av manipulert bro;
- separate schedulerflagg for web og cron;
- varig Paper-status og global lås;
- eksisterende ubetjent scheduler, runtime-sikkerhet og rapportdiagnostikk.

Lokale resultater:

- Python-kompilering: bestått;
- 66 målrettede tester: bestått;
- full regresjon: 758 bestått og 4 deltester bestått;
- 37 eldre regresjonstester feiler fortsatt på historiske versjonskontrakter og tidligere rapportsemantikk. Ingen av de nye RC16.21-testene feiler.

Live-status forblir `LOCAL_PASS_LIVE_REQUIRED` til en planlagt jobb er observert ende-til-ende på Render uten innlogget bruker.

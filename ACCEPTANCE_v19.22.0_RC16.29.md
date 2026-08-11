# Akseptanse v19.22.0-rc16.29

1. En kjøring med tre `action=BUY`-handler og tom shared `fills` skal bestå
   lærings-/rapportkonsistens med tre kjøp.
2. En shared `side=BUY`-handel skal fortsatt være canonical og bestå.
3. `OBSERVE` skal gi `first_blocker_code=NONE`.
4. En simulert feil skal ende `FAILED`, sette `completed_at` og frigjøre worker.
5. Autonomi skal sende fremdrift mellom fullført beslutningskjede,
   læringsaksept og rapportaudit.
6. Produksjonshandler skal fortsatt være adskilt fra `LEARNING_ONLY`.

Liveaksept krever én Render-kjøring som ender med rapport, Pushover og
læringsaksept `PASS` uten `STALLED`.

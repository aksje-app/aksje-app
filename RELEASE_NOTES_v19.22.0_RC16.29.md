# v19.22.0-rc16.29

RC16.29 retter den dokumenterte feilen fra diagnose MBJ-20260809-094352-CE87AF.

- Canonical læringshandler normaliserer nå både `side` og `action`.
- Tom delt læringskonto faller kontrollert tilbake til de faktiske, lagrede
  `LEARNING_ONLY`-handlene fra samme Autonomi-kjøring.
- Autonomi publiserer reell fremdrift etter kjeden, etter læringsaksept og før
  rapportkonsistenskontrollen, slik at en gyldig kjøring ikke feilaktig blir
  frigitt ved femminuttersgrensen.
- `OBSERVE` er et gyldig læringsutfall og registreres ikke lenger som
  `UNCLASSIFIED_BLOCKER`.
- Feilbanen er regresjonstestet for terminal `FAILED` og umiddelbar frigivelse
  av den lokale workerregistreringen.

Ingen ordinære kjøpsporter, produksjonsterskler eller virkelige handler er
endret.

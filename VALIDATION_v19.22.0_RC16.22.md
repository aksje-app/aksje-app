# Validering v19.22.0-rc16.22

- Python-kompilering: bestått.
- 17 målrettede scheduler-, lås-, cron-, varsling- og regresjonstester: bestått.
- Full regresjon: 758 bestått og 4 deltester bestått.
- 42 eldre tester forventer historiske versjonsnumre, tidligere rapportsemantikk, femminutters cron eller at webgrensesnittet starter scheduler. Disse forventningene er ikke produksjonskontrakten i RC16.22.

Live-akseptanse krever at Render Cron fullfører uten innlogget bruker, at samme rapport ikke kjøres to ganger, og at Pushover-kvitteringen inneholder riktig rapport-ID.

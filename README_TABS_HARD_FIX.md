# Tabs Hard Fix

Fikser:
- KeyError: 'bonus'
- signal_engine returnerer bonus for gammel UI-kompatibilitet
- fanene USA/Norge/Sverige henter nå markedet direkte
- sidepanelets markedvalg trengs ikke for fanene

Merk:
Hvis app.py har en helt annen tabs-struktur enn forventet, må vi patch direkte på den konkrete linjen.

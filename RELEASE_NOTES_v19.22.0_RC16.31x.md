# RC16.31x – Render Autonomi-minnehotfix

RC16.31x er bygget direkte fra RC16.31w.

- Autonomi-snapshot ekskluderer komplette råpayloads, dokumenter og artikkeltekster.
- Hvert kandidatsnapshot har rekursive grenser og maksimalt 96 KiB beslutningsinput.
- Snapshotbygging rapporterer fremdrift per ti kandidater.
- Bakgrunnsdiagnosen lagrer prosessens maksimale RSS-minnebruk.
- Fersk heartbeat før restart i Autonomi klassifiseres som sannsynlig ressursrestart, uttrykkelig som inferens.
- Foreldreløs rapport-eier frigjøres etter bekreftet prosessrestart.

Ingen handelsfullmakt, produksjonsterskel eller planlagt rapporttid er endret.

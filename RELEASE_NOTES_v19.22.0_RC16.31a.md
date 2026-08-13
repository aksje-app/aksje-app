# v19.22.0-rc16.31a

RC16.31a skiller rapportmotorens og Paper-skannerens globale låser, etablerer en eksplisitt Paper-cron og gjør skannestatusen sporbar med heartbeat, skann-ID, siste vellykkede skann og handelsspor.

Rapportmotoren vurderer nå `THEORETICAL_DECISIONS` fra det faktiske autonome porteføljesteget. En separat feil i kontrollert læring kan ikke lenger feilmerke en allerede dokumentert teoretisk beslutning. Reelt blokkerte eller manglende beslutninger feiler fortsatt lukket.

Midlertidige rapporttestjobber lagres ikke som ordinære jobbprofiler. Gamle testprofiler fjernes ved innlasting, og jobbskjemaet nullstiller forrige profils widgettilstand ved profilbytte.

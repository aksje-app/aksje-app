# Deploy RC16.31c

Deploy FULL eller kopier DELTA-innholdet til repositoryroten. Kontroller at kun én dedikert
`aksje-app-paper-scanner` finnes. Reservekjøringen i rapport-cron aktiveres bare når Paper-heartbeat
er eldre enn 45 minutter og bruker samme Paper-lås, slik at den ikke kan gi doble handler.

Etter deploy: bekreft programversjon, tre faste jobber, Paper-heartbeat og neste vellykkede skann.

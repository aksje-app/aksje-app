# Deploy RC16.31co

1. Pakk ut den rene deltaen over RC16.31cn.
2. Deploy samme kilde/commit til web og scheduler.
3. `EXPECTED_APP_VERSION` trenger ikke endres.
4. Åpne Jeep Commander 2.2 og bekreft: Hver 2. time, nattpause 00–07 og månedsgrense USD 12.
5. Kjør «Test DataForSEO uten varsler» én gang.
6. Aktiver DataForSEO bare dersom både OLX og Webmotors blir grønne.
7. Hvis én kilde fortsatt er rød, last ned den nye diagnose-ZIP-en og last den opp i samtalen.

Den stille testen bruker anslagsvis USD 0,04 og sender ingen Pushover.

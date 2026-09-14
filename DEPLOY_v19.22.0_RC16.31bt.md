# Deploy RC16.31bt

1. Deploy CLEAN DELTA oppå RC16.31bs.
2. Bekreft at web, scheduler og paper scanner viser `v19.22.0-rc16.31bt` og samme commit.
3. Start ett nytt Norge-utkast eller vent til neste univershenting.
4. Søk Render-loggen etter `NORWAY_UNIVERSE`.
5. Godkjenn bare dersom status er `OFFICIAL_LIVE` eller en tidligere verifisert `OFFICIAL_LAST_KNOWN_GOOD`.
6. `FALLBACK_UNVERIFIED` er fortsatt FAIL for komplett Norge-dekning.

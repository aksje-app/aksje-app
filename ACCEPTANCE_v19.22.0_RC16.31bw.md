# Acceptance RC16.31bw

PASS when all are true:
1. Runtime identities are all `v19.22.0-rc16.31bw` on one commit.
2. Norway master finishes `OFFICIAL_LIVE` with `source_authoritative_exchange_master=true`.
3. Official universe count is >150 and the packaged 82-symbol fallback is not active.
4. Exchange breakdown identifies Oslo Børs, Euronext Growth Oslo and Euronext Expand Oslo separately.
5. If `CURRENT_JSON_POST` is used, parsed rows are no longer 0 when `records_filtered` is about 294.
6. Main scan/Fresh Trend and Paper Trade continue to consume the shared Norway master.
7. BQ memory/terminal status, BS evidence semantics and Norway-only scanner policy remain unchanged.

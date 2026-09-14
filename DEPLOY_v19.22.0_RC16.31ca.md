# Deploy RC16.31ca

1. Deploy the clean DELTA files to the same GitHub/Render branch used by web, scheduler and paper scanner.
2. Confirm all services report `v19.22.0-rc16.31ca` and the same commit.
3. Open the latest completed report and confirm there is one **Rapportfiler** block with Standard PDF, Technical PDF, JSON and Diagnostic ZIP.
4. Build/download the complete report ZIP and verify it contains `report/report.pdf`, `report/report_technical.pdf`, `report/report.json` and, for a manual run with durable diagnostics, `diagnostics/*.zip`.
5. Confirm recommendation/observation/rejection tables show Oslo Børs / Euronext Growth Oslo / Euronext Expand Oslo rather than the generic country label when exchange metadata exists.
6. During an overnight run before Oslo opens, confirm a new learning observation waiting for the first post-entry trading day does not set global learning status to `DEGRADERT` solely for that reason.
7. Confirm the BZ progress display remains smooth and monotonic.

No environment-variable changes are required.

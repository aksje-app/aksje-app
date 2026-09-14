# Deploy RC16.31bq

1. Last opp filene fra clean DELTA til repository-roten og commit/push.
2. Verifiser at både web og scheduler viser `v19.22.0-rc16.31bq` og samme commit.
3. Kjør én Norge-only manuell rapport.
4. Last ned diagnosepakken og kontroller:
   - `state=COMPLETED`, `chain_status=OK` og `progress_event.status=COMPLETED` samtidig.
   - `resource_telemetry` er post-cleanup og viser cgroup anon/file-fordeling.
   - cgroup headroom er vesentlig bedre enn tidligere 170.7 MB; ønsket mål er > 500 MB dersom plattformen tillater reclaim.
5. Når Norge er stengt og andre markeder er åpne, scannerloggen skal si at ingen *aktiverte produksjonsmarkeder* er åpne, ikke at alle markeder er stengt.

Hvis `memory.reclaim` ikke er tillatt på Render, skal rapporten fortsatt fullføres. Diagnosen vil da vise reclaim som unsupported/permission error; dette er ikke en kjedefeil.

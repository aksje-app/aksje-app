# Deploy RC16.31bu

Deploy the clean DELTA on top of RC16.31bt/bs/br lineage and let all Render services reach the same commit.

After deploy, run one Norway draft/full report and inspect Render log for `NORWAY_UNIVERSE_ATTEMPT` and final `NORWAY_UNIVERSE` status.

If fallback remains active, download the diagnosis package. It must contain:
- `market/NORWAY_UNIVERSE_FETCH_DIAGNOSTICS.json`
- `market/NORWAY_UNIVERSE_MASTER_STATUS.json`

These files should identify the failed source, HTTP status/content type or parser result and concrete exception.

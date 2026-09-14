# Deploy RC16.31bw

Deploy the clean DELTA on top of RC16.31bv lineage and let web, scheduler and paper scanner reach the same commit.

After deploy, run one Norway Utkast/full report.

Expected PASS paths:
- Preferred: three `OFFICIAL_CSV_EXPORT` attempts (`MIC_XOSL`, `MIC_MERK`, `MIC_XOAS`) combine to >150 validated instruments.
- Secondary: `CURRENT_JSON_POST` reports `records_filtered=294` and parser `json_html_cells_flexible` with approximately the same parsed row count.
- Final master: `NORWAY_UNIVERSE status=OFFICIAL_LIVE`, count >150 and a non-zero split across Oslo Børs / Euronext Growth Oslo / Euronext Expand Oslo.

Do not accept `FALLBACK_UNVERIFIED` or the packaged 82-symbol universe as complete coverage.

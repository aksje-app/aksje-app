# Acceptance v19.22.0-rc16.31be

Local acceptance requires compile success, targeted production-closure tests, package structure validation and no changes to production decision thresholds.

Live Render acceptance additionally requires:
- authoritative PostgreSQL healthy outside transient recovery windows;
- retention APPLY effective and deleting only bounded, unprotected expired objects;
- one complete scanner cycle without unresolved storage finalization;
- complete 08:00, 14:00 and 22:00 report sequence with JSON, PDF and Pushover;
- no duplicate authoritative reports and no unresolved recovery receipt.

# Acceptance RC16.8

- Reports draft button uses `start_shared_manual_draft_job`, the same authoritative starter as Overview.
- No explicit full-page rerun after draft start in Reports.
- Manual job progress remains a Streamlit fragment.
- Complete replay ZIP reports collection, report packaging, runtime data, compression and integrity stages.
- Replay progress uses real work units and updates in a 3-second fragment.
- Download is exposed only after persisted ZIP integrity and SHA-256 verification.

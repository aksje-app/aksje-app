# Endringsinventar RC16.31y

- `services/market_snapshot_service.py`: full feltavgrensning, 32 KiB-grense og strømmende checksum.
- `domain/market_snapshot.py`: grunne, kontraktbevarende `to_dict()`-operasjoner.
- `autonomous_portfolio.py`: cgroup-basert minnevakt for valgfri parallellstrategi.
- `manual_job_background.py`: komplett ressurs- og restartdiagnose i ZIP.
- `app_version.py`: RC16.31y-identitet og historikk.
- Oppdaterte minne-, snapshot-, strategiprosess- og versjonstester.

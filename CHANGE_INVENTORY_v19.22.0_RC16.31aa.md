# Endringsinventar RC16.31aa

- `repositories/application.py`: separat immutable snapshotlagring, lett indeks og legacy-kompatibel lesing.
- `autonomous_portfolio.py`: eksplisitt lagringsfremdrift og gjenbruk av allerede materialisert snapshot.
- `pages/strategy_versions.py`: begrenset snapshotvisning.
- `pages/strategy_lab.py`: begrenset interaktiv snapshotlasting.
- `tests/test_rc16_31aa_snapshot_repository_memory.py`: historikk-, immutable-, indeks- og gjentatt-lagringstester.
- `app_version.py` og versjonskontrakttester: RC16.31aa-identitet.


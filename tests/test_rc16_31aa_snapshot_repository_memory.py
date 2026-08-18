from repositories.application import MarketSnapshotRepository
from services.storage_service import StorageService


class RecordingStorage(StorageService):
    def __init__(self, base_dir):
        super().__init__(base_dir=base_dir, database_url="", mode="local")
        self.reads: list[str] = []

    def read_json(self, name, default=None):
        self.reads.append(str(name))
        return super().read_json(name, default)


def _snapshot(snapshot_id: str, payload_size: int = 1000):
    return {
        "snapshot_id": snapshot_id,
        "captured_at": "2026-08-18T10:00:00+00:00",
        "source": "test", "run_id": f"RUN-{snapshot_id}",
        "checksum": f"checksum-{snapshot_id}",
        "candidates": [{"ticker": "AAA", "decision_inputs": {"padding": "x" * payload_size}}],
    }


def test_new_snapshot_save_never_reads_or_rewrites_legacy_collection(tmp_path):
    storage = RecordingStorage(tmp_path)
    legacy = [_snapshot(f"LEGACY-{index}", 20_000) for index in range(40)]
    storage.write_json("repositories/market_snapshots.json", legacy)
    storage.reads.clear()
    repository = MarketSnapshotRepository(storage)

    repository.upsert(_snapshot("NEW-1"))

    assert "repositories/market_snapshots.json" not in storage.reads
    assert storage.read_json("repositories/market_snapshots.json", [])[0]["snapshot_id"] == "LEGACY-0"
    assert repository.get("NEW-1")["checksum"] == "checksum-NEW-1"


def test_legacy_snapshot_remains_readable_without_migration_or_deletion(tmp_path):
    storage = RecordingStorage(tmp_path)
    storage.write_json("repositories/market_snapshots.json", [_snapshot("OLD-1")])
    repository = MarketSnapshotRepository(storage)

    assert repository.get("OLD-1")["snapshot_id"] == "OLD-1"
    repository.upsert(_snapshot("NEW-2"))
    listed = repository.list(limit=2)
    assert [row["snapshot_id"] for row in listed] == ["NEW-2", "OLD-1"]


def test_repeated_saves_only_grow_lightweight_index(tmp_path):
    storage = RecordingStorage(tmp_path)
    repository = MarketSnapshotRepository(storage)
    for index in range(75):
        repository.upsert(_snapshot(f"NEW-{index}", 30_000))
    index = storage.read_json(repository.INDEX_KEY, [])
    assert len(index) == 75
    assert all("candidates" not in row for row in index)
    assert sum(len(str(row)) for row in index) < 50_000
    assert repository.list(limit=3)[0]["snapshot_id"] == "NEW-74"


def test_same_snapshot_id_cannot_be_rewritten_with_different_checksum(tmp_path):
    storage = RecordingStorage(tmp_path)
    repository = MarketSnapshotRepository(storage)
    repository.upsert(_snapshot("IMMUTABLE"))
    changed = _snapshot("IMMUTABLE")
    changed["checksum"] = "different"
    try:
        repository.upsert(changed)
    except ValueError as exc:
        assert "annen checksum" in str(exc)
    else:
        raise AssertionError("immutable snapshot rewrite was accepted")

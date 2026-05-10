"""
services/storage_service.py

Small JSON storage adapter for local/Render filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from core_models import ServiceResult
except Exception:
    ServiceResult = None  # type: ignore


class StorageService:
    def __init__(self, base_dir: str = "data/services"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def read_json(self, name: str, default: Any = None) -> Any:
        path = self.base_dir / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, name: str, data: Any) -> bool:
        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def append_jsonl(self, name: str, row: Dict[str, Any]) -> bool:
        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True

    def read_jsonl(self, name: str, limit: int = 500) -> List[Dict[str, Any]]:
        path = self.base_dir / name
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        return rows


_default_storage = StorageService()


def get_storage_service() -> StorageService:
    return _default_storage

"""Application persistence facade for v19.2.0."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from repositories.application import RepositoryRegistry, get_repository_registry
from services.storage_service import StorageService, get_storage_service

@dataclass(frozen=True)
class PersistenceStatus:
    backend: str
    persistent: bool
    healthy: bool
    message: str
    schema_version: str = "2.0"

class PersistenceService:
    def __init__(self, storage: StorageService | None = None):
        self.storage = storage or get_storage_service()
        self.repositories: RepositoryRegistry = get_repository_registry(self.storage)

    def status(self) -> PersistenceStatus:
        health = self.storage.health()
        return PersistenceStatus(health.backend, health.persistent, health.ok, health.message)

    def require_persistent_backend(self) -> None:
        status = self.status()
        if not status.persistent:
            raise RuntimeError("PostgreSQL er ikke aktiv. Lokal fallback er kun tillatt for utvikling og test.")

    def repository(self, name: str) -> Any:
        if not hasattr(self.repositories, name):
            raise KeyError(f"Unknown repository: {name}")
        return getattr(self.repositories, name)

_default: PersistenceService | None = None

def get_persistence_service() -> PersistenceService:
    global _default
    if _default is None:
        _default = PersistenceService()
    return _default

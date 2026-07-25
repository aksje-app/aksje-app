"""Persistent repository layer for AI Aksje Analyzer v19.2.0."""
from repositories.application import RepositoryRegistry, get_repository_registry
from repositories.base import DocumentRepository, EventRepository, JsonRepository

__all__ = [
    "RepositoryRegistry", "get_repository_registry", "DocumentRepository",
    "EventRepository", "JsonRepository",
]

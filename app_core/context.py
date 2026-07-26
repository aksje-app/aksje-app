"""Explicit application context for extracted Streamlit renderers.

v19.2.x passed the complete ``globals()`` dictionary directly into every
extracted page. v19.5.0 keeps backward compatibility while exposing only names
that the target renderer's code objects actually reference. Services,
repositories, the authenticated user and the version contract are first-class
context properties.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import CodeType
import inspect
from typing import Any, Iterator, Mapping

from app_version import get_version_contract
from services.service_registry import ServiceRegistry, get_service_registry


def _code_names(code: CodeType) -> set[str]:
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(_code_names(value))
    return names


@dataclass(frozen=True)
class ApplicationContext(Mapping[str, Any]):
    """Read-only renderer context with explicit infrastructure dependencies."""

    exports: Mapping[str, Any]
    user: Any = None
    services: ServiceRegistry | None = None
    version_contract: Mapping[str, Any] = field(default_factory=get_version_contract)
    renderer_name: str = ""

    @property
    def repositories(self):
        return self.services.repositories if self.services is not None else None

    def __getitem__(self, key: str) -> Any:
        if key == "app_context":
            return self
        if key == "current_user" and self.user is not None:
            return self.user
        if key == "service_registry" and self.services is not None:
            return self.services
        if key == "repository_registry" and self.repositories is not None:
            return self.repositories
        if key == "version_contract_v1950":
            return dict(self.version_contract)
        return self.exports[key]

    def __iter__(self) -> Iterator[str]:
        names = set(self.exports)
        names.add("app_context")
        names.add("version_contract_v1950")
        if self.user is not None:
            names.add("current_user")
        if self.services is not None:
            names.update({"service_registry", "repository_registry"})
        return iter(sorted(names))

    def __len__(self) -> int:
        return sum(1 for _ in self.__iter__())

    def diagnostics(self) -> dict[str, Any]:
        return {
            "renderer": self.renderer_name,
            "export_count": len(self.exports),
            "service_registry": self.services is not None,
            "repository_registry": self.repositories is not None,
            "app_version": self.version_contract.get("app_version"),
        }


def build_renderer_context(
    namespace: Mapping[str, Any],
    renderer: Any,
    *,
    user: Any = None,
    services: ServiceRegistry | None = None,
) -> ApplicationContext:
    """Build the smallest compatible context for one extracted renderer.

    Names are derived from the renderer and nested code objects, then resolved
    against the application namespace. This removes the previous unrestricted
    mutation bridge while keeping legacy pages functional during staged
    dependency injection.
    """
    code = getattr(renderer, "__code__", None)
    required = _code_names(code) if isinstance(code, CodeType) else set(namespace)
    closure_values: dict[str, Any] = {}
    try:
        closure = inspect.getclosurevars(renderer)
    except (TypeError, ValueError):
        closure = None
    if closure is not None:
        for group in (closure.nonlocals, closure.globals):
            closure_values.update(group)
            required.update(group)
    # Function objects imported from the application shell retain their own
    # module globals. Only names referenced directly by the renderer and its
    # nested local code must therefore be exported into the page module.
    exports = {
        name: (namespace[name] if name in namespace else closure_values[name])
        for name in required
        if not name.startswith("__") and (name in namespace or name in closure_values)
    }
    return ApplicationContext(
        exports=exports,
        user=user,
        services=services or get_service_registry(),
        renderer_name=getattr(renderer, "__qualname__", getattr(renderer, "__name__", "renderer")),
    )

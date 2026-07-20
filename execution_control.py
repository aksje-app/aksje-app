"""Shared cooperative execution-control primitives."""


class ExecutionCancelled(RuntimeError):
    """Raised at a safe checkpoint after a persisted stop request."""


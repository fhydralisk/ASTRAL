"""Transport-independent Harness services."""

from .base import HarnessService, ServiceError

__all__ = ["HarnessService", "ServiceError", "LocalHarnessService", "HttpHarnessService"]


def __getattr__(name):
    if name == "LocalHarnessService":
        from .local import LocalHarnessService

        return LocalHarnessService
    if name == "HttpHarnessService":
        from .client import HttpHarnessService

        return HttpHarnessService
    raise AttributeError(name)

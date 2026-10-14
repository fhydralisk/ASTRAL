# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
"""Small infrastructure helpers shared by API provider adapters."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping


class RemoteModelCatalog:
    """Fetch and briefly cache one provider's remote model catalog."""

    def __init__(
        self,
        http_client: Callable[[str], Any],
        *,
        cache_seconds: float = 300.0,
    ) -> None:
        self._http_client = http_client
        self._cache_seconds = cache_seconds
        self._models: list[str] | None = None
        self._cached_at = 0.0

    def get(
        self,
        url: str,
        *,
        description: str,
        api_key: str | None = None,
        params: Mapping[str, str] | None = None,
        include: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[str]:
        """Return a model list, propagating failures without caching them."""
        now = time.monotonic()
        if self._models is not None and now - self._cached_at < self._cache_seconds:
            return list(self._models)

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        with self._http_client(url) as client:
            response = client.get(
                url,
                headers=headers,
                params=dict(params or {}),
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()

        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ValueError(f"{description} response does not contain a data list")
        models = sorted(
            {
                model_id.strip()
                for record in records
                if isinstance(record, dict)
                and (include is None or include(record))
                and isinstance((model_id := record.get("id")), str)
                and model_id.strip()
            }
        )
        if not models:
            raise ValueError(f"{description} returned no model identifiers")

        self._models = models
        self._cached_at = now
        return list(models)

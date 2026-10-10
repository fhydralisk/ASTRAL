from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


def _gateway_module():
    path = Path(__file__).resolve().parents[2] / "deploy/port30000/egress_gateway.py"
    spec = importlib.util.spec_from_file_location("srh_test_egress_gateway", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upstream_proxy_rejects_non_web_ports():
    gateway = _gateway_module()

    with pytest.raises(PermissionError, match="port is not allowed"):
        asyncio.run(gateway.open_upstream("http://example.com:22"))

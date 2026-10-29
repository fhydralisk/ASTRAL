"""Generate the checked-in transport contract without running a model or loading data."""
import json
from pathlib import Path
import tempfile
from sr_harness.service.local import LocalHarnessService
from sr_harness.http.app import create_app

with tempfile.TemporaryDirectory() as root:
    service = LocalHarnessService(root)
    try:
        schema = create_app(service, token="contract-generation-token-only").openapi()
        Path("contracts").mkdir(exist_ok=True)
        Path("contracts/harness.openapi.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    finally:
        service.close()

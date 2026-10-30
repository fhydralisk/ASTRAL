"""Generate the checked-in transport contract without running a model or loading data."""
import json
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
# A shared development interpreter may be installed editable against another
# worktree. Always export this checkout's implementation and write to this root.
sys.path.insert(0, str(ROOT / "src"))
from sr_harness.service.local import LocalHarnessService  # noqa: E402
from sr_harness.http.app import create_app  # noqa: E402

with tempfile.TemporaryDirectory() as root:
    service = LocalHarnessService(root)
    try:
        schema = create_app(service, token="contract-generation-token-only").openapi()
        (ROOT / "contracts").mkdir(exist_ok=True)
        (ROOT / "contracts/harness.openapi.json").write_text(
            json.dumps(schema, indent=2) + "\n", encoding="utf-8"
        )
    finally:
        service.close()

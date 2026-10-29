from __future__ import annotations
import math
from typing import Any
import sr_harness_engine as engine
from .base import ServiceError


def _resolve_run_state(session, run_id: str):
    state = getattr(session, "run_state", None) if session is not None else None
    if state is None or state.run_id != run_id:
        raise ServiceError(404, f"Run not found: {run_id}")
    return state


def _number_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach Web-only cursors without storing them in the search state."""
    return [dict(record, seq=index) for index, record in enumerate(records, 1)]


def _sanitize_json_value(value: Any) -> Any:
    """Return a standards-compliant JSON value by replacing non-finite floats."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    return value


def _strip_detail(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "detail"}


def _with_core_derivatives(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    record = _with_formula_latex(record)
    return _with_tool_summary(record, records_by_id or {})


def _with_formula_latex(record: dict[str, Any]) -> dict[str, Any]:
    core = record.get("core")
    if not isinstance(core, dict) or core.get("formula_latex"):
        return record
    formula = core.get("formula")
    if not formula:
        return record
    record = dict(record)
    core = dict(core)
    try:
        core["formula_latex"] = engine.parse(str(formula).replace("^", "**")).to_str(latex=True)
    except Exception:
        core["formula_latex"] = None
    record["core"] = core
    return record


def _with_tool_summary(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    core = record.get("core")
    if not isinstance(core, dict) or core.get("tool_summary"):
        return record
    record = dict(record)
    core = dict(core)
    output_counts: dict[str, int] = {}
    for name in core.get("tool_names") or []:
        if name:
            output_counts[str(name)] = output_counts.get(str(name), 0) + 1
    prompt_counts = _prompt_tool_counts(record.get("detail", {}).get("prompt", []))
    ancestor_counts = _ancestor_tool_counts(record, records_by_id)
    for name, count in ancestor_counts.items():
        prompt_counts[name] = max(prompt_counts.get(name, 0), count)
    names = sorted(set(prompt_counts) | set(output_counts))
    core["tool_summary"] = [
        {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "prompt_count": prompt_counts.get(name, 0),
            "output_count": output_counts.get(name, 0),
        }
        for name in names
    ]
    record["core"] = core
    return record


def _ancestor_tool_counts(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
    seen: set[str] | None = None,
) -> dict[str, int]:
    seen = seen or set()
    counts: dict[str, int] = {}
    for parent in record.get("parents") or []:
        if not isinstance(parent, dict):
            continue
        parent_id = parent.get("node_id")
        if not parent_id or parent_id in seen:
            continue
        parent_record = records_by_id.get(parent_id)
        if not parent_record:
            continue
        seen.add(parent_id)
        for name in (parent_record.get("core") or {}).get("tool_names") or []:
            if name:
                name = str(name)
                counts[name] = counts.get(name, 0) + 1
        for name, count in _ancestor_tool_counts(parent_record, records_by_id, seen).items():
            counts[name] = counts.get(name, 0) + count
    return counts


def _prompt_tool_counts(prompt: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(prompt, list):
        return counts
    for msg in prompt:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "tool" and msg.get("name"):
            name = str(msg["name"])
            counts[name] = counts.get(name, 0) + 1
    if counts:
        return counts
    for msg in prompt:
        if not isinstance(msg, dict):
            continue
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            name = call.get("name") or (call.get("function") or {}).get("name")
            if name:
                name = str(name)
                counts[name] = counts.get(name, 0) + 1
    return counts

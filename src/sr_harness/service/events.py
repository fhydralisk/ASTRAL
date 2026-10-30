"""Bounded timeline previews and full event downloads, independent of HTTP."""

import json
from itertools import chain, islice
from .base import ServiceError, Download
from .redaction import scrub
from ..core import json_value

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_NODES = 200_000
MAX_RESPONSE_DEPTH = 64


def check_response_budget(content):
    """Check node count, nesting depth and UTF-8 byte limits before encoding.

    Args:
        content: Candidate response payload to inspect.

    Raises:
        ServiceError: With status ``413`` if the payload exceeds size or depth limits.
    """
    stack = [(iter((content,)), 0)]
    nodes = 0
    text_bytes = 0
    while stack:
        iterator, depth = stack[-1]
        try:
            value = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        if nodes > MAX_RESPONSE_NODES or depth > MAX_RESPONSE_DEPTH:
            raise ServiceError(
                413,
                "Response is too large or deeply nested; "
                "use a smaller query or export the conversation.",
            )
        if isinstance(value, str):
            # Check character count first to avoid encoding a huge single string.
            if len(value) > MAX_RESPONSE_BYTES:
                raise ServiceError(
                    413,
                    "Response exceeds the 8 MiB limit; "
                    "use a smaller query or export the conversation.",
                )
            text_bytes += len(value.encode("utf-8"))
            if text_bytes > MAX_RESPONSE_BYTES:
                raise ServiceError(
                    413,
                    "Response exceeds the 8 MiB limit; "
                    "use a smaller query or export the conversation.",
                )
        elif isinstance(value, dict):
            stack.append((chain.from_iterable(value.items()), depth + 1))
        elif isinstance(value, (list, tuple, set, frozenset)):
            stack.append((iter(value), depth + 1))


def bounded(content):
    check_response_budget(content)
    encoded = json_value(content)
    check_response_budget(encoded)
    if (
        len(json.dumps(encoded, ensure_ascii=False, allow_nan=False).encode("utf8"))
        > MAX_RESPONSE_BYTES
    ):
        raise ServiceError(413, "Response exceeds the timeline polling budget")
    return encoded


def event_batch(manager, after_sequence):
    """Page timeline events, previewing oversized single events without skipping their cursors.

    Args:
        manager: :class:`~sr_harness.runtime.InteractionManager` owning the event buffer.
        after_sequence: Last event sequence number already received by the client.

    Returns:
        JSONResponse: Encoded event batch response.
    """
    limit = 32
    while True:
        try:
            batch = manager.get_recent_events(after_sequence, limit=limit)
            # A full page may have successors; one extra empty poll is harmless.
            batch = {**batch, "has_more": len(batch["events"]) == limit}
            return bounded(batch)
        except ServiceError as exc:
            if exc.status_code != 413:
                raise
            if limit == 1:
                if not batch["events"]:
                    raise
                for divisor in (1, 4, 16):
                    event = _event_preview(batch["events"][0], divisor)
                    try:
                        return bounded({**batch, "events": [event]})
                    except ServiceError as preview_error:
                        if preview_error.status_code != 413:
                            raise
                # Even unusual payloads can always advance the timeline cursor.
                event = {key: batch["events"][0][key] for key in ("seq", "id", "kind", "timestamp")}
                event.update(payload={}, transport={"truncated": True})
                return bounded({**batch, "events": [event]})
            limit = max(1, limit // 2)


def _event_preview(event, divisor):
    """Make a bounded display copy; never modify retained events or model messages."""
    nodes_left = max(16, min(4096, MAX_RESPONSE_NODES // 4) // divisor)
    bytes_left = max(32, min(64 * 1024, MAX_RESPONSE_BYTES // 8) // divisor)
    depth_limit = max(1, min(12, MAX_RESPONSE_DEPTH // 2))
    priority = (
        "response_id",
        "turn",
        "coord",
        "provider",
        "model",
        "role",
        "name",
        "id",
        "ok",
        "finish_reason",
        "content",
        "reasoning",
        "error",
        "status",
        "call",
        "params",
        "result_str",
        "message",
        "tool_calls",
        "messages",
        "result",
        "tool_schemas",
    )

    def preview(value, depth=0):
        nonlocal nodes_left, bytes_left
        nodes_left -= 1
        if depth > depth_limit or nodes_left < 0:
            return None
        if isinstance(value, str):
            cap = min(4096, bytes_left)
            prefix = value[:cap].encode("utf-8")[:cap].decode("utf-8", errors="ignore")
            bytes_left -= len(prefix.encode("utf-8"))
            return prefix
        if isinstance(value, dict):
            keys = list(
                dict.fromkeys([key for key in priority if key in value] + list(islice(value, 40)))
            )
            result = {}
            for key in keys:
                if nodes_left < 2 or bytes_left < len(str(key).encode("utf-8")):
                    break
                nodes_left -= 1
                bytes_left -= len(str(key).encode("utf-8"))
                result[key] = preview(value[key], depth + 1)
            return result
        if isinstance(value, (list, tuple)):
            result = []
            for item in islice(value, 12):
                if nodes_left < 1:
                    break
                result.append(preview(item, depth + 1))
            return result
        return value

    payload = event.get("payload", {})
    messages = payload.get("messages")
    transport = {"truncated": True}
    if event.get("kind") == "context" and isinstance(messages, list):
        transport["original_message_count"] = len(messages)
        # Keep the system instruction and recent work, rather than only old turns.
        if len(messages) > 7:
            payload = {**payload, "messages": [messages[0], *messages[-6:]]}
    return {**event, "payload": preview(payload), "transport": transport}


def event_download(manager, sequence, scope):
    """Stream one full retained event as JSON without the polling response budget."""
    if sequence < 1:
        raise ServiceError(404, "Timeline event is no longer available")
    events = manager.get_recent_events(sequence - 1, limit=1)["events"]
    if not events or events[0]["seq"] != sequence:
        raise ServiceError(404, "Timeline event is no longer available")
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, default=json_value)

    def chunks():
        parts, length = [], 0
        for part in encoder.iterencode(scrub(events[0])):
            for offset in range(0, len(part), 64 * 1024):
                piece = part[offset : offset + 64 * 1024]
                parts.append(piece)
                length += len(piece)
                if length >= 64 * 1024:
                    yield "".join(parts)
                    parts, length = [], 0
        if parts:
            yield "".join(parts)

    return Download(
        (part.encode("utf8") for part in chunks()),
        f"{scope}-event-{sequence}.json",
        "application/json",
    )

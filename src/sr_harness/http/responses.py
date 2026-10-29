"""Bound large responses and encode them outside the HTTP event loop."""

from itertools import chain

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_NODES = 200_000
MAX_RESPONSE_DEPTH = 64


def check_response_budget(content):
    """Verify iteratively that ``content`` stays within node-count, nesting-depth, and UTF-8 byte
    limits before JSON encoding.

        Args:
            content: Candidate response payload to inspect.

        Raises:
            HTTPException: With status ``413`` if the payload exceeds size or depth limits.
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
            raise HTTPException(
                413,
                (
                    "Response is too large or deepl"
                    "y nested; use a smaller query "
                    "or export the conversation."
                ),
            )
        if isinstance(value, str):
            # Check character count first to avoid encoding a huge single string.
            if len(value) > MAX_RESPONSE_BYTES:
                raise HTTPException(
                    413,
                    (
                        "Response exceeds the 8 MiB lim"
                        "it; use a smaller query or exp"
                        "ort the conversation."
                    ),
                )
            text_bytes += len(value.encode("utf-8"))
            if text_bytes > MAX_RESPONSE_BYTES:
                raise HTTPException(
                    413,
                    (
                        "Response exceeds the 8 MiB lim"
                        "it; use a smaller query or exp"
                        "ort the conversation."
                    ),
                )
        elif isinstance(value, dict):
            stack.append((chain.from_iterable(value.items()), depth + 1))
        elif isinstance(value, (list, tuple, set, frozenset)):
            stack.append((iter(value), depth + 1))


def worker_json_response(content):
    """Validate ``content`` against the response size budget and encode it as a
    :class:`fastapi.responses.JSONResponse`.

        Args:
            content: Serializable Python structure to return from an endpoint.

        Returns:
            JSONResponse: Encoded FastAPI JSON response.
    """
    check_response_budget(content)
    encoded = jsonable_encoder(content)
    check_response_budget(encoded)
    response = JSONResponse(encoded)
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise HTTPException(
            413, "Response exceeds the 8 MiB limit; use a smaller query or export the conversation."
        )
    return response


def worker_event_response(manager, after_sequence):
    """Fetch a batch of recent timeline events that fits within the 8 MiB response size budget
    without skipping sequence cursors.

        Args:
            manager: :class:`~sr_harness.runtime.InteractionManager` owning the event buffer.
            after_sequence: Last event sequence number already received by the client.

        Returns:
            JSONResponse: Encoded event batch response.
    """
    limit = 32
    while True:
        try:
            return worker_json_response(manager.get_recent_events(after_sequence, limit=limit))
        except HTTPException as exc:
            if exc.status_code != 413 or limit == 1:
                raise
            limit = max(1, limit // 2)

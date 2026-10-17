"""Bound large responses and encode them outside the HTTP event loop."""
from itertools import chain

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_NODES = 200_000
MAX_RESPONSE_DEPTH = 64


def check_response_budget(content):
    """Iterative traversal bounds work before recursive JSON encoding.

    Shared references count each time they occur in JSON. Cycles exceed the
    depth budget without recursive stack overflow or allocating a huge queue.
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
            raise HTTPException(413, "Response is too large or deeply nested; use a smaller query or export the conversation.")
        if isinstance(value, str):
            # Check character count first to avoid encoding a huge single string.
            if len(value) > MAX_RESPONSE_BYTES:
                raise HTTPException(413, "Response exceeds the 8 MiB limit; use a smaller query or export the conversation.")
            text_bytes += len(value.encode('utf-8'))
            if text_bytes > MAX_RESPONSE_BYTES:
                raise HTTPException(413, "Response exceeds the 8 MiB limit; use a smaller query or export the conversation.")
        elif isinstance(value, dict):
            stack.append((chain.from_iterable(value.items()), depth + 1))
        elif isinstance(value, (list, tuple, set, frozenset)):
            stack.append((iter(value), depth + 1))


def worker_json_response(content):
    check_response_budget(content)
    encoded = jsonable_encoder(content)
    check_response_budget(encoded)
    response = JSONResponse(encoded)
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise HTTPException(413, "Response exceeds the 8 MiB limit; use a smaller query or export the conversation.")
    return response


def worker_event_response(manager, after_sequence):
    """Shrink a page to the response budget without skipping any event cursor."""
    limit = 32
    while True:
        try:
            return worker_json_response(manager.get_recent_events(after_sequence, limit=limit))
        except HTTPException as exc:
            if exc.status_code != 413 or limit == 1:
                raise
            limit = max(1, limit // 2)

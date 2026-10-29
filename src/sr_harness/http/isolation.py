"""Bound synchronous HTTP work so one conversation cannot monopolize workers."""

from __future__ import annotations

import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
import threading

from fastapi import HTTPException
from starlette.responses import JSONResponse


request_work_keys: ContextVar[tuple[str, ...]] = ContextVar(
    "request_work_keys", default=("unbound",)
)


class RequestWorkPool:
    """Bounded thread-pool admission controller that prevents a single conversation from
    monopolizing HTTP workers.

        Timed-out synchronous requests keep their admission slot until the underlying
        worker thread actually exits, preventing client retries from spawning unbounded
        background threads.
    """

    def __init__(self, *, workers=16, per_key=4, timeout=30.0):
        """Initialize the bounded HTTP worker pool.

        Args:
            workers: Total maximum concurrent worker threads across all conversations.
            per_key: Maximum concurrent worker threads permitted per conversation/tenant key.
            timeout: Per-request execution timeout in seconds before returning HTTP 504.
        """
        self.workers = workers
        self.per_key = per_key
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="srh-http")
        self._lock = threading.Lock()
        self._counts = Counter()
        self._total = 0
        self._closed = False

    async def run(self, function, *args, **kwargs):
        """Execute ``function(*args, **kwargs)`` in the worker pool while enforcing per-key
        admission limits and timeouts.

                Args:
                    function: Synchronous callable to execute.
                    *args: Positional arguments passed to ``function``.
                    **kwargs: Keyword arguments passed to ``function``.

                Returns:
                    Any: Return value of ``function``.
        """
        keys = tuple(set(request_work_keys.get()))
        with self._lock:
            if any(self._counts[key] >= self.per_key for key in keys):
                raise HTTPException(
                    429,
                    "This conversation has too much pending work; retry shortly.",
                    headers={"Retry-After": "3"},
                )
            if self._total >= self.workers:
                raise HTTPException(
                    503, "Request workers are busy; retry shortly.", headers={"Retry-After": "3"}
                )
            self._total += 1
            self._counts.update(keys)

        def release(_future=None):
            with self._lock:
                self._total -= 1
                for key in keys:
                    self._counts[key] -= 1
                    if not self._counts[key]:
                        del self._counts[key]

        completed = release

        context = copy_context()
        try:
            future = self._executor.submit(context.run, function, *args, **kwargs)
        except BaseException:
            completed(None)
            raise
        future.add_done_callback(completed)
        wrapped = asyncio.wrap_future(future)
        # Consume late exceptions even after the HTTP caller has timed out.
        wrapped.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout=self.timeout)
        except TimeoutError as exc:
            raise HTTPException(
                504,
                (
                    "This request took too long. It"
                    " may still be finishing; check"
                    " its state before retrying."
                ),
            ) from exc

    def start(self):
        """Ensure the underlying ``ThreadPoolExecutor`` is running (recreating it if previously
        closed).
        """
        with self._lock:
            if self._closed:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.workers, thread_name_prefix="srh-http"
                )
                self._closed = False

    def close(self):
        """Shut down the underlying ``ThreadPoolExecutor`` without waiting for hung threads."""
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)


class RequestBodyLimit:
    """ASGI middleware that rejects oversized HTTP request bodies (including chunked transfers)
    before JSON parsing.
    """

    def __init__(self, app, max_bytes=4 * 1024 * 1024):
        """Initialize the request body size limiter middleware.

        Args:
            app: Downstream ASGI application.
            max_bytes: Maximum allowed request body size in bytes (defaults to 4 MiB).
        """
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        """Enforce the request body byte limit on incoming HTTP requests before forwarding to
        ``self.app``.

                Args:
                    scope: ASGI connection scope dictionary.
                    receive: ASGI receive callable.
                    send: ASGI send callable.
        """
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        # Upload already streams to disk with its own 256 MiB size check.
        if (
            scope.get("path", "").startswith("/v1/sessions/")
            and scope.get("path", "").endswith("/workspace/upload")
            and scope.get("method") == "PUT"
        ):
            return await self.app(scope, receive, send)
        limit = self.max_bytes
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        if declared > limit:
            return await JSONResponse(
                {
                    "error": {
                        "code": "request_too_large",
                        "message": "Request exceeds the 4 MiB limit.",
                    }
                },
                status_code=413,
            )(scope, receive, send)
        # Buffer only small API bodies, then replay them once to the application.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Request exceeds the 4 MiB limit.",
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

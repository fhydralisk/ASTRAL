"""Bound synchronous HTTP work so one conversation cannot monopolize workers."""
from __future__ import annotations

import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from functools import wraps
import inspect
import threading

from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse, Response

from .responses import worker_json_response

request_mutating: ContextVar[bool] = ContextVar("request_mutating", default=False)

request_session_lease: ContextVar = ContextVar("request_session_lease", default=None)

request_work_keys: ContextVar[tuple[str, ...]] = ContextVar("request_work_keys", default=("unbound",))


class RequestWorkPool:
    """No unbounded queue; timed-out work keeps its slot until it really exits.

    Python threads cannot be killed safely. Admission accounting deliberately
    outlives the HTTP timeout, preventing retries from spawning unlimited work.
    This is containment of HTTP work, not OS-level memory/GIL isolation.
    """

    def __init__(self, *, workers=16, per_key=4, timeout=30.0):
        self.workers = workers
        self.per_key = per_key
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="srh-http")
        self._lock = threading.Lock()
        self._counts = Counter()
        self._total = 0
        self._closed = False

    async def run(self, function, *args, **kwargs):
        keys = tuple(set(request_work_keys.get()))
        with self._lock:
            if any(self._counts[key] >= self.per_key for key in keys):
                raise HTTPException(429, "This conversation has too much pending work; retry shortly.", headers={"Retry-After": "3"})
            if self._total >= self.workers:
                raise HTTPException(503, "Request workers are busy; retry shortly.", headers={"Retry-After": "3"})
            self._total += 1
            self._counts.update(keys)

        def release(_future=None):
            with self._lock:
                self._total -= 1
                for key in keys:
                    self._counts[key] -= 1
                    if not self._counts[key]:
                        del self._counts[key]

        lease = request_session_lease.get()
        try:
            if lease is not None:
                lease[0].acquire(lease[1])
        except BaseException:
            release()
            raise

        def completed(future):
            try:
                if lease is not None:
                    lease[0].release(lease[1])
            finally:
                release(future)

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
            raise HTTPException(504, "This request took too long. It may still be finishing; check its state before retrying.") from exc

    def start(self):
        with self._lock:
            if self._closed:
                self._executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="srh-http")
                self._closed = False

    def close(self):
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)


def install_route_isolation(app, pool):
    class IsolatedRoute(APIRoute):
        def __init__(self, path, endpoint, **kwargs):
            if not inspect.iscoroutinefunction(endpoint):
                original = endpoint

                def execute(*args, **kwargs):
                    try:
                        result = original(*args, **kwargs)
                        return result if isinstance(result, Response) else worker_json_response(result)
                    finally:
                        # A timed-out mutating endpoint may finish after middleware exits.
                        if request_mutating.get() and app.state.conversation_registry is not None:
                            try:
                                session = app.state.session.current_session()
                            except RuntimeError:
                                session = None
                            if session is not None:
                                session._persistence_generation = getattr(session, "_persistence_generation", 0) + 1

                @wraps(original)
                async def endpoint(*args, **kwargs):
                    return await pool.run(execute, *args, **kwargs)

                # Resolve postponed annotations in the original module, not here.
                endpoint.__signature__ = inspect.signature(original, eval_str=True).replace(return_annotation=Response)
            super().__init__(path, endpoint, **kwargs)

    app.router.route_class = IsolatedRoute


class RequestBodyLimit:
    """Reject large bodies before JSON parsing, including chunked requests."""

    def __init__(self, app, max_bytes=4 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') in {'GET', 'HEAD', 'OPTIONS'}:
            return await self.app(scope, receive, send)
        # Upload already streams to disk with its own 256 MiB size check.
        if scope.get('path') == '/api/workspace/upload':
            return await self.app(scope, receive, send)
        limit = self.max_bytes
        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
        except ValueError:
            declared = limit + 1
        if declared > limit:
            return await JSONResponse({'detail': 'Request exceeds the 4 MiB limit.'}, status_code=413)(scope, receive, send)
        # Buffer only small API bodies, then replay them once to the application.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > limit:
                return await JSONResponse({'detail': 'Request exceeds the 4 MiB limit.'}, status_code=413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)

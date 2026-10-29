import asyncio
import threading

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from sr_harness.web.app import create_app
from sr_harness.web.conversations import ConversationRegistry
from sr_harness.web.isolation import RequestWorkPool, request_work_keys
from sr_harness.web.responses import worker_json_response
import sr_harness.web.responses as responses


def test_timed_out_conversation_keeps_its_slot_and_other_conversation_works(tmp_path):
    app = create_app(tmp_path)
    app.state.work_pool.per_key = 1
    app.state.work_pool.timeout = .1
    entered, release = threading.Event(), threading.Event()

    @app.middleware('http')
    async def tenant(request, call_next):
        token = request_work_keys.set((request.headers.get('x-test-tenant', 'other'),))
        try:
            return await call_next(request)
        finally:
            request_work_keys.reset(token)

    @app.get('/slow')
    def slow():
        entered.set()
        release.wait(10)
        return {'done': True}

    @app.get('/fast')
    def fast():
        return {'ok': True}

    with TestClient(app) as client:
        try:
            assert client.get('/slow', headers={'x-test-tenant': 'bad'}).status_code == 504
            assert entered.is_set()
            for _ in range(5):
                assert client.get('/slow', headers={'x-test-tenant': 'bad'}).status_code == 429
            assert app.state.work_pool._total == 1
            assert client.get('/fast', headers={'x-test-tenant': 'good'}).status_code == 200
            assert client.get('/health').status_code == 200
        finally:
            release.set()


def test_request_and_response_size_failures_do_not_break_next_request(monkeypatch, tmp_path):
    app = create_app(tmp_path)
    monkeypatch.setattr(responses, 'MAX_RESPONSE_BYTES', 1000)

    @app.get('/huge')
    def huge():
        return {'value': 'x' * 1001}

    @app.post('/echo')
    def echo(payload: dict):
        return payload

    with TestClient(app) as client:
        assert client.get('/huge').status_code == 413
        assert client.post('/echo', content=b'x' * (4 * 1024 * 1024 + 1)).status_code == 413
        assert client.post('/echo', json={'ok': True}).json() == {'ok': True}
        assert client.get('/health').status_code == 200


def test_response_cycles_fail_before_encoder_recursion():
    cycle = []; cycle.append(cycle)
    with pytest.raises(HTTPException) as error:
        worker_json_response(cycle)
    assert error.value.status_code == 413


def test_failed_snapshot_does_not_block_other_snapshots_or_reads(tmp_path, monkeypatch):
    registry = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=3600)
    bad = registry.default_session
    good_record = registry.create('owner', 'Healthy')
    good = registry._session_for(good_record)
    original = bad.export_persistent_state
    try:
        def fail():
            raise ValueError('invalid session data')
        monkeypatch.setattr(bad, 'export_persistent_state', fail)
        good.initial_prompt = 'must be persisted'
        with pytest.raises(RuntimeError):
            registry.persist()
        assert registry._session_snapshot_path(good_record).is_file()
        assert good_record['id'] not in registry._persistence_errors
        assert registry.resolve('owner', good_record['id'])[1] is good
        assert registry.list('owner', bad.conversation_id)['persistence_warning']
    finally:
        monkeypatch.setattr(bad, 'export_persistent_state', original)
        registry.close()


def test_conversation_list_does_not_restore_broken_selected_session(tmp_path, monkeypatch):
    writer = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=3600)
    writer.default_session
    writer.persist(); writer.close()
    reader = ConversationRegistry(tmp_path, read_only=True)
    app = create_app(tmp_path, session=reader.session_proxy, conversation_registry=reader)
    monkeypatch.setattr(reader, '_session_for', lambda record: (_ for _ in ()).throw(ValueError('bad snapshot')))
    try:
        with TestClient(app) as client:
            assert client.get('/api/conversations').status_code == 200
            assert client.get('/health').status_code == 200
    finally:
        reader.close()


def test_event_page_shrinks_without_losing_events(monkeypatch, tmp_path):
    app = create_app(tmp_path)
    monkeypatch.setattr(responses, 'MAX_RESPONSE_BYTES', 2000)
    manager = app.state.interaction_manager
    for index in range(40):
        manager.publish_event('prompt_added', {'content': str(index) + 'x' * 200})
    collected = []
    with TestClient(app) as client:
        cursor = 0
        while True:
            result = client.get(f'/api/control/events?after_seq={cursor}')
            assert result.status_code == 200
            assert len(result.content) <= 2000
            events = result.json()['events']
            if not events:
                break
            collected.extend(events)
            cursor = events[-1]['seq']
    assert collected == manager.get_recent_events()['events']


def test_client_cancellation_does_not_release_running_work():
    async def check():
        pool = RequestWorkPool(workers=2, per_key=1)
        started, release = threading.Event(), threading.Event()
        def slow():
            started.set()
            release.wait(5)
        token = request_work_keys.set(('bad',))
        task = asyncio.create_task(pool.run(slow))
        try:
            await asyncio.to_thread(started.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(HTTPException) as exc:
                await pool.run(lambda: None)
            assert exc.value.status_code == 429
            request_work_keys.set(('good',))
            assert await pool.run(lambda: 7) == 7
        finally:
            release.set()
            request_work_keys.reset(token)
            pool.close()
    asyncio.run(check())


def test_chunked_body_limit_is_enforced_without_content_length():
    from sr_harness.web.isolation import RequestBodyLimit
    async def check():
        called = []
        async def downstream(scope, receive, send):
            called.append(True)
        chunks = iter([
            {'type': 'http.request', 'body': b'123', 'more_body': True},
            {'type': 'http.request', 'body': b'456', 'more_body': False},
        ])
        async def receive():
            return next(chunks)
        sent = []
        async def send(message):
            sent.append(message)
        await RequestBodyLimit(downstream, max_bytes=5)(
            {'type': 'http', 'method': 'POST', 'path': '/api/example', 'headers': []}, receive, send)
        assert sent[0]['status'] == 413
        assert not called
    asyncio.run(check())


def test_idle_snapshot_is_not_rewritten_but_changes_are_saved(tmp_path, monkeypatch):
    registry = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=3600)
    session = registry.default_session
    original = session.export_persistent_state
    calls = []
    def counted():
        calls.append(1)
        return original()
    monkeypatch.setattr(session, 'export_persistent_state', counted)
    try:
        registry.persist()
        registry.persist()
        assert len(calls) == 1
        session.initial_prompt = 'changed'
        registry.persist()
        assert len(calls) == 2
        session.data_interaction_manager.publish_event('prompt_added', {'content': 'new'})
        registry.persist()
        assert len(calls) == 3
    finally:
        registry.close()


def test_failed_session_lease_does_not_leak_worker_capacity():
    from sr_harness.web.isolation import request_session_lease

    class BrokenRegistry:
        def acquire(self, conversation_id):
            raise RuntimeError("session unavailable")

    async def check():
        pool = RequestWorkPool(workers=1, per_key=1)
        token = request_session_lease.set((BrokenRegistry(), "broken"))
        try:
            with pytest.raises(RuntimeError, match="session unavailable"):
                await pool.run(lambda: None)
        finally:
            request_session_lease.reset(token)
        try:
            assert await pool.run(lambda: 7) == 7
        finally:
            pool.close()

    asyncio.run(check())

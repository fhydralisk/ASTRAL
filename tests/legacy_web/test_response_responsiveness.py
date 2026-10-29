from concurrent.futures import ThreadPoolExecutor
import threading

from fastapi.testclient import TestClient

from sr_harness.web.app import create_app
from sr_harness.web.conversations import ConversationRegistry
from sr_harness.web import responses


def test_slow_event_encoding_does_not_block_event_loop(monkeypatch, tmp_path):
    app = create_app(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    original = responses.jsonable_encoder

    def slow_encoder(content):
        entered.set()
        assert release.wait(10)
        return original(content)

    monkeypatch.setattr(responses, 'jsonable_encoder', slow_encoder)
    with TestClient(app) as client, ThreadPoolExecutor() as pool:
        request = pool.submit(client.get, '/api/control/events')
        try:
            assert entered.wait(5)
            health = pool.submit(client.get, '/health')
            assert health.result(timeout=2).status_code == 200
        finally:
            release.set()
        assert request.result(timeout=5).status_code == 200


def test_event_pages_replay_every_sequence(tmp_path):
    app = create_app(tmp_path)
    manager = app.state.interaction_manager
    for i in range(70):
        manager.publish_event('command_received', {'action': 'pause', 'index': i})
    expected = manager.get_recent_events()['events']
    received = []
    with TestClient(app) as client:
        cursor = 0
        while True:
            batch = client.get(f'/api/control/events?after_seq={cursor}').json()['events']
            assert len(batch) <= 32
            if not batch:
                break
            received.extend(batch)
            cursor = batch[-1]['seq']
        reset = client.get('/api/control/events?after_seq=9999').json()
        assert reset['cursor_reset']
        assert reset['events'] == expected[:32]
    assert received == expected


def test_health_does_not_resolve_or_create_a_conversation(monkeypatch, tmp_path):
    registry = ConversationRegistry(tmp_path)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)

    def forbidden(*args, **kwargs):
        raise AssertionError('health must bypass conversation resolution')

    monkeypatch.setattr(registry, 'resolve', forbidden)
    try:
        with TestClient(app) as client:
            assert client.get('/health').json() == {'status': 'ok'}
    finally:
        registry.close()

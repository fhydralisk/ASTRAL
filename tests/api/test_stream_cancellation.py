"""Cancellation remains responsive while provider network reads are stalled."""
import threading
from types import SimpleNamespace

import pytest

from sr_harness.api.openrouter_api import OpenRouterAPI


@pytest.mark.parametrize("stall_before_headers", [True, False])
def test_force_cancel_does_not_wait_for_provider_chunk(stall_before_headers):
    entered, release, finished, closed = (threading.Event() for _ in range(4))
    errors = []
    class Client:
        def __init__(self):
            self.chat = self.completions = self
        def create(self, **payload):
            if stall_before_headers:
                entered.set()
                release.wait(3)
            return self.chunks()
        def chunks(self):
            if not stall_before_headers:
                entered.set()
                release.wait(3)
            yield SimpleNamespace(choices=[], usage=None)
        def close(self):
            closed.set()
    api = OpenRouterAPI()
    updates = []
    def consume():
        try:
            api.stream_openai_chat_completion(Client(), {}, sample=1, callback=updates.append)
        except InterruptedError:
            errors.append("cancelled")
        finally:
            finished.set()
    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    try:
        assert entered.wait(1)
        api.cancel()
        assert finished.wait(1), "Cancellation waited for a blocked provider read"
        assert errors == ["cancelled"]
        assert closed.wait(1)
        assert not any(u["type"] == "delta" for u in updates)
    finally:
        release.set()
        thread.join(3)

def test_stream_idle_timeout_is_distinct_from_total_generation_time():
    release = threading.Event()
    class Client:
        def __init__(self):
            self.chat = self.completions = self
        def create(self, **payload):
            release.wait(2)
            return iter(())
        def close(self):
            release.set()
    api = OpenRouterAPI()
    api.STREAM_IDLE_TIMEOUT_SECONDS = 0.05
    try:
        with pytest.raises(TimeoutError, match="idle timeout"):
            list(api._cancellable_stream(Client(), {}))
    finally:
        release.set()

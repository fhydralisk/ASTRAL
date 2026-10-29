import asyncio
import threading

import pytest
from fastapi import HTTPException
from sr_harness.http.isolation import RequestWorkPool, request_work_keys


def test_timeout_retains_slot_and_other_conversations_still_run():
    async def scenario():
        pool = RequestWorkPool(workers=2, per_key=1, timeout=0.03)
        entered, release = threading.Event(), threading.Event()

        def slow():
            entered.set()
            release.wait(3)

        token = request_work_keys.set(("session:slow",))
        try:
            with pytest.raises(HTTPException) as error:
                await pool.run(slow)
            assert error.value.status_code == 504 and pool._total == 1
            with pytest.raises(HTTPException) as error:
                await pool.run(lambda: None)
            assert error.value.status_code == 429
            other = request_work_keys.set(("session:other",))
            try:
                assert await pool.run(lambda: "responsive") == "responsive"
            finally:
                request_work_keys.reset(other)
        finally:
            release.set()
            request_work_keys.reset(token)
            pool.close()

    asyncio.run(scenario())

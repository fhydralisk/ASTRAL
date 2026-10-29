"""Process-local secret redaction; values are never persisted."""

import logging
import threading

_secrets: set[str] = set()
_lock = threading.RLock()
_installed = False


def scrub(value):
    if isinstance(value, str):
        with _lock:
            for secret in _secrets:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [scrub(v) for v in value]
    return value


def register(secret):
    global _installed
    with _lock:
        if secret:
            _secrets.add(secret)
        if not _installed:
            previous = logging.getLogRecordFactory()

            def factory(*args, **kwargs):
                record = previous(*args, **kwargs)
                record.msg, record.args = scrub(record.getMessage()), ()
                if record.exc_info:
                    record.exc_info = None
                    record.exc_text = "[Service exception details withheld]"
                return record

            logging.setLogRecordFactory(factory)
            _installed = True

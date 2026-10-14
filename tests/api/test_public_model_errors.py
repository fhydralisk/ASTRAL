from sr_harness.api import public_model_api_error


class StatusError(RuntimeError):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def wrapped(cause):
    try:
        raise cause
    except Exception as exc:
        try:
            raise RuntimeError("provider failed after retries") from exc
        except RuntimeError as outer:
            return outer


def test_public_model_error_reports_insufficient_balance_without_details():
    error = public_model_api_error(wrapped(StatusError("secret upstream body", 402)))

    assert error["error_kind"] == "insufficient_balance"
    assert "balance or quota" in error["error"]
    assert "secret upstream body" not in error["error"]


def test_public_model_error_reports_network_failure():
    error = public_model_api_error(wrapped(ConnectionError("connection refused")))

    assert error["error_kind"] == "network_unreachable"
    assert "unreachable" in error["error"]


def test_public_model_error_uses_safe_unknown_fallback():
    error = public_model_api_error(wrapped(ValueError("private malformed response")))

    assert error == {
        "error_kind": "unknown",
        "error": "Model API request failed for an unknown reason. Check the server logs for details.",
    }

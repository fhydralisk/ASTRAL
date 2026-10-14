from sr_harness.api import OpenRouterAPI


def wrapped(cause):
    try:
        raise cause
    except Exception as exc:
        try:
            raise RuntimeError("provider failed after retries") from exc
        except RuntimeError as outer:
            return outer


def test_provider_error_is_returned_directly_and_logged(caplog):
    api = OpenRouterAPI()

    with caplog.at_level("ERROR", logger="sr_harness.sr_harness.api.base_api"):
        message = api.error_message(ValueError("upstream rejected this request"))

    assert message == "upstream rejected this request"
    assert "upstream rejected this request" in caplog.text


def test_private_path_marker_withholds_frontend_error_but_remains_in_log(caplog):
    api = OpenRouterAPI()
    error = wrapped(ValueError("failed under /data2/yuzihan/private/config"))

    with caplog.at_level("ERROR", logger="sr_harness.sr_harness.api.base_api"):
        message = api.error_message(error)

    assert "sensitive information" in message
    assert "yuzihan" not in message
    assert "yuzihan" in caplog.text


def test_api_key_suffix_marker_withholds_frontend_error(caplog):
    api = OpenRouterAPI(environment={"OPENROUTER_API_KEY": "sk-example-secret-4a9"})

    with caplog.at_level("ERROR", logger="sr_harness.sr_harness.api.base_api"):
        message = api.error_message(ValueError("upstream echoed credential suffix 4a9"))

    assert "sensitive information" in message
    assert "4a9" not in message
    assert "4a9" in caplog.text


def test_short_test_key_suffix_does_not_trigger_temporary_filter():
    api = OpenRouterAPI(environment={"OPENROUTER_API_KEY": "test-key"})

    assert api.error_message(ValueError("invalid API key")) == "invalid API key"

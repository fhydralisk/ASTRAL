import base64
from urllib.parse import unquote, urlsplit

from sr_harness.runtime.network import proxy_environment, routed_proxy


def test_routed_proxy_uses_deployment_gateway_by_default():
    assert routed_proxy("", "http://egress-proxy:3128") == "http://egress-proxy:3128"


def test_routed_proxy_encodes_user_upstream_for_gateway():
    value = routed_proxy(
        "http://alice:secret@overseas.example:7890",
        "http://egress-proxy:3128",
    )
    parsed = urlsplit(value)
    assert parsed.hostname == "egress-proxy"
    assert parsed.port == 3128
    token = unquote(parsed.username)[4:]
    token += "=" * (-len(token) % 4)
    assert base64.urlsafe_b64decode(token).decode() == (
        "http://alice:secret@overseas.example:7890"
    )


def test_proxy_environment_does_not_mutate_process_environment():
    result = proxy_environment(
        {"OPENROUTER_API_KEY": "secret", "HTTP_PROXY": "old"},
        user_proxy="http://user-proxy.example:8080",
        egress_proxy="http://egress-proxy:3128",
    )
    assert result["OPENROUTER_API_KEY"] == "secret"
    assert result["HTTP_PROXY"].startswith("http://srh.")
    assert result["HTTPS_PROXY"] == result["HTTP_PROXY"]

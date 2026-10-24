"""Session-scoped outbound proxy routing."""
from __future__ import annotations

import base64
from collections.abc import Mapping
from urllib.parse import quote, urlsplit, urlunsplit


def routed_proxy(user_proxy: str, egress_proxy: str) -> str:
    """Combine a user-configured upstream proxy with an optional deployment egress gateway.

    Args:
        user_proxy: User-specified HTTP, HTTPS, or SOCKS proxy URL (or empty string).
        egress_proxy: Deployment-managed HTTP egress gateway URL (or empty string).

    Returns:
        str: Effective proxy URL for HTTP clients (encoding ``user_proxy`` in
            gateway credentials when both are active).
    """
    user_proxy = user_proxy.strip()
    egress_proxy = egress_proxy.strip()
    if not egress_proxy:
        return user_proxy
    if not user_proxy:
        return egress_proxy
    if urlsplit(user_proxy).scheme not in {"http", "https"}:
        raise ValueError("the deployment egress gateway supports HTTP(S) upstream proxies only")
    parsed = urlsplit(egress_proxy)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("SRH_EGRESS_PROXY must be an HTTP or HTTPS URL")
    token = base64.urlsafe_b64encode(user_proxy.encode()).decode().rstrip("=")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if parsed.port:
        host += f":{parsed.port}"
    netloc = f"{quote('srh.' + token, safe='')}:x@{host}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def proxy_environment(
    environment: Mapping[str, str], *, user_proxy: str, egress_proxy: str,
) -> dict[str, str]:
    """Build a copy of ``environment`` with ``HTTP_PROXY`` and ``HTTPS_PROXY`` set to the effective outbound proxy.

    Args:
        environment: Base environment variable mapping.
        user_proxy: User-configured proxy URL (or empty string).
        egress_proxy: Deployment egress gateway URL (or empty string).

    Returns:
        dict[str, str]: Updated environment dictionary.
    """
    result = dict(environment)
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        result.pop(name, None)
    effective = routed_proxy(user_proxy, egress_proxy)
    if effective:
        result.update({"HTTP_PROXY": effective, "HTTPS_PROXY": effective})
    return result


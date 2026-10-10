"""Small policy-enforcing HTTP CONNECT/forward proxy for the public demo."""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import os
import socket
import ssl
import time
from urllib.parse import urlsplit

MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "32"))
MAX_DESTINATION_CONNECTIONS = int(os.getenv("MAX_DESTINATION_CONNECTIONS", "6"))
REQUESTS_PER_SECOND = float(os.getenv("REQUESTS_PER_SECOND", "8"))
BURST_REQUESTS = float(os.getenv("BURST_REQUESTS", "16"))
BYTES_PER_SECOND = int(os.getenv("BYTES_PER_SECOND", str(512 * 1024)))
HEADER_LIMIT = 64 * 1024
ALLOWED_TARGET_PORTS = {80, 443}

connection_limit = asyncio.Semaphore(MAX_CONNECTIONS)
destination_limits: dict[tuple[str, int], asyncio.Semaphore] = {}
rate_lock = asyncio.Lock()
rate_tokens = BURST_REQUESTS
rate_updated = time.monotonic()


async def consume_request_token() -> None:
    """Apply a process-wide token bucket to all public requests."""
    global rate_tokens, rate_updated
    async with rate_lock:
        now = time.monotonic()
        rate_tokens = min(BURST_REQUESTS, rate_tokens + (now - rate_updated) * REQUESTS_PER_SECOND)
        rate_updated = now
        if rate_tokens < 1:
            await asyncio.sleep((1 - rate_tokens) / REQUESTS_PER_SECOND)
            rate_tokens = 0
            rate_updated = time.monotonic()
        else:
            rate_tokens -= 1


async def public_addresses(host: str, port: int) -> list[str]:
    """Resolve a host and reject every non-public result."""
    try:
        literal = ipaddress.ip_address(host)
        addresses = [str(literal)]
    except ValueError:
        rows = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM,
        )
        addresses = list(dict.fromkeys(row[4][0] for row in rows))
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise PermissionError("destination must resolve only to public addresses")
    return addresses


def upstream_from_headers(headers: dict[str, str]) -> str:
    """Decode the optional user upstream carried in proxy basic-auth username."""
    authorization = headers.pop("proxy-authorization", "")
    if not authorization.lower().startswith("basic "):
        return ""
    try:
        username = base64.b64decode(authorization.split(None, 1)[1]).decode().split(":", 1)[0]
        if not username.startswith("srh."):
            return ""
        token = username[4:]
        token += "=" * (-len(token) % 4)
        return base64.urlsafe_b64decode(token).decode()
    except Exception as exc:
        raise PermissionError("invalid upstream proxy token") from exc


async def open_public(host: str, port: int, *, tls: bool = False):
    """Connect to a resolved public address without a second DNS lookup."""
    addresses = await public_addresses(host, port)
    last_error = None
    for address in addresses:
        try:
            context = ssl.create_default_context() if tls else None
            return await asyncio.open_connection(
                address, port, ssl=context, server_hostname=host if tls else None,
            )
        except OSError as exc:
            last_error = exc
    raise last_error or ConnectionError("destination is unavailable")


async def open_upstream(value: str):
    """Open a validated public HTTP(S) upstream proxy connection."""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("upstream proxy must be an HTTP or HTTPS URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_TARGET_PORTS:
        raise PermissionError("upstream proxy port is not allowed")
    reader, writer = await open_public(parsed.hostname, port, tls=parsed.scheme == "https")
    authorization = ""
    if parsed.username is not None:
        credentials = f"{parsed.username}:{parsed.password or ''}".encode()
        authorization = "Proxy-Authorization: Basic " + base64.b64encode(credentials).decode() + "\r\n"
    return reader, writer, authorization


async def read_response_head(reader: asyncio.StreamReader) -> bytes:
    """Read one bounded HTTP response header."""
    return await reader.readuntil(b"\r\n\r\n")


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Relay one stream with a per-direction bandwidth ceiling."""
    interval = .1
    chunk_size = max(1024, BYTES_PER_SECOND // 10)
    try:
        while chunk := await reader.read(chunk_size):
            started = time.monotonic()
            writer.write(chunk)
            await writer.drain()
            await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def reject(writer: asyncio.StreamWriter, status: str, message: str) -> None:
    body = message.encode()
    try:
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    """Validate and forward one HTTP request or CONNECT tunnel."""
    async with connection_limit:
        remote_writer = None
        try:
            raw_head = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), 15)
            if len(raw_head) > HEADER_LIMIT:
                raise ValueError("request header is too large")
            lines = raw_head.decode("iso-8859-1").split("\r\n")
            method, target, version = lines[0].split(" ", 2)
            headers: dict[str, str] = {}
            original_headers: list[tuple[str, str]] = []
            for line in lines[1:]:
                if not line:
                    continue
                name, value = line.split(":", 1)
                headers[name.lower()] = value.strip()
                original_headers.append((name, value.strip()))
            upstream = upstream_from_headers(headers)
            await consume_request_token()

            if method.upper() == "CONNECT":
                host, separator, port_text = target.rpartition(":")
                if not separator:
                    raise ValueError("CONNECT target requires a port")
                port = int(port_text)
            else:
                parsed = urlsplit(target)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    raise ValueError("proxy requests require an absolute HTTP URL")
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if port not in ALLOWED_TARGET_PORTS:
                raise PermissionError("target port is not allowed")
            await public_addresses(host, port)
            destination_limit = destination_limits.setdefault((host, port), asyncio.Semaphore(MAX_DESTINATION_CONNECTIONS))

            async with destination_limit:
                if upstream:
                    remote_reader, remote_writer, upstream_auth = await open_upstream(upstream)
                else:
                    remote_reader, remote_writer = await open_public(host, port)
                    upstream_auth = ""

                if method.upper() == "CONNECT":
                    if upstream:
                        remote_writer.write(
                            f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{upstream_auth}Connection: keep-alive\r\n\r\n".encode()
                        )
                        await remote_writer.drain()
                        response_head = await read_response_head(remote_reader)
                        if not response_head.startswith(b"HTTP/1.1 200") and not response_head.startswith(b"HTTP/1.0 200"):
                            client_writer.write(response_head)
                            await client_writer.drain()
                            return
                    client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await client_writer.drain()
                    await asyncio.gather(
                        relay(client_reader, remote_writer),
                        relay(remote_reader, client_writer),
                    )
                    return

                filtered = [
                    (name, value) for name, value in original_headers
                    if name.lower() not in {"proxy-authorization", "proxy-connection", "connection"}
                ]
                request_target = target
                if not upstream:
                    parsed = urlsplit(target)
                    request_target = parsed.path or "/"
                    if parsed.query:
                        request_target += "?" + parsed.query
                head = f"{method} {request_target} {version}\r\n"
                head += "".join(f"{name}: {value}\r\n" for name, value in filtered)
                head += upstream_auth + "Connection: close\r\n\r\n"
                remote_writer.write(head.encode("iso-8859-1"))
                length = int(headers.get("content-length", "0"))
                if length:
                    remote_writer.write(await client_reader.readexactly(length))
                await remote_writer.drain()
                await relay(remote_reader, client_writer)
        except PermissionError as exc:
            await reject(client_writer, "403 Forbidden", str(exc))
        except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
            await reject(client_writer, "400 Bad Request", str(exc))
        except Exception as exc:
            await reject(client_writer, "502 Bad Gateway", str(exc))
        finally:
            if remote_writer is not None:
                remote_writer.close()


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 3128, limit=HEADER_LIMIT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

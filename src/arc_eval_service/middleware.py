"""Cross-cutting ASGI middleware for the API boundary.

The evaluator exposes an OTLP/HTTP traces endpoint. The OTLP/HTTP specification
recommends that receivers accept gzip-encoded request bodies, and the
OpenTelemetry Collector's ``otlphttp`` exporter compresses request bodies with
gzip **by default**. Starlette does not transparently decompress request bodies,
so without this middleware an OTLP export arrives as gzip bytes, JSON parsing
fails, and the endpoint returns ``400`` (the collector then drops the batch as a
permanent error).

:class:`GzipRequestMiddleware` makes the service a conformant receiver: it
decompresses any request whose ``Content-Encoding`` is ``gzip`` before routing,
then fixes ``Content-Length`` and strips the encoding header so downstream body
parsing is transparent.
"""

from __future__ import annotations

import gzip
import zlib

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Headers rewritten once a body is decompressed: the original length/encoding no
# longer describe the payload handed downstream.
_STRIPPED_HEADERS = (b"content-encoding", b"content-length")


class GzipRequestMiddleware:
    """Decompress gzip-encoded request bodies before they reach the route.

    Pure ASGI (not :class:`~starlette.middleware.base.BaseHTTPMiddleware`) so the
    request stream is rewritten without buffering responses. Non-HTTP scopes and
    requests without gzip encoding pass straight through.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        encoding = Headers(scope=scope).get("content-encoding", "")
        if "gzip" not in encoding.lower():
            await self._app(scope, receive, send)
            return

        body = await _read_request_body(receive)
        try:
            decoded = gzip.decompress(body) if body else body
        except (OSError, EOFError, zlib.error):
            # Malformed gzip: forward the original bytes and let the route reject
            # it with a normal validation error rather than masking the cause.
            decoded = body

        scope = dict(scope)
        scope["headers"] = _rewrite_headers(scope["headers"], len(decoded))
        await self._app(scope, _replay_body(decoded), send)


async def _read_request_body(receive: Receive) -> bytes:
    """Drain ``http.request`` messages into a single bytes payload."""
    chunks = bytearray()
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.extend(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return bytes(chunks)


def _replay_body(body: bytes) -> Receive:
    """Build a one-shot ``receive`` that yields ``body`` then disconnects."""
    delivered = False

    async def receive() -> Message:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _rewrite_headers(
    headers: list[tuple[bytes, bytes]], content_length: int
) -> list[tuple[bytes, bytes]]:
    """Drop encoding/length headers and set the decompressed ``Content-Length``."""
    rewritten = [
        (key, value) for key, value in headers if key.lower() not in _STRIPPED_HEADERS
    ]
    rewritten.append((b"content-length", str(content_length).encode("latin-1")))
    return rewritten

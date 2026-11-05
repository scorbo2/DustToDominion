"""In-process sd-server stub for the NPC generator tests (spec 17:
Stub server).

The hermetic test suite needs a stand-in for the real sd-server that
``sd-client.py`` can hit. The stub is owned by the *test process*, as
opposed to ``sd-client.py`` which is a subprocess - so it runs in-process
here, on an ephemeral loopback port (``http.server`` on port 0), and the
test hands its URL to the tool through the ``--server`` config. No real
network, no GPU, no excuses.

The two endpoints and both response bodies are the spec's verbatim:

- ``POST /sdcpp/v1/img_gen`` ->
  ``{"id":"stub1","status":"queued","poll_url":"/jobs/stub1"}``
- ``GET /jobs/stub1`` ->
  ``{"status":"completed","result":{"images":[{"index":0,"b64_json":"<base64 blank PNG>"}]}}``

The blank PNG is encoded from scratch below (stdlib zlib/struct) rather
than pasted as an opaque base64 blob, so "blank PNG" stays a claim the
code proves instead of a magic string it trusts.

Two deliberate design notes for stage 5:

- Every request is appended to ``StubImageServer.requests`` (method,
  path, parsed Json body), so wiring tests can assert what the tool
  actually sent - prompt, dimensions, seed - without a second proxy.
- ``BaseHTTPRequestHandler.log_message`` is silenced: its stock access
  log goes to stderr and would pollute every ``capsys`` assertion about
  the tool's stderr. The structured request log is the only record.
"""
from __future__ import annotations

import base64
import json
import struct
import threading
import zlib
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: Endpoint paths and the submit response, verbatim from spec 17.
IMG_GEN_PATH = "/sdcpp/v1/img_gen"
JOB_ID = "stub1"
JOB_POLL_PATH = f"/jobs/{JOB_ID}"
SUBMIT_RESPONSE: dict = {
    "id": JOB_ID,
    "status": "queued",
    "poll_url": JOB_POLL_PATH,
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """One PNG chunk: length, type, payload, CRC - per the PNG spec."""
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def encode_blank_png(
    width: int = 8, height: int = 8, rgb: tuple[int, int, int] = (0, 0, 0)
) -> bytes:
    """Encode a solid-color 8-bit RGB PNG with only the stdlib.

    Filter byte 0 (None) on every scanline keeps the IDAT an
    uncompressed-color run through zlib: simple enough to audit, valid
    enough for pygame and every real decoder.
    """
    raw_rows = b"".join(
        b"\x00" + bytes(rgb) * width for _ in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw_rows))
        + _png_chunk(b"IEND", b"")
    )


#: The blank PNG the completed job serves, base64-encoded for the
#: ``b64_json`` field sd-client.py decodes.
BLANK_PNG_BYTES = encode_blank_png()
BLANK_PNG_BASE64 = base64.b64encode(BLANK_PNG_BYTES).decode("ascii")


def job_completed_response() -> dict:
    """Fresh copy of the spec's poll response on every call, so a
    caller poking at the parsed Json can never mutate the stub."""
    return {
        "status": "completed",
        "result": {"images": [{"index": 0, "b64_json": BLANK_PNG_BASE64}]},
    }


@dataclass(frozen=True)
class StubRequest:
    """One recorded request: method, request path, and the parsed Json
    body (empty dict when there was none or it was not Json)."""

    method: str
    path: str
    payload: dict = field(default_factory=dict)


class _StubHandler(BaseHTTPRequestHandler):
    """Serves the two spec endpoints; 404 + Json error elsewhere.

    Reaches the owning ``StubImageServer`` through ``self.server`` (see
    ``_StubHttpServer``).
    """

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        """Silence the stock stderr access log (module docstring note)."""

    def do_POST(self) -> None:
        stub: StubImageServer = self.server.stub  # type: ignore[attr-defined]
        payload = self._read_json_body()
        stub.requests.append(StubRequest("POST", self.path, payload))
        if self.path == IMG_GEN_PATH:
            self._send_json(200, dict(SUBMIT_RESPONSE))
        else:
            self._send_json(404, {"error": f"no such endpoint: {self.path}"})

    def do_GET(self) -> None:
        stub: StubImageServer = self.server.stub  # type: ignore[attr-defined]
        stub.requests.append(StubRequest("GET", self.path, {}))
        if self.path == JOB_POLL_PATH:
            self._send_json(200, job_completed_response())
        else:
            self._send_json(404, {"error": f"no such job path: {self.path}"})

    def _read_json_body(self) -> dict:
        """Parse the request body as Json, tolerating absent or junk
        bodies so the recording never explodes on a malformed client."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"<unparseable>": raw.decode("utf-8", errors="replace")}
        return parsed if isinstance(parsed, dict) else {"<not-object>": parsed}

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _StubHttpServer(ThreadingHTTPServer):
    """Loopback, ephemeral port, daemon threads; carries the stub so
    the handler can record into it. The stub attribute is set before
    ``serve_forever`` ever runs, so handlers never see a half-built
    server."""

    daemon_threads = True

    def __init__(self, stub: "StubImageServer") -> None:
        super().__init__(("127.0.0.1", 0), _StubHandler)
        self.stub = stub


class StubImageServer:
    """In-process sd-server stub (spec 17: Stub server).

    Use as a context manager::

        with StubImageServer() as stub:
            config["server"] = stub.url   # hand the URL to the tool
            ...

    or drive ``start()``/``stop()`` directly when a test needs the
    server to vanish mid-scenario (connection-refused paths). ``stop()``
    is idempotent.
    """

    def __init__(self) -> None:
        self.requests: list[StubRequest] = []
        self._server = _StubHttpServer(self)
        self._thread: threading.Thread | None = None
        self._stopped = False

    @property
    def port(self) -> int:
        """The ephemeral port the OS assigned (port 0 binding)."""
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        """Base URL for the tool's ``--server`` config / sd-client's
        ``--server`` argument."""
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "StubImageServer":
        """Start serving (idempotent); returns self for chaining."""
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="npc-generator-stub-server",
                daemon=True,
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        """Stop serving and close the socket (idempotent)."""
        if self._stopped:
            return
        self._stopped = True
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._server.server_close()

    def __enter__(self) -> "StubImageServer":
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.stop()
        return False

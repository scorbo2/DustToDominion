"""In-process sd-server stub tests (spec 17: Stub server, dev plan
stage 4).

The stub's contract, straight from the spec's Stub server section:

- ``POST /sdcpp/v1/img_gen`` answers the queued submission Json
  verbatim (id stub1, poll_url /jobs/stub1)
- ``GET /jobs/stub1`` answers the completed-job Json verbatim, with a
  base64 blank PNG that decodes to a genuinely valid PNG (the header
  says "blank PNG"; the tests hold it to that)
- served by an in-process ``http.server`` on an ephemeral loopback
  port - no real network
- unknown paths answer HTTP 404 with a Json error body
- every request is recorded for stage 5 wiring assertions
- the server is silent on stderr, so it cannot poison ``capsys``
  assertions about the tool's own stderr

And the acceptance that makes stage 4 more than a fixture with
feelings: a real ``tools/sd-client.py`` subprocess, pointed at the
stub via ``--server``, walks the whole submit-poll-save flow and
writes the exact blank PNG bytes to disk (spec 17: Stub server - a
stub service that ``sd-client.py`` can *hit*).
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

import pytest

from helpers_npc_generator_stub import (
    BLANK_PNG_BASE64,
    BLANK_PNG_BYTES,
    IMG_GEN_PATH,
    JOB_ID,
    JOB_POLL_PATH,
    PNG_SIGNATURE,
    StubImageServer,
    StubRequest,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SD_CLIENT_PATH = PROJECT_ROOT / "tools" / "sd-client.py"

# Generous on purpose: these are in-process localhost calls and a tiny
# stdlib subprocess; anything slower means something hung, and the
# timeout should say so instead of the suite freezing.
HTTP_TIMEOUT_SECONDS = 10
SUBPROCESS_TIMEOUT_SECONDS = 60


def _http_json(
    url: str, payload: dict | None = None
) -> tuple[int, dict]:
    """Fetch ``url`` (GET, or POST with a Json body when ``payload`` is
    given) and return ``(status, parsed Json body)``."""
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


# ------------------------------------------------------------------ #
# the two spec endpoints
# ------------------------------------------------------------------ #

def test_stub_withPostToImgGen_shouldAnswerTheSpecsQueuedSubmissionVerbatim(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # GIVEN the stub serving in-process:
    with StubImageServer() as stub:
        # WHEN sd-client's submit endpoint is POSTed a generation
        # request, THEN the answer is the spec's submission Json,
        # verbatim (spec 17: Stub server):
        status, body = _http_json(
            stub.url + IMG_GEN_PATH, {"prompt": "a stubborn stub", "width": 64}
        )

    assert status == 200
    assert body == {
        "id": "stub1",
        "status": "queued",
        "poll_url": "/jobs/stub1",
    }
    # AND the handler thread stayed silent: nothing on stderr for the
    # stock access log to add.
    assert capsys.readouterr().err == ""


def test_stub_withGetToJobPoll_shouldAnswerTheSpecsCompletedBlankPngVerbatim() -> None:
    # GIVEN the stub serving in-process:
    with StubImageServer() as stub:
        # WHEN the poll_url from the submission is GETed, THEN the
        # answer is the spec's completed-job Json, verbatim:
        status, body = _http_json(stub.url + JOB_POLL_PATH)

    assert status == 200
    assert body == {
        "status": "completed",
        "result": {"images": [{"index": 0, "b64_json": BLANK_PNG_BASE64}]},
    }


# ------------------------------------------------------------------ #
# the blank PNG is a real PNG
# ------------------------------------------------------------------ #

def test_blankPngConstant_shouldDecodeToAValidSolidPng() -> None:
    # GIVEN the blank PNG the stub serves:
    # THEN it carries the PNG signature and an 8x8 8-bit RGB header:
    assert BLANK_PNG_BYTES.startswith(PNG_SIGNATURE)
    ihdr_length = struct.unpack(">I", BLANK_PNG_BYTES[8:12])[0]
    assert ihdr_length == 13
    width, height, bit_depth, color_type = struct.unpack(
        ">IIBB", BLANK_PNG_BYTES[16:26]
    )
    assert (width, height, bit_depth, color_type) == (8, 8, 8, 2)

    # AND its single IDAT decompresses to exactly height filter-0 rows
    # of black pixels (the chunk layout is ours, so the offsets are
    # known: signature + 25-byte IHDR chunk, then IDAT):
    idat_length = struct.unpack(">I", BLANK_PNG_BYTES[33:37])[0]
    idat_data = BLANK_PNG_BYTES[41 : 41 + idat_length]
    rows = zlib.decompress(idat_data)
    assert rows == b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))


# ------------------------------------------------------------------ #
# request recording (the seam stage 5's wiring tests lean on)
# ------------------------------------------------------------------ #

def test_stub_shouldRecordEveryRequestWithMethodPathAndParsedBody() -> None:
    # GIVEN the stub serving in-process:
    with StubImageServer() as stub:
        # WHEN a submit and a poll happen back to back:
        payload = {"prompt": "portrait of a captain", "seed": 7}
        _http_json(stub.url + IMG_GEN_PATH, payload)
        _http_json(stub.url + JOB_POLL_PATH)

        # THEN each request is recorded in order, with the Json body
        # parsed for inspection:
        assert stub.requests == [
            StubRequest("POST", IMG_GEN_PATH, payload),
            StubRequest("GET", JOB_POLL_PATH, {}),
        ]


def test_stub_withJunkOrMissingPostBody_shouldRecordItWithoutExploding() -> None:
    # GIVEN the stub serving in-process:
    with StubImageServer() as stub:
        # WHEN a POST carries a non-Json body (junk client - stage 5
        # must not be able to wedge the stub by accident):
        request = urllib.request.Request(
            stub.url + IMG_GEN_PATH,
            data=b"this is not json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request, timeout=HTTP_TIMEOUT_SECONDS
        ) as resp:
            body = json.loads(resp.read().decode("utf-8"))

    assert body["id"] == JOB_ID
    assert stub.requests[0].payload == {"<unparseable>": "this is not json"}


# ------------------------------------------------------------------ #
# unknown paths
# ------------------------------------------------------------------ #

def test_stub_withUnknownGetPath_shouldAnswerJsonHttp404() -> None:
    # GIVEN the stub serving in-process:
    with StubImageServer() as stub:
        # WHEN an unknown path is GETed (sd-client parses an "error"
        # field out of HTTP error bodies, so provide one):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _http_json(stub.url + "/jobs/other-job")

    assert excinfo.value.code == 404
    body = json.loads(excinfo.value.read().decode("utf-8"))
    assert "error" in body


def test_stub_withUnknownPostPath_shouldAnswer404AndStillRecordTheRequest() -> None:
    # GIVEN the stub serving in-process:
    with StubImageServer() as stub:
        # WHEN an unknown path is POSTed (e.g. sd-client's cancel
        # path, which the stub does not implement):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _http_json(stub.url + f"{JOB_POLL_PATH}/cancel", {})

    assert excinfo.value.code == 404
    assert stub.requests == [StubRequest("POST", f"{JOB_POLL_PATH}/cancel", {})]


# ------------------------------------------------------------------ #
# in-process, ephemeral, loopback - and stay dead when stopped
# ------------------------------------------------------------------ #

def test_stub_shouldBindAnEphemeralLoopbackPortAndRefuseConnectionsAfterStop() -> None:
    # GIVEN a freshly started stub:
    stub = StubImageServer().start()
    try:
        # THEN the OS assigned an ephemeral port on loopback only:
        assert 0 < stub.port < 65536
        assert stub.url == f"http://127.0.0.1:{stub.port}"
    finally:
        stub.stop()
        stub.stop()  # idempotent - stage 5 must not fear double stop

    # AND after stop() the port is closed: connection refused, which is
    # exactly how stage 5 will exercise the unreachable-server failure
    # path:
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(
            stub.url + JOB_POLL_PATH, timeout=HTTP_TIMEOUT_SECONDS
        )


def test_stub_twoConcurrentInstances_shouldGetDistinctPorts() -> None:
    # GIVEN two stubs running at once (stage 5 may need one per
    # scenario):
    with StubImageServer() as first, StubImageServer() as second:
        # THEN each has its own ephemeral port and answers its own:
        assert first.port != second.port
        assert _http_json(first.url + JOB_POLL_PATH)[0] == 200
        assert _http_json(second.url + JOB_POLL_PATH)[0] == 200


# ------------------------------------------------------------------ #
# the acceptance probe: real sd-client.py, real subprocess, stub server
# ------------------------------------------------------------------ #

def test_sdClientSubprocess_withStubServer_shouldSubmitPollAndSaveTheBlankPng(
    tmp_path: Path,
) -> None:
    # GIVEN the stub serving in-process and a real sd-client.py
    # subprocess pointed at it via --server (spec 17: Stub server -
    # "a stub service that sd-client.py can hit"):
    with StubImageServer() as stub:
        output_path = tmp_path / "image.png"
        result = subprocess.run(
            [
                sys.executable,
                str(SD_CLIENT_PATH),
                "head and shoulders closeup picture",
                "--server",
                stub.url,
                "--width",
                "64",
                "--height",
                "32",
                "-o",
                str(output_path),
                "--output-format",
                "png",
            ],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )

        # THEN sd-client exits 0 and saved the exact blank PNG bytes
        # the stub served:
        assert result.returncode == 0, result.stderr
        assert output_path.is_file()
        assert output_path.read_bytes() == BLANK_PNG_BYTES

    # AND the stub recorded both legs of the flow, with the tool-facing
    # fields visible for assertions (prompt, dimensions, png format):
    submit = stub.requests[0]
    assert submit.method == "POST" and submit.path == IMG_GEN_PATH
    assert submit.payload["prompt"] == "head and shoulders closeup picture"
    assert submit.payload["width"] == 64
    assert submit.payload["height"] == 32
    assert submit.payload["output_format"] == "png"
    assert StubRequest("GET", JOB_POLL_PATH, {}) in stub.requests

"""A model door sends a request on uncompressed, its own re-serialization, so the request's encoding is dropped; the
ANSWER is the provider's as it comes, its encoding with it. Dropped from the answer too (85ed7bb), the provider's
compressed stream reached the CLI unannounced and every model call through a door ended in a JSON parse error with no
token (gb-coreutils-tnrqbl588, 2026-10-31)."""
import io

from gfso.adapters import door as D


class _Answer:
    status = 200

    def __init__(self, headers, body: bytes):
        self._h, self._b = headers, io.BytesIO(body)

    def getheaders(self):
        return self._h

    def read1(self, n):
        return self._b.read(n)


class _Handler:
    def __init__(self):
        self.sent, self.wfile, self.status = [], io.BytesIO(), None

    def send_response(self, status):
        self.status = status

    def send_header(self, k, v):
        self.sent.append((k.lower(), v))

    def end_headers(self):
        pass


def test_the_answer_keeps_its_encoding_and_drops_the_hops_own():
    h = _Handler()
    D._relay(h, _Answer([("Content-Encoding", "gzip"), ("Content-Length", "4"), ("Connection", "close"),
                         ("Content-Type", "text/event-stream")], b"\x1f\x8b\x08\x00"))
    assert ("content-encoding", "gzip") in h.sent and ("content-type", "text/event-stream") in h.sent
    assert not {k for k, _ in h.sent} & {"content-length", "connection"}
    assert h.wfile.getvalue() == b"4\r\n\x1f\x8b\x08\x00\r\n0\r\n\r\n"


def test_the_request_carries_neither_its_key_nor_an_encoding_upstream():
    assert {"content-encoding", "authorization", "x-api-key", "host"} <= D.DROPPED
    assert "content-encoding" not in D.HOP

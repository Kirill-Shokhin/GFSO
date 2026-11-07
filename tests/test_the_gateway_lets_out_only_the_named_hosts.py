"""The allowlist's gateway opens a connection only to an allowed name, at a public address, when the TLS handshake names
that same host — a session cannot ask for an allowed name and talk to another tenant of its address, nor reach the host
or a cloud's metadata through a name that resolves there."""
import socket
import ssl
import threading

import pytest

from gfso.adapters import egress


def _hello(name: str) -> bytes:
    """The ClientHello a TLS client sends for `name`."""
    out = ssl.MemoryBIO()
    tls = ssl.create_default_context().wrap_bio(ssl.MemoryBIO(), out, server_hostname=name)
    with pytest.raises(ssl.SSLWantReadError):
        tls.do_handshake()
    return out.read()


def test_the_handshake_names_its_host_only_when_read_whole():
    """The gateway must read a handshake as the server would: one whole record within its declared lengths, else
    nothing (critic over the gateway)."""
    hello = _hello("api.anthropic.com")
    assert egress.server_name(hello) == "api.anthropic.com"
    assert egress.server_name(b"GET / HTTP/1.1\r\n\r\n") is None
    assert egress.server_name(hello + b"\x16\x03\x01") is None, "bytes past the record"
    assert egress.server_name(hello[:-1]) is None, "a record cut short"
    longer = hello[:3] + (int.from_bytes(hello[3:5], "big") + 1).to_bytes(2, "big") + hello[5:]
    assert egress.server_name(longer) is None, "a record declaring more than it holds"


def test_a_handshake_split_across_reads_is_read_whole():
    here, there = socket.socketpair()
    hello = _hello("api.anthropic.com")
    here.sendall(hello[:7])
    threading.Timer(0.1, here.sendall, args=(hello[7:],)).start()
    assert egress._record(there) == hello


def test_past_its_cap_the_log_drops_refusals_and_keeps_openings(tmp_path, monkeypatch):
    """A session refusing itself in a loop must neither fill the host's disk through the gateway's log nor blind it to
    the connection it opens next (critic 2 over the gateway)."""
    monkeypatch.setattr(egress, "LOG_CAP", 100)
    monkeypatch.setattr(egress, "_full", [])
    log = str(tmp_path / "egress.log")
    for _ in range(20):
        egress._say(log, "10.0.0.2 refused example.com:443")
    egress._say(log, "10.0.0.2 opened api.anthropic.com 160.79.104.10", opened=True)
    lines = (tmp_path / "egress.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 8 and lines.count("the log is full: refusals are no longer written, openings still are") == 1
    assert lines[-1] == "10.0.0.2 opened api.anthropic.com 160.79.104.10"


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    """Ask the gateway once: what it answered and where it connected."""
    opened = []

    class Up:
        def __init__(self, addr):
            opened.append(addr[0])

        def sendall(self, data):
            pass

        def recv(self, n):
            return b""

        def settimeout(self, t):
            pass

        def shutdown(self, how):
            pass

    monkeypatch.setattr(egress.socket, "create_connection", lambda addr, timeout: Up(addr))

    def ask(connect: bytes, hello: bytes, resolves="160.79.104.10"):
        monkeypatch.setattr(egress.socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", (resolves, 443))])
        here, there = socket.socketpair()
        t = threading.Thread(target=egress._serve, args=(there, ("10.0.0.2", 0), {"api.anthropic.com"},
                                                          str(tmp_path / "egress.log")))
        t.start()
        here.sendall(connect)
        answer = here.recv(100)
        if answer.startswith(b"HTTP/1.1 200"):
            here.sendall(hello)
        here.shutdown(socket.SHUT_WR)
        t.join(5)
        here.close()
        return answer.split(b"\r\n")[0].decode(), opened

    return ask


def test_an_allowed_name_named_by_its_handshake_is_let_out(gateway):
    assert gateway(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n", _hello("api.anthropic.com")) == (
        "HTTP/1.1 200 Connection established", ["160.79.104.10"])


@pytest.mark.parametrize("connect, resolves", [
    (b"CONNECT example.com:443 HTTP/1.1\r\n\r\n", "93.184.215.14"),       # not on the list
    (b"CONNECT api.anthropic.com:80 HTTP/1.1\r\n\r\n", "160.79.104.10"),   # not 443
    (b"GET http://api.anthropic.com/ HTTP/1.1\r\n\r\n", "160.79.104.10"),  # not a tunnel
    (b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n", "169.254.169.254"),  # a name resolving off the internet
    (b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n", "192.168.65.254"),
])
def test_anything_else_is_refused_before_a_connection(gateway, connect, resolves):
    assert gateway(connect, b"", resolves) == ("HTTP/1.1 403 Forbidden", [])


def test_a_handshake_naming_another_host_is_not_let_out(gateway):
    said, opened = gateway(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n", _hello("example.com"))
    assert said.startswith("HTTP/1.1 200") and opened == []


def _with_extension(hello: bytes, kind: int) -> bytes:
    """`hello` with one more extension of `kind`, every length it sits inside grown with it."""
    ext = kind.to_bytes(2, "big") + (1).to_bytes(2, "big") + b"\x00"
    i = 9 + 2 + 32
    i += 1 + hello[i]
    i += 2 + int.from_bytes(hello[i:i + 2], "big")
    i += 1 + hello[i]
    out = bytearray(hello[:i] + (int.from_bytes(hello[i:i + 2], "big") + len(ext)).to_bytes(2, "big")
                    + hello[i + 2:] + ext)
    out[3:5], out[6:9] = (len(out) - 5).to_bytes(2, "big"), (len(out) - 9).to_bytes(3, "big")
    return bytes(out)


def test_an_encrypted_client_hello_is_not_let_out():
    """Under ECH the name that counts travels encrypted; the outer one is only the front's (critic 3 over the gateway)."""
    hello = _hello("registry.npmjs.org")
    assert egress.server_name(_with_extension(hello, 0x1234)) == "registry.npmjs.org", "an unknown extension is fine"
    for kind in egress.ECH:
        assert egress.server_name(_with_extension(hello, kind)) is None

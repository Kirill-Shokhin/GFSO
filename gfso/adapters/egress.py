"""A project's way out under an allowlist, run in a container of its own (`python3 egress.py <host,host…> <log>`): the
project's container stands on an internal network with no route out, and this gateway, the one member of both networks,
lets a session reach an allowed name and nothing else. It takes `CONNECT <name>:443`, refuses a name not on the list and
one that resolves to no public address, and opens the connection only when one whole TLS ClientHello, read within its
own declared lengths and with no encrypted ClientHello inside, names that same server — so the session's first word goes
to the host it asked for. What it cannot see: inside the encrypted stream a request may still name another site the same
front serves. It caches nothing and mirrors nothing (the 2026 OpenAI × Hugging Face escape went through exactly such a
component). Every connection is one line appended to `<log>`, a host file out of the session's reach, written as it
happens so a crash loses none; past a cap refusals are no longer written, so they cannot fill the host's disk, while
every opening still is — about a hundred bytes per tunnel to an allowed host, the one growth left. It listens only on
its address in the project's network (`<listen>`, the name it has there): a container elsewhere on Docker's bridge
cannot reach it. Stdlib only — it runs on the execution's own image."""
import ipaddress
import socket
import sys
import threading

PORT = 3128
#: what the log may grow to — past it one line says so and the rest is not written
LOG_CAP = 20 * 2 ** 20
#: encrypted ClientHello (and the draft ESNI before it): the server name that counts would travel encrypted inside, the
#: one this gateway reads being only the front's — a session could name an allowed host and reach another tenant of it
ECH = (0xfe0d, 0xffce)
#: how long a client may take to send its CONNECT and its ClientHello, and an allowed host to answer the connect
WAIT = 15
_log_lock = threading.Lock()
#: non-empty once the log has said it is full — it says so once
_full: list = []


def server_name(hello: bytes):
    """The server name of ONE whole TLS ClientHello record, every length inside its own declared bounds — anything
    else (a split, trailing bytes, a second name) is None: the gateway must read it as the server would."""
    try:
        if len(hello) < 9 or hello[0] != 0x16 or hello[5] != 0x01:
            return None
        if len(hello) != 5 + int.from_bytes(hello[3:5], "big") or int.from_bytes(hello[6:9], "big") != len(hello) - 9:
            return None
        end = len(hello)
        i = 9 + 2 + 32                                   # handshake header, version, random
        i += 1 + hello[i]                                # session id
        i += 2 + int.from_bytes(hello[i:i + 2], "big")   # cipher suites
        i += 1 + hello[i]                                # compression methods
        if i + 2 + int.from_bytes(hello[i:i + 2], "big") != end:
            return None
        i, names = i + 2, []
        while i < end:
            kind, n = int.from_bytes(hello[i:i + 2], "big"), int.from_bytes(hello[i + 2:i + 4], "big")
            if i + 4 + n > end:
                return None
            if kind in ECH:
                return None
            if kind == 0:                                # server_name: list length, type, name length, name
                body = hello[i + 4:i + 4 + n]
                k = int.from_bytes(body[3:5], "big")
                if n < 5 or int.from_bytes(body[:2], "big") != n - 2 or body[2] != 0 or 5 + k != n:
                    return None
                names.append(body[5:].decode("ascii"))
            i += 4 + n
        return names[0] if len(names) == 1 else None
    except (IndexError, UnicodeDecodeError):
        return None


def _record(c) -> bytes:
    """One TLS record as the client sends it, however it is split across reads."""
    got = b""
    while len(got) < 5 or len(got) < 5 + int.from_bytes(got[3:5], "big"):
        if not (more := c.recv(16384)) or len(got) > 1 << 16:
            break
        got += more
    return got


def _pipe(a, b):
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:      # either end hung up: the tunnel is over, and its close is logged by the one serving it
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:      # already shut by the other end
                pass


def _say(log: str, line: str, *, opened: bool = False) -> None:
    """One line of the log. Past its cap only refusals are dropped: a session that floods it with refusals must not
    leave unrecorded the connection it opens next — and a write that fails is dropped, never raised into the
    connection: a full disk would otherwise refuse every opening after it (critic over 71b49ad)."""
    try:
        with _log_lock, open(log, "a", encoding="utf-8") as f:
            if opened or f.tell() < LOG_CAP:
                f.write(line + "\n")
            elif not _full:
                _full.append(f.write("the log is full: refusals are no longer written, openings still are\n"))
    except OSError:          # …a log line the disk refuses is dropped: the request is served all the same
        pass


def _serve(c, peer, allowed, log):
    said = "refused"
    try:
        c.settimeout(WAIT)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            head += c.recv(4096) or b"\r\n\r\n"
        line = head.split(b"\r\n", 1)[0].decode(errors="replace").split()
        name, _, port = (line[1] if len(line) > 1 else "").rpartition(":")
        said = f"refused {name[:253] or '?'}:{port[:5] or '?'}"      # a DNS name is at most 253
        if line[:1] != ["CONNECT"] or port != "443" or name not in allowed:
            return c.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        public = [a[4][0] for a in socket.getaddrinfo(name, 443, socket.AF_INET, socket.SOCK_STREAM)
                  if ipaddress.ip_address(a[4][0]).is_global]
        if not public:
            return c.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        hello = _record(c)
        if (asked := server_name(hello)) != name:
            said = f"refused {name}: the handshake names {asked!r}"
            return
        up = socket.create_connection((public[0], 443), timeout=WAIT)
        up.settimeout(None)
        c.settimeout(None)
        up.sendall(hello)
        _say(log, f"{peer[0]} opened {name} {public[0]}", opened=True)
        said = f"closed {name}"
        threading.Thread(target=_pipe, args=(up, c), daemon=True).start()
        _pipe(c, up)
    except OSError as e:
        said += f" ({type(e).__name__})"
    finally:
        _say(log, f"{peer[0]} {said}", opened=said.startswith("closed"))
        c.close()


def main(allowed: set, log: str, listen: str) -> None:
    """Serve on `listen`'s address until the container is removed."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((socket.gethostbyname(listen), PORT))
    s.listen(64)
    while True:
        c, peer = s.accept()
        threading.Thread(target=_serve, args=(c, peer, allowed, log), daemon=True).start()


if __name__ == "__main__":
    main(set(filter(None, sys.argv[1].split(","))), sys.argv[2], sys.argv[3])

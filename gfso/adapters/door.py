"""A project's door to its model, run in a container of its own (`python3 door.py <upstream> <log> <listen> <closed>`):
the one place of the project that holds the provider's credential. A model client inside a session holds only this
door's KEY — a placeholder no other door answers — and calls it over plain HTTP; the door refuses a request without
that key and any request but the model's messages (`MODEL_PATHS`) — the credential opens far more of the account — and
takes the rest to the provider's `upstream` alone, over TLS it verifies, with the credential put in where the key was,
and streams the answer back. No agent process — the client, its tools, what they run — ever holds the
credential, so none can carry it away (the agent CLI's own scrubbing of its tools needs bubblewrap, which a container
without privileges cannot run). The credential is laid by the system in a file of the door's memory-backed `RUN`
directory, read once and removed: it is in no container's configuration, environment or disk.

Under a closed switch (`closed` = 1) the door is no way out of its own: it passes only a request the model answers by
itself (`model_alone`) — the client's own tools, content it carries — never a tool the provider runs, a URL it would
fetch, an MCP server it would call; and it forwards exactly the request it read. What it cannot stop: a session
spending the model through it, as its client does. Every request is one line appended to `<log>`, a host file out of
the session's reach, written as it happens — a passed one when its answer starts; past `LOG_CAP` refusals are no longer
written, so a flood of them cannot erase or crowd out what was passed, while every passed request still is. Stdlib
only — it runs on the execution's own image, which must have `python3`."""
import contextlib
import http.client
import json
import os
import socket
import socketserver
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer

with contextlib.suppress(ImportError):      # …POSIX's: the door runs in a container, its tests may not
    import resource

#: where the system lays the credential for the door to read once (a tmpfs of the door's container)
RUN = "/gfso-door-run"
LOG_CAP = 20 * 2 ** 20
#: the header each kind of credential travels in, as the provider reads it
HEADER = {"token": ("authorization", "Bearer {}"), "api": ("x-api-key", "{}")}
#: what is the hop's own, in either direction
HOP = {"connection", "keep-alive", "proxy-authorization", "proxy-connection", "te", "trailer", "transfer-encoding",
       "upgrade", "content-length"}
#: …and what the client's request does not carry upstream besides: its key, and an encoding — the door sends on its own
#: re-serialization, never compressed. The ANSWER keeps its encoding: stripped, the provider's compressed stream reached
#: the CLI as bytes it parsed as JSON (a JSON parse error on the first byte), every model call through a door (2026-10-31)
DROPPED = HOP | {"host", "authorization", "x-api-key", "content-encoding"}
#: the only requests a door passes, under every switch: the model's answer and its token count
MODEL_PATHS = ("/v1/messages", "/v1/messages/count_tokens")
#: the tools a closed switch's door passes: the client's own, which it runs itself — any other kind the provider runs
CLIENT_TOOLS = (None, "custom")
#: what a request may not carry under a closed switch: a server or a container for the provider to reach
CLOSED_DENIED = ("mcp_servers", "container")
#: how long a client may take to send a request — a held connection is one of the door's few threads
WAIT = 60
#: connections one address may hold at a door
PER_CLIENT = 16
#: what the log says of a connection past that
FULL = "refused: past its share of connections"
#: the largest request body a door reads — the provider's own cap on a messages request
MAX_BODY = 32 * 2 ** 20
#: the address space a door may take, under its container's 256 MiB (`_SMALL`), and a thread's stack in it
MEMORY, STACK, READER_STACK = 240 * 2 ** 20, 2 ** 19, 16 * 2 ** 20
_lock = threading.Lock()
_full: list = []


def _say(log: str, line: str, *, passed: bool = False) -> None:
    """One line of the log. Past its cap only refusals are dropped: a passed request is spend, and always written —
    and a write that fails is dropped, never raised into the request: a log's full disk let a flood of refusals turn
    every keyed request after it into a 502 (critic over 71b49ad, measured)."""
    try:
        with _lock, open(log, "a", encoding="utf-8") as f:
            if passed or f.tell() < LOG_CAP:
                f.write(line + "\n")
            elif not _full:
                _full.append(f.write("the log is full: refusals are no longer written, passed requests still are\n"))
    except OSError:          # …a log line the disk refuses is dropped: the request is served all the same
        pass


def model_alone(body: bytes) -> bool:
    """Does a messages request ask the provider for the model's answer and nothing beyond it — every tool the client's
    own, no server or container named, and nowhere in it content the provider would fetch (a source of type `url`)? What
    does not read as such an object is not."""
    try:
        asked = json.loads(body or b"{}")
    except ValueError:
        return False
    tools = asked.get("tools", []) if isinstance(asked, dict) else None
    return (isinstance(tools, list) and not any(k in asked for k in CLOSED_DENIED)
            and all(isinstance(t, dict) and t.get("type") in CLIENT_TOOLS for t in tools) and not _fetches(asked))


def _fetches(x) -> bool:
    """Is there content the provider would fetch — a `source` of type `url` — anywhere but in what a model's tool call
    said (its `input` is the client's to run)?"""
    if isinstance(x, dict):
        if x.get("type") == "tool_use":       # …its `input` alone: a whole request typed so passed a URL under it (critic)
            x = {k: v for k, v in x.items() if k != "input"}
        return (isinstance(x.get("source"), dict) and x["source"].get("type") == "url") or any(map(_fetches, x.values()))
    return isinstance(x, list) and any(map(_fetches, x))


#: the content blocks that name what the account holds by its id
STORED = ("container_upload",)


def _stored(x) -> bool:
    """Does a message's content name a file the account already holds — a block whose source is of type `file`, or a
    block of a type that carries one (`container_upload`) — anywhere in the messages or the system prompt? The door's
    credential would read it out of the account for whoever asked (critic F5). Not a tool's declared schema: a
    parameter named `file_id` there is the client's own (critic B6)."""
    if isinstance(x, list):
        return any(map(_stored, x))
    if not isinstance(x, dict) or x.get("type") == "tool_use":
        return False
    return (x.get("type") in STORED or (isinstance(x.get("source"), dict) and x["source"].get("type") == "file")
            or any(_stored(v) for k, v in x.items() if isinstance(v, (list, dict))))


def refused(keyed: bool, command: str, path: str, body, closed: bool):
    """Why a request is not passed, or None: without this door's key; anything but the model's messages, a body that is
    no JSON object, or one whose messages name a file the account holds, under every switch — the credential opens far
    more of the account than the session's own, and a body read one way here and another upstream (compressed, invalid
    text, a key twice) passed what this did not see (critic B6); under a closed one, what the model does not answer
    alone. What passes is sent on as it was read here (`canonical`)."""
    if not keyed:
        return "refused: not this door's key"
    if command != "POST" or path not in MODEL_PATHS:
        return "refused: not the model's messages"
    if (asked := canonical(body)) is None:
        return "refused: no JSON object"
    if _stored([asked.get("messages"), asked.get("system")]) or "container" in asked:
        return "refused: a file the account holds"      # …or a container of its, its files and skills (critic B7)
    return "refused: the switch is closed" if closed and not model_alone(body) else None


def _once(pairs: list) -> dict:
    """An object of `pairs`, each key once: a key given twice is read one way here and maybe another upstream."""
    if len({k for k, _ in pairs}) != len(pairs):
        raise ValueError("a key twice")
    return dict(pairs)


def canonical(body):
    """The request as this door reads it — a JSON object, decoded strictly, no key given twice — or None."""
    try:
        got = json.loads((body or b"{}").decode("utf-8"), object_pairs_hook=_once)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    return got if isinstance(got, dict) else None


def _judged(keyed: bool, command: str, path: str, body, closed: bool) -> tuple:
    """(why it is refused or None, what goes upstream: exactly what was read, no second parse there). On `_READER`, whose
    stack is the depth a body's nesting reaches in the C parser: on a connection's thin one a million brackets ended the door
    (measured); one at a time, what parsing the largest bodies holds in memory is one body's."""
    status = refused(keyed, command, path, body, closed)
    if status or not body:
        return status, body
    try:
        return None, json.dumps(canonical(body)).encode()
    except RecursionError:
        return "refused: no JSON object", None


_READER = ThreadPoolExecutor(1)


def _relay(h, r) -> None:
    """The provider's answer `r` back through the handler `h`, as it comes: the client reads a stream of events."""
    h.send_response(r.status)
    for k, v in r.getheaders():
        if k.lower() not in HOP:
            h.send_header(k, v)
    h.send_header("transfer-encoding", "chunked")
    h.end_headers()
    while chunk := r.read1(65536):
        h.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
        h.wfile.flush()
    h.wfile.write(b"0\r\n\r\n")


def handler(upstream: str, cred: dict, log: str, closed: bool):
    """The request handler over one upstream, one credential and its key."""
    name, value_of = HEADER[cred["kind"]]
    key, tls = value_of.format(cred["key"]), ssl.create_default_context()

    class _Door(BaseHTTPRequestHandler):
        protocol_version, timeout = "HTTP/1.1", WAIT

        def _pass(self):
            n, path = int(self.headers.get("content-length") or 0), self.path.split("?")[0]
            keyed = self.headers.get(name) == key
            # …the key and the size before the body is read: any container on the bridge, keyless, ran four 400 MB bodies
            # into memory at once and the door was killed, its address free for the next container to take (critic)
            body = self.rfile.read(n) if keyed and 0 < n <= MAX_BODY else None
            status, body = (_READER.submit(_judged, keyed, self.command, path, body, closed).result() if not n or body is not None
                            else ("refused: not this door's key" if not keyed else "refused: the body is over its cap", None))
            try:
                if status:
                    _say(log, f"{self.client_address[0]} {self.command} {path[:200]} {status}")
                    status = "said"
                    return self.send_error(403)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in DROPPED}
                headers[name] = value_of.format(cred["value"])
                up = http.client.HTTPSConnection(upstream, 443, context=tls, timeout=600)
                up.request(self.command, self.path, body=body, headers=headers)
                r = up.getresponse()
                # …written as the answer starts: a door ended mid-stream still leaves the passed request on record
                _say(log, f"{self.client_address[0]} {self.command} {path[:200]} {r.status}", passed=True)
                status = "said"
                _relay(self, r)
            except OSError as e:
                if status is None:                          # nothing answered yet: the client is told so
                    try:
                        self.send_error(502)
                    except OSError:      # the client is gone too
                        pass
                status = f"{'cut' if status == 'said' else 'failed'} ({type(e).__name__})"
            finally:
                if status != "said":
                    _say(log, f"{self.client_address[0]} {self.command} {path[:200]} {status}")

        def _within_memory(self):
            """A request the door has no memory for is refused by a status its client retries."""
            try:
                self._pass()
            except MemoryError:
                _say(log, f"{self.client_address[0]} {self.command} refused: no memory for it")
                with contextlib.suppress(OSError, MemoryError):
                    self.send_error(503)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _within_memory

        def log_message(self, *a):
            """Nothing: the door writes its own log, one line a request."""

    return _Door


class _Server(socketserver.ThreadingMixIn, HTTPServer):
    """A thread a connection, and no one address holding more than `PER_CLIENT`: one session's 300 idle connections left its
    neighbours no door, with no key asked (critic, ran)."""
    daemon_threads = True
    held: dict = {}
    held_lock = threading.Lock()
    log = os.devnull

    def verify_request(self, request, client_address) -> bool:
        """Room for this address? Past it, said to the client as a status its model client waits on and retries (a bare close
        read as a network fault, and it gave up with no cause anywhere: critic, ran), and on the log."""
        with self.held_lock:
            room = self.held.get(client_address[0], 0) < PER_CLIENT
            if room:
                self.held[client_address[0]] = self.held.get(client_address[0], 0) + 1
        if not room:
            _say(self.log, f"{client_address[0]} {FULL}")
            with contextlib.suppress(OSError):
                request.sendall(b"HTTP/1.1 429 Too Many Requests\r\nretry-after: 5\r\ncontent-length: 0\r\nconnection: close\r\n\r\n")
        return room

    def _leave(self, client_address) -> None:
        with self.held_lock:
            self.held[client_address[0]] -= 1

    def process_request(self, request, client_address) -> None:
        """…and a thread that would not start gives its room back: at the door's process limit an address's retries filled
        its count for the door's life, the next container on that address inheriting it (critic, ran)."""
        try:
            super().process_request(request, client_address)
        except RuntimeError:
            self._leave(client_address)
            raise

    def process_request_thread(self, request, client_address) -> None:
        """Its room back when its connection ends."""
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._leave(client_address)


def _laid(wait: float = 120) -> dict:
    """The credential and its key as the system laid them — read once, the file removed."""
    f, end = os.path.join(RUN, "credential"), time.monotonic() + wait
    while not os.path.exists(f):
        if time.monotonic() > end:
            sys.exit("no credential was laid for the door")
        time.sleep(0.1)
    with open(f, encoding="utf-8") as fh:
        cred = json.load(fh)
    os.remove(f)
    return cred


def main(upstream: str, log: str, listen: str, closed: str, port: str) -> None:
    """Serve on `listen`'s address and `port` until the container is removed."""
    # …under its container's memory, so a request too large for what is left fails alone and the door stays: eight keyed bodies of
    # the largest size at once had the kernel end it, every client of its project with it (measured). Thin stacks: address space counts them
    threading.stack_size(READER_STACK)
    _READER.submit(int).result()
    threading.stack_size(STACK)
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    server = _Server((socket.gethostbyname(listen), int(port)), handler(upstream, _laid(), log, closed == "1"))
    server.log = log
    server.serve_forever()


if __name__ == "__main__":
    main(*sys.argv[1:6])

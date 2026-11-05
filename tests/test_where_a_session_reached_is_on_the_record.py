"""Where each session reached is written by the system, one mechanism under every switch (DECISION S6): under `open`, the
default, nothing recorded it. A critic stopped the first form with one datagram, forged another project's row with a name's
line break, and found another's traffic on a record through a freed address.

A later critic ran it: a stranger's flood into a container hid what the container sent, with nothing said; a process with
no container stood a listener; `gfso run` admitted nothing; fragments invented ports.

CONTROLS: in `_Book.heard`, take the `try` off and the hostile lines stop the reader; `learn` without its grace and a freed
address keeps its dead holder; `admit` passing on a failure and work runs off the record; the kernel filter back to TCP, UDP
and ICMP and the live test's SCTP line goes; the filter's first two lines off and the inbound flood test goes red."""
import inspect
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from gfso.adapters import children, door, execution as E
from gfso import config as C, runtime as RT, workspaces as WS
from gfso.adapters import worktrees as W
from gfso.mcp import server as S
from gfso.adapters import netrecord as N
from gfso.core.types import PlaceUnavailable
from tests.test_a_session_holds_only_its_own_place import IMAGE, made, project  # noqa: F401 — a fixture

docker = pytest.mark.skipif(subprocess.run(["docker", "version"], capture_output=True).returncode != 0, reason="no Docker")


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setattr(N, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(E, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _the_record_on(monkeypatch):
    """The suite runs off it; here it is the subject, each test's record its own with no watch left behind to stand a
    listener under the next one's name."""
    monkeypatch.delenv("GFSO_NETWORK_RECORD", raising=False)
    monkeypatch.setattr(N._Record, "_watch", lambda self: None)


def _rows(data, project="p"):
    return [json.loads(x) for x in (data / "network" / f"{project}.jsonl").read_text().splitlines()]


def _flow(src="172.17.0.2", proto=6, to="1.1.1.1", port=443, asked=""):
    return json.dumps({"src": src, "proto": proto, "to": to, "port": port, "asked": asked})


def _book(*holders):
    b = N._Book()
    b.learn("".join(f"/{c}|{p}|n|executor|{ip} \n" for c, p, ip in (holders or [("a", "p", "172.17.0.2")])))
    return b


def test_a_flow_is_booked_under_its_container_s_project(data):
    b = _book()
    b.heard(_flow(), 5.0)
    b.heard(_flow(proto=17, to="8.8.8.8", port=53, asked="example.com"), 6.0)
    rows = _rows(data)
    assert [(r["kind"], r["to"], r["port"]) for r in rows] == [("tcp", "1.1.1.1", 443), ("dns", "8.8.8.8", 53)]
    assert rows[0]["node"] == "n" and rows[0]["role"] == "executor" and rows[1]["asked"] == "example.com"


@pytest.mark.parametrize("proto, kind", [(132, "sctp"), (136, "udplite"), (1, "icmp"), (250, "ip250")])
def test_any_protocol_a_session_can_send_is_named(data, proto, kind):
    _book().heard(_flow(proto=proto), 1.0)
    assert _rows(data)[0]["kind"] == kind


@pytest.mark.parametrize("line", ["not json", "[]", "{", '{"src": 5}', '{"src": "172.17.0.2"}', '{"src": "172.17.0.2", "proto": 6, "to": "x", "port": "a", "asked": ""}'])
def test_no_line_stops_the_reader_or_books_a_row(data, line):
    b = _book()
    b.heard(line, 1.0)
    b.heard(_flow(), 2.0)
    assert [r["to"] for r in _rows(data)] == ["1.1.1.1"]


def test_a_name_with_a_line_break_or_a_space_stays_one_row_of_its_own_project(data):
    b = _book()
    forged = 'x\n{"src": "172.17.0.3", "proto": 6, "to": "6.6.6.6", "port": 1, "asked": ""} y'
    b.heard(_flow(proto=17, port=53, asked=forged), 1.0)
    rows = _rows(data)
    assert len(rows) == 1 and rows[0]["asked"] == forged and not (data / "network" / "q.jsonl").exists()


def test_a_flow_of_no_container_of_this_installation_is_not_recorded(data):
    _book().heard(_flow(src="172.17.0.9"), 5.0)
    assert not (data / "network").exists()


def test_a_freed_address_leaves_its_holder_and_the_next_user_s_flow_is_on_no_record(data, monkeypatch):
    b = _book()
    b.learn("", whole=True)
    b.heard(_flow(to="1.1.1.1"), 1.0)                         # …its last flow, read after it ended
    assert _rows(data)[0]["container"] == "a"
    t = time.monotonic()
    monkeypatch.setattr(N.time, "monotonic", lambda: t + N.GRACE_S + 1)
    b.learn("", whole=True)
    b.heard(_flow(to="2.2.2.2"), 2.0)
    assert [r["to"] for r in _rows(data)] == ["1.1.1.1"]


def test_a_stranger_on_a_freed_address_is_written_under_no_one_and_the_next_start_under_its_name_is(data):
    """By the address alone a stranger went on the record of the one that left; by the link first read a place's next
    container, the same name and address, was silently off it (critics, ran). The MAC of that start tells both."""
    b = N._Book()
    b.learn("/a|p|n|executor|172.17.0.2/aa:aa \n")
    flow = lambda to, mac: json.dumps({**json.loads(_flow(to=to)), "mac": mac})
    b.heard(flow("1.1.1.1", "aaaa"), 1.0)
    b.heard(flow("6.6.6.6", "bbbb"), 2.0)
    b.heard('{"drops": 1000000, "src": "172.17.0.2", "mac": "bbbb"}', 3.0)
    assert [r.get("to") for r in _rows(data)] == ["1.1.1.1"]
    b.learn("/a|p|n|executor|172.17.0.2/cc:cc \n")                    # …its next start, the same name and address
    b.heard(flow("7.7.7.7", "cccc"), 4.0)
    assert _rows(data)[-1]["to"] == "7.7.7.7"


def test_an_address_a_standing_container_left_is_no_longer_its(data, monkeypatch):
    """A switch moves a container to another address under the same name: the old stayed its for as long as the name stood."""
    b = N._Book()
    b.learn("/a|p|n|executor|172.17.0.2/aa \n", whole=True)
    b.learn("/a|p|n|executor|172.19.0.3/bb \n", whole=True)
    t = time.monotonic()
    monkeypatch.setattr(N.time, "monotonic", lambda: t + N.GRACE_S + 1)
    b.learn("/a|p|n|executor|172.19.0.3/bb \n", whole=True)
    assert list(b.holders) == [("172.19.0.3", "bb")]


def test_a_torn_line_stops_no_reader_and_is_said(data):
    b = _book()
    b.heard('{"drops": 5, "src": "172.17.0.2"}', 1.0)
    with N.record_path("p").open("a") as f:
        f.write('{"at": 1, "tor\n')
    assert any("1 lines" in x for x in N.said_apart("p")) and any("5 packets" in x for x in N.said_apart("p"))


def test_two_writers_tear_no_row(data):
    """Three processes at full speed left torn lines and lost rows on Windows (critic, ran); this is one process's threads,
    each with its own open, which contend for the same lock."""
    path = data / "r.jsonl"
    threads = [threading.Thread(target=lambda: [N.append(path, {"at": 1.0, "x": "y" * 500}) for _ in range(100)]) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    rows, bad = N.rows_of(path)
    assert len(rows) == 400 and bad == 0


def test_docker_gone_with_work_standing_leaves_a_gap_and_a_quiet_end_none(data, monkeypatch):
    """Docker dies, its containers with it, the server lives: the turn saw no containers, as at any quiet end, and said nothing (critic, ran)."""
    r = N._Record()
    r.book = _book()
    r.proc = SimpleNamespace(poll=lambda: 1, stdin=SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(N, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(N, "_work_stands", lambda: [])
    r.turn()
    assert "gap" in _rows(data)[0]
    r.book, r.proc = _book(), SimpleNamespace(poll=lambda: None, stdin=SimpleNamespace(close=lambda: None))
    r.turn()
    assert len(_rows(data)) == 1, "the listener still stood: work simply ended"


def test_a_root_s_end_carries_what_the_records_say_of_themselves(data, monkeypatch):
    """Read only by whoever ran `gfso network`, so a session's hiding reached no one who did not ask (critic, read)."""
    engine = SimpleNamespace(project_name="p", graph=SimpleNamespace(setting=lambda _: None))
    monkeypatch.setattr(S, "_ui_link", lambda _: "link")
    ended = lambda complete=True: (out := {"complete": complete}, S._link_and_say("next_steps", out, "p", engine))[0]
    assert "the_records_say" not in ended(), "nothing to say, no key"
    _book().heard('{"drops": 5, "src": "172.17.0.2"}', 1.0)
    said = ended()
    assert "a: 5 packets" in said["the_records_say"][0] and "the_records_say" in said["say"]
    assert "the_records_say" not in ended(False), "at the end: each poll would read the whole record"
    stopped = {}
    S._link_and_say("stop_project", stopped, "p", engine)
    assert "a: 5 packets" in stopped["the_records_say"][0], "a stopped run says it too"


def test_a_reader_is_told_when_the_file_record_turned_or_named_less_than_changed(data, monkeypatch):
    """Two turns lost a session's first writes and a reading of 452 named 200, each with nothing said (critic, ran)."""
    monkeypatch.setattr(N, "append", N.append)
    path = N.file_record_path("p")
    N.append(path, {"at": 1.0, "x": 1})
    N.append(path, {"at": 1.0, "x": 2}, 1)
    assert any("turned over 1 times" in x for x in N.said_apart("p"))
    N.append(path, {"at": 1.0, "session": "s", "dir": "d", "changed": ["f a"], "changed_n": 452})
    assert any("1 readings of what changed named fewer" in x for x in N.said_apart("p"))
    for i in range(30):
        N.append(path, {"at": 1.0, "session": f"s{i}", "dir": "d", "cut": True})
    said = N.said_apart("p")
    assert "and 10 more such" in said and len(said) < 25, "a long list of it hides what comes first"


def test_a_listener_gone_says_its_gap_before_it_stands_again(data, monkeypatch):
    """Said only once it rose: a rise that failed until the work ended said nothing at all (critic, ran)."""
    r = N._Record()
    r.book, r.stood, r.proc = _book(), True, SimpleNamespace(poll=lambda: 1, stdin=SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(N, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(N, "_image", lambda: None)
    with pytest.raises(OSError):
        r.up()
    assert "gap" in _rows(data)[0]
    with pytest.raises(OSError):
        r.up()
    assert len(_rows(data)) == 1, "once"


def test_what_is_left_to_do_at_exit_runs_past_the_reap(monkeypatch):
    """A graceful stop on Linux reaps first, and past that every child died at its spawn: no container removed, no last reading (critic, ran)."""
    closing = []
    monkeypatch.setattr(children, "_CLOSING", True)
    monkeypatch.setattr(children, "_AT_EXIT", [lambda: closing.append(children._CLOSING)])
    monkeypatch.setattr(children, "_LIVE", set())
    children._end_all(closing=True)
    assert closing == [False] and children._CLOSING is True


def test_docker_not_answering_is_not_every_holder_gone(data, monkeypatch):
    b = _book()
    monkeypatch.setattr(N, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))
    assert N._holders(["c"]) is None
    assert b.holders


def test_only_a_server_starts_the_watches(monkeypatch):
    """Started by any process's first container they stood in two at once, each its own ledger and its own record of what it
    ended: a judge ended by the other read as its delivery's failure, and the holder's bound was not the server's (critic, ran)."""
    src = inspect.getsource(E._run_and_admit)
    assert "watch_disk" not in src and "watch_ceiling" not in src


def test_the_bound_s_refusals_are_read_from_its_listing_and_told(data):
    listing = "Chain gfso-flows (1 references)\n    pkts      bytes target\n      10      290 RETURN  0 -- * * 0.0.0.0/0\n      37     1073 DROP  0 -- * * 0.0.0.0/0\n"
    assert E._flows_dropped(listing) == 37 and E._flows_dropped("") == 0
    assert E._flows_dropped(listing + listing) == 74, "every chain's"
    assert E._flows_dropped(listing + "    ip protocol tcp ct state new ct count over 1024 counter packets 5 bytes 300 reject with tcp reset\n") == 42, "nft's bound too"
    N._append("p", {"at": 1.0, "container": "c", "flows_dropped": 37})
    assert any("c: 37 packets past its bounds" in x for x in N.said_apart("p"))


def test_one_address_holds_no_more_of_a_door_than_its_share():
    """One session's 300 idle connections left its neighbours no door, no key asked (critic, ran)."""
    s = door._Server.__new__(door._Server)
    s.held = {}
    assert all(s.verify_request(None, ("172.17.0.2", 1)) for _ in range(door.PER_CLIENT))
    assert not s.verify_request(socket.socket(), ("172.17.0.2", 1)), "past its share"
    assert s.verify_request(None, ("172.17.0.3", 1)), "a neighbour's room is its own"


def test_a_door_past_its_share_says_so_to_the_client_and_on_its_log(tmp_path):
    """A bare close read as a network fault: a real client gave up with no cause on any record (critic, ran)."""
    s = door._Server.__new__(door._Server)
    s.held, s.log = {"172.17.0.2": door.PER_CLIENT}, str(tmp_path / "door.log")
    a, b = socket.socketpair()
    b.settimeout(2)
    assert not s.verify_request(a, ("172.17.0.2", 1))
    assert b.recv(99).startswith(b"HTTP/1.1 429 ")
    assert door.FULL in (tmp_path / "door.log").read_text()
    assert s.verify_request(socket.socket(), ("172.17.0.3", 1)), "another's room"


def test_a_thread_that_will_not_start_gives_its_address_its_room_back(monkeypatch):
    """At the door's process limit the count went up and stayed: an address locked out for the door's life (critic, ran)."""
    s = door._Server.__new__(door._Server)
    s.held, s.block_on_close = {}, False
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(RuntimeError("can't start new thread")))
    assert s.verify_request(None, ("172.17.0.2", 1))
    s.log = os.devnull
    s.process_request(None, ("172.17.0.2", 1))
    assert s.held["172.17.0.2"] == 0


def test_a_docker_that_hangs_on_the_bound_s_line_costs_the_line_not_the_removal(monkeypatch):
    """The exec past its time raised out of `stop`: no `docker rm`, and the sessions after it stood (critic, stubbed)."""
    def hung(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 30)
    monkeypatch.setattr(E, "run", hung)
    E.PlaceContainer._say_the_bound(SimpleNamespace(container="c", project_name="p"))


def _body(n):
    a, b = socket.socketpair()
    b.sendall(b"x" * n)
    return a.makefile("rb"), a, b


def test_a_door_holds_what_has_arrived_of_bodies_and_one_address_at_most_one_of_the_largest(monkeypatch):
    """Room taken for what a request declared let two trickling connections hold a project's door from everyone (critic, ran)."""
    monkeypatch.setattr(door, "MAX_BODY", 3000)
    monkeypatch.setattr(door, "BODIES", 5000)
    trickler, peer = door._Room("t"), _body(10)
    assert trickler.read(peer[0], 10) == b"x" * 10 and door._Room.now == 10, "ten bytes came, ten are held, whatever it declared"
    big, other = door._Room("a"), door._Room("a")
    assert big.read(_body(3000)[0], 3000) and door._Room.now == 3010
    with pytest.raises(door._NoRoom):
        other.read(_body(10)[0], 10)
    assert door._Room("b").read(_body(1990)[0], 1990)
    with pytest.raises(door._NoRoom):
        door._Room("c").read(_body(10)[0], 10)
    big.free()
    assert door._Room("c").read(_body(10)[0], 10), "room back"
    door._Room.now, door._Room.by_address = 0, {}


def test_two_ids_that_spell_one_name_have_two_places():
    keys = [WS._place_key(i) for i in ("db/schema", "db_schema", "m.", "m", "k:1", "k;1", "Case", "case")]
    assert len(set(keys)) == len(keys), keys
    assert WS._place_key("db_schema") == "db_schema" and WS._place_key("root") == "root", "a plain id's place keeps its name"


def test_a_project_spelled_otherwise_is_the_project_as_it_was_made(tmp_path):
    (tmp_path / "Caps.db").write_bytes(b"")
    r = SimpleNamespace(_engines={}, _dir=str(tmp_path))
    assert RT.ProjectRegistry._spelled(r, "caps") == "Caps" and RT.ProjectRegistry._spelled(r, "Caps") == "Caps"
    assert RT.ProjectRegistry._spelled(r, "other") == "other"
    assert RT.ProjectRegistry._spelled(r, "GFSO") == "default", "the default project's own file"


@pytest.mark.skipif(not shutil.which("git"), reason="no git")
def test_a_submodule_the_user_committed_is_no_delivery_s_nested_repository(tmp_path, monkeypatch):
    def git(*a, cwd):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    base, place = tmp_path / "b", tmp_path / "p"
    for repo in (base, place):
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("update-index", "--add", "--cacheinfo", f"160000,{'a' * 40},vendor/lib", cwd=repo)
        git("commit", "-q", "-m", "c", cwd=repo)
    monkeypatch.setattr(W, "base_of", lambda p: str(base))
    assert W.nested(place, "HEAD", None) == [], "the same commit at the same path carries nothing of a node's"
    git("update-index", "--add", "--cacheinfo", f"160000,{'b' * 40},vendor/lib", cwd=place)
    git("update-index", "--add", "--cacheinfo", f"160000,{'a' * 40},mine", cwd=place)
    git("commit", "-q", "-m", "c2", cwd=place)
    assert sorted(W.nested(place, "HEAD", None)) == ["mine", "vendor/lib"], "moved, or new, it is the node's"


def test_a_length_that_is_no_number_is_past_a_door_s_cap():
    """Each wrote a traceback on the log, no key asked (critic, ran)."""
    assert door._declared("abc") > door.MAX_BODY and door._declared("-5") > door.MAX_BODY and door._declared(None) == 0 and door._declared("7") == 7


def test_a_door_opens_the_provider_at_its_rate():
    """28 requests a second from one session took host ports past every bound, under every switch, unspent on the model (critic, ran)."""
    now = [0.0]
    b = door._Bucket(2, 3, clock=lambda: now[0])
    assert [b.take() for _ in range(4)] == [True, True, True, False]
    now[0] = 1.0
    assert [b.take() for _ in range(3)] == [True, True, False]
    now[0] = 100.0
    assert [b.take() for _ in range(4)] == [True, True, True, False], "a burst, no more"


def test_a_request_gives_its_body_s_room_back_and_one_with_no_memory_is_told(tmp_path):
    sent, log = [], str(tmp_path / "door.log")
    h = SimpleNamespace(client_address=("172.17.0.2", 1), command="POST", send_error=sent.append)

    def reads_then(e=None):
        def answer(room):
            room.read(_body(100)[0], 100)
            if e:
                raise e
        return answer
    door._within_memory(h, log, reads_then())
    assert door._Room.now == 0 and not sent and not door._Room.by_address
    door._within_memory(h, log, reads_then(MemoryError()))
    assert door._Room.now == 0 and sent == [503], "its room back, its client told"
    door._within_memory(h, log, reads_then(door._NoRoom()))
    assert sent == [503, 503] and door._Room.now == 0
    assert "no memory" in (tmp_path / "door.log").read_text() and "no room" in (tmp_path / "door.log").read_text()


@docker
@pytest.mark.parametrize("fake, unread",[('find(){ rm -rf "$1"; return 1; }; ', False), ("find(){ return 1; }; ", True)])
def test_live_a_directory_gone_as_it_is_read_is_not_an_image_that_cannot_say(fake, unread):
    """A check's directory removed between the test and the find read as "this image's find cannot say": false, and it
    reached a person through a clean run (engineering, a real client)."""
    got = subprocess.run(["docker", "run", "--rm", "--tmpfs", "/v", "--entrypoint", "sh", IMAGE, "-c", "mkdir /v/d; " + fake + E._CHANGED, "sh", "1000", "5", "d", "new"],
                         capture_output=True, timeout=60)
    assert got.returncode == 0, got.stderr
    assert (b"\0\2\0" in got.stdout) is unread, got.stdout


def test_a_door_closing_puts_what_it_refused_on_its_project_s_record(data, monkeypatch, tmp_path):
    monkeypatch.setattr(E, "_log_out", lambda *a: f"172.17.0.2 {door.FULL}\n172.17.0.2 POST /v1/messages 200\n172.17.0.2 {door.FULL}\n")
    monkeypatch.setattr(E, "run", lambda *a, **k: None)
    d = E.Door(SimpleNamespace(home=tmp_path, container="c", project="p"))
    d.held = {"x": ("door-1", "k")}
    d.close()
    assert any("c: its model door refused 2 connections" in x for x in N.said_apart("p"))


def test_a_torn_line_that_reads_as_a_number_stops_no_reader(data):
    """`123` in a record raised out of `said_apart`, and the page read the 500 as records saying nothing (critic)."""
    at = N.record_path("p")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text('123\n{"at": 1.0, "container": "c", "flows_dropped": 2}\n', encoding="utf-8")
    said = N.said_apart("p")
    assert any("c: 2 packets" in x for x in said) and any("1 lines of the records could not be read" in x for x in said)


def test_what_a_door_refused_is_said_once_at_its_latest_count(data):
    N._append("p", {"at": 1.0, "door": "d", "door_refused": 3})
    N._append("p", {"at": 2.0, "door": "d", "door_refused": 7})
    said = [x for x in N.said_apart("p") if "model door" in x]
    assert len(said) == 1 and "refused 7 connections" in said[0]


@docker
def test_live_what_the_bound_refused_is_on_the_record_as_a_session_goes(data, monkeypatch, project):  # noqa: F811
    monkeypatch.setenv("GFSO_NETWORK_RECORD", "off")
    monkeypatch.setenv("GFSO_NEW_FLOWS", "1")
    made(project, "a")
    s = project.session(str(project.own / "a"))
    try:
        got = s.run(["python3", "-c", "import socket\nfor i in range(80):\n try:\n  socket.socket(socket.AF_INET,socket.SOCK_DGRAM).sendto(b'x',('192.0.2.70',5000+i))\n except OSError:\n  pass\n"],
                    cwd=str(project.own / "a"), timeout=60)
        assert got.returncode == 0, got.stderr
    finally:
        project.stop()
    dropped = [r["flows_dropped"] for r in _rows(data, project.project_name) if "flows_dropped" in r]
    assert dropped and sum(dropped) >= 20, dropped


def test_a_reader_is_told_what_the_file_record_could_not_say(data):
    E_row = {"at": 1.0, "session": "s", "dir": "d"}
    N.append(N.file_record_path("p"), {**E_row, "cut": True})
    N.append(N.file_record_path("p"), {**E_row, "cut": True})
    assert N.said_apart("p") == ["s: d: more changed than a reading could read"]


def test_a_server_gone_with_its_work_standing_leaves_a_gap_on_the_record(data, monkeypatch):
    home = E._home()
    monkeypatch.setattr(E.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(E, "_keep_logs", lambda ids: None)
    removed = []

    def docker(args, **kw):
        if args[1] == "ps":
            return SimpleNamespace(returncode=0, stdout=f"a {home} p\nb other q\nc  \n")
        removed.extend(args)
        return SimpleNamespace(returncode=0, stdout="")
    monkeypatch.setattr(E, "run", docker)
    E.end_leftovers()
    assert "a" in removed and "c" in removed and "b" not in removed
    assert "gap" in _rows(data)[0] and not (data / "network" / "q.jsonl").exists()
    assert "gap" in json.loads(E.file_record_path("p").read_text().splitlines()[0]), "both records"


def test_the_next_holder_of_an_address_takes_it_at_once(data):
    b = _book()
    b.heard(_flow(), 1.0)
    b.learn("/b|q|n|check|172.17.0.2 \n")
    b.heard(_flow(), 2.0)
    assert _rows(data)[0]["container"] == "a" and _rows(data, "q")[0]["container"] == "b"


def test_a_container_past_its_budget_or_its_ports_is_said_under_its_name(data):
    b = _book()
    b.heard('{"src": "172.17.0.2", "cut": 2000}', 1.0)
    b.heard(_flow(to="1.1.1.1", port=-1), 1.0)
    cut, more = _rows(data)
    assert "2000" in cut["cut"] and cut["container"] == "a"
    assert "port" not in more and "more than" in more["more_ports"]


def test_the_record_turns_over_keeping_its_last_turn_and_a_project_s_deletion_takes_it(data, monkeypatch):
    monkeypatch.setattr(N, "CAP", 300)
    b = _book()
    for i in range(30):
        b.heard(_flow(to=f"1.1.1.{i}"), 1.0)
    path = N.record_path("p")
    assert path.stat().st_size < 800 and path.with_suffix(".jsonl.1").exists() and _rows(data)[-1]["to"] == "1.1.1.29"
    assert any("turned" in r for r in _rows(data)), "what is gone is said"
    N.forget("p")
    assert not path.exists() and not path.with_suffix(".jsonl.1").exists()


def test_a_turnover_the_host_refuses_loses_no_row(data, monkeypatch):
    """A reader holding the file on Windows: the replace raised, and each destination then was never written again."""
    monkeypatch.setattr(N, "CAP", 10)
    b = _book()
    b.heard(_flow(to="1.1.1.1"), 1.0)
    monkeypatch.setattr(N.os, "replace", lambda *_: (_ for _ in ()).throw(PermissionError("held")))
    b.heard(_flow(to="1.1.1.2"), 2.0)
    assert [r["to"] for r in _rows(data)] == ["1.1.1.1", "1.1.1.2"]


def test_a_reader_is_told_who_lost_lines_or_passed_its_budget(data):
    assert N.said_apart("p") == []
    b = _book()
    b.heard(_flow(), 1.0)
    assert N.said_apart("p") == [], "an honest record says nothing of itself"
    b.heard('{"drops": 5, "src": "172.17.0.2"}', 1.0)
    b.heard('{"drops": 2, "src": "172.17.0.2"}', 1.0)
    b.heard('{"src": "172.17.0.2", "cut": 2000}', 1.0)
    N._append("p", {"at": 1.0, "gap": "x"})
    said = "\n".join(N.said_apart("p"))
    assert "a: 7 packets" in said and "a: past its 2000" in said and "1 times" in said


def test_no_code_runs_before_the_listener_says_its_link_is_open(data, monkeypatch):
    """Its link was opened whenever the listener got to the kernel's notice: 4 to 7 of 8 first datagrams under load (critic,
    ran). An admission waits for its word, and without the word nothing runs."""
    r, asked = N._Record(), []
    monkeypatch.setattr(r, "up", lambda: None)
    monkeypatch.setattr(N, "_holders", lambda ids: "/c|p|n|executor|172.17.0.2 \n")
    monkeypatch.setattr(N, "SYNC_S", 0.05)
    r.proc = SimpleNamespace(stdin=SimpleNamespace(write=asked.append, flush=lambda: None))
    with pytest.raises(PlaceUnavailable, match="did not open"):
        r.admit(SimpleNamespace(container="c", name="default", image=None))
    assert asked == ["s"]
    r.proc.stdin.flush = r.synced.set
    r.admit(SimpleNamespace(container="c", name="default", image=None))


def test_a_listener_taken_down_on_purpose_says_no_gap(data, monkeypatch):
    r = N._Record()
    r.proc, r.stood = SimpleNamespace(poll=lambda: None), True
    r.book = _book()
    monkeypatch.setattr(r, "down", lambda: None)
    monkeypatch.setattr(N, "_work_stands", lambda: [])
    r.turn()
    assert r.stood is False and not r.book.holders


def test_no_container_runs_where_nothing_keeps_the_record(monkeypatch):
    """`gfso run`, a reload worker: the watch was registered by `serve` and `mcp` alone, and an empty list admitted anything."""
    assert any(getattr(a, "__func__", None) is N._Record.admit for a in E.ON_START), "importing the module registers it"
    monkeypatch.setattr(E, "ON_START", [])
    monkeypatch.setattr(E, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    ex = SimpleNamespace(name="default", run_args=lambda: [], volume=SimpleNamespace(require=lambda _: None))
    with pytest.raises(PlaceUnavailable, match="off it"):
        E._run_and_admit(ex)
    monkeypatch.setenv("GFSO_NETWORK_RECORD", "off")
    E._run_and_admit(ex)


def test_the_watch_starts_at_a_process_s_first_admission_and_once(monkeypatch):
    monkeypatch.undo()
    started = []
    monkeypatch.setattr(N.threading, "Thread", lambda **k: SimpleNamespace(start=lambda: started.append(k["name"])))
    r = N._Record()
    r._watch()
    r._watch()
    assert started == ["gfso-net"]


def test_what_a_flood_lost_is_said_on_the_record(data):
    _book().heard('{"drops": 17, "src": "172.17.0.2"}', 1.0)
    row = _rows(data)[0]
    assert row["lost_packets"] == 17 and row["container"] == "a"


def test_no_work_runs_off_the_record_unless_the_installation_said_so(data, monkeypatch):
    r = N._Record()
    monkeypatch.setattr(r, "up", lambda: (_ for _ in ()).throw(OSError("host network refused")))
    monkeypatch.delenv("GFSO_NETWORK_RECORD", raising=False)
    with pytest.raises(PlaceUnavailable, match="host network refused"):
        r.admit(SimpleNamespace(container="c", name="default", image=None))
    monkeypatch.setenv("GFSO_NETWORK_RECORD", "off")
    r.admit(SimpleNamespace(container="c", name="default", image=None))


def test_an_admission_with_no_address_known_does_not_pass(data, monkeypatch):
    r = N._Record()
    monkeypatch.delenv("GFSO_NETWORK_RECORD", raising=False)
    monkeypatch.setattr(N, "network_record_off", lambda: False)
    monkeypatch.setattr(r, "up", lambda: None)
    monkeypatch.setattr(N, "_holders", lambda ids: "")
    with pytest.raises(PlaceUnavailable, match="no address"):
        r.admit(SimpleNamespace(container="c", name="default", image=None))


def test_the_word_in_the_installation_s_file_is_heard_by_a_process_that_never_took_it_in(tmp_path, monkeypatch):

    monkeypatch.delenv("GFSO_NETWORK_RECORD", raising=False)
    monkeypatch.setattr(C, "data_dir", lambda: tmp_path)
    assert not C.network_record_off()
    (tmp_path / "serve.json").write_text('{"GFSO_NETWORK_RECORD": "off"}')
    assert C.network_record_off()


def test_each_process_has_a_listener_of_its_own(monkeypatch):
    monkeypatch.setattr(N.os, "getpid", lambda: 1)
    one = N.listener()
    monkeypatch.setattr(N.os, "getpid", lambda: 2)
    assert one != N.listener()


def test_a_docker_that_did_not_answer_is_no_empty_installation(monkeypatch):
    r, downs = N._Record(), []
    r.proc = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(r, "down", lambda: downs.append(1))
    monkeypatch.setattr(N, "_work_stands", lambda: None)
    r.turn()
    assert not downs
    monkeypatch.setattr(N, "_work_stands", lambda: [])
    r.turn()
    assert downs == [1]


@docker
def test_live_a_real_session_is_admitted_before_its_first_command_and_its_flow_is_on_its_project_s_record(data, monkeypatch, project):  # noqa: F811
    r = N._Record()
    monkeypatch.setattr(N, "_image", lambda: project.image)
    monkeypatch.setattr(E, "ON_START", [r.admit])
    made(project, "a")
    try:
        got = project.session(str(project.own / "a")).run(
            ["python3", "-c", "import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\ns.sendto(b'x',('192.0.2.11',4446))\n"],
            cwd=str(project.own / "a"), timeout=60)
        assert got.returncode == 0, got.stderr
        deadline, rows = time.monotonic() + 20, []
        while time.monotonic() < deadline and not rows:
            time.sleep(1)
            path = N.record_path(project.project_name)
            rows = [x for x in _rows(data, project.project_name) if x.get("to") == "192.0.2.11"] if path.exists() else []
        assert rows and rows[0]["role"] and rows[0]["container"], rows
    finally:
        project.stop()
        r.down()


@docker
def test_live_a_session_s_every_way_out_is_on_the_record_from_its_first_packet_and_a_hostile_name_stops_nothing(data, monkeypatch):
    home, project, name, image = E._home(), f"net{uuid.uuid4().hex[:6]}", f"gfso-nettest-{uuid.uuid4().hex[:6]}", IMAGE
    monkeypatch.setattr(N, "_image", lambda: image)
    r = N._Record()
    try:
        subprocess.run(["docker", "run", "-d", "--name", name, "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--label", f"{E.HOME}={home}",
                        "--label", f"{E.PROJECT}={project}", "--label", f"{E.NODE}=a", "--label", f"{E.ROLE}=executor", "--entrypoint", "sleep", image, "120"],
                       check=True, capture_output=True)
        r.admit(SimpleNamespace(container=name, name="default", image=image))         # …no turn of a watch: its first packet is known
        program = ("import socket\n"
                   "def q(n):\n return bytes(4)+bytes([0,1,0,0,0,0,0,0])+bytes([len(n)])+n.encode()+bytes(5)\n"
                   "u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
                   "u.sendto(q('a b'+chr(10)+'{'),('192.0.2.6',53))\n"
                   "try:\n socket.create_connection(('192.0.2.7',8443),timeout=2)\nexcept OSError:\n pass\n"
                   "u.sendto(b'x',('192.0.2.8',4444))\n"
                   "said=[]\n"
                   "for what,addr in ((socket.IPPROTO_ICMP,('192.0.2.9',0)),(136,('192.0.2.10',4445))):\n"
                   " try:\n  i=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,what)\n  i.sendto(bytes([8,0,0,0,0,0,0,0]),addr)\n  said.append(what)\n except OSError:\n  pass\n"
                   "print(said)\n"
                   "try:\n socket.socket(socket.AF_PACKET,socket.SOCK_RAW)\n print('READ THE WIRE')\nexcept OSError:\n print('no wire')\n")
        said = subprocess.run(["docker", "exec", name, "python3", "-c", program], capture_output=True, text=True, timeout=60).stdout
        assert "no wire" in said, said
        want = {("dns", "192.0.2.6", 53), ("tcp", "192.0.2.7", 8443), ("udp", "192.0.2.8", 4444)}
        want |= {("icmp", "192.0.2.9", 0)} if "1," in said or "[1" in said else set()
        want |= {("udplite", "192.0.2.10", 4445)} if "136" in said else set()
        deadline, got = time.monotonic() + 20, set()
        while time.monotonic() < deadline and not want <= got:
            time.sleep(1)
            got = {(x["kind"], x["to"], x["port"]) for x in _rows(data, project)} if N.record_path(project).exists() else set()
        assert want <= got, (said, got)
        assert r.reader.is_alive(), "a hostile name stopped the reader"
    finally:
        r.down()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _start(name, project, image, labelled=True):
    subprocess.run(["docker", "run", "-d", "--name", name, "--cap-drop", "ALL", "--cpus", "1", "--memory", "128m",
                    *(["--label", f"{E.HOME}={E._home()}", "--label", f"{E.PROJECT}={project}", "--label", f"{E.NODE}=a",
                       "--label", f"{E.ROLE}=executor"] if labelled else []), "--entrypoint", "sleep", image, "90"],
                   check=True, capture_output=True)


def _send(name, program):
    return subprocess.run(["docker", "exec", name, "python3", "-c", "import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n" + program],
                          capture_output=True, text=True, timeout=60)


def _said(r):
    """Each line the listener says, before the reader passes over a source no container holds: on Docker Desktop a later
    fragment reaches it under the VM's address, and a stranger's line goes no further."""
    lines, heard = [], r.book.heard
    r.book.heard = lambda line, now: (lines.append(json.loads(line)), heard(line, now))[1]
    return lines


def _wait_rows(data, project, enough, within=20):
    end, rows = time.monotonic() + within, []
    while time.monotonic() < end:
        rows = _rows(data, project) if N.record_path(project).exists() else []
        if enough(rows):
            break
        time.sleep(1)
    return rows


@docker
def test_live_a_stranger_s_flood_into_a_container_hides_nothing_it_sends(data, monkeypatch):
    """What comes in was read too: its source no holder of the installation, the loss it caused went unsaid, and the
    container's own lines were lost with it (critic, ran: 4 of 50). Only what leaves a container is read now."""
    tag, image = uuid.uuid4().hex[:6], IMAGE
    monkeypatch.setattr(N, "_image", lambda: image)
    r, us, peer = N._Record(), f"gfso-nettest-us-{tag}", f"gfso-nettest-peer-{tag}"
    try:
        _start(us, f"in{tag}", image)
        _start(peer, "", image, labelled=False)
        r.admit(SimpleNamespace(container=us, name="default", image=image))
        at = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", us], capture_output=True, text=True).stdout.strip()
        assert at, "no address to flood"
        said = _said(r)
        flood = subprocess.Popen(["docker", "exec", peer, "python3", "-c",
                                  f"import socket,time\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\nt=time.time()\nwhile time.time()-t<10:\n s.sendto(b'x',('{at}',9))\n"])
        time.sleep(2)
        _send(us, "import time\nfor i in range(50):\n s.sendto(b'x',('192.0.2.40',5000+i%60))\n s.sendto(b'x',('192.0.2.41',i+1))\n time.sleep(0.02)\n")
        flood.wait(timeout=30)
        rows = _wait_rows(data, f"in{tag}", lambda got: len([x for x in got if x.get("to") == "192.0.2.40"]) == 50)
        assert len([x for x in rows if x.get("to") == "192.0.2.40"]) == 50, rows[:5]
        assert len([x for x in said if x.get("to") == at and x.get("port") == 9]) == 1, "read where it left the stranger, never where it came in"
    finally:
        r.down()
        subprocess.run(["docker", "rm", "-f", us, peer], capture_output=True)


@docker
def test_live_a_host_s_ports_spend_no_other_host_s_room_and_a_fragment_invents_no_port(data, monkeypatch):
    tag, image = uuid.uuid4().hex[:6], IMAGE
    monkeypatch.setattr(N, "_image", lambda: image)
    r, us = N._Record(), f"gfso-nettest-pt-{tag}"
    try:
        _start(us, f"pt{tag}", image)
        r.admit(SimpleNamespace(container=us, name="default", image=image))
        said = _said(r)
        _send(us, "import os\nfor i in range(300):\n s.sendto(b'x',('192.0.2.50',6000+i))\n"
                  "for _ in range(5):\n s.sendto(os.urandom(6000),('192.0.2.51',7001))\n"
                  "s.sendto(b'x',('192.0.2.52',7002))\n").check_returncode()
        rows = _wait_rows(data, f"pt{tag}", lambda got: any(x.get("to") == "192.0.2.52" for x in got))
        ports = [x for x in rows if x.get("to") == "192.0.2.50"]
        assert len(ports) == N.PORTS + 1 and "more_ports" in ports[-1], ports[-3:]
        assert [x["port"] for x in rows if x.get("to") == "192.0.2.51"] == [7001], "once, and only the port it went to"
        assert {x["port"] for x in said if x.get("to") == "192.0.2.51"} == {7001}, "a later fragment's bytes are no port"
        assert any(x.get("to") == "192.0.2.52" for x in rows)
    finally:
        r.down()
        subprocess.run(["docker", "rm", "-f", us], capture_output=True)


@docker
def test_live_a_first_packet_is_on_the_record_under_another_s_flood(data, monkeypatch):
    """Its link was opened whenever the listener got to the kernel's notice: 4 to 7 of 8 first datagrams (critic, ran)."""
    tag, image = uuid.uuid4().hex[:6], IMAGE
    monkeypatch.setattr(N, "_image", lambda: image)
    r, flooder, firsts = N._Record(), f"gfso-nettest-fl-{tag}", [f"gfso-nettest-f{i}-{tag}" for i in range(6)]
    try:
        _start(flooder, f"fl{tag}", image)
        r.admit(SimpleNamespace(container=flooder, name="default", image=image))
        flood = subprocess.Popen(["docker", "exec", flooder, "python3", "-c",
                                  "import socket,time\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\nt=time.time()\nwhile time.time()-t<25:\n s.sendto(b'x',('192.0.2.60',9))\n"])
        for i, n in enumerate(firsts):
            _start(n, f"fi{tag}", image)
            r.admit(SimpleNamespace(container=n, name="default", image=image))
            _send(n, f"s.sendto(b'x',('192.0.2.61',{5000 + i}))\n").check_returncode()
        want = {5000 + i for i in range(6)}
        rows = _wait_rows(data, f"fi{tag}", lambda got: {x.get("port") for x in got} >= want)
        assert {x.get("port") for x in rows} >= want, rows
        assert not any("lost_packets" in x for x in rows), ("a neighbour's flood is not their loss", rows)
        flood.kill()
    finally:
        r.down()
        subprocess.run(["docker", "rm", "-f", flooder, *firsts], capture_output=True)


@docker
def test_live_one_container_s_flood_blinds_no_other(data, monkeypatch):
    home, tag, image = E._home(), uuid.uuid4().hex[:6], IMAGE
    monkeypatch.setattr(N, "_image", lambda: image)
    r, names = N._Record(), [f"gfso-nettest-{w}-{tag}" for w in ("flood", "quiet")]
    try:
        for n, project in zip(names, (f"fl{tag}", f"qu{tag}")):
            subprocess.run(["docker", "run", "-d", "--name", n, "--cap-drop", "ALL", "--cpus", "1", "--memory", "128m", "--label", f"{E.HOME}={home}", "--label", f"{E.PROJECT}={project}",
                            "--label", f"{E.NODE}=a", "--label", f"{E.ROLE}=executor", "--entrypoint", "sleep", image, "60"], check=True, capture_output=True)
            r.admit(SimpleNamespace(container=n, name="default", image=image))
        flood = subprocess.Popen(["docker", "exec", names[0], "python3", "-c",
                                  "import socket,time\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\nt=time.time()\nwhile time.time()-t<12:\n s.sendto(b'x',('192.0.2.20',9))\n"])
        time.sleep(3)
        subprocess.run(["docker", "exec", names[1], "python3", "-c",
                        "import socket\nfor i in range(20):\n s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n s.sendto(b'x',('192.0.2.21',5000+i))\n"], capture_output=True, timeout=30)
        flood.wait(timeout=30)
        time.sleep(3)
        quiet = {x.get("port") for x in _rows(data, f"qu{tag}")}
        assert len(quiet & set(range(5000, 5020))) == 20, sorted(quiet)
        assert r.reader.is_alive()
    finally:
        r.down()
        subprocess.run(["docker", "rm", "-f", *names], capture_output=True)

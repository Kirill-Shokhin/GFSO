"""Where each session reached is written by the system, one mechanism under every switch (DECISION S6): under `open`, the
default, nothing recorded it. A critic stopped the first form with one datagram, forged another project's row with a name's
line break, and found another's traffic on a record through a freed address.

CONTROLS: in `_Book.heard`, take the `try` off and the hostile lines stop the reader; `learn` without its grace and a freed
address keeps its dead holder; `admit` passing on a failure and work runs off the record; the kernel filter back to TCP, UDP
and ICMP and the live test's SCTP line goes."""
import json
import os
import subprocess
import time
import uuid
from types import SimpleNamespace

import pytest

from gfso.adapters import execution as E
from gfso import config as C
from gfso.adapters import netrecord as N
from gfso.core.types import PlaceUnavailable
from tests.test_a_session_holds_only_its_own_place import made, project  # noqa: F401 — a fixture

docker = pytest.mark.skipif(subprocess.run(["docker", "version"], capture_output=True).returncode != 0, reason="no Docker")


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setattr(N, "data_dir", lambda: tmp_path)
    return tmp_path


def _rows(data, project="p"):
    return [json.loads(x) for x in (data / "network" / f"{project}.jsonl").read_text().splitlines()]


def _flow(src="172.17.0.2", proto=6, to="1.1.1.1", port=443, asked=""):
    return json.dumps({"src": src, "proto": proto, "to": to, "port": port, "asked": asked})


def _book(*holders):
    b = N._Book()
    b.learn("".join(f"/{c}|{p}|n|executor|{ip} \n" for c, p, ip in (holders or [("a", "p", "172.17.0.2")])))
    return b


def test_a_flow_is_booked_once_under_its_container_s_project(data):
    b = _book()
    for _ in range(3):
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
    assert [r["to"] for r in _rows(data)] == ["1.1.1.1"] and b.seen == {}


def test_the_next_holder_of_an_address_takes_it_at_once(data):
    b = _book()
    b.heard(_flow(), 1.0)
    b.learn("/b|q|n|check|172.17.0.2 \n")
    b.heard(_flow(), 2.0)
    assert _rows(data)[0]["container"] == "a" and _rows(data, "q")[0]["container"] == "b"


def test_one_container_s_flood_takes_its_own_budget_alone_and_the_server_s_memory_stays_bound(data, monkeypatch):
    monkeypatch.setattr(N, "BUDGET", 5)
    b = _book(("a", "p", "172.17.0.2"), ("b", "p", "172.17.0.3"))
    for i in range(50):
        b.heard(_flow(to=f"1.1.1.{i}"), 1.0)
    b.heard(_flow(src="172.17.0.3", to="9.9.9.9"), 2.0)
    rows = _rows(data)
    assert len(rows) == 7 and "cut" in rows[5] and rows[6]["container"] == "b" and len(b.seen["a"]) == 6


def test_the_record_turns_over_keeping_its_last_turn_and_a_project_s_deletion_takes_it(data, monkeypatch):
    monkeypatch.setattr(N, "CAP", 300)
    b = _book()
    for i in range(30):
        b.heard(_flow(to=f"1.1.1.{i}"), 1.0)
    path = N.record_path("p")
    assert path.stat().st_size < 600 and path.with_suffix(".jsonl.1").exists() and _rows(data)[-1]["to"] == "1.1.1.29"
    N.forget("p")
    assert not path.exists() and not path.with_suffix(".jsonl.1").exists()


def test_what_a_flood_lost_is_said_on_the_record(data):
    _book().heard('{"drops": 17}', 1.0)
    assert _rows(data)[0]["lost_packets"] == 17


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


def test_a_replaced_holder_takes_its_memory_with_it(data):
    b = _book()
    b.heard(_flow(), 1.0)
    b.learn("/b|p|n|check|172.17.0.2 \n")
    assert "a" not in b.seen


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
    r.proc = object()
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
    home, project, name = E._home(), f"net{uuid.uuid4().hex[:6]}", f"gfso-nettest-{uuid.uuid4().hex[:6]}"
    image = next(x for x in subprocess.run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], capture_output=True, text=True).stdout.split()
                 if x.startswith(("gfso-agent:", "gfso-keep:", "e3-linux-agent:")))
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

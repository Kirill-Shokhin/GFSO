"""`gfso wait`: the customer's agent waits on a run in the background and stays free for the person — the author,
2026-11-13: «не уместно занимать агента на 600 секунд ожиданием … мониторинг есть мониторинг». It asks only the
live server and never runs an engine of its own, which `gfso run`'s local path would (no container, no branch)."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from gfso import __version__, tools_llm as TL
from gfso.api.server import create_app
from tests.support import make_engine


def _serve(answers: list):
    calls = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            body = json.dumps(answers.pop(0) if len(answers) > 1 else answers[0]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, calls


def _wait(port, *extra):
    env = {**os.environ, "GFSO_SHARED_URL": f"http://127.0.0.1:{port}"}
    env.pop("GFSO_AGENT_ID", None)
    return subprocess.run([sys.executable, "-m", "gfso.cli", "wait", "project=p", *extra], env=env,
                          capture_output=True, text=True, timeout=60)


def test_it_returns_when_the_run_needs_its_customer_and_not_before():
    busy = {"complete": False, "steps": [{"task_id": "root.a", "mine": False}], "run": {"state": "running"}}
    srv, calls = _serve([busy, busy, {"complete": True, "steps": [], "needs_you": "the root is settled"}])
    try:
        r = _wait(srv.server_address[1])
    finally:
        srv.shutdown()
    assert r.returncode == 0 and "the root is settled" in r.stdout
    assert len(calls) == 3 and all(p == "/api/wait" and b == {"project": "p"} for p, b in calls)


def test_what_the_server_says_needs_you_is_what_it_prints():
    srv, _ = _serve([{"steps": [{"task_id": "root", "mine": True, "directive": "PASS or FAIL"}],
                      "needs_you": "1 move(s) are yours"}])
    try:
        r = _wait(srv.server_address[1])
    finally:
        srv.shutdown()
    assert r.returncode == 0 and "1 move(s) are yours" in r.stdout and "- root: PASS or FAIL" in r.stdout


def test_the_wait_ends_on_each_of_its_exits_and_not_before():
    """One wait, on the server: the root settled, a move of the caller's, `stuck`, the run stopped."""
    for answer, said in (({"complete": True}, "the root is settled"),
                         ({"steps": [{"mine": True}, {"mine": True, "optional": True}, {"mine": False}]}, "1 move(s) are yours"),
                         ({"stuck": True, "directive": "clear what blocks the merge"}, "the run is stuck: clear what blocks the merge"),
                         ({"run": {"state": "stopping"}}, "the run is stopping"),
                         ({"steps": [{"mine": False}], "run": {"state": "running"}}, None)):
        assert TL.needs_its_customer(answer) == said, answer


def test_with_no_server_it_waits_on_nothing_and_builds_no_engine_here():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = srv.server_address[1]
    srv.server_close()
    r = _wait(port)
    assert r.returncode == 2 and "no server answering" in r.stdout


def test_one_install_command_is_enough_its_output_leads_to_setup():
    """«должно ставиться одной командой» (the author, 2026-11-13): pipx says nothing of what follows, so `gfso` and
    `gfso --help` say it first, and `setup` heads the list."""
    for argv in ([], ["--help"]):
        out = subprocess.run([sys.executable, "-m", "gfso.cli", *argv], capture_output=True, text=True,
                             encoding="utf-8", timeout=60).stdout
        # the first paragraph past the usage: how many lines argparse wraps the usage into differs by Python version
        assert "Run `gfso setup`" in next(p for p in out.split("\n\n") if not p.startswith("usage:")), out[:300]
        assert out.index("{setup,") > 0


def test_a_stuck_run_wakes_it_with_its_directive_and_a_refused_wait_is_not_a_dead_server():
    """A root whose join was refused answers `stuck` with no step: the wait slept 24 h through it; and a 404 for a
    wrong project read as "no server answering", sending the agent to restart a server that was up (critic)."""
    srv, _ = _serve([{"complete": False, "stuck": True, "steps": [], "directive": "clear what blocks the merge",
                      "needs_you": "the run is stuck: clear what blocks the merge"}])
    try:
        r = _wait(srv.server_address[1])
    finally:
        srv.shutdown()
    assert r.returncode == 0 and "stuck: clear what blocks the merge" in r.stdout

    class NotFound(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"detail": "no project p"}')

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), NotFound)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = _wait(srv.server_address[1])
    finally:
        srv.shutdown()
    assert r.returncode == 2 and "refused the wait (404)" in r.stdout and "no server answering" not in r.stdout


def test_server_json_describes_this_release():
    """A registry entry hard-coded to 0.3.0 would describe 0.3.0 after a 0.4.0 publish (critic)."""
    s = json.loads((Path(__file__).parents[1] / "server.json").read_text(encoding="utf-8"))
    assert s["version"] == __version__ and all(p.get("version") == __version__ for p in s.get("packages", ()))


def test_a_stop_during_a_wait_answers_it_at_once():
    """The frontier has no step for a stop: the person's stop came back at the wait's end, minutes late (critic)."""
    e = make_engine()
    e.start()
    threading.Timer(0.5, lambda: e.pause("system", "a finding only the user rules")).start()
    t0 = time.monotonic()
    out = TL.wait_for_the_customer(e, seconds=60)
    assert time.monotonic() - t0 < 15 and out["needs_you"] == "the run is stopped"
    e.stop()


def test_the_endpoint_answers_when_the_run_needs_its_customer():
    e = make_engine()
    e.start()
    e.pause("user", "held")
    with TestClient(create_app(e)) as c:
        out = c.post("/api/wait", json={"seconds": 30}, headers={"Host": "127.0.0.1:8000"}).json()
    assert out["needs_you"] == "the run is stopped" and out["waited_seconds"] < 5, out
    e.stop()

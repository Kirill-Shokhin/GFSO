"""`gfso log -f` read through a pipe — how an agent watches a run in the background (`gfso log -f | grep
--line-buffered …` under a monitor) — gets each event while the follower still runs, not when it exits: a print
left to the pipe's block buffer held every line back (a tester's run, 2026-11-13)."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Pipeline(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps([{"ts": "2026-11-13T10:00:00", "source": "system", "message": "the one event"}]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_a_followed_log_prints_each_event_before_it_exits():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Pipeline)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {**os.environ, "GFSO_SHARED_URL": f"http://127.0.0.1:{srv.server_address[1]}"}
    env.pop("PYTHONUNBUFFERED", None)
    p = subprocess.Popen([sys.executable, "-m", "gfso.cli", "log", "-f"], stdout=subprocess.PIPE, env=env)
    try:
        got = []
        t = threading.Thread(target=lambda: got.append(p.stdout.readline()), daemon=True)
        t.start()
        t.join(30)
        assert got and b"the one event" in got[0], "the event stayed in the pipe's buffer while the follower ran"
        assert p.poll() is None
    finally:
        p.kill()
        p.wait()
        srv.shutdown()

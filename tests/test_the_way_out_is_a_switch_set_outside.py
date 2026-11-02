"""A project container's way out is a switch set outside the system — open, an allowlist, off — held outside its reach.

The author, 2026-10-28: «вкл выкл сети должен быть рубильниками просто наружу». The OpenAI × Hugging Face intrusion
(2026-07) left its sandbox through the one way out it was allowed, so a closed switch leaves no other: the container
stands on a network with no route out, no DNS, no IPv6, and under an allowlist one gateway outside it reaches only the
named hosts, the handshake naming the host asked for.
"""
import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution

IMAGE = os.environ.get("GFSO_TEST_IMAGE", "e3-linux-agent:2")   # CI: the product's own image


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.setattr(E, "_SWITCH", {})


def _ex(tmp_path, network=None, project="p"):
    base = tmp_path / "work" / "base"
    base.mkdir(parents=True, exist_ok=True)
    return ContainerExecution("t", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base), project, network)


def test_open_shuts_only_the_host(tmp_path):
    x = _ex(tmp_path)
    assert f"iptables -A OUTPUT -d {E.HOST_NET} -j REJECT && " in x.way.seal() and         'iptables -A OUTPUT -d "$gw" -j REJECT && ' in x.way.seal(), "Docker Desktop's host and Docker Engine's"
    assert x.way.seal().endswith("iptables -A INPUT -j DROP"), "and nothing reaches in"
    assert "net.ipv6.conf.all.disable_ipv6=1" in x.run_args(), "the seal is IPv4's: no IPv6 around it"


def test_a_closed_switch_stands_on_its_internal_network_with_no_capability(tmp_path):
    """The fence is the network's, and nothing reaches in: root seals the container's inbound with the one capability it
    holds — no agent's process runs as root — and only the allowlist names the gateway as its proxy."""
    for mode in ("allowlist", "off"):
        x = _ex(tmp_path, {"mode": mode, "hosts": ["api.anthropic.com"] if mode == "allowlist" else []})
        a = x.run_args()
        assert a[a.index("--network") + 1] == x.way.net and x.way.seal().endswith("iptables -A INPUT -j DROP")
        assert "--dport 53" not in x.way.seal() and E.PRIVATE_NETS[0] not in x.way.seal(),             "a closed switch's network has no route out to shut — only its own network's peers (`two_sessions`)"
        assert ("HTTPS_PROXY=http://gateway:3128" in a) == (mode == "allowlist")
        assert ["--cap-drop", "ALL", "--cap-add", "NET_ADMIN"] == a[a.index("--cap-drop"):][:4], "root's seal's alone"
    x = _ex(tmp_path, {"mode": "allowlist", "hosts": ["api.anthropic.com", "pypi.org"]})
    g, args = x.way.gateway_args()
    assert ["--cap-drop", "ALL"] == g[g.index("--cap-drop"):][:2] and "--read-only" in g and "no-new-privileges" in g
    assert "net.ipv4.ip_forward=0" in g, "the gateway forwards nothing it did not open itself"
    assert args == ["api.anthropic.com,pypi.org", "/gfso-own/egress.log", "gateway"] and "--mount" not in g
    assert g[g.index("--network") + 1] == x.way.net, "started on the project's network, it listens there alone"
    assert not any("/gfso-place" in m or str(x.state_dir()) in m for m in g), "the gateway holds nothing of the project"
    assert not x.way.log().is_relative_to(x.state_dir()), "the session's container mounts its state"


def test_a_host_with_no_public_address_is_refused_not_dropped(tmp_path, monkeypatch):
    """The host's own network and a cloud's metadata address resolve to no public address: dropping such a name would
    start a gateway whose allowlist silently differs from the declared one."""
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("169.254.169.254", 443))])
    with pytest.raises(OSError, match="metadata.example"):
        _ex(tmp_path, {"mode": "allowlist", "hosts": ["metadata.example"]}).way.open()
    assert ran == []


@pytest.mark.parametrize("network", [{"mode": "closed"}, {"mode": "allowlist", "hosts": ["x.com; reboot"]},
                                     {"mode": "allowlist", "hosts": ["localhost"]}])
def test_a_switch_is_a_known_mode_over_host_names(tmp_path, network):
    with pytest.raises(ValueError):
        _ex(tmp_path, network)


def test_turning_the_switch_starts_the_container_again(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    _ex(tmp_path).start()
    _ex(tmp_path).start()
    _ex(tmp_path, {"mode": "off"}).start()
    assert sum(1 for a in ran if a[:3] == ["docker", "run", "-d"]) == 2
    assert ran[-1][-1].startswith(_ex(tmp_path, {"mode": "off"}).way.seal())


def _docker():
    return bool(shutil.which("docker")) and subprocess.run(["docker", "image", "inspect", IMAGE],
                                                           capture_output=True).returncode == 0


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
@pytest.mark.parametrize("mode, reached", [("allowlist", "api.anthropic.com"), ("off", None), ("open", "example.com")])
def test_live_the_switch_holds_for_the_agent(tmp_path, mode, reached):
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = _ex(tmp_path, {"mode": mode, "hosts": ["api.anthropic.com"] if mode == "allowlist" else []},
            f"net{mode}{time.time_ns()}")
    probe = ("for h in api.anthropic.com example.com 192.168.65.254 1.1.1.1; do "
             "(timeout 5 bash -c \"echo > /dev/tcp/$h/443\" && echo direct-$h) 2>/dev/null; done; "
             # the network's own bridge address — the Docker VM's, on-link for every member (critic 2 over the gateway)
             "v=$(hostname -i | awk -F. '{print $1\".\"$2\".\"$3\".1\"}'); "
             "(timeout 3 bash -c \"echo > /dev/tcp/$v/111\" && echo direct-vm) 2>/dev/null; "
             "for h in api.anthropic.com example.com; do c=$(curl -s -m 10 -o /dev/null -w '%{http_code}' https://$h/); "
             "[ \"$c\" != 000 ] && echo $h; done; "
             "getent hosts example.org >/dev/null && echo DNS; iptables -F 2>/dev/null && echo FLUSHED; "
             # …the user's own networks shut under open: refused at once, never a timeout (critic over the stream in use)
             "for h in 10.255.255.1 100.100.100.100 169.254.169.254; do (timeout 5 bash -c \"echo > /dev/tcp/$h/443\") "
             "2>&1 | grep -q refused && echo shut-$h; done; "
             "grep -Eq 'NoNewPrivs:[[:space:]]+1' /proc/self/status || echo PRIVILEGED; true")
    try:
        got = x.run(["bash", "-c", probe], cwd=str(x.base), timeout=120).stdout.split()
        if mode == "open":
            assert {"direct-api.anthropic.com", "example.com", "DNS"} <= set(got) and "direct-192.168.65.254" not in got
            assert {"shut-10.255.255.1", "shut-100.100.100.100", "shut-169.254.169.254"} <= set(got), got
        else:
            assert got == ([reached] if reached else []), f"{mode}: the agent got out to {got}"
        if mode == "allowlist":       # a container elsewhere on Docker's bridge does not reach the gateway
            on_bridge = subprocess.run(["docker", "inspect", "-f", "{{.NetworkSettings.Networks.bridge.IPAddress}}",
                                        x.way.gateway], capture_output=True, text=True).stdout.strip()
            knock = subprocess.run(["docker", "run", "--rm", IMAGE, "bash", "-c",
                                    f"timeout 3 bash -c 'echo > /dev/tcp/{on_bridge}/3128' 2>/dev/null && echo REACHED"],
                                   capture_output=True, text=True).stdout
            assert on_bridge and "REACHED" not in knock
    finally:
        x.stop()
    if mode == "allowlist":
        log = x.way.log().read_text(encoding="utf-8")
        assert "opened api.anthropic.com" in log and "refused example.com:443" in log


def test_a_switch_turned_during_a_start_waits_for_it(tmp_path, monkeypatch):
    """A start seals and records ONE switch: turned mid-start, the container would be sealed open and recorded off,
    and never started again (critic 3, reproduced with the turn inside the seal)."""
    x, turned = _ex(tmp_path), []

    def fake(args, **kw):
        if args[:4] == ["docker", "exec", "-u", "0"] and not turned:
            turned.append(threading.Thread(target=x.way.switch, args=({"mode": "off"},)))
            turned[0].start()
            turned[0].join(0.5)
            assert turned[0].is_alive(), "the switch turned while the start was sealing"
        return subprocess.CompletedProcess(args, 0, "true" if args[:2] == ["docker", "inspect"] else "", "")

    monkeypatch.setattr(E, "run", fake)
    monkeypatch.setattr(E, "_STARTED", {})
    x.start()
    turned[0].join(5)
    assert E._STARTED[x.container][1] == ("open", ()) and x.way.network == ("off", ())


@pytest.mark.parametrize("bad", [{"mode": "closed"}, "off", {"mode": "allowlist", "hosts": "api.anthropic.com"},
                                 {"mode": "allowlist", "hosts": ["x.com; reboot"]}])
def test_a_switch_that_does_not_read_shuts_the_way_out(tmp_path, bad):
    """A holder keeps its object for a whole session: an operator's typo while closing must not leave it out."""
    x = _ex(tmp_path)
    with pytest.raises(ValueError):
        x.way.switch(bad)
    assert x.way.network == ("off", ())


def test_every_object_of_a_container_starts_it_under_the_switch_as_last_declared(tmp_path, monkeypatch):
    """A session keeps its object for its whole life; a second object of the same container (a lookup race, a role's
    place moved, a project dropped under a holder) must not start it back under an older switch (critic 4)."""
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    held, other = _ex(tmp_path, {"mode": "open"}), _ex(tmp_path)
    held.start()
    other.way.switch({"mode": "off"})
    held.start()
    other.start()
    held.start()
    seals = [a[-1] for a in ran if a[:4] == ["docker", "exec", "-u", "0"]]
    assert len(seals) == 2 and seals[-1].startswith(_ex(tmp_path).way.seal()) and held.way.network == ("off", ())


def test_a_turned_switch_ends_the_running_container_at_once(tmp_path, monkeypatch):
    """A session already out under the old switch is cut when it turns, not when something else next calls in."""
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    x = _ex(tmp_path)
    x.start()
    ran.clear()
    x.switch({"mode": "open"})
    assert ran == [], "an unchanged switch touches nothing"
    x.switch({"mode": "off"})
    assert ["docker", "rm", "-f", x.container] in ran and x.container not in E._STARTED


def test_a_dead_gateway_is_a_dead_container(tmp_path, monkeypatch):
    """A gateway that died (its process limit, a Docker restart) must start the project again, not leave it hanging on
    proxy errors with no cause said (critic 3 over the gateway)."""
    x = _ex(tmp_path, {"mode": "allowlist", "hosts": ["api.anthropic.com"]})
    monkeypatch.setattr(E, "run", lambda args, **kw: subprocess.CompletedProcess(
        args, 0, "false" if args[-1] == x.way.gateway else "true", ""))
    assert not x._running()
    x.switch({"mode": "off"})
    assert x._running(), "no gateway to wait for when there is none"


def test_a_turn_stops_the_container_under_the_starts_lock(tmp_path, monkeypatch):
    """A turn stops what a start holds: outside the start's lock it could remove what a start on another thread just
    made while that start records it as running (critic 3 over the gateway)."""
    x, held = _ex(tmp_path), []
    monkeypatch.setattr(E, "_STARTED", {x.container: ([], ("open", ()))})
    monkeypatch.setattr(x, "stop", lambda: held.append(E._START._is_owned()))
    x.switch({"mode": "off"})
    assert held == [True]


def test_a_projects_containers_stand_as_one_stack_subgrouped_by_role(tmp_path):
    """«контейнеры которые создаются для одной задачи логично держать в группе» (the author, 2026-10-28): a row's twenty
    containers hung side by side, alike by name. Every container of a project carries its compose project, by role."""
    x = _ex(tmp_path, {"mode": "allowlist", "hosts": ["pypi.org"]})
    place = E.PlaceContainer(x, x.own / "node")

    def group(args):
        labels = dict(a.split("=", 1) for a in args[1:] if a.startswith("com.docker.compose."))
        return labels["com.docker.compose.project"], labels["com.docker.compose.service"]
    project = group(x.run_args())[0]
    assert group(x.run_args()) == (project, "system") and group(place.run_args()) == (project, "executors")
    assert group(x.way.gateway_args()[0]) == (project, "gateway")


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
@pytest.mark.parametrize("mode", ["off", "open"])
def test_live_no_session_reaches_what_runs_in_another_nodes_container(tmp_path, mode):
    """On one project network a session reached another node's judge by its name and read the server the judge was
    testing (critic F5); under an open switch, by its address on Docker's bridge. Nothing reaches in: its own loopback
    does."""
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = _ex(tmp_path, {"mode": mode, "hosts": []}, f"in{mode}{time.time_ns()}")
    own = x.own
    try:
        x.run(["mkdir", "-p", str(own / "a"), str(own / ".gfso-scratch-b/b_1/batch1/delivery")], cwd=str(x.base),
              timeout=60)
        judge = x.session(str(own / ".gfso-scratch-b/b_1/batch1/delivery"))
        judge.popen(["python3", "-m", "http.server", "8099"], env={}, cwd=str(own / ".gfso-scratch-b/b_1/batch1/delivery"),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        ip = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                             judge.container], capture_output=True, text=True).stdout.split()[0]
        here = judge.run(["sh", "-c", "curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8099/"],
                         cwd=str(own / ".gfso-scratch-b/b_1/batch1/delivery"), timeout=60).stdout
        assert here == "200", f"the judge's own server does not answer it: {here!r}"
        for client in (x.session(str(own / "a")), x.session(str(own / "a")).client()):
            got = client.run(["sh", "-c", f"for h in {ip} {judge.container}; do curl -s -m 5 -o /dev/null "
                                          f"-w '%{{http_code}} ' http://$h:8099/; done"],
                             cwd=str(own / "a"), timeout=60).stdout.split()
            assert "200" not in got, f"{mode}: node a reached node b's judge: {got}"
    finally:
        x.stop()


_TALK = '''import socket, sys
peer, me, kind = sys.argv[1], sys.argv[2], sys.argv[3]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if kind == "udp" else socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 8080)); s.settimeout(0.3)
for _ in range(25):
    try:
        if kind == "udp":
            s.sendto(me.encode(), (peer, 8080)); print("got", s.recvfrom(100)[0].decode()); break
        s.connect((peer, 8080)); s.sendall(me.encode()); print("got", s.recv(100).decode()); break
    except OSError:
        if kind != "udp":
            s.close(); s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", 8080)); s.settimeout(0.3)
'''


@pytest.mark.skipif(not shutil.which("docker"), reason="needs docker")
@pytest.mark.parametrize("mode", ["off", "open"])
@pytest.mark.parametrize("kind", ["udp", "tcp"])
def test_live_two_sessions_sending_to_each_other_open_no_channel(tmp_path, mode, kind):
    """Each of two sealed sessions sending to the other from the same port: under the inbound seal alone each one's
    packets were the other's «answers» — a channel between nodes under a closed switch (run live). On its own network a
    session opens nothing but its project's door and gateway, by TCP from a port the kernel picks."""
    net, seal = f"talk{time.time_ns()}", _ex(tmp_path, {"mode": mode}).way.seal()
    subprocess.run(["docker", "network", "create", *(["--internal"] if mode == "off" else []), net], check=True,
                   capture_output=True)
    names = [f"{net}-{c}" for c in "ab"]
    try:
        for n in names:
            subprocess.run(["docker", "run", "-d", "-u", "0", "--name", n, "--network", net, "--cap-add", "NET_ADMIN",
                            "--entrypoint", "sh", IMAGE, "-c", f"{seal} && sleep 120"], check=True, capture_output=True)
        time.sleep(3)
        ip = [subprocess.run(["docker", "inspect", "-f", f'{{{{(index .NetworkSettings.Networks "{net}").IPAddress}}}}',
                              n], capture_output=True, text=True).stdout.strip() for n in names]
        talk = [subprocess.Popen(["docker", "exec", "-u", "1001", n, "python3", "-c", _TALK, ip[1 - i], n[-1], kind],
                                 stdout=subprocess.PIPE, text=True) for i, n in enumerate(names)]
        heard = [t.communicate(timeout=60)[0] for t in talk]
        assert not any("got" in h for h in heard), f"{mode}/{kind}: two sessions talked past the seal: {heard}"
    finally:
        subprocess.run(["docker", "rm", "-f", *names], capture_output=True)
        subprocess.run(["docker", "network", "rm", net], capture_output=True)

"""A project container's way out is a switch set outside the system — open, an allowlist, off — held outside its reach.

The author, 2026-10-28: «вкл выкл сети должен быть рубильниками просто наружу». The OpenAI × Hugging Face intrusion
(2026-07) left its sandbox through the one way out it was allowed, so a closed switch leaves no other: the container
stands on a network with no route out, no DNS, no IPv6, and under an allowlist one gateway outside it reaches only the
named hosts, the handshake naming the host asked for.
"""
import shutil
import socket
import subprocess
import threading
import time

import pytest

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution

IMAGE = "e3-linux-agent:2"


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.setattr(E, "_SWITCH", {})


def _ex(tmp_path, network=None, project="p"):
    base = tmp_path / "work" / "base"
    base.mkdir(parents=True, exist_ok=True)
    return ContainerExecution("t", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base), project, network)


def test_open_shuts_only_the_host(tmp_path):
    x = _ex(tmp_path)
    assert x.way.seal() == f"iptables -A OUTPUT -d {E.HOST_NET} -j REJECT"
    assert "--sysctl" not in x.run_args()


def test_a_closed_switch_stands_on_its_internal_network_with_no_capability(tmp_path):
    """The fence is the network's: a closed container gets no NET_ADMIN to lift anything with, and only the allowlist
    names the gateway as its proxy."""
    for mode in ("allowlist", "off"):
        x = _ex(tmp_path, {"mode": mode, "hosts": ["api.anthropic.com"] if mode == "allowlist" else []})
        a = x.run_args()
        assert "NET_ADMIN" not in a and a[a.index("--network") + 1] == x.way.net and x.way.seal() == "true"
        assert ("HTTPS_PROXY=http://gateway:3128" in a) == (mode == "allowlist")
        assert ["--cap-drop", "ALL"] == a[a.index("--cap-drop"):][:2], "a closed container has no capability at all"
    x = _ex(tmp_path, {"mode": "allowlist", "hosts": ["api.anthropic.com", "pypi.org"]})
    g = x.way.gateway_args()
    assert ["--cap-drop", "ALL"] == g[g.index("--cap-drop"):][:2] and "--read-only" in g and "no-new-privileges" in g
    assert "net.ipv4.ip_forward=0" in g, "the gateway forwards nothing it did not open itself"
    assert g[-5:] == ["python3", "/gfso-egress.py", "api.anthropic.com,pypi.org", "/log/egress.log", "gateway"]
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
    assert sum(1 for a in ran if a[:2] == ["docker", "run"]) == 2
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
             "grep -Eq 'NoNewPrivs:[[:space:]]+1' /proc/self/status || echo PRIVILEGED; true")
    try:
        got = x.run(["bash", "-c", probe], cwd=str(x.base), timeout=120).stdout.split()
        if mode == "open":
            assert {"direct-api.anthropic.com", "example.com", "DNS"} <= set(got) and "direct-192.168.65.254" not in got
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

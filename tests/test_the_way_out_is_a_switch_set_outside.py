"""A project container's way out is a switch set outside the system — open, an allowlist, off — held by the kernel.

The author, 2026-10-28: «вкл выкл сети должен быть рубильниками просто наружу». The OpenAI × Hugging Face intrusion
(2026-07) left its sandbox through the one way out it was allowed, so a closed switch leaves no other: no DNS to carry
names out, no IPv6, the host shut as before, and an allowed host pinned at start to its public addresses only.
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
    assert x.seal() == f"iptables -A OUTPUT -d {E.HOST_NET} -j REJECT"
    assert "--sysctl" not in x.run_args()


def test_a_closed_switch_leaves_no_way_out_but_the_pinned_hosts(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_public_v4", lambda h: {"160.79.104.10"} if h == "api.anthropic.com" else set())
    rules = _ex(tmp_path, {"mode": "allowlist", "hosts": ["api.anthropic.com"]}).seal().split(" && ")
    assert rules[:3] == [f"iptables -A OUTPUT -d {E.HOST_NET} -j REJECT", f"iptables -A OUTPUT -d {E.DNS_INSIDE} -j REJECT",
                         "iptables -A OUTPUT -o lo -j ACCEPT"], "DNS is refused before loopback lets it through"
    assert rules[3:] == ["iptables -A OUTPUT -d 160.79.104.10 -p tcp --dport 443 -j ACCEPT",
                         "echo '160.79.104.10 api.anthropic.com' >>/etc/hosts", "iptables -A OUTPUT -j REJECT"]
    off = _ex(tmp_path, {"mode": "off"})
    assert off.seal().endswith("-o lo -j ACCEPT && iptables -A OUTPUT -j REJECT")
    assert ["--sysctl", "net.ipv6.conf.all.disable_ipv6=1"] == off.run_args()[off.run_args().index("--sysctl"):][:2]


def test_a_host_with_no_public_address_is_refused_not_dropped(tmp_path, monkeypatch):
    """The host's own network and a cloud's metadata address resolve to no public address: pinning nothing for such a
    name would start a container whose allowlist silently differs from the declared one."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("169.254.169.254", 443))])
    with pytest.raises(OSError, match="metadata.example"):
        _ex(tmp_path, {"mode": "allowlist", "hosts": ["metadata.example"]}).seal()


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
    assert ran[-1][-1].startswith(_ex(tmp_path, {"mode": "off"}).seal())


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
             "(timeout 5 bash -c \"echo > /dev/tcp/$h/443\" && echo $h) 2>/dev/null; done; "
             "getent hosts example.org >/dev/null && echo DNS; iptables -F 2>/dev/null && echo FLUSHED; "
             "grep -Eq 'NoNewPrivs:[[:space:]]+1' /proc/self/status || echo PRIVILEGED; true")
    try:
        got = x.run(["bash", "-c", probe], cwd=str(x.base), timeout=120).stdout.split()
        if mode == "open":
            assert {"api.anthropic.com", "example.com", "DNS"} <= set(got) and "192.168.65.254" not in got
        else:
            assert got == ([reached] if reached else []), f"{mode}: the agent got out to {got}"
    finally:
        x.stop()


def test_a_switch_turned_during_a_start_waits_for_it(tmp_path, monkeypatch):
    """A start seals and records ONE switch: turned mid-start, the container would be sealed open and recorded off,
    and never started again (critic 3, reproduced with the turn inside the seal)."""
    x, turned = _ex(tmp_path), []

    def fake(args, **kw):
        if args[:4] == ["docker", "exec", "-u", "0"] and not turned:
            turned.append(threading.Thread(target=x.switch, args=({"mode": "off"},)))
            turned[0].start()
            turned[0].join(0.5)
            assert turned[0].is_alive(), "the switch turned while the start was sealing"
        return subprocess.CompletedProcess(args, 0, "true" if args[:2] == ["docker", "inspect"] else "", "")

    monkeypatch.setattr(E, "run", fake)
    monkeypatch.setattr(E, "_STARTED", {})
    x.start()
    turned[0].join(5)
    assert E._STARTED[x.container][1] == ("open", ()) and x.network == ("off", ())


@pytest.mark.parametrize("bad", [{"mode": "closed"}, "off", {"mode": "allowlist", "hosts": "api.anthropic.com"},
                                 {"mode": "allowlist", "hosts": ["x.com; reboot"]}])
def test_a_switch_that_does_not_read_shuts_the_way_out(tmp_path, bad):
    """A holder keeps its object for a whole session: an operator's typo while closing must not leave it out."""
    x = _ex(tmp_path)
    with pytest.raises(ValueError):
        x.switch(bad)
    assert x.network == ("off", ())


def test_every_object_of_a_container_starts_it_under_the_switch_as_last_declared(tmp_path, monkeypatch):
    """A session keeps its object for its whole life; a second object of the same container (a lookup race, a role's
    place moved, a project dropped under a holder) must not start it back under an older switch (critic 4)."""
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    held, other = _ex(tmp_path, {"mode": "open"}), _ex(tmp_path)
    held.start()
    other.switch({"mode": "off"})
    held.start()
    other.start()
    held.start()
    seals = [a[-1] for a in ran if a[:4] == ["docker", "exec", "-u", "0"]]
    assert len(seals) == 2 and seals[-1].startswith(_ex(tmp_path).seal()) and held.network == ("off", ())

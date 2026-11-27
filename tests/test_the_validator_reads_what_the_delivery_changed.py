"""The validator is handed what the delivery changed: the `--stat` and the patch from the commit the node's work was
taken at to the commit DELIVER recorded, read in the project's store, the patch bounded and its cut said — and, where
no start is recorded, one line saying so and no diff. Measured: without it the validator missed both defects an
outside critic, handed the diff, found in a scenario no pinned check builds (2026-11)."""
from __future__ import annotations

import gfso.packets as P
import gfso.past as PA
import gfso.tools_llm as TL
import gfso.validate as VAL
from tests.test_a_chat_delivery_is_the_tree_it_handed_in import _commit, _git, _in_chat, _repo, _take


class _Hears:
    """A fake validator keeping the packet it was handed; it reports nothing parseable (the packet is the point)."""

    def __init__(self):
        self.packets, self.calls = [], []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return "no report"

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _packet(tmp_path, text: str) -> tuple[str, str, str]:
    """(the validator's packet, the commit the root was taken at, the commit delivered) of a chat delivery of f.txt."""
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    (repo / "f.txt").write_text(text)
    head = _commit(repo, "f.txt")
    assert TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")["accepted"]
    VAL.validate_result(e, "root", _llm=(llm := _Hears()))
    e.stop()
    assert llm.packets, "no validator was started"
    return llm.packets[0], base, head


def test_the_packet_carries_the_change_since_the_work_was_taken(tmp_path):
    packet, base, head = _packet(tmp_path, "v1\nsecond line\n")
    assert f"From {base[:12]}, where this node's work was taken, to {head[:12]}" in packet, packet
    assert "f.txt | 2 ++" in packet, "the change's --stat is not carried"
    assert "+v1\n+second line" in packet, "the change's patch is not carried"
    assert "README" not in packet.split("What this delivery changed")[1].split("```diff")[1], \
        "the diff reaches below the commit the work was taken at"


def test_the_patch_is_cut_at_its_cap_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CHANGE_CAP", 200)
    packet, _, _ = _packet(tmp_path, "".join(f"line {i}\n" for i in range(500)))
    diff = packet.split("```diff\n")[1].split("\n```")[0]
    assert "the patch is cut here, past 200 characters" in diff, diff
    assert len(diff) < 200 + 200 and "+line 499" not in diff, "the cap does not hold"
    assert "f.txt | 500 +" in packet, "the stat no longer names what the cut left out"


def test_with_no_recorded_start_it_says_so_and_carries_no_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(PA, "start_of", lambda engine, node: "")    # …a delivery from before ACCEPT recorded its HEAD
    packet, _, head = _packet(tmp_path, "v1\n")
    assert f"No commit is recorded where this node's work was taken, so what {head[:12]} changed is not read" in packet
    assert "```diff" not in packet and "+v1" not in packet, "a diff against a guessed base was carried"

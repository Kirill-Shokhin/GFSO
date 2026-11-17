"""The user-agent asked "why is it done this way, and does it hold?" had nowhere to look: it found the theory only
through a link on the README's second screen (a tester's run, 2026-11-13). `canon` gives it the map and any chapter
or section of this version's text — the checkout's own file, or this release's on GitHub, fetched once."""
from gfso import canon as C
from gfso import tools_llm as T


def test_the_map_names_every_chapter_and_a_section_is_read_alone():
    m = C.read("")
    assert "12. The machine and its invariants" in m["sections"] and "12.4. Inv-6: the admissible sets" in m["sections"]
    s = C.read("§12.4")["text"]
    assert s.startswith("### 12.4. Inv-6") and "### 12.5." not in s
    ch = C.read("12")["text"]
    assert "### 12.16. Conformance" in ch and "## 13." not in ch
    assert "error" in C.read("99.9")
    assert "canon" in T.TOOLS


def test_installed_from_the_index_it_reads_this_versions_text_once(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "ROOT", tmp_path / "no-checkout")
    monkeypatch.setattr(C, "data_dir", lambda: tmp_path)
    asked = []
    body = "## Introduction\nx\n## 0. Conventions\n### 0.1. Grades\ng\n"

    def fetch(v):
        asked.append(v)
        return body
    assert C.read("0.1", fetch)["text"].startswith("### 0.1. Grades")
    assert C.read("0.1", fetch)["text"].startswith("### 0.1. Grades") and len(asked) == 1
    monkeypatch.setattr(C, "data_dir", lambda: tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    assert "error" in C.read("", lambda v: (_ for _ in ()).throw(OSError("offline")))

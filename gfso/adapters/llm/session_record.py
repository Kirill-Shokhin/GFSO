"""What a work session did to its place, as its own tool calls record it: the files it read and changed, the last range
of each, and the last distinct commands it ran that do more than look, with their exit status. The session that
continues the task after a handover is handed it beside the note (`budget._reopen`): the system's record, where the note
is the closing session's word about it. A reopen spent its first requests finding again what the last one had open —
75 % of a row's re-reads fell before a reopen's first edit (docs/notes/E4_HANDOVER.md); on the bench this part, written
from the trace with no model (experiments/e3_specbench/e4/bench/sysmap.py, whose reading this is, its task-specific
"build or check" test made general), moved a fresh session's first moves toward the previous one's own (+0.039 against
a length-matched block)."""
from __future__ import annotations

import re
from collections import OrderedDict

#: a file a command names: a path to a Makefile, or a path with an extension that is not a number
_SRC = r"((?:[A-Za-z]:)?(?:[\w./~-]*/)?Makefile|(?:[A-Za-z]:)?(?![\d.]+\b)[\w./~-]*\w\.\w{1,8})\b"
_SEG = re.compile(r"&&|\|\||;|\||\n")
#: what a line is classified on: its own lines without any heredoc's body (the data it feeds), its quoted strings
#: blanked — a `\|` inside a grep pattern is no pipe
_HEREDOC, _QUOTED = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?"), re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")


def _without_bodies(cmd: str) -> str:
    """`cmd` with every heredoc's body left out, the lines that open and close each kept."""
    out, until = [], None
    for line in cmd.splitlines():
        if until is not None:
            if line.strip() == until:
                until = None
            continue
        out.append(line)
        if tags := _HEREDOC.findall(line):
            until = tags[-1]
    return "\n".join(out)
#: a segment that only looks, sets up, keeps house (git, moving files about) or feeds a script on stdin (a patch, as the
#: bench counted it); a line of nothing else is no build or check a later session re-runs to know where the work stands
_QUIET = re.compile(r"^\s*(?:cat|ls|head|tail|sed\s+-n|grep|rg|find|wc|echo|printf|pwd|cd|pushd|popd|export|set|mkdir|"
                    r"which|true|test|\[|git|rm|cp|mv|chmod|touch|ln|sleep|for|do|done|while|if|then|else|fi|"
                    r"\w+=(?:\$\(.*\)|\S*)\s*$|python3?\s+-(?:\s|$))")
#: the file a shell command writes: a redirect or tee target (never `->`, `>=` or a number) or sed -i's file, read on
#: the line before any heredoc body, where the code it feeds would read as redirects; and a python open(F, 'w'/'a')
#: anywhere in it, a script on stdin included
_REDIRECTS = re.compile(r"(?:(?<![0-9&>=-])>>?(?![=>])|\btee(?: -a)?)\s*" + _SRC
                        + r"|sed -i\S* +(?:'[^']*'|\"[^\"]*\"|\S+) +" + _SRC)
_OPENS = re.compile(r"open\(['\"]" + _SRC + r"['\"],\s*['\"][wa]")
_EXIT = re.compile(r"Exit code (\d+)")
#: the CLI's answer to a Read of a file read before and unchanged since: no new range was read
_UNCHANGED = "Wasted call"
EDITS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
SHOWN_READ, SHOWN_RUN, COMMAND_CHARS = 30, 3, 600


def _text(result: dict) -> str:
    c = result.get("content")
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict) and isinstance(x.get("text"), str))
    return c if isinstance(c, str) else ""


def _shell_reads(cmd: str) -> list[tuple[str, str]]:
    out = []
    for s in (x.strip() for x in _SEG.split(cmd)):
        if m := re.match(r"sed -n ['\"]?(\d+),(\d+)p['\"]? +" + _SRC, s):
            out.append((m[3], f"{m[1]}-{m[2]}"))
        elif m := re.match(r"head (?:-n *)?-?(\d+) +" + _SRC, s):
            out.append((m[2], f"1-{m[1]}"))
        elif m := re.match(r"tail (?:-n *)?-?(\d+) +" + _SRC, s):
            out.append((m[2], f"last {m[1]}"))
        elif re.match(r"cat +(?![<>])", s) and "<<" not in s and ">" not in s:
            out += [(f, "whole") for f in re.findall(_SRC, s[4:])]
    return out


def _put(d: OrderedDict, key: str, value: str) -> None:
    d.pop(key, None)
    d[key] = value


class SessionRecord:
    """One session's record, fed its tool calls and their results as the stream carries them (`note_session`)."""

    def __init__(self, place: str = "") -> None:
        self.place = str(place or "").replace(chr(92), "/").rstrip("/")     # paths under it are named from it
        self.read: OrderedDict = OrderedDict()
        self.changed: OrderedDict = OrderedDict()
        self.ran: list[tuple[str, int]] = []
        self._asked: dict = {}

    def _rel(self, path: str) -> str:
        path = str(path or "").replace(chr(92), "/")
        return path[len(self.place) + 1:] if self.place and path.startswith(self.place + "/") else path

    def use(self, block: dict) -> None:
        """A tool call — kept until its result says how it went (a call refused or failed did nothing to the place)."""
        if isinstance(block.get("input"), dict) and isinstance(block.get("id"), str):
            self._asked[block["id"]] = (str(block.get("name")), block["input"])

    def result(self, result: dict, detail: dict | None = None) -> None:
        """A call's result, with the CLI's structured account of it where the event carries one (`detail`): a read, a
        change or a command that ran goes into the record; a failed or refused one did nothing to the place."""
        tid = result.get("tool_use_id")
        name, inp = self._asked.pop(tid, (None, None)) if isinstance(tid, str) else (None, None)
        failed, text = bool(result.get("is_error")), _text(result)
        if name is None or (failed and name != "Bash"):
            return
        if name == "Read" and not text.startswith(_UNCHANGED):
            o, n = inp.get("offset"), inp.get("limit")
            _put(self.read, self._rel(inp.get("file_path")), f"{o or 1}-{(o or 1) + n - 1}" if n else "whole")
        elif name in EDITS:
            hunks = (detail or {}).get("structuredPatch") if isinstance(detail, dict) else None
            span = ", ".join(f"{h['newStart']}-{h['newStart'] + h['newLines'] - 1}" for h in hunks or ()
                             if isinstance(h, dict) and {"newStart", "newLines"} <= h.keys())
            _put(self.changed, self._rel(inp.get("file_path") or inp.get("notebook_path")),
                 span or ("whole" if name == "Write" else "edited"))
        elif name == "Bash" and (cmd := str(inp.get("command") or "").strip()):
            self._ran(cmd, failed, text)

    def _ran(self, cmd: str, failed: bool, text: str) -> None:
        m = _EXIT.match(text.strip())
        if failed and not m:
            return                                       # refused before it ran: a deny rule, a permission
        head = _without_bodies(cmd)
        for f, r in _shell_reads(head):
            _put(self.read, self._rel(f), r)
        for w in _REDIRECTS.findall(head) + [(f,) for f in _OPENS.findall(cmd)]:
            _put(self.changed, self._rel(next(x for x in w if x)), "? (shell write)")
        if not all(_QUIET.match(s) for s in _SEG.split(_QUOTED.sub("''", head)) if s.strip()):
            self.ran.append((cmd, int(m[1]) if failed else 0))

    def render(self) -> str:
        """The record as the next session reads it, or '' where the session did nothing it records."""
        if not (self.read or self.changed or self.ran):
            return ""
        last, seen = [], set()
        for cmd, code in reversed(self.ran):
            if cmd not in seen and len(last) < SHOWN_RUN:
                seen.add(cmd)
                last.append(f"- exit {code}: `{cmd[:COMMAND_CHARS]}`")
        return "\n".join(
            ["Files changed (newest first; lines after the change):"]
            + ([f"- {f}: {r}" for f, r in list(reversed(self.changed.items()))[:SHOWN_READ]] or ["- none"])
            + ["Files read (newest first; the last range read):"]
            + ([f"- {f}: {r}" for f, r in list(reversed(self.read.items()))[:SHOWN_READ]] or ["- none"])
            + ["Last commands run that do more than look (newest first), with the exit status of the whole line:"]
            + (last or ["- none"]))

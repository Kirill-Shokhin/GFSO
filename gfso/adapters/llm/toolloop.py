"""An agent run over any chat wire that calls tools — what `claude -p` is to Anthropic's models, for every other one.

The work tools are the system's own vocabulary — Read, Write, Edit, Bash, Glob, Grep — the names every role offers
(`sessions.EXECUTOR_TOOLS`, the validator's, the contact's) and every prompt speaks, so nothing above the provider
changes. Files are read and written at the place's host paths (a container mounts the same directories); commands run
through the place's `ExecutionPort`, inside its container where the project runs in one. A run writes only in its own
place and reads there and in the scratch its execution lends: it sees its own work.

The loop keeps the CLI's rules where the roles rely on them: a round cut at its turn cap is continued by the next call
naming its session, any other round ends with its conversation; a run with no answer returns "" and its record says
why. And it owns its transcript, so it keeps it small: outputs of tool calls long past are elided when the context
nears the window — the compaction a headless CLI does not do.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

from gfso.config import agent_trace_dir, env_without_secrets
from gfso.core.types import PlaceUnavailable
from gfso.adapters.worktrees import base_of

#: what one tool result may carry into the context — the CLI's own cap on a command's output
OUTPUT_CAP = 30_000
READ_LINES = 2000
LINE_CAP = 2000
LISTED = 200
#: past this share of the window, outputs older than the last `KEEP_OUTPUTS` are elided before the next turn
ELIDE_AT = 0.6
KEEP_OUTPUTS = 6
#: …and with no window known, past this many characters of transcript
CHAR_CEILING = 400_000
SHELL_TIMEOUT_S = 600

TOOLS = {
    "Read": {"description": "Read a text file. Lines come numbered; `offset` (1-based line) and `limit` read a part.",
             "parameters": {"type": "object", "properties": {"file_path": {"type": "string"},
                                                             "offset": {"type": "integer"}, "limit": {"type": "integer"}},
                            "required": ["file_path"]}},
    "Write": {"description": "Write a file whole, creating its directories.",
              "parameters": {"type": "object", "properties": {"file_path": {"type": "string"},
                                                              "content": {"type": "string"}},
                             "required": ["file_path", "content"]}},
    "Edit": {"description": "Replace `old_string` by `new_string` in a file; `old_string` must occur exactly once "
                            "unless `replace_all`.",
             "parameters": {"type": "object", "properties": {"file_path": {"type": "string"},
                                                             "old_string": {"type": "string"},
                                                             "new_string": {"type": "string"},
                                                             "replace_all": {"type": "boolean"}},
                            "required": ["file_path", "old_string", "new_string"]}},
    "Bash": {"description": "Run a shell command in the working directory; its output (stdout then stderr, capped) "
                            "and exit code come back. `timeout` in seconds.",
             "parameters": {"type": "object", "properties": {"command": {"type": "string"},
                                                             "timeout": {"type": "integer"}},
                            "required": ["command"]}},
    "Glob": {"description": "Files matching a glob pattern (e.g. `src/**/*.c`), newest first.",
             "parameters": {"type": "object", "properties": {"pattern": {"type": "string"},
                                                             "path": {"type": "string"}},
                            "required": ["pattern"]}},
    "Grep": {"description": "Search file contents by regular expression. `output_mode`: files_with_matches (default), "
                            "content (matching lines with numbers) or count; `glob` filters files; `-i` ignores case.",
             "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"},
                                                             "glob": {"type": "string"},
                                                             "output_mode": {"type": "string"},
                                                             "-i": {"type": "boolean"}},
                            "required": ["pattern"]}},
}


def _answer_pending(msgs: list, why: str) -> None:
    """Answer every tool call of the last reply no tool message answered: a chat server refuses a conversation that
    leaves one open, so a round cut mid-call kept a transcript no next round could resume (critic over the chat path)."""
    last = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i].get("role") == "assistant"), None)
    if last is None:
        return
    done = {m.get("tool_call_id") for m in msgs[last + 1:] if m.get("role") == "tool"}
    msgs += [{"role": "tool", "tool_call_id": c["id"], "content": why}
             for c in msgs[last].get("tool_calls") or () if c.get("id") not in done]


def transcript_path(execution, session: str) -> Path:
    """Where a session's conversation is kept between rounds — beside the agent state of its execution."""
    return Path(execution.state_dir()) / "gfso-sessions" / f"{session}.json"


def _capped(text: str, cap: int = OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    half = cap // 2
    return f"{text[:half]}\n… [{len(text) - cap} characters cut from the middle] …\n{text[-half:]}"


class Place:
    """The tools of one run, confined to its place: it writes only under its working directory, and reads there, in
    the base a node's place is a checkout of (its packet sends it there for what the checkout lacks) and in the scratch
    its execution lends (where a packet's inputs are laid). Each tool answers in text, an error included; a command
    gets the time the run has left."""

    def __init__(self, execution, cwd: str, deadline: float = float("inf")):
        # its commands run in the session's own place (`ExecutionPort.session`), not the system's
        self.exec, self.cwd, self.deadline = execution.session(str(cwd)), Path(cwd).resolve(), deadline
        base = base_of(str(self.cwd))
        self.roots = [self.cwd, Path(self.exec.temp_root()).resolve(), *([Path(base).resolve()] if base else [])]

    def _inside(self, full: Path, write: bool = False) -> bool:
        return any(full == r or full.is_relative_to(r) for r in (self.roots[:1] if write else self.roots))

    def path(self, p: str, write: bool = False) -> Path:
        """The host path a tool's argument names, however the model spelled it — refused outside the place."""
        p = self.exec.to_outside(str(p or ""))
        if os.name == "nt" and (m := re.match(r"^/([a-zA-Z])/(.*)$", p)):        # Git bash's /c/… spelling
            p = f"{m.group(1)}:/{m.group(2)}"
        full = (Path(p) if Path(p).is_absolute() else self.cwd / p).resolve()
        if not self._inside(full, write):
            raise PermissionError(f"{p} is outside this run's place ({self.cwd})" + (" — it writes only there" if write else ""))
        return full

    def Read(self, file_path, offset=None, limit=None):
        """The file's lines, numbered, a window of them at most."""
        f = self.path(file_path)
        if f.is_dir():
            return f"Error: {file_path} is a directory"
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(offset or 1))
        part = lines[start - 1:start - 1 + int(limit or READ_LINES)]
        body = "\n".join(f"{n:6}\t{line[:LINE_CAP]}" for n, line in enumerate(part, start))
        more = len(lines) - (start - 1 + len(part))
        return _capped(body + (f"\n… {more} more lines (read on with `offset`)" if more > 0 else "") or "(empty file)")

    def Write(self, file_path, content):
        """The file written whole."""
        f = self.path(file_path, write=True)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8", newline="")
        return f"wrote {len(content)} characters to {file_path}"

    def Edit(self, file_path, old_string, new_string, replace_all=False):
        """One occurrence replaced — or every one, asked so; none or several where one was meant is an error."""
        f = self.path(file_path, write=True)
        with open(f, encoding="utf-8", newline="") as h:          # as written: a CRLF file stays CRLF
            text = h.read()
        if "\r\n" in text and "\r\n" not in old_string:
            old_string, new_string = (s.replace("\n", "\r\n") for s in (old_string, new_string))
        n = text.count(old_string)
        if n == 0:
            return f"Error: old_string not found in {file_path}"
        if n > 1 and not replace_all:
            return f"Error: old_string occurs {n} times in {file_path} — give more context or set replace_all"
        f.write_text(text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1),
                     encoding="utf-8", newline="")
        return f"replaced {n if replace_all else 1} occurrence(s) in {file_path}"

    def Bash(self, command, timeout=None):
        """The command run in the place's working directory through its execution, its output capped; this process's
        keys are not in its environment."""
        shell = self.exec.shell()
        args = [shell, "-c", command] if shell else ["cmd", "/c", command]
        left = self.deadline - time.monotonic()
        if left <= 0:
            return "Error: the run's time is up"
        cap = max(1, int(min(int(timeout or SHELL_TIMEOUT_S), SHELL_TIMEOUT_S * 3, left)))
        try:
            r = self.exec.run(args, cwd=str(self.cwd), timeout=cap, env=env_without_secrets())
        except subprocess.TimeoutExpired:
            return f"Error: the command ran past {cap}s and was ended"
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return _capped(out.strip() + f"\n[exit code {r.returncode}]")

    def _walk(self, base: Path, pattern: str):
        """Files under `base` matching `pattern`, newest first — every one inside the place: an absolute pattern is read
        from its own fixed head, and one climbing out (`..`) finds nothing outside."""
        if Path(pattern).is_absolute():
            parts = Path(pattern).parts
            fixed = next((i for i, x in enumerate(parts) if any(c in x for c in "*?[")), len(parts))
            base, pattern = self.path(str(Path(*parts[:fixed]))), str(Path(*parts[fixed:])) if fixed < len(parts) else "*"
        found = (p.resolve() for p in base.glob(pattern))
        return sorted((p for p in found if p.is_file() and ".git" not in p.parts and self._inside(p)),
                      key=lambda p: p.stat().st_mtime, reverse=True)

    def Glob(self, pattern, path=None):
        """Files matching, newest first, a listing's worth at most."""
        found = self._walk(self.path(path or "."), pattern)
        shown = "\n".join(str(p) for p in found[:LISTED])
        return (shown + (f"\n… {len(found) - LISTED} more" if len(found) > LISTED else "")) or "no files match"

    def Grep(self, pattern, path=None, glob=None, output_mode="files_with_matches", **kw):
        """Files, lines or counts matching a regular expression; binary and huge files skipped."""
        rx = re.compile(pattern, re.IGNORECASE if kw.get("-i") else 0)
        base = self.path(path or ".")
        hits = []
        for f in [base] if base.is_file() else self._walk(base, glob or "**/*"):
            matched = _matching(f, rx)
            if not matched:
                continue
            if output_mode == "content":
                hits += [f"{f}:{n}:{l[:LINE_CAP]}" for n, l in matched]
            else:
                hits.append(f"{f}:{len(matched)}" if output_mode == "count" else str(f))
        shown = "\n".join(hits[:LISTED * 2])
        return _capped(shown + (f"\n… {len(hits) - LISTED * 2} more" if len(hits) > LISTED * 2 else "")) or "no matches"

    def call(self, name: str, args: dict) -> str:
        """One tool call's answer; a failure of the call is told to the model as text, never raised to the loop."""
        if "__unparsed__" in args:
            return f"Error: the arguments were not valid JSON: {str(args['__unparsed__'])[:200]}"
        try:
            return getattr(self, name)(**args)
        except PlaceUnavailable:
            raise                                   # the place is down: the run ends, the project stops (`ToolLoop`)
        except TypeError as e:
            return f"Error: {name} was called with the wrong arguments ({e})"
        except Exception as e:  # noqa: BLE001 — whatever a tool meets is told to the model; a run never dies of it
            return f"Error: {type(e).__name__}: {e}"


def _matching(f: Path, rx) -> list:
    try:
        if f.stat().st_size > 2_000_000 or b"\0" in f.open("rb").read(4096):
            return []
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []                                  # a file gone or unreadable mid-walk is simply not a match
    return [(n, l) for n, l in enumerate(lines, 1) if rx.search(l)]


class ToolLoop:
    """One agent run of a `ChatProvider`: turns until the model answers without asking for a tool."""

    def __init__(self, provider):
        self.p = provider

    def _elide(self, msgs: list, last_prompt: int | None, force: bool = False) -> None:
        window = self.p.wire.context_window
        size = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or "")) for m in msgs)
        if not force and not ((window and last_prompt and last_prompt > ELIDE_AT * window) or size > CHAR_CEILING):
            return
        outputs = [m for m in msgs if m.get("role") == "tool" and not m.get("_elided")]
        for m in outputs[:-(2 if force else KEEP_OUTPUTS)]:
            m["content"] = (f"[earlier output elided to keep the context small: {len(str(m['content']))} characters "
                            f"— run the tool again if you need it]")
            m["_elided"] = True

    def run(self, system, user, allowed_tools, cwd, timeout, max_turns, session) -> str:
        """The run's final answer, or "" where it gave none; its record booked on the provider either way."""
        p, t0 = self.p, time.monotonic()
        names = [n for n in dict.fromkeys(t.split("(", 1)[0].strip() for t in allowed_tools) if n in TOOLS]
        kept = transcript_path(p.execution, session) if session else None
        resumed = bool(kept and kept.is_file())
        msgs = json.loads(kept.read_text(encoding="utf-8")) if resumed else [{"role": "system", "content": system}]
        # a conversation not found opens on what the run reopens on (`resume_fallback`), as the CLI's cold retry does
        msgs.append({"role": "user", "content": user if resumed else (p.resume_fallback or user)})
        p.begin_run()
        turns, (answer, ended, stop, error) = [], ("", "answered", None, None)
        trace, place = _open_trace(p.stage_hint), None
        try:
            answer, ended, stop, error = self._turns(msgs, names, Place(p.execution, cwd, t0 + timeout), turns, t0,
                                                     timeout, max_turns, trace)
        except PlaceUnavailable as e:
            answer, ended, stop, error, place = "", "unavailable", None, str(e), e.place
            _answer_pending(msgs, f"Error: the place went down before this ran ({e}) — run it again")
        finally:
            if trace is not None:
                trace.close()
        p.book(turns, t0, ended=ended, resumed=resumed, stop_reason=stop, error=error, place=place)
        if kept is not None:                # only a round cut at its cap is continued (the CLI's rule)
            if stop == "max_turns" or ended in ("limit", "unavailable", "unauthorized"):
                # …and a round a stop refused mid-run is continued after the lift, as the CLI's is (`headless`)
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_text(json.dumps(msgs), encoding="utf-8")
            else:
                kept.unlink(missing_ok=True)
        return answer if ended == "answered" else ""

    def _turns(self, msgs, names, place, turns, t0, timeout, max_turns, trace):
        """Turn after turn until an answer, a failure, the time cap or the turn cap: (answer, ended, stop, error)."""
        specs = [{"name": n, **TOOLS[n]} for n in names]
        shrunk = False
        for n in (range(max_turns) if max_turns else itertools.count()):
            left = timeout - (time.monotonic() - t0)
            if left <= 0:
                return "", "cut", None, f"the run's cap of {timeout}s passed"
            self._elide(msgs, turns[-1].prompt_tokens if turns else None)
            t = self.p.wire.turn([{k: v for k, v in m.items() if not k.startswith("_")} for m in msgs], specs,
                                 timeout=left)
            if t.finish == "context" and not shrunk:          # once: everything but the last outputs elided, again
                shrunk = True
                self._elide(msgs, None, force=True)
                continue
            turns.append(t)
            if not n and self.p.wire.context_window is None:
                self.p.wire.discover_window()       # a local server lists its window only once the model is loaded
            self.p.note_peak(t.prompt_tokens)
            self._tick(n, t, t0)
            if t.failed:
                return "", t.ended, None, t.error
            msgs.append(t.raw_assistant or {"role": "assistant", "content": t.text})
            if not t.tool_calls:
                return t.text, "answered", t.stop_reason or "end_turn", None
            results = []
            for c in t.tool_calls:
                if c["name"] in names and "__unparsed__" not in c["arguments"]:
                    self.p.note_tool(c["name"])            # counted where it ran: a malformed call ran nothing
                out = place.call(c["name"], c["arguments"]) if c["name"] in names else \
                    f"Error: no tool {c['name']!r} in this run (offered: {', '.join(names)})"
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out})
                results.append(out)
            _traced(trace, n, t, results)
        return "", "max_turns", "max_turns", "error_max_turns: the run reached its turn cap"

    def _tick(self, n, t, t0) -> None:
        if self.p.on_tick is not None:
            try:
                self.p.on_tick(f"{self.p.stage_hint or 'agent run'}: turn {n + 1} · context {t.prompt_tokens or '?'} "
                               f"tokens · {time.monotonic() - t0:.0f}s")
            except Exception:  # noqa: BLE001 — a tick is presentation: it never breaks the run it reports on
                return


def _open_trace(stage: str):
    """The run's audit trace (`GFSO_AGENT_TRACE_DIR`), or None — losing it never costs the run."""
    if not (tdir := agent_trace_dir()):
        return None
    try:
        Path(tdir).mkdir(parents=True, exist_ok=True)
        tag = "".join(c if c.isalnum() else "_" for c in (stage or "call"))[-60:]
        return open(Path(tdir) / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}-{tag}.jsonl", "w",
                    encoding="utf-8", buffering=1)
    except OSError:
        return None


def _traced(trace, n, t, results) -> None:
    if trace is None:
        return
    try:
        trace.write(json.dumps({"turn": n + 1, "assistant": t.raw_assistant, "tool_results": results,
                                "prompt_tokens": t.prompt_tokens, "output_tokens": t.output_tokens}) + "\n")
    except OSError:
        return                                     # an audit aid: a failed write never costs the run

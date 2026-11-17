"""A shell command read as a POSIX shell reads it: its words, its simple commands, and which of them run in a
subshell of their own.

Why a module of its own: a guard that asks what a pinned probe RUNS — which program, from which directory, under
which environment — is answered only by the shell's own reading, never by a pattern over the string (a `PYTHONPATH=`
prefix on a first command let a second through; a `cd` left by a subshell still counted; a split that gave up on an
apostrophe in a comment read the rest as words: critics over the probe guard, 2026-11-14). So the reader never gives
up: an unclosed quote or substitution runs to the end of the text, as a shell would wait for its close.
"""
from __future__ import annotations


#: operators, longest first so `&&` is not read as two `&`
_OPS = sorted(("&&", "||", ";;", "|&", "&>>", "&>", ">>", ">&", "<&", "<<<", "<<-", "<<", "<>", ">|",
               ";", "|", "&", "(", ")", "\n", "<", ">"), key=len, reverse=True)
_REDIRECTS = {"&>>", "&>", ">>", ">&", "<&", "<<<", "<<-", "<<", "<>", ">|", "<", ">"}
_HEREDOCS = {"<<", "<<-"}
#: what puts the command beside it in a subshell: a pipe on either side, or `&` after it
_PIPES, _BACKGROUND = {"|", "|&"}, {"|", "|&", "&"}
#: words that mean something only where a command begins
_RESERVED = {"{", "}", "!"}


class Word(str):
    """A word as the shell hands it on, its quotes removed; `subs` the text of each command substitution in it."""
    subs: tuple = ()


class Op(str):
    """An operator: a separator, a parenthesis or a redirection."""


class _Builder:
    """The word being read: its pieces and the substitutions in it — no word at all until something is read into it."""

    def __init__(self):
        self.buf, self.subs, self.started = [], [], False

    def add(self, text: str) -> None:
        """A piece read into the word — an empty one too: `''` is a word."""
        self.buf.append(text)
        self.started = True

    def take(self) -> list:
        """The word read so far, as a one-element list (none if nothing was read), and a fresh start."""
        w = []
        if self.started:
            w = [Word("".join(self.buf))]
            w[0].subs = tuple(self.subs)
        self.__init__()
        return w


def substitution_end(cmd: str, i: int) -> int:
    """The index just past the `)` that closes a `$(` whose text starts at `i` — quotes and nesting respected."""
    depth = 1
    while i < len(cmd) and depth:
        ch = cmd[i]
        if ch in "'\"`":
            end = cmd.find(ch, i + 1)
            i = len(cmd) if end < 0 else end + 1
            continue
        depth += (ch == "(") - (ch == ")")
        i += 2 if ch == "\\" else 1
    return min(i, len(cmd))


def _substitution(cmd: str, i: int, w: _Builder) -> int:
    """The `$( … )`, `<( … )`, `>( … )` or backquoted substitution at `i`: its text kept in the word, its inner command
    noted — a process substitution runs its command as surely as a command substitution does."""
    if cmd[i] == "`":
        j = i + 1
        while j < len(cmd) and cmd[j] != "`":
            j += 2 if cmd[j] == "\\" else 1
        w.subs.append(cmd[i + 1:j].replace("\\`", "`"))
        w.add(cmd[i:j + 1])
        return j + 1
    j = substitution_end(cmd, i + 2)
    w.subs.append(cmd[i + 2:j - 1] if cmd[j - 1:j] == ")" else cmd[i + 2:j])
    w.add(cmd[i:j])
    return j


def brace_end(cmd: str, i: int) -> int:
    """The index just past the `}` that closes the `${` at `i` — quotes, nested `${…}` and `$(…)` inside it respected:
    `"${x:-"(none)"}"` is one word, its inner quotes the expansion's own (a critic's case, refused by a reader that
    closed the outer quote there)."""
    j, depth = i + 2, 1
    while j < len(cmd) and depth:
        ch = cmd[j]
        if ch == "\\":
            j += 2
        elif ch in "'\"":
            k = j + 1
            while k < len(cmd) and cmd[k] != ch:
                k += 2 if ch == '"' and cmd[k] == "\\" else 1
            j = k + 1
        elif cmd.startswith("${", j):
            depth, j = depth + 1, j + 2
        elif cmd.startswith("$(", j):
            j = substitution_end(cmd, j + 2)
        else:
            depth -= ch == "}"
            j += 1
    return min(j, len(cmd))


def _braced(cmd: str, i: int, w: _Builder) -> int:
    """A `${ … }` expansion, one piece of the word whatever it holds."""
    j = brace_end(cmd, i)
    w.add(cmd[i:j])
    return j


def _bracketed(cmd: str, i: int, w: _Builder) -> int:
    """A `$[ … ]` arithmetic expansion, one piece of the word whatever it holds."""
    j, depth = i + 2, 1
    while j < len(cmd) and depth:
        depth += (cmd[j] == "[") - (cmd[j] == "]")
        j += 1
    w.add(cmd[i:j])
    return j


def _single(cmd: str, i: int, w: _Builder) -> int:
    """A single-quoted run: every character as it stands."""
    j = cmd.find("'", i + 1)
    j = len(cmd) if j < 0 else j
    w.add(cmd[i + 1:j])
    return j + 1


def _ansi(cmd: str, i: int, w: _Builder) -> int:
    """A `$'…'` run: a backslash escapes the next character, `\\'` included — its escapes kept as written."""
    j = i + 2
    while j < len(cmd) and cmd[j] != "'":
        j += 2 if cmd[j] == "\\" else 1
    w.add(cmd[i + 2:j])
    return j + 1


def _double(cmd: str, i: int, w: _Builder) -> int:
    """A double-quoted run: `\\` escapes only `" \\ $ `` and a newline, substitutions still run."""
    w.add("")
    i += 1
    while i < len(cmd) and cmd[i] != '"':
        if cmd[i] == "\\" and cmd[i + 1:i + 2] in ('"', "\\", "$", "`", "\n"):
            w.add(cmd[i + 1].strip("\n"))
            i += 2
        elif cmd.startswith("$(", i) or cmd[i] == "`":
            i = _substitution(cmd, i, w)
        elif cmd.startswith("${", i):
            i = _braced(cmd, i, w)
        else:
            w.add(cmd[i])
            i += 1
    return i + 1


def _escape(cmd: str, i: int, w: _Builder) -> int:
    """A backslash outside quotes: the next character as it stands; before a newline, a line continued."""
    if cmd[i + 1:i + 2] != "\n":
        w.add(cmd[i + 1:i + 2])
    return i + 2


#: what starts a piece of a word, and who reads it
_READERS = (("$(", _substitution), ("<(", _substitution), (">(", _substitution), ("${", _braced), ("$[", _bracketed), ("`", _substitution), ("$'", _ansi), ("'", _single),
            ('"', _double), ("\\", _escape))


def tokens(cmd: str) -> list:
    """`cmd` as the shell splits it: `Word`s and `Op`s; comments and here-document bodies are not part of it."""
    out, w, heredocs, i = [], _Builder(), [], 0
    while i < len(cmd):
        if cmd[i] in " \t\r":
            out += w.take()
            i += 1
        elif cmd[i] == "#" and not w.started:
            i = cmd.find("\n", i) % (len(cmd) + 1)
        elif reader := next((r for p, r in _READERS if cmd.startswith(p, i)), None):
            i = reader(cmd, i, w)
        elif op := next((o for o in _OPS if cmd.startswith(o, i)), None):
            i = _operator(cmd, i, Op(op), w, out, heredocs)
        else:
            w.add(cmd[i])
            i += 1
    return out + w.take()


def _operator(cmd: str, i: int, op: Op, w: _Builder, out: list, heredocs: list) -> int:
    """The operator `op` at `i` ends the word before it — a number before a redirection is its descriptor, no word —
    and a newline after here-document operators skips their bodies. Returns where reading goes on."""
    if op in _REDIRECTS and "".join(w.buf).isdigit():
        w.__init__()
    out += w.take() + [op]
    if op in _HEREDOCS:
        heredocs.append((len(out), op))                        # its delimiter is the next word
    elif op == "\n" and heredocs:
        delimiters = [(out[k], o) for k, o in heredocs if k < len(out)]
        heredocs.clear()
        return _past_heredocs(cmd, i + 1, delimiters)
    return i + len(op)


def _past_heredocs(cmd: str, i: int, delimiters: list) -> int:
    """Skip each here-document body that starts at `i`, one per (delimiter, operator), each up to its delimiter's own
    line — exactly it after `<<`, after leading tabs only after `<<-`: an indented `  END` ends no `<<` body."""
    for d, op in delimiters:
        while i < len(cmd):
            j = cmd.find("\n", i)
            line, i = (cmd[i:], len(cmd)) if j < 0 else (cmd[i:j], j + 1)
            if (line.rstrip("\r").lstrip("\t") if op == "<<-" else line.rstrip("\r")) == d:
                break
    return i


def commands(cmd: str) -> list[tuple]:
    """The simple commands of `cmd` in order, with the groups around them:
    ("cmd", words, own_subshell) — redirections dropped; own_subshell where a pipe or `&` runs it apart;
    ("open", own_subshell) … ("close",) — a `( … )`, always its own subshell, or a `{ … }`, its own only when
    piped or put in the background; a close ends the group opened last."""
    return _Commands(tokens(cmd)).read()


class _Commands:
    """One pass over the tokens, keeping the command being read and the operator before it."""

    def __init__(self, toks: list):
        self.toks, self.out, self.words, self.prev, self.k = toks, [], [], "", 0

    def read(self) -> list[tuple]:
        """The commands and groups, as `commands` returns them."""
        while self.k < len(self.toks):
            t = self.toks[self.k]
            self.k += 1
            (self._op if isinstance(t, Op) else self._word)(t)
        self._flush("")
        return self.out

    def _op(self, t: Op) -> None:
        if t in _REDIRECTS:                                    # …and its target
            self.k += self.k < len(self.toks) and not isinstance(self.toks[self.k], Op)
            return
        self._flush(self._next_op(self.k) if t == ")" else t)
        if t in ("(", ")"):
            self.out.append(("open", True) if t == "(" else ("close",))
        self.prev = t

    def _word(self, t: Word) -> None:
        if t == "{" and self.words[:1] == ["function"]:      # `function f {`: its header is no command
            self.words = []
        if self.words or t not in _RESERVED:
            self.words.append(t)
        elif t == "{":
            alone = self.prev in _PIPES or self._next_op(_group_end(self.toks, self.k)) in _BACKGROUND
            self.out.append(("open", alone))
        elif t == "}":
            self.out.append(("close",))

    def _flush(self, nxt: str) -> None:
        if self.words:
            self.out.append(("cmd", self.words, self.prev in _PIPES or nxt in _BACKGROUND))
        self.words = []

    def _next_op(self, j: int) -> str:
        """The first separator from `j` on, redirections and their targets passed over."""
        while j < len(self.toks):
            t = self.toks[j]
            if isinstance(t, Op) and t not in _REDIRECTS:
                return t
            j += 2 if isinstance(t, Op) else 1
        return ""


def _group_end(toks: list, k: int) -> int:
    """The index just past the `}` closing the brace group whose body starts at `k`."""
    depth = 1
    while k < len(toks) and depth:
        t = toks[k]
        k += 1
        if not isinstance(t, Op) and (k < 2 or isinstance(toks[k - 2], Op)) and t in ("{", "}"):
            depth += 1 if t == "{" else -1
    return k

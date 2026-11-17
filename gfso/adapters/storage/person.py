"""The person's name of before 0.4.0, `agent`, written `user` once in a graph that holds it, so one spelling names one
person (docs/notes/PERSON_NAME.md, the author's (M)). Exact party values only, at the fields a scan of real databases
found them in; the rewrite records itself (from, to, when, rows per field) and runs once."""
from __future__ import annotations

import json
from datetime import datetime

from gfso.config import AGENT, PERSON

OLD = AGENT
#: the setting a rewrite records itself in, which also says it ran
MARK = "person_renamed"
#: the columns whose whole value is a party, with the rows where it is one
_WHOLE = (("audit_log", "source", "1"), ("tasks", "assignee", "1"), ("settings", "value", "key LIKE 'issuer:%'"))
#: the JSON columns a party is written in, under one of `_KEYS` at any depth
_JSON = (("settings", "key", "value"), ("critiques", "task_id", "critique_json"),
         ("exec_verdicts", "task_id", "verdict_json"))
_KEYS = frozenset({"by", "actor", "validator"})


class TwoParties(RuntimeError):
    """`user` already names a party where `agent` is to be written `user`: rewriting would merge two parties."""


def merge_refusal(where: str) -> str:
    """The refusal of a rewrite that would merge the person with a party `user` standing `where`, and its lift."""
    return (f"gfso cannot write the person `{OLD}` as `{PERSON}`: {where} already names a party `{PERSON}`, and "
            f"the rewrite would make it and the person one. Rename or remove that `{PERSON}` (unregister the role, "
            f"revoke the token), then open again.")


def record(counts: dict) -> str:
    """What a rewrite records: the mapping (the old name a key, so no party value says `agent` after it), when, rows
    per field."""
    return json.dumps({"rewrote": {OLD: PERSON}, "at": datetime.now().isoformat(timespec="seconds"), "rows": counts})


def _walk(v, to, path, counts, old):
    """`v` with every `old` under a party key written `to` (`to` None: unchanged), each counted at its path."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in _KEYS and x == old:
                counts[f"{path}.{k}"] = counts.get(f"{path}.{k}", 0) + 1
                out[k] = to if to is not None else x
            else:
                out[k] = _walk(x, to, f"{path}.*" if path.endswith("disputes") else f"{path}.{k}", counts, old)
        return out
    if isinstance(v, list):
        return [_walk(x, to, f"{path}[]", counts, old) for x in v]
    return v


def _tables(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _found(conn, name: str, to=None) -> tuple[dict, list]:
    """Where `name` stands as a party: rows per field, and the JSON rewrites that would write it `to`."""
    counts, writes, have = {}, [], _tables(conn)
    for table, col, where in _WHOLE:
        if table in have and (n := conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ? AND {where}",
                                                (name,)).fetchone()[0]):
            counts[f"{table}.{col}"] = n
    for table, key, col in _JSON:
        if table not in have:
            continue
        for k, raw in conn.execute(f"SELECT {key}, {col} FROM {table} WHERE {col} LIKE ?", (f'%"{name}"%',)).fetchall():
            try:
                v = json.loads(raw)
            except (TypeError, ValueError):
                continue
            seen = {}
            new = _walk(v, to, f"{table}.{col}", seen, name)
            for p, n in seen.items():
                counts[p] = counts.get(p, 0) + n
            if seen:
                writes.append((table, key, col, k, json.dumps(new, ensure_ascii=False)))
    return counts, writes


def pending(conn) -> dict:
    """What a rewrite of this graph would write, rows per field; empty where it ran or has nothing to do."""
    if "settings" in _tables(conn) and conn.execute("SELECT 1 FROM settings WHERE key = ?", (MARK,)).fetchone():
        return {}
    return _found(conn, OLD)[0]


def refusal(conn, where: str = "this graph") -> str | None:
    """Why this graph's rewrite is refused, or None: it holds a party `user` beside the `agent` it would rewrite."""
    held = pending(conn) and _found(conn, PERSON)[0]
    return merge_refusal(f"{where} ({', '.join(sorted(held))})") if held else None


def rename(conn) -> dict:
    """`agent` written `user` in this graph's party fields, once, the rewrite recorded in its settings: rows per field
    written, empty where nothing was. Refused (`TwoParties`) where the graph already holds a party `user`."""
    # …READ UNDER THE WRITE LOCK: two first opens reading before either wrote lost the other's write (a mode set between
    # one's read and its whole-row write-back came back as before — critic over 2b8e97f, reproduced on two connections)
    if not pending(conn):
        return {}                       # nothing to write: no lock taken, so a graph read-only to this process opens
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        if (why := refusal(conn)):
            raise TwoParties(why)
        if not pending(conn):
            conn.rollback()
            return {}
        counts, writes = _found(conn, OLD, PERSON)
        for table, col, where in _WHOLE:
            conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ? AND {where}", (PERSON, OLD))
        for table, key, col, k, new in writes:
            conn.execute(f"UPDATE {table} SET {col} = ? WHERE {key} = ?", (new, k))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (MARK, record(counts)))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return counts

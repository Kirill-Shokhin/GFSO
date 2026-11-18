"""An executor report that did not parse (stranger run s17c, 00:47) cost a retried session — and its record could not
say why. The line kept the text's last 400 characters, quoted by `repr`, which wrote the apostrophe of «issuer's» as
`\\'`; read as the model's invalid escape, it was not one: the 400 characters end a valid report, and the defect lay in
the text before them, which nothing kept. So the line now names what the parser met, and where (`why_unread`), in the
candidate the parser tried, and quotes the tail as JSON does. An escape JSON lacks is kept as written (s18b2)."""
from __future__ import annotations

import json
import random

import gfso.delegate as D
import gfso.tools_llm as TL
from gfso.adapters.llm.structured import kept_escapes, parse_structured, why_unread
from gfso.core.types import TaskId
from gfso.sessions import EXECUTOR_SCHEMA
from tests.test_a_holder_dispatches_its_work import _LLM, _project

#: the last 400 characters of the unread report, as s17c's pipeline log kept them (row 31)
S17C_TAIL = (" what correct work prints for that DIR, because the planted os.py and argparse.py are regular .py files "
             "directly in DIR and are counted. This machine prints `2 py ⏎ 1 a ⏎ rc=0`, rc=0. The substance "
             "of that criterion holds (no planted module is imported, the count is correct, rc=0). The pin is the only "
             "mismatch, and it is left for the issuer's contract.\", \"self_validation\": \"PASS\", \"build\": \"\"}\n```")
HEAD = '```json\n{"status": "delivered", "summary": "The pinned check expects `1 a`, which is not'


class _Says(_LLM):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        super().run_agent(system, user, allowed_tools, cwd, timeout)
        return self.text


def _run(tmp_path, text):
    e, agents = _project(tmp_path)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "user").get("accepted")
    out = D.run_executor(e, TaskId("root"), "exec-1", agents, _llm=_Says(text))
    return out, [r["message"] for r in e.pipeline_log() if "DID NOT PARSE" in str(r.get("message"))]


def test_the_kept_tail_ends_a_valid_report():
    assert len(S17C_TAIL) == 400
    assert parse_structured(HEAD + S17C_TAIL, EXECUTOR_SCHEMA)["self_validation"] == "PASS"
    assert why_unread(HEAD + S17C_TAIL, EXECUTOR_SCHEMA) == ""


def test_an_escape_json_lacks_is_kept_as_written():
    """s18b2's report quoted `\\xNN` in prose and was unread. An escape JSON lacks is kept as its two characters: the
    under-escaped shell idiom `'it'\\''s'` stays the command it was (read as `'` it broke), and a quote left bare stays
    unread. CONTROL: `_loads` without the fallback — the first three go red."""
    for summary, said in (("escaped (\\\\ and \\xNN) per line", "escaped (\\ and \\xNN) per line"),
                          ("echo \\$HOME", "echo \\$HOME"),
                          ("printf 'it'\\''s'", "printf 'it'\\''s'")):
        raw = "{\"status\": \"delivered\", \"summary\": \"" + summary + "\"}"
        assert parse_structured(raw, EXECUTOR_SCHEMA)["summary"] == said, raw
    assert parse_structured("{\"status\": \"delivered\", \"summary\": \"ran (cd \"$T\" && x)\"}", EXECUTOR_SCHEMA) is None


def test_the_reading_changes_no_valid_document():
    """Every backslash of a valid document starts an escape JSON has, so the fallback is never its reading."""
    rnd = random.Random(7)
    alphabet = "ab\\\"'/xu\n\t\x01é$ "
    for _ in range(3000):
        doc = json.dumps({"s": "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 24)))})
        assert kept_escapes(doc) == doc, doc


def test_the_record_names_what_the_parser_met_and_quotes_the_tail_as_json(tmp_path):
    """CONTROL: `_unread` returning `unparsed` alone — the line names no error and this goes red."""
    broken = HEAD + ' ran (cd "$T" && python exts.py) and' + S17C_TAIL
    out, said = _run(tmp_path, broken)
    assert out["status"] == "unparsed" and said, out
    assert "The JSON is invalid" in said[-1] and " at line 1 column " in said[-1], said
    assert "its text ends: " + json.dumps(broken[-400:], ensure_ascii=False) in said[-1], said
    assert "issuer\\'s" not in said[-1], "an apostrophe quoted as the escape a model writes misleads the next reader"


def test_the_error_is_located_in_the_object_after_the_prose():
    """CONTROL: `why_unread` reading the whole text — the error is met at the prose's first letter and this goes red."""
    why = why_unread('I checked it all.\n{"status": "delivered", "summary": "ran "x" twice"}', EXECUTOR_SCHEMA)
    assert why.startswith("The JSON is invalid: Expecting ',' delimiter at line 1 column 42"), why
    assert "I checked" not in why, why


BS = chr(92)


def test_a_u_with_no_four_hex_digits_is_read_as_written_and_a_real_one_decodes():
    """A backslash-u before no four hex digits (a Windows path's user directory) is no escape JSON has: it made the
    report unread (11-17)."""
    raw = "{\"a\": \"C:" + BS + "user and " + BS + "u12 and " + BS + "u00e9\"}"
    assert parse_structured(raw, {"type": "object", "required": ["a"]}) == {"a": "C:" + BS + "user and " + BS + "u12 and " + chr(0xE9)}


def test_an_error_after_the_escape_repair_is_located_where_the_model_wrote_it():
    """The repair adds a backslash per unknown escape, and the parser's column pointed into the repaired text."""
    raw = "{\"a\": \"" + BS + "x " + BS + "q\", \"b\": 1,, \"c\": 2}"
    why = why_unread(raw, {})
    assert f"at line 1 column {raw.index(',,') + 2}," in why, why

"""Provider-agnostic structured-output machinery — OURS, not the transport's.

No provider is trusted to enforce a schema: the instruction appends the JSON schema to the user
content, and `parse` validates the reply (fenced block preferred, strict=False tolerates literal
control chars inside strings — the dominant LLM-JSON defect). Every LLMProviderPort adapter
(headless Anthropic, generic OpenAI-compatible) composes these same three pieces, which is what
makes the one-shot layer provider-portable by construction.
"""
from __future__ import annotations

import json
import re

# Every fenced block, each matched up to its OWN closing fence. A greedy single match spanned from
# the first fence to the last, so a reply that emitted more than one block (observed live: models
# echo the schema, then answer) parsed as nothing — and a checker with no verdict is a checker that
# silently fails closed. Blocks are tried in order; the first that satisfies the schema wins.
FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

RETRY_SUFFIX = ("\n\nYour previous output could not be parsed against the schema "
                "(missing required keys or invalid JSON). Re-emit the ONE fenced json "
                "object, complete and valid.")

#: The retry when the first answer was CUT at the output limit (`stop_reason == "max_tokens"`): asked again for the
#: whole object, a model meets the same limit again — the retry used to repeat the full request unchanged.
RETRY_SHORTER = ("\n\nYour previous output was cut off at the output-length limit before the json object closed. "
                 "Re-emit the ONE fenced json object, complete and valid, and SHORTER: terse descriptions, no "
                 "restated goal text, nothing repeated between fields — every required key and every item kept.")


def schema_instruction(schema: dict) -> str:
    """The sentence appended to a prompt that makes the model answer in a schema we can parse.

    One owner, because every verb that reads structure appends it: two spellings would be two
    contracts with the model, and the parse failure they cause is charged to the caller's round."""
    return (
        "\n\n# OUTPUT FORMAT (mechanical requirement, not content guidance)\n"
        "Return your answer as ONE fenced ```json code block containing a single object that conforms "
        "to this JSON schema (every `required` key present, exact key names):\n"
        f"```json\n{json.dumps(schema)}\n```"
    )


def _bare_objects(text: str) -> list:
    """Every top-level `{...}` in the text, brace-balanced and string-aware, outermost first.

    Not a JSON parser and not a repairer: it only decides where an object STARTS and ENDS so the
    real parser can be handed a clean candidate. A quoted brace inside a probe command
    (`grep -c "^}" file`) is exactly why this counts strings and escapes rather than regexing.
    """
    out, i, n = [], 0, len(text)
    while True:
        start = text.find("{", i)
        if start < 0:
            return out
        depth, j, in_str, esc = 0, start, False, False
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[start:j + 1])
                    break
            j += 1
        if depth != 0:                     # unterminated: nothing further can balance either
            return out
        i = j + 1


def holds_an_object(text: str) -> bool:
    """Does the text carry a JSON object — the shape every structured answer of this system takes?"""
    for cand in _bare_objects(text or ""):
        try:
            if isinstance(json.loads(cand), dict):
                return True
        except ValueError:
            continue
    return False


def parse_structured(text: str, schema: dict):
    """The FIRST candidate in the reply that is a dict carrying the schema's `required` keys, or None.

    Candidates: each fenced block in order, then the bare text. Trying them all is what makes a
    schema-echo (or any preamble block) harmless — it parses as JSON but lacks the required keys, so
    it is skipped rather than swallowing the real answer."""
    # …AND THE FIRST BALANCED OBJECT IN THE BARE TEXT, which is the shape that actually cost
    # money. Fenced blocks were handled and so was a bare payload; what was not is a report that
    # writes a sentence first and then emits its JSON WITHOUT a fence — `json.loads` sees the
    # prose and fails, the engine records no verdict, and the node waits for a validation that
    # was sitting in the reply. Measured on two honest runs the same afternoon (2026-09-05):
    # after the coverage-discipline refusals fell to zero, THIS became the dominant reason a
    # paid validation round decided nothing — two of the two runs hit it, one twice.
    # Balanced braces, string-aware: a substring found by regex would split on the first `}`
    # inside a quoted probe command. Malformed JSON still fails, save the closers `_restored` identifies.
    candidates = ([m.group(1) for m in FENCED.finditer(text or "")]
                  + [(text or "").strip()] + _bare_objects(text or ""))
    for read in (_parsed, lambda raw: _restored(raw, schema)):   # a block as written first; a repaired one only failing all
        for raw in candidates:
            obj = read(raw)
            if isinstance(obj, dict) and _answers(obj, schema):
                return obj
    return None


def _parsed(raw: str):
    try:
        return json.loads(raw, strict=False)
    except ValueError:
        return None


def _restored(raw: str, schema: dict):
    """`raw` with the closers put back that a sunk top-level field names, parsed — else None.

    Haiku writes the last entry's probes, closes them, and goes straight on to the report's own `seams` and
    `failed_criteria` — the entry and the `per_criterion` list left open — in about one long batch report of five (23 of
    the 25 unreadable batch reports kept from two rows), and the batch was run again whole: two minutes on the root's
    critical path (GB_coreutils_tmsy21348). Read only where that is what the text says: inside an entry of a list, a
    field the schema keeps only at the top, followed at that level by such fields alone, none already written at the
    top — then the entry and the list closed before the comma that precedes it, and nothing else moves. A report cut
    short, or broken any other way, stays unread (critic over the first form: a cut reply had its fields lifted and a
    top-level word overwritten); what parses is still held to the schema by the caller."""
    top, keys = _top_only_keys(schema), _keys(raw)
    sunk = next((k for k in keys if len(k[1]) > 1 and k[2] in top), None)
    if sunk is None or sunk[3] is None or sunk[1][1] != "[":
        return None
    # …in a list the schema REQUIRES and whose entries declare their fields: elsewhere an undeclared field is no evidence
    # of where it belongs (critic: a cut reshape's `children` and a patch's subtasks had their fields lifted)
    held = next((k[2] for k in reversed(keys) if k[0] < sunk[0] and len(k[1]) == 1), None)
    if held not in (schema.get("required") or ()) or not ((schema["properties"].get(held) or {}).get("items") or {}).get(
            "properties"):
        return None
    after = [k[2] for k in keys if k[0] >= sunk[0] and k[1] == sunk[1]]
    if not set(after) <= top or len(after) != len(set(after)) or set(after) & {k[2] for k in keys if len(k[1]) == 1}:
        return None
    closers = "".join("]" if c == "[" else "}" for c in reversed(sunk[1][1:]))
    return _parsed(raw[:sunk[3]] + closers + raw[sunk[3]:])


def _top_only_keys(schema: dict) -> set:
    """The schema's top-level fields that no nested object declares."""
    props = schema.get("properties") or {}
    return set(props).difference(*(_field_names(v) for v in props.values()))


def _field_names(s: dict) -> set:
    """Every field name declared anywhere under schema `s`."""
    props = s.get("properties") or {}
    return set(props).union(*(_field_names(v) for v in [*props.values(), *([s["items"]] if s.get("items") else [])]))


def _keys(raw: str) -> list:
    """[(where, the containers open around it, key, the comma before it)] for every object key outside strings."""
    out, stack, in_str, esc, comma, start = [], [], False, False, None, 0
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                if raw[i + 1:i + 40].lstrip().startswith(":"):
                    out.append((start, "".join(stack), raw[start + 1:i], comma))
        elif ch == '"':
            in_str, start = True, i
        elif ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            stack and stack.pop()
        elif ch == ",":
            comma = i
    return out


def _answers(obj: dict, schema: dict) -> bool:
    """Is this object the reply, or something else that also happens to be JSON?

    The required keys are the discriminator wherever there are any. WHERE THERE ARE NONE they say
    nothing — `all(... for k in [])` is true of every object — and the docstring's protection ("an
    echo parses as JSON but lacks the required keys, so it is skipped") is then vacuous. That is not
    a corner: the two PATCH schemas make every field optional on purpose, because a corrective round
    re-emits only what it changes, and those are exactly the schemas the refinement rounds use.
    Probed 2026-09-07: against the fold schema, a schema echo placed before the real answer WINS,
    and so does any unrelated object (`{"note": "nothing"}`); against a schema with required keys
    the real answer wins — the control that pins the mechanism to the empty list.

    With nothing required, what still separates a reply from a bystander is the schema's own
    VOCABULARY: a reply speaks the declared fields, an echo speaks `type` and `properties`. An empty
    object stays a reply, because "nothing to change" is the one honest answer a patch can give and
    refusing it would turn a converged round into a failed call.
    """
    required = schema.get("required") or ()
    if required:
        return all(k in obj for k in required)
    return not obj or bool(set(obj) & set(schema.get("properties") or ()))

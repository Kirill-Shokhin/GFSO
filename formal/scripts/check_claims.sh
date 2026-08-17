#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# check_claims.sh — the THIRD drift surface: COUNTS and RETIRED FORMULATIONS.
#
# `check_refs.sh` guards §-pointers. `check_naming.sh` guards retired NAMES. Neither can see a
# mirror that states a different NUMBER for an object the canon counts, or that repeats a
# FORMULATION the canon has since replaced — because both compare addresses, never assertions.
# That is exactly the hole through which four canon addenda propagated only into the artifacts they
# happened to name downstream, while the same claim went stale everywhere else.
#
# Two halves, both fail-closed:
#   (1) COUNTS — read off the canon at every run (never transcribed here), then every mirror is
#       scanned for a statement of a DIFFERENT number for the same object. If the canon's own
#       sentence stops matching, the derivation fails loudly rather than silently guarding nothing.
#   (2) RETIRED FORMULATIONS — a small list of wordings the canon replaced. Each entry carries the
#       canon ANCHOR that superseded it; if the anchor is gone from the canon, the entry is stale
#       and the guard fails, so the list cannot rot into a lie. This half scans the CANON TOO, not
#       only the mirrors: a canon that carries both the anchor and the wording it retired is
#       self-contradictory, and scanning mirrors alone let exactly that survive twice (§14 preamble,
#       §26.9(b)). The canon's **Changelog** is excluded from this scan and only from it — a
#       changelog legitimately names the formulation it replaced, that being what provenance IS.
#       The COUNT half never scans the canon: the canon is where the counts are read FROM.
#
# Not in scope, each for the same reason as the sibling guards: `docs/architecture.md` (mirrors the
# CODE, declares its lag in a banner), `docs/EVIDENCE_LOG.md`
# (dated records — a superseded count inside a dated merge entry is provenance, not drift),
# `docs/e1/`, `experiments/`, `gfso/`, `tests/`, `examples/`.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

CANON=../docs/applied_gfso_v4_en.md

FILES=(../README.md ../docs/CORE.md ../docs/method_gfso.md ../docs/gfso_dependency_map.md
       ../docs/applied_gfso_vision.md ../docs/falsifiability.md README.md
       GFSO/Standards.lean GFSO/FailureModes.lean GFSO/Protocol.lean GFSO/Fsm.lean
       GFSO/FsmCanon.lean GFSO/Postulates.lean GFSO.lean check_axioms.lean)

MISSING=0
for f in "${FILES[@]}"; do
  [[ -e "$f" ]] || { echo "WATCHED FILE MISSING: ${f#../} — update FILES deliberately" >&2; MISSING=1; }
done
[[ -e "$CANON" ]] || { echo "CANON MISSING: $CANON" >&2; MISSING=1; }
[[ $MISSING -eq 0 ]] || exit 1

python - "$CANON" "${FILES[@]}" <<'PY'
import io, re, sys

canon_path, files = sys.argv[1], sys.argv[2:]
canon = io.open(canon_path, encoding='utf-8').read()
fail = []

# ---------------------------------------------------------------------------
# (1) DERIVE the counts from the canon. A derivation that stops matching is a FAILURE, never a
#     silent skip: a guard that cannot read its own contract is guarding nothing.
# ---------------------------------------------------------------------------
def derive(name, pattern, transform=lambda m: m.group(1)):
    m = re.search(pattern, canon)
    if not m:
        fail.append(f"DERIVE FAIL [{name}]: the canon sentence this count is read from no longer "
                    f"matches /{pattern}/ — fix the canon or teach this guard, do not let it pass")
        return None
    return transform(m)

# FM-1 sub-taxonomy: the letters actually present as rows of the §12.2 table.
subtypes = sorted(set(re.findall(r'\|\s*FM-1\.([a-z])\s', canon)))
if not subtypes:
    fail.append("DERIVE FAIL [subtypes]: no `| FM-1.x` table rows found in the canon")
last_sub = subtypes[-1] if subtypes else None

checks   = derive('checks',  r'counts \*\*(\w+)\*\* CHECKs')
axioms   = derive('axioms',  r'yields \*\*exactly (\w+) covering axioms\*\*')
classes  = derive('classes', r'the twelve states carry (\w+) behaviour classes')

# The §14.2 signal defect split, read off the canon's own count line. It lives in five carriers
# (canon §14.2 and Ch. 27, Protocol.lean's header/`defect_distribution`, formal/README, the
# dependency map), which is exactly the drift surface this guard exists for.
split = derive('signal split',
               r'FM \((\d+):[^)]*\), FSM deadlock \((\d+):[^)]*\), IC \((\d+):[^)]*\), '
               r'operation \((\d+):',
               lambda m: '/'.join(m.groups()))

WORD = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,
        'ten':10,'eleven':11,'twelve':12}
def num(w):
    return WORD.get(w.lower()) if w and not w.isdigit() else (int(w) if w else None)

n_checks, n_axioms, n_classes = num(checks), num(axioms), num(classes)

# ---------------------------------------------------------------------------
# (2) The contradiction scan. Each rule: a regex that MATCHES a statement, and a predicate that
#     decides whether the matched statement contradicts the canon-derived value.
# ---------------------------------------------------------------------------
def letters_to(ch):
    return ''.join(chr(c) for c in range(ord('a'), ord(ch) + 1))

RULES = []

if last_sub:
    span = f"a–{last_sub}"
    RULES.append((
        'FM-1 sub-taxonomy span',
        re.compile(r'sub-?(?:types?|taxonomy)[^.\n]{0,40}?a[–-]([a-z])'),
        lambda m: m.group(1) != last_sub,
        f"the canon's table carries FM-1.a–{last_sub}",
    ))
    RULES.append((
        'FM-1 sub-taxonomy enumeration',
        re.compile(r'sub:\s*((?:[a-z]\s+){2,}[a-z])'),
        lambda m: ''.join(m.group(1).split()) != letters_to(last_sub),
        f"the canon's table carries {' '.join(letters_to(last_sub))}",
    ))

if n_checks:
    RULES.append((
        'CHECK battery count',
        re.compile(r'CHECK-1\s*(?:\.\.|–|-|to )\s*8\b'),
        lambda m: True,
        f"the canon's battery counts {n_checks} CHECKs (1, 1b, 2–8) — 'CHECK-1..8' states {n_checks-1}",
    ))

if n_axioms:
    RULES.append((
        'covering-axiom count',
        re.compile(r'(\w+)\s+covering axioms\b'),
        # "the OTHER two covering axioms" is a partition of the same three, not a count of them;
        # and a line that also states the true total is self-correcting.
        lambda m: num(m.group(1)) not in (None, n_axioms)
                  and not m.string[:m.start()].rstrip().endswith('other')
                  and str(n_axioms) not in m.string and 'THREE' not in m.string,
        f"the canon's closure yields exactly {n_axioms} covering axioms",
    ))

if split:
    RULES.append((
        'signal defect split',
        re.compile(r'\b(\d)\s*/\s*(\d)\s*/\s*(\d)\s*/\s*(\d)\b'),
        # `FM-1/2/4/5/7` and `Prop 3/4/6/7` are slash-joined LABEL lists, not a split — exclude a
        # match whose prefix is a result label (possibly already part-consumed by the slash run).
        lambda m: '/'.join(m.groups()) != split and not re.search(
            r'(?:FM|Prop|Thm|Cor|Lemma|Inv|STD|CHECK|Link|Ch\.|Chapter|§)[-\s.]*[\d/]*$',
            m.string[:m.start()]),
        f"the canon's §14.2 count line states the split {split}",   # spaced forms included
    ))

if n_classes:
    RULES.append((
        'behaviour-class count',
        re.compile(r'(\w+)\s+behaviour(?:al)? classes\b'),
        lambda m: num(m.group(1)) not in (None, n_classes),
        f"the canon measures {n_classes} behaviour classes over the twelve states",
    ))

# ---------------------------------------------------------------------------
# (3) RETIRED FORMULATIONS. Each carries the canon anchor that superseded it; a vanished anchor
#     makes the entry itself a failure, so this list cannot quietly become false.
# ---------------------------------------------------------------------------
RETIRED = [
    (r'guaranteed axiomatic|closed axiomatic',
     "A1 fixes FM-3's verdict FORM, not its truth; no structural CHECK guards it",
     "no structural CHECK guards FM-3"),
    (r'each (?:of the 12 )?signals? answers? (?:a specific )?(?:an )?FM\b',
     "4 of the 12 signals answer an FM; 4 close FSM deadlocks, 3 close IC seams, 1 initiates",
     "FM (4: CHALLENGE, BLOCK, FAIL, CANCEL)"),
    # The corrective sentence names both terms; only the ASSERTION that ACCEPT_CHALLENGE *is* FM-5
    # is retired, so the rule excludes any line that negates it ("is IC, not FM-5" / "not FM-5").
    (r'ACCEPT_CHALLENGE(?![^.\n]{0,80}(?:not FM-5|is IC))[^.\n]{0,60}(?<!not )FM-5',
     "ACCEPT_CHALLENGE is IC, not FM-5: re-ASSIGN carries the spec update (Inv-1, §14.3); "
     "what only it carries is the dispute's positive closure",
     "IC (3: ACCEPT, REJECT_CHALLENGE, ACCEPT_CHALLENGE)"),
    (r'no adoption threshold',
     "Cor 5 is an INFORMATION claim; the net-payoff threshold is Prop 4's",
     "There is no *information* threshold"),
    (r'FORM is exactly \{',
     "the FORM interior is the LOAD-BEARING three, not an exhaustive partition",
     "the **load-bearing** interior of well-posedness over the map is {connectivity/Dep"),
    (r'Timeouts on every state\b',
     "Inv-5 exempts IDLE by name",
     "every non-terminal state **except IDLE**"),
]

for pat, why, anchor in RETIRED:
    if anchor not in canon:
        fail.append(f"STALE GUARD ENTRY: the canon anchor {anchor!r} is gone, so the retired-formulation "
                    f"rule /{pat}/ no longer has a superseding site — re-derive or drop the entry")

# ---------------------------------------------------------------------------
# (4) Scan.
# ---------------------------------------------------------------------------
# The canon body = everything before the Changelog (provenance legitimately names retired wordings).
_cut = canon.find(chr(10) + '## Changelog')
if _cut == -1:
    fail.append("DERIVE FAIL [canon body]: no '## Changelog' heading — the retired-formulation scan "
                "cannot separate the body from its provenance; teach this guard, do not let it pass")
    canon_body = ''
else:
    canon_body = canon[:_cut]

for i, line in enumerate(canon_body.split(chr(10)), 1):
    for pat, why, anchor in RETIRED:
        m = re.search(pat, line)
        if m:
            fail.append(f"RETIRED FORMULATION IN THE CANON: {canon_path.replace('../','')}:{i} "
                        f"carries {m.group(0)!r} — {why}")

for path in files:
    try:
        text = io.open(path, encoding='utf-8').read()
    except OSError as e:
        fail.append(f"UNREADABLE WATCHED FILE: {path} ({e})")
        continue
    lines = text.split('\n')
    for i, line in enumerate(lines, 1):
        for name, rx, contradicts, expected in RULES:
            for m in rx.finditer(line):
                if contradicts(m):
                    fail.append(f"COUNT DRIFT [{name}]: {path.replace('../','')}:{i} says "
                                f"{m.group(0)!r} — {expected}")
        for pat, why, anchor in RETIRED:
            m = re.search(pat, line)
            if m:
                fail.append(f"RETIRED FORMULATION: {path.replace('../','')}:{i} carries "
                            f"{m.group(0)!r} — {why}")

if fail:
    for f in fail:
        sys.stderr.write(f + "\n")
    sys.stderr.write(f"\nCLAIM DRIFT: {len(fail)} finding(s).\n")
    sys.exit(1)

print(f"ok: counts stated in the mirrors agree with the canon "
      f"(FM-1.a–{last_sub} · {n_checks} CHECKs · {n_axioms} covering axioms · {n_classes} behaviour classes),")
print("    and no formulation the canon replaced survives in a live mirror OR in the canon body")
print("    — every count is read off the canon at run time, and every retired-formulation rule")
print("      carries the canon anchor that superseded it (a vanished anchor fails the guard).")
PY

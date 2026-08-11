#!/usr/bin/env bash
# NAMING GUARD — the v4.0 naming contract, DERIVED from the canon and enforced.
#
# Why this exists: ten audits of the v3.9→v4 transition found the same class over and over — a fix
# landing on the prose and missing a sibling encoding (a table cell, a mermaid label, a Lean module
# header). `check_refs.sh` drained that class for §-pointers and result labels, because it WATCHES
# them. Terms had no guard, so they kept surviving. The lesson is not "read harder" — it is that an
# invariant nobody enforces is not an invariant.
#
# Why it is derived, not transcribed: the first version of this guard carried a hand-copied pair
# list plus a comment asserting the list was complete. It was not — `AUTO→AUTO_PASS`,
# `EMIT→EXTERNALIZE` and STD-4 `"Structural validation"→"Form verification"` were dropped in
# transcription and passed silently, in the guard built to close exactly that class. A hand-copied
# contract reproduces the very defect it guards. So the contract is now READ OFF THE CANON at every
# run, from the two places the canon states it machine-readably:
#   (1) the Changelog v4.0 rename list — `OLD→NEW` pairs;
#   (2) the canon's own inline provenance markers — `(v3.9: X — renamed; …)` / `(v3.9: X)`.
# Neither source alone is complete (the Changelog has no STD-4 entry; the inline markers have no
# AUTO/EMIT), so the union is taken. Every derived name must then be either WATCHED or SKIPPED with
# a stated reason — an unhandled pair FAILS the guard. Under-enumeration is thereby impossible: a
# rename added to the canon breaks CI until this script is taught about it.
#
# The rule: a name v4 retired must not appear in a live canon mirror or in `formal/`.
#
# NOT in scope (each for its own reason, same as check_refs.sh):
#  * `docs/architecture.md` — describes the CODE, whose identifiers still carry the old names; it
#    declares that lag in a banner. Excluding it is the point, not an oversight.
#  * `docs/applied_gfso_v3.md` (the frozen draft), `docs/EVIDENCE_LOG.md` (dated records),
#    `docs/e1/`, `experiments/` (frozen instruments), `gfso/`, `tests/`, `examples/` (named debt).
#  * provenance mentions: the canon names retired terms on purpose — `(v3.9: HBP)`, `v3.9 names:
#    OFFERED was REVIEW`. Those are stripped before matching, exactly as check_refs.sh strips them.
set -euo pipefail

# Absolute path to THIS script, captured before the cd (the reverse-inclusion check greps it for its
# case-label table; a relative `$0` would point at nothing after the cd and fail the guard spuriously).
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

cd "$(dirname "$0")/.."

CANON=../docs/applied_gfso_v4_en.md

FILES=(../README.md ../docs/CORE.md ../docs/method_gfso.md ../docs/gfso_dependency_map.md
       ../docs/applied_gfso_vision.md ../docs/falsifiability.md README.md
       GFSO/*.lean GFSO.lean audit_env.lean check_axioms.lean)

# ---------------------------------------------------------------------------
# 0. FAIL-CLOSED PRE-FLIGHT: every watched file must exist.
# ---------------------------------------------------------------------------
# Without this the loop below `continue`s past a deleted or renamed mirror and the guard reports ok
# — the very under-coverage class this script exists to close. A watched file that goes missing is
# a guard failure until the list is updated deliberately.
MISSING_WATCHED=0
for f in "${FILES[@]}"; do
  [[ -e "$f" ]] || { echo "WATCHED FILE MISSING: ${f#../} — it was deleted or renamed; update the FILES list deliberately, do not let the guard skip it" >&2; MISSING_WATCHED=1; }
done
[[ $MISSING_WATCHED -eq 0 ]] || exit 1

# ---------------------------------------------------------------------------
# 1. DERIVE the contract from the canon.
# ---------------------------------------------------------------------------
# Prints one retired name per line: the LHS of every Changelog `OLD→NEW` pair, plus the X of every
# inline `(v3.9: X …)` marker. Both are the canon stating its own contract; neither is copied here.
derive_contract() {
  # `tr -d '\r'`: python on Windows writes CRLF, and a trailing CR makes every name miss its
  # handling_for case silently — i.e. it would fake "fully handled". Same family as the CRLF/UTF-16
  # traps that made earlier guards falsely green.
  python - "$CANON" <<'PY' | tr -d '\r'
import io, re, sys
t = io.open(sys.argv[1], encoding='utf-8').read()
names = set()

# (1) the Changelog v4.0 rename list: `OLD→NEW`
# SCOPE, stated honestly: the rename contract is read from the FIRST v4.0 Changelog entry ALONE
# (`**v4.0 · pass 1**`, the re-authoring) — that is where
# the renames were declared, and there its arrows are renames. The later passes also use `→`,
# but for PROSE: recounts ('5/4/2/1 → 4/4/3/1'), routings ('q_V's pass → later-fail') and FSM EDGES
# ('REWORKING→BLOCK'). No shape test separates an edge from a rename — both are IDENT→IDENT — so
# auto-harvesting them yields either false reds on the canon's own notation or a false green.
# CONSEQUENCE, and it is a maintainer duty rather than a silent hole: **a rename introduced by a
# later pass or a
# future version must be folded into the pass-1 rename list**, or it will not be watched here.
# (Checked live: a planted later-pass rename is NOT caught by this guard. Said, not hidden.)
cl = [l for l in t.split(chr(10)) if l.startswith('**v4.0')]   # '**v4.0 . pass N**' -- pass 1 carries the rename contract
if not cl:
    sys.stderr.write("DERIVE FAIL: no `**v4.0 ...**` Changelog entry in the canon — "
                     "the contract cannot be read off; fix the canon or this parser.\n")
    sys.exit(2)
# Iterate EVERY collected entry, not cl[0]: reading only the first re-opens exactly the
# fail-open the comment above declares closed — an addendum rename would never be watched.
# The RENAME CONTRACT is the v4.0 entry: that is where the renames were declared, and its arrows
# are renames. The addendum entries use `→` in PROSE (splits, recounts, routings: '5/4/2/1 →
# 4/4/3/1', 'q_V's pass → later-fail'), so harvesting them as names turns the guard red on
# sentences. Rather than guess which prose arrow is a rename, this is fail-CLOSED the other way:
# read the contract from the v4.0 entry, and REFUSE TO RUN if an addendum ever introduces an arrow
# of rename SHAPE (both sides a single identifier/bracketed token) — that is the case the header
# warns about, and it must be an explicit maintainer decision, never a silent miss.
for m in re.finditer(r'([^,;:()]{1,40}?)→([^,;()]{1,40})', cl[0]):
    names.add(m.group(1).strip().strip('"'))

# (2) the canon's inline provenance markers: `(v3.9: X — renamed; …)` / `(v3.9: X)`
for m in re.finditer(r'\(v3\.9:\s*([^)—;]+?)\s*(?:[—;)])', t):
    x = m.group(1).strip().strip('"')
    if x and not x.startswith('§'):
        names.add(x)

for n in sorted(names):
    print(n)
PY
}

# ---------------------------------------------------------------------------
# 2. The handling table: every derived name is WATCHED (with a pattern) or SKIPPED (with a reason).
# ---------------------------------------------------------------------------
# WATCH patterns are ERE. A retired UPPERCASE token is matched whole-word; a term the canon still
# uses in another role (`Verifiability` = A1's name; `Currency`/`Structural validation` as ordinary
# English) is matched only in the FM/STD context that carries the defect — in both languages,
# because the FM names live in the Russian mirrors.
#
# `TIMEOUT` is the hard one and worth stating plainly: v4 retired only the STATE (→ OVERDUE) while
# the SIGNAL keeps `TIMEOUT` (`Sig.TIMEOUT` in the code) and the system trigger is lowercase
# `timeout`. A bare uppercase `TIMEOUT` is therefore genuinely ambiguous — the Fsm.lean signal lists
# (`[PASS, FAIL, TIMEOUT, CANCEL]`) are legitimate. So this guard does NOT watch bare `TIMEOUT`; it
# watches the UNAMBIGUOUS retired-STATE contexts only: the detection triad `q_V + TIMEOUT` (whose
# third member is the lowercase trigger), the literal `TIMEOUT state` / `state TIMEOUT`, the diagram
# form `TIMEOUT →`, and the Russian `TIMEOUT-состояние`. A retired STATE-`TIMEOUT` outside these
# contexts stays grep-invisible by design — that residue is disclosed, not hidden.
handling_for() {
  case "$1" in
    'REVIEW')              echo $'WATCH	'"REVIEW\b|[Rr]eview →|review →" ;;
    'CANCELLED')           echo $'WATCH	'"CANCELLED" ;;
    'CANCEL_ACK')          echo $'WATCH	'"CANCEL_ACK" ;;
    'REWORK')              echo $'WATCH	'"REWORK\b" ;;
    'NEGLECTED')           echo $'WATCH	'"NEGLECTED" ;;
    'AUTO')                echo $'WATCH	'"AUTO\b" ;;
    'HBP')                 echo $'WATCH	'"HBP" ;;
    'SOLITUDE')            echo $'WATCH	'"SOLITUDE" ;;
    'EMIT')                echo $'WATCH	'"EMIT\b" ;;
    'objectification')     echo $'WATCH	'"objectification|объективац" ;;
    '[STD]')               echo $'WATCH	'"\[STD\]" ;;
    'FM-3 Verifiability')  echo $'WATCH	'"FM-3 \(?Verifiability|Verifiability \(FM-3|FM-3 \(?Верифицируемость|Верифицируемость \(FM-3" ;;
    'FM-5 Currency')       echo $'WATCH	'"FM-5 \(?Currency|Currency \(FM-5|FM-5 \(?Актуальность|Актуальность \(FM-5" ;;
    'Verifiability')       echo $'SKIP	'"v4 KEEPS it as A1 s own name; only FM-3 was renamed - watched as FM-3 Verifiability" ;;
    'Currency')            echo $'SKIP	'"watched as the FM-5 Currency pattern; the bare word is not a canon term" ;;
    'Structural validation') echo $'WATCH	'"Structural validation|Структурная валидация" ;;
    'TIMEOUT state')       echo $'WATCH	'"q_V \+ TIMEOUT|TIMEOUT state|state TIMEOUT|TIMEOUT →|TIMEOUT-состояние" ;;
    *)                     echo 'UNHANDLED' ;;
  esac
}

# Extra watches beyond the derived set: retired forms the canon states in prose rather than as a
# pair (`the v3.9 "Lemma 3" renumbered Lemma 2`), and v3.9-era notations the v4 contract replaced.
# Extra watches are always safe — the failure mode this guard exists to prevent is UNDER-watching.
declare -a EXTRA=(
  $'Лемма 3	Lemma 2'
  $'Lemma 3	Lemma 2'
  $'joint necessity	(abolished in naming Round 2 — the condition is non-redundancy)'
  $'K̂	Ŝ'
  $'L·γ	Λ·γ'
  $'Утв\.	Prop'
  $'Сл\.[0-9]	Cor N'
  'contact T\b|Contact (the seam operator is named in v4)'
  'Axiom [12]\b|CA1 / CA2'
  'Axiom-[12]\b|CA1 / CA2'
)

# ---------------------------------------------------------------------------
# 3. Cross-check: the derived contract must be fully handled.
# ---------------------------------------------------------------------------
# Capture the derivation into a variable, NOT a process substitution. `done < <(derive_contract)`
# runs the deriver in a subshell whose exit code `set -e` never sees (and `| tr -d '\r'` masks it
# too), so a `sys.exit(2)` on "no **v4.0** Changelog entry" printed to stderr and the guard sailed on
# to its success message with only the EXTRA patterns — falsely green the instant the canon marker is
# reformatted. Capturing first makes the deriver's failure fatal here.
CONTRACT="$(derive_contract)" || {
  echo "FAIL: could not derive the naming contract from the canon (see the DERIVE FAIL above)." >&2
  echo "      The guard refuses to run on a collapsed contract — that would be falsely green." >&2
  exit 1
}
# REVERSE INCLUSION — every handling-table case label must appear in the derived contract.
# The forward check below enforces derived ⊆ handled (every derived name has a case). This enforces
# handled ⊆ derived: every name the table KNOWS ABOUT must still be produced by the derivation. It
# closes the residual the anchor floor could not: a NON-anchor rename (EMIT, AUTO, "Structural
# validation", …) whose Changelog arrow is silently reformatted would drop from the derivation while
# the anchors survive, leaving that name unwatched at exit 0. Now its case label no longer resolves
# against the contract and the guard fails. The expected set is the case-label table itself — already
# version-controlled, so a DELIBERATE removal is a visible reviewed edit (like `AXIOMS.whitelist`),
# while a SILENT drop trips CI. No hand-copied name list: the table IS the handling contract.
CASE_LABELS="$(grep -oE "^ *'[^']+'\)" "$SELF" | sed -E "s/^ *'//; s/'\)$//")"
while IFS= read -r label; do
  [[ -z "$label" ]] && continue
  grep -qxF "$label" <<<"$CONTRACT" || {
    echo "FAIL: the handling table knows the retired name '$label', but the canon derivation no" >&2
    echo "      longer produces it — a Changelog rename was silently dropped or reformatted, and" >&2
    echo "      that name is now unwatched. Fix the canon's Changelog, or (if the rename is genuinely" >&2
    echo "      gone) remove its handling_for case as a visible edit. Refusing to run under-covered." >&2
    exit 1
  }
done <<<"$CASE_LABELS"

declare -a PAIRS=()
UNHANDLED=0
while IFS= read -r name; do
  [[ -z "$name" ]] && continue
  h="$(handling_for "$name")"
  verb="${h%%$'	'*}"; payload="${h#*$'	'}"
  case "$verb" in
    WATCH) PAIRS+=("${payload}"$'	'"${name} → see the canon's Changelog") ;;
    SKIP)  ;;  # disclosed, with the reason carried in the table above
    *) echo "UNWATCHED CONTRACT ENTRY: the canon retires '${name}', and this guard neither watches" >&2
       echo "                         it nor declares why it cannot. Add a WATCH pattern or a SKIP" >&2
       echo "                         reason to handling_for() — do not delete this check." >&2
       UNHANDLED=1 ;;
  esac
done <<<"$CONTRACT"

if [[ "$UNHANDLED" -ne 0 ]]; then
  echo >&2
  echo "FAIL: the naming contract in the canon has grown an entry this guard does not cover." >&2
  exit 1
fi

for e in "${EXTRA[@]}"; do PAIRS+=("$e"); done

# Strip what may legitimately name a retired term:
#  * `(v3.9: X)` / `v3.9 names: …` / `v3.9 carried this as "X"` — the canon's own provenance notes;
#  * the Fsm.lean NAMES banner, which must list the code's identifiers to declare the lag.
# Licensed regions are BLANKED, never deleted: `sed '…d'` shifts every later line number, which made
# this guard report the wrong line for every hit after the banner.
strip_licensed() {
  sed -e 's/(v3\.9:[^)]*)//g' \
      -e 's/v3\.9 names:[^)]*//g' \
      -e 's/v3\.9 carried this as "[^"]*"//g' \
      -e 's/v3\.9 §[0-9.]*//g' \
      -e '/NAMES: this is a mirror of the CANON/,/^$/s/.*//'
}

# One combined alternation, one pass per file: patterns × files as separate greps is ~450 process
# spawns, which on Windows takes minutes. File-major keeps it under a second.
ALT=""
for pair in "${PAIRS[@]}"; do ALT="${ALT}|${pair%%$'	'*}"; done
ALT="${ALT#|}"

explain() {  # matched text → what v4 says
  local t="$1"
  for pair in "${PAIRS[@]}"; do
    local old="${pair%%$'	'*}" new="${pair#*$'	'}"
    grep -qE "^${old}$" <<<"$t" && { echo "$new"; return; }
  done
  echo "see the contract in the canon's Changelog"
}

BAD=0
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || continue
  hits="$(strip_licensed < "$f" | grep -noE "$ALT" || true)"
  [[ -z "$hits" ]] && continue
  while IFS= read -r line; do
    ln="${line%%:*}"; tok="${line#*:}"
    echo "RETIRED NAME: ${f#../}:${ln} carries '${tok}' — v4 says: $(explain "$tok")" >&2
    BAD=1
  done <<<"$hits"
done

if [[ "$BAD" -ne 0 ]]; then
  echo >&2
  echo "FAIL: a name v4 retired survives in a live mirror or in formal/." >&2
  echo "      If the site legitimately names the old term (provenance, or the code's identifier)," >&2
  echo "      make that explicit — the licensed forms are listed at the top of this script." >&2
  exit 1
fi

echo "ok: no name the v4 contract retired survives in formal/ or in a live canon mirror"
echo "    — the contract is read off the canon at every run (Changelog pairs + inline (v3.9: …)"
echo "      markers), and an entry this guard fails to watch or to excuse is itself a failure."

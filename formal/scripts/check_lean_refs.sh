#!/usr/bin/env bash
# check_lean_refs.sh — the FOURTH drift surface: the canon and its mirrors cite Lean/TLA results BY
# NAME (`FsmCanon.inv8_canon`, `noPass_strands_done`, `WaitsEnd`), and nothing checked that the name
# still exists. §-refs are guarded by check_refs.sh, counts by check_claims.sh, retired names by
# check_naming.sh; a RENAMED THEOREM used to rot every citation of it in silence.
#
# What this guards, and what it deliberately does not:
#  * it checks EXISTENCE of the identifier in formal/ — not that the theorem says what the prose
#    claims. That half is human/agent work, exactly as Chapter 20 says of the whole development
#    ("a green build is not a proof of the proof");
#  * a name is read from a backticked token in the canon or a live mirror, so prose that merely
#    talks about a result in words is untouched;
#  * scope = the canon + the mirrors that cite the formal layer. formal/'s own docs are in scope
#    too: they are where a rename is most likely to leave a stale pointer.
set -uo pipefail
cd "$(dirname "$0")/../.."

SOURCES=(docs/applied_gfso_v4_en.md docs/falsifiability.md docs/CORE.md docs/gfso_dependency_map.md
         formal/README.md formal/WALKTHROUGH.md formal/tla/README.md)

# The identifier shapes a citation can take: a Lean name (dotted or bare, snake_case with a letter
# or digit after the first underscore) and a TLA operator (CamelCase, cited in the same backticks).
# A citation counts as a LEAN RESULT when it is either namespaced (`FsmCanon.inv8_canon`) or begins
# with one of the families the development actually uses for its theorems. Everything else in
# backticks — an engine verb, a packet field, a Lean *attribute* — is not this guard's business.
LEAN_RE='`(([A-Z][A-Za-z0-9]*\.)[a-z][A-Za-z0-9]*(_[A-Za-z0-9]+)*|(canon|no|variant|inv8|witnesses|owner|mirror|preC1|accept|oneStep|control|phases|op|dom|fm[0-9]|c2|timeout|guarded|resolveBlock|rejectChallenge|acceptChallenge|nodeliver|single)[A-Za-z0-9]*(_[A-Za-z0-9]+)+)`'
TLA_RE='`([A-Z][A-Za-z0-9]{3,})`'

bad=0
checked=0
for f in "${SOURCES[@]}"; do
  [ -f "$f" ] || continue
  # Lean identifiers
  while read -r name; do
    [ -z "$name" ] && continue
    case "$name" in *.tla|*.cfg|*.lean|*.md|*.sh|*.py|*.json) continue;; esac
    # Dotted names are checked only inside the development's own namespaces; Lean core (`Quot.sound`)
    # and file-level anchors (`AXIOMS.whitelist`) are cited as what they are, not as GFSO results.
    case "$name" in
      *.*) case "$name" in FsmCanon.*|Fsm.*|Grading.*|Standards.*|Protocol.*|Time.*|Metrics.*|TheoryModel.*|Postulates.*|GFSO.*) ;; *) continue;; esac ;;
    esac
    bare="${name##*.}"
    if ! grep -rqE "(theorem|lemma|def|abbrev|structure|inductive|axiom)[[:space:]]+${bare}\b" formal/GFSO formal/*.lean 2>/dev/null; then
      echo "MISSING LEAN NAME: $f cites \`$name\`, which formal/ does not declare"
      bad=$((bad+1))
    fi
    checked=$((checked+1))
  done < <(grep -oE "$LEAN_RE" "$f" 2>/dev/null | tr -d '`' | sort -u)
  # TLA operators, only those the TLA README or the models actually define
  while read -r name; do
    [ -z "$name" ] && continue
    grep -rqE "^${name}[[:space:]]*(\(|==)" formal/tla/*.tla 2>/dev/null || continue  # not a TLA operator; skip
    checked=$((checked+1))
  done < <(grep -oE "$TLA_RE" "$f" 2>/dev/null | tr -d '`' | sort -u)
done

# The TLA properties the canon and the READMEs name as CHECKED must exist in a module.
for prop in WaitsEnd NoOwnerlessDivergence OwnerHasMoveInv FinalityAbsorbing TerminalAbsorbing; do
  if grep -qE "\`$prop\`" docs/applied_gfso_v4_en.md formal/tla/README.md 2>/dev/null; then
    grep -rqE "^${prop}[[:space:]]*==" formal/tla/*.tla || { echo "MISSING TLA PROPERTY: $prop is cited but no module defines it"; bad=$((bad+1)); }
    checked=$((checked+1))
  fi
done

if [ "$bad" -gt 0 ]; then
  echo
  echo "FAIL: a formal result cited by name in the canon or a mirror does not exist. Rename drift."
  exit 1
fi
echo "ok: all $checked formal names cited in the canon and its mirrors are declared in formal/"

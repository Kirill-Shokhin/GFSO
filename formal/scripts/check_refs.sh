#!/usr/bin/env bash
# CANON REFERENCE GUARD — catches citation drift when the canon is edited.
#
# What it does: every `§X.Y` / `Chapter X` cited in `formal/**`, in a live canon mirror, or in the
# canon's own body must exist in the canon's BODY (the Changelog is excluded — see below), and every
# citation range must ascend. The mirrors are in scope because they are bound projections of the
# canon (never their own version), so a canon renumbering rots them exactly as it rots `formal/` —
# silently, until a reader follows a pointer into nothing.
# What it CANNOT do: verify that the citing statement still *means* what that section says — the
# defect where a §-token was swapped and the sentence around it was not re-read. That half is a
# reading job and no cheap check replaces it; it is where every audit of this layer found its real
# defects. This guard catches the mechanical half only.
#
# NOT in scope, deliberately, and each for its own reason:
#  * the frozen RU draft (`applied_gfso_v3.md`) — provenance; its §-refs ARE the old numbering;
#  * the E1/E2 instruments (`docs/e1/`, `experiments/`) — frozen: renaming inside them would break
#    run-to-run comparability, and they cite the frozen draft, so their pointers still resolve;
#  * `docs/notes/` — untracked;
#  * `gfso/**`, `tests/**`, `examples/**` — the product tree. It carries ~175 canon §-refs in code
#    comments plus `gfso/mcp/ORCHESTRATOR.md`, all still on v3.9 numbering. They are NOT
#    dangling-by-accident here: that tree migrates as one unit with the enum rename (the engineer's
#    post-E3 item, declared in `docs/architecture.md`), and guarding it before the migration would
#    fire on every file it is about to touch. **This is a named debt, not a clean surface** — when
#    the migration lands, the §-refs go with it and this exclusion should be deleted.
# EVIDENCE_LOG is out of scope too, but for a WEAKER reason and only as a whole file: it
# is mixed — its dated snapshots keep the old numbering legitimately (they record what was true then),
# while its navigation/status lines are live and are kept anchored by hand. Guarding it wholesale
# would fire on the snapshots; guarding it per-line needs a distinction this script cannot draw.
set -euo pipefail

cd "$(dirname "$0")/.."
CANON_FILE="../docs/applied_gfso_v4_en.md"

if [[ ! -f "$CANON_FILE" ]]; then
  echo "FAIL: canon not found at $CANON_FILE" >&2
  exit 1
fi

# The haystack is the canon's BODY — everything before the Changelog. The Changelog names the OLD
# numbering as provenance ("formerly §18.10–§18.11, §17.4–§17.6"), and searching it would let a
# mirror cite exactly the sections v4 dissolved — the four highest-risk tokens — and pass.
CANON="$(mktemp)"
trap 'rm -f "$CANON"' EXIT
sed '/^## Changelog/,$d' "$CANON_FILE" > "$CANON"

# Live canon mirrors. A doc joins this list when it starts citing the canon.
# (`README.md` unprefixed = formal/README.md, the Lean layer's own entry doc.)
MIRRORS=(../README.md ../docs/CORE.md ../docs/method_gfso.md ../docs/gfso_dependency_map.md
         ../docs/applied_gfso_vision.md ../docs/falsifiability.md ../docs/architecture.md README.md)

# FAIL-CLOSED PRE-FLIGHT: a watched mirror that is deleted or renamed must break the guard, not be
# silently dropped by the `2>/dev/null` on the `cat`s below.
MISSING_MIRROR=0
for m in "${MIRRORS[@]}"; do
  [[ -e "$m" ]] || { echo "WATCHED MIRROR MISSING: ${m#../} — update MIRRORS deliberately" >&2; MISSING_MIRROR=1; }
done
[[ $MISSING_MIRROR -eq 0 ]] || exit 1

# §-refs that must NOT be resolved against the canon. Three kinds, each carrying an explicit marker:
# `EVIDENCE_LOG §N` / `§N of the evidence log` = that log's section; `§N этого дока` = the vision
# doc's own section; `v3.9's §N` = the OLD numbering named as provenance (the canon does this once,
# at "v3.9's §17.4–§17.6 — are developed in Chapter 6"; those sections do not exist in v4 and must
# not be blessed by the mention). The marker sits on EITHER side, and a range carries two refs.
# The newline→space fold is load-bearing: a foreign ref may straddle a line break ("…(EVIDENCE_LOG\n
# §9.1 …"), which a line-oriented filter would miss and then report as canon drift.
strip_foreign() {
  tr '\n' ' ' \
    | sed -e 's/EVIDENCE_LOG[^§]\{0,15\}§[0-9.]*\(–\(§\)\{0,1\}[0-9.]*\)\{0,1\}//g' \
          -e 's/§[0-9.]*\(–\(§\)\{0,1\}[0-9.]*\)\{0,1\} *\(of the evidence log\|этого дока\)//g' \
          -e "s/v3\.9\('s\)\{0,1\}:\{0,1\} *§[0-9.]*\(–\(§\)\{0,1\}[0-9.]*\)\{0,1\}//g"
}

# Both citation forms count — the canon's own prose overwhelmingly says "Chapter N", so a mirror that
# adopts that form must not thereby fall out of the guard's sight. Rather than teach every check both
# forms (an earlier version taught only the §-check, and `Chapters 8–2` sailed through the range
# check), normalise `Chapter(s) N` / `Ch. N` to `§N` ONCE, up front; everything downstream then sees
# one form. Case-insensitive: the form is prose, and prose gets typed in lower case.
# KNOWN LIMIT, not covered: a comma continuation — the canon writes "(Ch. 15, 21)", and only the
# first number is collected. Catching the second needs the comma to bind, which prose does not
# guarantee ("§15, 12 signals"), so a false positive would be the price. Left uncaught, named here.
normalize_chapters() { sed -E 's/(Chapters?|Ch\.) ?([0-9]+(\.[0-9]+)*)/§\2/gI'; }

collect() { grep -ohE '§[0-9]+(\.[0-9]+)*' || true; }

# A citation RANGE must ascend. A range's TAIL carries no § of its own ("§12.2–4.8": the head moved
# to v4, the tail stayed in the old numbering), so the §-only collector above cannot see it, and both
# endpoints may exist in the canon while the range is nonsense — existence is not the test, order is.
# HONEST LIMIT: this catches only ranges that do not ascend. A half-remap that happens to stay
# ascending (§2.1–3.2) is invisible here and no cheap check finds it — that half stays a reading job.
# Two encoding traps, both of which made an earlier version of this guard silently pass:
#  * do NOT put both dashes in one bracket expression — `[–-]` is read as a character RANGE;
#  * do NOT write `§?` — `§` is a two-byte UTF-8 char, so `?` binds to its second byte and
#    the `§` itself stays MANDATORY. Group it: `(§)?`.
# The en-dash is normalised to '-' up front.
check_ranges() {
  local bad=0 head tail
  while read -r range; do
    [[ -z "$range" ]] && continue
    head="${range%%-*}"; head="${head#§}"
    tail="${range##*-}"; tail="${tail#§}"
    if [[ "$(printf '%s\n%s\n' "$head" "$tail" | sort -V | head -1)" != "$head" || "$head" == "$tail" ]]; then
      echo "BROKEN RANGE: §${head}–${tail} does not ascend — a half-remapped citation" >&2
      bad=1
    fi
  done < <(cat "${MIRRORS[@]}" "$CANON" GFSO/*.lean *.lean 2>/dev/null | normalize_chapters \
            | strip_foreign | sed 's/–/-/g' \
            | grep -ohE '§[0-9]+(\.[0-9]+)*-(§)?[0-9]+(\.[0-9]+)*' || true)
  return $bad
}

REFS_FORMAL="$(cat GFSO/*.lean *.lean 2>/dev/null | normalize_chapters | strip_foreign | collect | sed 's/^§//' | sort -u -V)"
# The canon's own body is scanned too: a self-citation into a section it does not have is the same
# defect as a mirror's, and nothing else was watching that surface.
# A range's TAIL is a cited section too ("§12.2–99" cites 99). check_ranges only orders them; if the
# tail is never resolved, a cited section goes unchecked. Feed both endpoints in.
REFS_TAILS="$(cat "${MIRRORS[@]}" "$CANON" GFSO/*.lean *.lean 2>/dev/null | normalize_chapters | strip_foreign               | sed 's/–/-/g' | grep -ohE '§[0-9]+(\.[0-9]+)*-(§)?[0-9]+(\.[0-9]+)*'               | sed -E 's/.*-(§)?//' | sort -u -V || true)"
REFS_MIRROR="$(cat "${MIRRORS[@]}" "$CANON" 2>/dev/null | normalize_chapters | strip_foreign | collect | sed 's/^§//' | sort -u -V)"
REFS="$(printf '%s\n%s\n%s\n' "$REFS_FORMAL" "$REFS_MIRROR" "$REFS_TAILS" | sort -u -V | grep -v '^$')"

MISSING=0
for r in $REFS; do
  # A section exists iff the canon HAS one: a numbered heading, or a bold-lead item for the few
  # sub-items carried that way (26.5-bis). Deliberately NOT "the canon mentions §r somewhere" —
  # that test is defeated twice over: the canon names the OLD numbering as provenance in its own
  # body ("v3.9's §17.4–§17.6 — are developed in Chapter 6"), which would bless the very sections
  # v4 dissolved; and a ref collected FROM the canon would resolve against its own citation,
  # making the self-citation check vacuous.
  if grep -qE "^#{1,4} +${r//./\\.}\." "$CANON" \
     || grep -qE "^\*\*${r//./\\.}\." "$CANON"; then
    :
  else
    where="a canon mirror"
    grep -q "^${r}$" <<<"$REFS_FORMAL" && where="formal/"
    echo "MISSING: §${r} is cited in ${where} but not found in the canon" >&2
    MISSING=1
  fi
done

check_ranges || MISSING=1

# LABELS. A citation is not only a §: the canon's results carry names, and a mirror can cite a name
# the canon does not have. This is not hypothetical — an audit found `Prop 1–2` fabricated in a
# mirror, against a canon that says in §1.2 "P1/P2 are NOT members of this series". The §-collector
# is blind to it: the sentence carrying `Prop 1–2` cited a § that exists.
# Rule: every Thm/Prop/Cor/FM/Inv/STD/CHECK/Link number cited must exist in the canon's body. The
# canon spells them both long and short (Theorem 1 / Thm 1, Corollary 5 / Cor 5) — accept both.
check_labels() {
  local bad=0 kind pat num
  # Plurals and ranges are live forms: the canon writes "Theorems 1–2", "Corollaries 1–3". An earlier
  # version matched a trailing space only ('(Thm|Theorem) '), so every plural slipped past, and it read
  # a range's head while never resolving its tail — the same gap the §-checker closed with REFS_TAILS.
  # Both endpoints of a label range are cited labels; extract every number in the run.
  #
  # SCOPE, and why it is narrower than the §-check: the canon's OWN body is not scanned for labels.
  # A label has no uniform definition marker — `Theorem 1` reads the same where it is defined and
  # where it is cited — so `canon_nums` and `cited` would be built by one regex over one text and the
  # canon would always bless itself (the §-check escapes this trap only because a section's
  # definition site IS distinguishable: it is a heading). Rather than run a vacuous check and report
  # it as coverage, the canon's self-citations of labels are left to the reading job, and the
  # success message says so.
  # `Lemma` earns its place the hard way: v4 renumbered Lemma 3 → Lemma 2 — exactly the rename class
  # this check exists for — and the guard did not watch the family until an audit said so.
  for spec in 'Thm:(Thms?|Theorems?)' 'Prop:(Props?|Propositions?)' 'Cor:(Cors?|Corollar(y|ies))' \
              'Lemma:(Lemmas?|Леммы?|Лемма)' \
              'FM:FM-' 'Inv:Inv-' 'STD:STD-' 'CHECK:CHECK-' 'Link:Link-'; do
    kind="${spec%%:*}"; pat="${spec#*:}"
    local canon_nums cited
    # `[0-9]+(\.[a-z])?` — the FM family carries sub-modes (FM-1.a … FM-1.e). Matching the number
    # alone would strip the ".x" and bless a fabricated FM-1.z on the strength of FM-1 existing.
    # Build the canon's label set from the canon MINUS its v3.9 provenance mentions. The canon names
    # retired labels on purpose — `v3.9 carried this as "Lemma 3"`, `(v3.9: NEGLECTED)` — and reading
    # those as live definitions lets a mirror cite the very label v4 renumbered and pass. This is the
    # same trap the §-checker escapes by requiring a heading, and the reason `Lemma 3` sailed through
    # the first version of this check.
    canon_nums="$(sed 's/v3\.9[^"]\{0,40\}"[^"]*"//g' "$CANON" \
                  | grep -ohE "${pat} ?[0-9]+(\.[a-z])?" | grep -ohE '[0-9]+(\.[a-z])?$' | sort -u)"
    cited="$(cat "${MIRRORS[@]}" GFSO/*.lean *.lean 2>/dev/null | sed 's/–/-/g'              | grep -ohE "${pat} ?[0-9]+(\.[a-z])?(-[0-9]+(\.[a-z])?)?"              | grep -ohE '[0-9]+(\.[a-z])?' | sort -u)"
    for num in $cited; do
      grep -qx "$num" <<<"$canon_nums" || { echo "MISSING LABEL: ${kind} ${num} is cited but the canon has no such result" >&2; bad=1; }
    done
  done
  return $bad
}

check_labels || MISSING=1

if [[ "$MISSING" -ne 0 ]]; then
  echo >&2
  echo "FAIL: a canon citation in formal/ or in a mirror is broken. Citation drift." >&2
  exit 1
fi

echo "ok: all $(printf '%s\n' "$REFS" | grep -c . ) cited canon sections exist and every range ascends"
echo "    — across formal/, the mirrors, AND the canon's own body;"
echo "    and every result label (Thm/Prop/Cor/Lemma/FM/Inv/STD/CHECK/Link) cited in formal/ or a"
echo "    mirror names a result the canon has — read off the canon minus its v3.9 provenance notes."

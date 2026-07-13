#!/usr/bin/env bash
# CANON REFERENCE GUARD — catches citation drift when the canon is edited.
#
# What it does: every `§X.Y` cited anywhere in formal/**/*.lean must still exist in the canon.
# What it CANNOT do: verify that the Lean statement still *means* what that section says. Semantic
# conformance is a human/agent job (roadmap DoD 2.4). This guard catches the cheap half — a section
# renumbered or removed by a canon edit, leaving `formal/` pointing at nothing.
set -euo pipefail

cd "$(dirname "$0")/.."
CANON="../docs/applied_gfso_v3.md"

if [[ ! -f "$CANON" ]]; then
  echo "FAIL: canon not found at $CANON" >&2
  exit 1
fi

# Collect every §-reference used in the Lean sources (and the audit file).
REFS="$(grep -ohE '§[0-9]+(\.[0-9]+)*' GFSO/*.lean *.lean 2>/dev/null \
        | sed 's/^§//' | sort -u -V || true)"

MISSING=0
for r in $REFS; do
  # Accept either an explicit "§r" citation in the canon, or a heading numbered "r."
  if grep -qF "§${r}" "$CANON" || grep -qE "^#{1,4} +${r//./\\.}\." "$CANON" \
     || grep -qE "^\*\*${r//./\\.}\." "$CANON"; then
    :
  else
    echo "MISSING: §${r} is cited in formal/ but not found in the canon" >&2
    MISSING=1
  fi
done

if [[ "$MISSING" -ne 0 ]]; then
  echo >&2
  echo "FAIL: formal/ cites canon sections that no longer exist. Citation drift." >&2
  exit 1
fi

echo "ok: all $(printf '%s\n' "$REFS" | grep -c . ) cited canon sections exist"

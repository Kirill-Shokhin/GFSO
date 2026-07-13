#!/usr/bin/env bash
# CLOSURE GUARD — fail-closed. The postulate set is an invariant the engine rejects violations of.
#
# `audit_env.lean` walks the compiled environment, enumerates EVERY theorem under `GFSO.*` (no hand
# list), and reports:
#     DECL_AXIOM / DECL_OPAQUE   what we declared under GFSO.*
#     USES                       every axiom transitively used by any GFSO theorem, wherever it lives
#
# We fail on:
#   (a) any `opaque` under GFSO.*                  — an assumption `#print axioms` cannot see;
#   (b) DECL_AXIOM set != AXIOMS.whitelist          — a new postulate crept in, or one was discharged;
#   (c) any USED axiom outside {propext, Quot.sound, Classical.choice} ∪ whitelist
#       — this catches `sorryAx` (a hole), `Lean.ofReduceBool`/`ofReduceNat` (i.e. `native_decide`),
#         and — the vector that defeated the previous version — an axiom declared in a FOREIGN
#         namespace (e.g. `Externals.smuggled : 2 = 3`) and used by a GFSO theorem.
#
# DISCLOSED LIMIT: an assumption moved into a theorem's *signature* (a hypothesis) is invisible here,
# by construction and legitimately — a hypothesis is dischargeable and appears in the type. So
# "axiom-free" certifies "assumes nothing beyond its stated premises", not "assumes nothing".
# Also: `AXIOMS.whitelist` is plaintext, so a new GFSO axiom can be laundered by adding a line — but
# that edit is version-controlled and shows in review. Foreign-namespace axioms can no longer be.
set -euo pipefail

cd "$(dirname "$0")/.."

CORE_ALLOWED=$'propext\nQuot.sound\nClassical.choice'

echo "── walking the compiled environment ───────────────────────────────────"
ENVDUMP="$(lake env lean audit_env.lean)"
echo "$ENVDUMP" | tail -3
echo

# (a) no opaque under GFSO.*
if grep -q '^DECL_OPAQUE ' <<<"$ENVDUMP"; then
  echo "FAIL: 'opaque' constant(s) under GFSO.* — an assumption invisible to #print axioms." >&2
  grep '^DECL_OPAQUE ' <<<"$ENVDUMP" >&2
  exit 1
fi
echo "ok: no opaque constants under GFSO.*"

WHITELIST="$(grep -vE '^\s*(#|$)' AXIOMS.whitelist | sort -u)"

# (b) declared axioms == whitelist
DECLARED="$(grep '^DECL_AXIOM ' <<<"$ENVDUMP" | awk '{print $2}' | sort -u)"
if ! diff <(printf '%s\n' "$DECLARED") <(printf '%s\n' "$WHITELIST") > /tmp/axdiff 2>&1; then
  echo "FAIL: the declared GFSO axiom set changed." >&2
  echo "      '<' = in the build but NOT whitelisted;  '>' = whitelisted but gone." >&2
  cat /tmp/axdiff >&2
  exit 1
fi
echo "ok: declared GFSO axioms == whitelist"

# (c) every USED axiom is core-allowed or whitelisted — regardless of namespace
ALLOWED="$(printf '%s\n%s\n' "$CORE_ALLOWED" "$WHITELIST" | sort -u)"
USED="$(grep '^USES ' <<<"$ENVDUMP" | awk '{print $2}' | sort -u)"
ROGUE="$(comm -23 <(printf '%s\n' "$USED") <(printf '%s\n' "$ALLOWED") || true)"

if [[ -n "$ROGUE" ]]; then
  echo "FAIL: GFSO theorems lean on axioms that are neither Lean foundations nor whitelisted:" >&2
  printf '  %s\n' $ROGUE >&2
  echo "      (sorryAx = a hole; Lean.ofReduceBool/ofReduceNat = native_decide;" >&2
  echo "       anything else = a smuggled assumption, in ANY namespace.)" >&2
  exit 1
fi

N_AX="$(printf '%s\n' "$WHITELIST" | grep -c .)"
N_THM="$(grep -oE 'theorems audited: [0-9]+' <<<"$ENVDUMP" | awk '{print $3}')"
echo "ok: $N_THM GFSO theorems use only {propext, Quot.sound, Classical.choice} + the $N_AX whitelisted postulates"
echo
echo "CLOSURE HOLDS."

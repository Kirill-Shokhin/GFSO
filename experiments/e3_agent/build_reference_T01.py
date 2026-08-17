"""
Build the T01 (Subscription billing logic) reference decomposition into a persistent SQLite DB.
Faithfully transcribes the FROZEN GOLD REFERENCE from experiments/e2_agent/complex/references/T01.md.

Usage:
    python experiments/e3_agent/build_reference_T01.py
"""
from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path when run from any directory
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import (
    Spec, Criteria, NeglectedItem, CriterionMapping, Predictability, TaskId, AgentId,
    Task, DepEdge,
)

DB_PATH = "data/t01_reference.db"

# ─── Delete DB for a clean build ────────────────────────────────────────────
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"Deleted existing {DB_PATH}")

# ─── Engine (no start — we build graph directly, no event loop needed) ───────
# We bypass the async event loop to avoid SQLite concurrency issues in a build script.
# All writes go directly to storage; _recompute_checks is called manually at the end.
engine = Engine(SqliteStorage(DB_PATH), HumanAgent(), llm=None, validate_signals=False)
# Do NOT call engine.start() — the event loop is not needed for graph construction.

HUMAN = AgentId("human")

# ─── ROOT task spec ──────────────────────────────────────────────────────────
# Root criteria = V-I1..I8 ONLY — the spanning, billing-wide money invariants (by definition multi-child).
# V-E1..E8 (boundary cases) and V-F1..F4 (defect-couplings) are NOT root criteria: each is a decidable
# predicate of ONE capability and lives on its OWNING child node (see the child specs below). This makes
# the graph 1:1 with the reference — each of the 45 items in exactly one place: V-I → root criteria,
# V-E/V-F → owning child criteria, D → node, Dep → edge (glue), N → root NeglectedItem.
root_criteria = (
    # V-I spanning invariants
    Criteria("money_conservation",
             "V-I1: Across every event, money in = money out + balance change; no credit/refund/proration "
             "path mints or vaporizes money."),
    Criteria("charge_idempotency",
             "V-I2: A retried/duplicated charge attempt for the same invoice must not capture money twice — "
             "idempotency key or equivalent dedupe on the charge."),
    Criteria("invoice_reconciles",
             "V-I3: Final amount charged equals the sum of line items (base ± proration − credit + tax), "
             "each rounded under one regime, with no residual."),
    Criteria("tax_at_event_time",
             "V-I4: Tax uses the rate and jurisdiction applicable at the moment of the billable event on the "
             "correct net base — not a stale or future rate."),
    Criteria("append_only_ledger",
             "V-I5: Billing records are append-only — corrections are new reversing entries, never in-place "
             "edits or deletions of posted records."),
    Criteria("no_over_refund",
             "V-I6: Charges to the payment method are never negative (negatives go through the refund path); "
             "cumulative refunds for a charge cannot exceed what was actually captured."),
    Criteria("entitlement_coupled_to_payment",
             "V-I7: Paid access is granted only after a charge actually succeeds (or a valid trial/credit "
             "covers it); a failed/declined charge does not silently grant or retain paid access past grace."),
    Criteria("exactly_once_cycle_advancement",
             "V-I8: Each billing period advances exactly once — never twice and never skipped; simultaneous "
             "lifecycle/clock events at the same boundary are ordered deterministically to one obligation."),
)

root_neglected = (
    NeglectedItem(
        item="Proration/rounding policy is a stated input, not derived",
        predictability=Predictability.EXTRAORDINARY,
        justification=(
            "S-regularity exists: every billing system parameterizes proration basis (time-based vs "
            "usage-based) and rounding rule (half-up / banker's / largest-remainder) as a business-policy "
            "input. The logic applies it consistently (Dep7) and allocates residuals (V-F4), but does not "
            "derive which policy is correct — that is a product/finance decision."
        ),
        invalidation_condition=(
            "If the proration/rounding policy is left undefined, proration becomes ambiguous and rounding "
            "leaks (V-F4) re-enter as in-scope defects."
        ),
    ),
    NeglectedItem(
        item="Tax rates / jurisdiction tables / nexus are supplied by an external tax engine",
        predictability=Predictability.EXTRAORDINARY,
        justification=(
            "S-regularity exists: tax engines (Avalara, TaxJar, etc.) are the industry norm. A wrong rate "
            "from the engine is an external-dependency error, not a billing-logic defect; the logic's job "
            "is to apply the supplied rate to the correct base (Dep1/Dep2) at the correct time (V-I4)."
        ),
        invalidation_condition=(
            "If rate determination is in-scope (the logic must compute jurisdiction/nexus itself), "
            "tax-rate-sourcing becomes a primary requirement."
        ),
    ),
    NeglectedItem(
        item="Payment gateway capture/settlement mechanics are assumed external",
        predictability=Predictability.EXTRAORDINARY,
        justification=(
            "S-regularity exists: gateways are universal. The billing logic computes what to charge and "
            "when; the gateway's capture/auth/settlement, PCI handling, and 3DS/SCA flows are downstream. "
            "Note: the ambiguous-result reconciliation (V-F1) is NOT excluded — it is in-scope."
        ),
        invalidation_condition=(
            "If the logic must implement settlement/auth itself (acting as the processor), capture "
            "mechanics become in-scope."
        ),
    ),
    NeglectedItem(
        item="Revenue recognition / accounting (GAAP/IFRS) is out of scope",
        predictability=Predictability.EXTRAORDINARY,
        justification=(
            "S-regularity exists: revenue recognition (ASC 606 / IFRS 15 deferred-revenue schedules) is a "
            "separate downstream accounting concern. The billing logic emits charges/credits; the GL "
            "recognizes them."
        ),
        invalidation_condition=(
            "If the task required producing rev-rec schedules, deferred-revenue logic becomes in-scope."
        ),
    ),
    NeglectedItem(
        item="Fraud / chargeback / disputes are out of scope",
        predictability=Predictability.EXTRAORDINARY,
        justification=(
            "S-regularity exists: fraud detection and chargeback/dispute handling are a distinct "
            "risk/operations layer. The billing logic's correctness (right amount, conserved money) is "
            "independent of whether a charge is later disputed."
        ),
        invalidation_condition=(
            "If chargeback-driven reversals must flow back into the ledger automatically, dispute handling "
            "(and its money-conservation impact, V-I1) becomes in-scope."
        ),
    ),
    NeglectedItem(
        item="Coupons / promotional discounts are out of scope (distinct from account credits)",
        predictability=Predictability.EXTRAORDINARY,
        justification=(
            "S-regularity exists: coupon engines are a standard separate capability. The task text lists "
            "'account credits / balance' (a stored, conserved customer balance — D8/Dep4) but not coupons "
            "or promotional discounts (percent-off / fixed-off codes applied at checkout). A coupon engine "
            "is a separate pricing-adjustment capability whose absence is not a billing-correctness bug for "
            "the in-scope capabilities."
        ),
        invalidation_condition=(
            "If the spec adds coupons/promo codes, a discount component plus a discount-before-tax ordering "
            "seam and a discount×proration interaction become in-scope."
        ),
    ),
)

root_spec = Spec(
    description=(
        "Design the subscription billing logic — the rules of what to charge a customer and when "
        "(not the infrastructure and not the project, specifically the calculation logic) — that stays "
        "correct under any combination of the following capabilities co-existing in one product: "
        "monthly and annual plans; mid-period plan change (upgrade/downgrade) with proration; "
        "trial period converting to paid; refunds (full and partial); account credits / balance; "
        "country-dependent tax; failed charges and retries (dunning); cancellation and reactivation; "
        "pause and resume. Decompose this task."
    ),
    criteria=root_criteria,
    accepted_risks=root_neglected,
)

# ─── ROOT task — save directly to storage (no FSM event loop needed) ─────────
root_task = Task(id=TaskId("billing"), spec=root_spec, assignee=HUMAN)
engine._graph.save_task(root_task)

# ─── Children D1..D9 ─────────────────────────────────────────────────────────
children = [
    (
        TaskId("d1_lifecycle"),
        Spec(
            description=(
                "D1 — Subscription lifecycle / state machine: define the states a subscription occupies "
                "(trialing, active, past_due/dunning, paused, canceled, expired) and the legal transitions "
                "between them (trial→active, active→paused→active, active→canceled→reactivated, "
                "active→past_due→active/canceled). Each transition defines whether and what it bills. "
                "Trial is a lifecycle state with zero/deferred charge."
            ),
            criteria=(
                Criteria("state_machine_states_and_transitions",
                         "Named subscription states (trialing, active, past_due/dunning, paused, canceled, "
                         "expired) and the legal transitions between them (trial→active, active→paused→active, "
                         "active→canceled→reactivated, active→past_due→active/canceled); each transition "
                         "defines whether and what it bills — the spine the money events hang on."),
                Criteria("trial_state_no_charge",
                         "Trial is a lifecycle state with a zero/deferred charge — no charge during trial; "
                         "conversion triggers the first real charge."),
                # V-E5 (owned here — lifecycle boundary)
                Criteria("trial_to_paid_conversion",
                         "V-E5: the trial bills nothing (or a $0 invoice); conversion at trial end triggers "
                         "the first real charge on the correct anchor (Dep9); early-cancel-during-trial owes "
                         "nothing; covers trial-with-required-card vs no-card."),
                # V-E8 (owned here — lifecycle ordering anchor; spans D1/D9/D5)
                Criteria("cancel_refund_reactivate_ordering",
                         "V-E8: cancel/refund/reactivate timing & ordering corners — reactivation after a "
                         "refund-on-cancel doesn't re-grant a refunded period for free; a refund after a "
                         "downgrade-credit doesn't double-refund the already-credited remainder; cancel during "
                         "dunning stops retries cleanly; upgrade-effective-now vs downgrade-effective-next-period "
                         "per stated policy; a backdated change does NOT mutate the finalized invoice (V-I5) but "
                         "issues a correcting credit/charge memo for the over/under-billed delta. "
                         "(Spanning D1/D9/D5; owned here as the lifecycle-ordering anchor.)"),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d2_pricing"),
        Spec(
            description=(
                "D2 — Plan & pricing model: the catalog of plans and how a price is determined — "
                "monthly vs annual billing period, per-plan amount, currency, and the period→amount mapping. "
                "Defines what a full-period charge is before any proration/tax/credit."
            ),
            criteria=(
                Criteria("plan_catalog_and_period",
                         "Catalog of plans and how a price is determined: monthly vs annual billing period, "
                         "per-plan amount, currency, and the period→amount mapping. Defines what a full-period "
                         "charge is before any proration/tax/credit — the base amount everything else adjusts."),
                # V-F2 (owned here — the plan-price pinning half; spans D3 anchoring / D6 rate)
                Criteria("plan_rate_snapshot",
                         "V-F2: a plan-price change mid-cycle must not retro-price an already-anchored invoice "
                         "— pin the plan-version in force at invoice generation (point-in-time snapshot) so a "
                         "later catalog change doesn't re-price a period the customer already committed to. "
                         "(Owned here for the plan-price half; the tax-rate half is V-I4/D6, the anchoring is "
                         "D3.)"),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d3_cycle"),
        Spec(
            description=(
                "D3 — Billing-cycle / schedule engine (anchor & period boundaries): the rule that decides "
                "when a charge is due — billing anchor date, period start/end, next-renewal computation, and "
                "how the period boundary is defined. Uses an injected/controllable clock with explicit timezone "
                "so day-boundary and proration decisions are deterministic. Month-end anchor clamp: an anchor "
                "on the 31st renews on Feb 28/29 on short months. Distinct from D2 (D2 = the price; D3 = the "
                "when and the period window)."
            ),
            criteria=(
                Criteria("renewal_schedule_and_boundary",
                         "Billing anchor date, period start/end, next-renewal computation, and how the period "
                         "boundary is defined (the instant proration is measured against). Drives renewal "
                         "charges and the proration denominator. Distinct from D2 (D2 = the price; D3 = the "
                         "when and the period window)."),
                Criteria("injected_clock_timezone",
                         "Time is read from an injected/controllable clock with an explicit timezone so "
                         "day-boundary and proration decisions are deterministic and reproducible in replay "
                         "(not wall-clock now())."),
                Criteria("month_end_anchor_clamp",
                         "Periods use the real calendar interval with a month-end anchor clamp — an anchor on "
                         "the 31st renews on Feb 28/29 and other short months — so the boundary is "
                         "well-defined."),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d4_invoice"),
        Spec(
            description=(
                "D4 — Invoice / charge computation (line-item assembly → total): the assembly point that builds "
                "an invoice from line items (base charge, proration credit/debit, account-credit application, "
                "tax line) and computes the final amount to charge. Defines the canonical order of assembly "
                "(base → proration → credit → tax-on-net). The hub every other capability feeds; the V-I3 "
                "reconciliation predicate lives on its output."
            ),
            criteria=(
                Criteria("line_item_assembly_order",
                         "Assembles an invoice from line items (base charge, proration credit/debit, "
                         "account-credit application, tax line) and computes the final amount to charge, in "
                         "the canonical order base → proration → credit → tax-on-net (Dep1/Dep2/Dep4). The hub "
                         "every other capability feeds; the V-I3 reconciliation predicate lives on its output."),
                # V-E6 (owned here — zero/negative total at the assembly point)
                Criteria("zero_amount_invoice",
                         "V-E6: an invoice whose net is zero (credit ≥ charge, a $0 plan, or 100% coupon) must "
                         "not submit a $0/negative charge to the gateway (V-I6), must still post the invoice "
                         "and draw down credit (Dep4), and must grant entitlement (V-I7) without a capture."),
                # V-E7 (owned here — rounding-boundary values reconciling at the total)
                Criteria("currency_rounding_boundary",
                         "V-E7: amounts at the rounding edge — sub-cent proration slices, a zero-decimal "
                         "currency (JPY), banker's-vs-half-up at exactly .5 — follow the stated regime (Dep7) "
                         "so parts still reconcile to the total (V-I3) with no leaked fraction."),
                # V-F4 (owned here — residual-cent allocation that makes V-I3 hold)
                Criteria("rounding_residual_allocation",
                         "V-F4: rounding each line item independently (base, proration, credit, tax) can make "
                         "the rounded parts not sum to the rounded total — a sub-cent leak. A defined "
                         "residual-allocation rule (largest-remainder / penny-allocation: compute the total "
                         "once, distribute the rounding residue to a designated line) makes parts reconcile to "
                         "the total (V-I3) and nothing leaks."),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d5_proration"),
        Spec(
            description=(
                "D5 — Proration: when a change happens mid-paid-period (plan change, mid-cycle cancel/pause), "
                "compute the partial-period value — credit for the unused portion of the old plan and/or charge "
                "for the used/remaining portion of the new plan, on the period defined by D3. Defines the "
                "proration basis (time-based by default) and rounding hand-off (N1)."
            ),
            criteria=(
                Criteria("prorates_partial_period",
                         "On a mid-paid-period change (plan change, mid-cycle cancel/pause), computes the "
                         "partial-period value — credit for the unused portion of the old plan and/or charge "
                         "for the used/remaining portion of the new plan, on the period defined by D3. "
                         "Proration basis is time-based by default; the rounding policy is a hand-off (N1)."),
                # V-E1 (owned here — boundary-instant change resolution)
                Criteria("boundary_instant_change",
                         "V-E1: a plan change (or cancel) landing exactly on the renewal instant is resolved "
                         "by a single old-vs-new-period rule at one decision point — no double proration, no "
                         "zero-day-window double-charge."),
                # V-E2 (owned here — stacked prorations in one cycle)
                Criteria("stacked_prorations",
                         "V-E2: more than one plan change within a single billing period — each proration "
                         "composes correctly so the net is conserved (no re-crediting an already-credited "
                         "remainder, no compounding rounding); proration is computed against the current "
                         "effective state, not the period start each time."),
                # V-E3 (owned here — sub-day / short-remainder proration)
                Criteria("short_remainder_proration",
                         "V-E3: proration of a tiny remaining fraction (a few hours/days, or a last-day "
                         "switch) — the basis and rounding yield a sensible, conserved amount (no rounding "
                         "artifact that over/under-charges, no negative remainder). Ties to V-F4."),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d6_tax"),
        Spec(
            description=(
                "D6 — Tax computation: compute country/jurisdiction-dependent tax on the correct taxable base "
                "(net amount after proration and credit — see Dep1, Dep2, Dep4) at the rate in force at event "
                "time (V-I4). Defines whether the plan price is tax-inclusive or tax-exclusive per "
                "plan/jurisdiction: inclusive backs out the tax (net + tax = stated price); exclusive adds tax "
                "on top. Where a charge carries multiple tax components (state + county + city, or VAT + levy), "
                "each is its own line summing to the invoice tax (Dep7). Handles tax-exempt customers (V-E4)."
            ),
            criteria=(
                Criteria("tax_by_jurisdiction_on_net_base",
                         "Computes country/jurisdiction-dependent tax on the correct taxable base — the net "
                         "amount after proration and credit (Dep1, Dep2, Dep4) — at the rate in force at the "
                         "event time (V-I4). The externally-supplied rate/jurisdiction is N2."),
                Criteria("tax_inclusive_exclusive",
                         "Defines whether the plan price is tax-inclusive or tax-exclusive per "
                         "plan/jurisdiction: an inclusive price contains the tax (back it out so net + tax = "
                         "the stated price, never base + tax on top); an exclusive price has tax added on top."),
                Criteria("stacked_tax_components",
                         "Where a charge carries multiple tax components (state + county + city, or VAT + "
                         "levy), each is its own line summing to the invoice tax (Dep7 rounds them)."),
                # V-E4 (owned here — tax-exempt / zero-rate boundary)
                Criteria("tax_exempt_customer",
                         "V-E4: a tax-exempt customer or zero-rate jurisdiction (tax-exempt entity, zero-rate "
                         "region, reverse-charge B2B) produces a zero/absent tax line by rule, not by a failed "
                         "lookup, and the invoice still reconciles (V-I3)."),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d7_charge_dunning"),
        Spec(
            description=(
                "D7 — Payment / charge execution & dunning (retry): submit the computed amount to the payment "
                "method, record the result (success/decline), and on failure run the dunning policy: schedule "
                "retries, move the subscription to past_due, and define the give-up/cancel terminal. Carries "
                "the charge-idempotency requirement (V-I2) so a retry never double-charges."
            ),
            criteria=(
                Criteria("charge_and_dunning",
                         "Submits the computed amount to the payment method, records the result "
                         "(success/decline), and on failure runs the dunning policy: schedule retries and move "
                         "the subscription to past_due. Carries the charge-idempotency requirement (V-I2) so a "
                         "retry never double-charges."),
                # V-F3 (owned here — bounded dunning terminal)
                Criteria("dunning_give_up_terminal",
                         "V-F3: dunning has a bounded give-up terminal (max attempts / max days → "
                         "cancel/expire) that revokes entitlement (ties V-I7) — not an infinite or "
                         "indefinitely-retained-access retry loop."),
                # V-F1 (owned here — ambiguous-result reconciliation channel)
                Criteria("ambiguous_charge_reconciliation",
                         "V-F1: a charge attempt that times out or returns ambiguously (gateway captured but "
                         "the response was lost) is reconciled (query the gateway / webhook) before retry — "
                         "not a blind retry. The idempotency key (V-I2) makes the retry safe; V-F1 is the "
                         "channel that determines whether the first attempt actually captured."),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d8_credit"),
        Spec(
            description=(
                "D8 — Account credit / balance ledger: the customer's stored credit/balance — how credit is "
                "created (proration credit, refund-to-credit, goodwill, overpayment) and consumed (applied to "
                "reduce a future invoice total — Dep4). A monotonic, conserved ledger of credit movements "
                "(V-I1, V-I5)."
            ),
            criteria=(
                Criteria("credit_balance_create_consume",
                         "The customer's stored credit/balance: how credit is created (proration credit, "
                         "refund-to-credit, goodwill, overpayment) and consumed (applied to reduce a future "
                         "invoice total — Dep4)."),
                Criteria("credit_ledger_conserved",
                         "A monotonic, conserved ledger of credit movements — a ledger entry for every "
                         "credit/debit, no value minted or lost (V-I1, V-I5)."),
            ),
        ),
        HUMAN,
    ),
    (
        TaskId("d9_refund"),
        Spec(
            description=(
                "D9 — Refund (full & partial): reverse money already captured — a full or partial refund "
                "against a prior charge, bounded by what was actually captured (V-I6), routed either back to "
                "the payment method or to account credit (Dep5). Defines what a refund reverses including its "
                "tax portion (Dep6)."
            ),
            criteria=(
                Criteria("full_partial_refund",
                         "A full or partial refund that reverses money already captured against a prior "
                         "charge, bounded by what was actually captured (V-I6), routed either back to the "
                         "payment method or to account credit (Dep5)."),
                Criteria("refund_reverses_tax_portion",
                         "Defines what a refund reverses including its tax portion (Dep6) — a partial refund "
                         "reverses a proportional slice of the tax line, not just the base amount."),
            ),
        ),
        HUMAN,
    ),
]

# ─── Criterion mappings ──────────────────────────────────────────────────────
# Every root criterion must map to ≥1 child (CHECK-1 coverage).
# Every child must appear in ≥1 mapping (CHECK-1b non-redundancy).
criterion_mappings = [
    # V-I1 money_conservation → D5 proration, D8 credit, D9 refund, D4 invoice
    CriterionMapping("money_conservation", TaskId("d5_proration")),
    CriterionMapping("money_conservation", TaskId("d8_credit")),
    CriterionMapping("money_conservation", TaskId("d9_refund")),
    CriterionMapping("money_conservation", TaskId("d4_invoice")),

    # V-I2 charge_idempotency → D7 charge/dunning
    CriterionMapping("charge_idempotency", TaskId("d7_charge_dunning")),

    # V-I3 invoice_reconciles → D4 invoice, D5 proration, D6 tax, D8 credit
    CriterionMapping("invoice_reconciles", TaskId("d4_invoice")),
    CriterionMapping("invoice_reconciles", TaskId("d5_proration")),
    CriterionMapping("invoice_reconciles", TaskId("d6_tax")),
    CriterionMapping("invoice_reconciles", TaskId("d8_credit")),

    # V-I4 tax_at_event_time → D6 tax, D3 cycle
    CriterionMapping("tax_at_event_time", TaskId("d6_tax")),
    CriterionMapping("tax_at_event_time", TaskId("d3_cycle")),

    # V-I5 append_only_ledger → D4 invoice, D7 charge_dunning, D8 credit, D9 refund
    CriterionMapping("append_only_ledger", TaskId("d4_invoice")),
    CriterionMapping("append_only_ledger", TaskId("d7_charge_dunning")),
    CriterionMapping("append_only_ledger", TaskId("d8_credit")),
    CriterionMapping("append_only_ledger", TaskId("d9_refund")),

    # V-I6 no_over_refund → D7 charge_dunning, D9 refund
    CriterionMapping("no_over_refund", TaskId("d7_charge_dunning")),
    CriterionMapping("no_over_refund", TaskId("d9_refund")),

    # V-I7 entitlement_coupled_to_payment → D1 lifecycle, D7 charge_dunning
    CriterionMapping("entitlement_coupled_to_payment", TaskId("d1_lifecycle")),
    CriterionMapping("entitlement_coupled_to_payment", TaskId("d7_charge_dunning")),

    # V-I8 exactly_once_cycle_advancement → D1 lifecycle, D3 cycle, D7 charge_dunning
    CriterionMapping("exactly_once_cycle_advancement", TaskId("d1_lifecycle")),
    CriterionMapping("exactly_once_cycle_advancement", TaskId("d3_cycle")),
    CriterionMapping("exactly_once_cycle_advancement", TaskId("d7_charge_dunning")),

    # D2 pricing → V-I3 invoice_reconciles: D2 produces the base amount, which V-I3's truth-maker lists
    # explicitly ("base ± proration − credit + tax"). A broken base price breaks the reconciled total →
    # D2 is load-bearing for V-I3. This is D2's non-redundancy anchor (CHECK-1b). [Judgment call: the
    # reference prose's V-I3 span-list omits D2, but its text names "base", which only D2 supplies.]
    # V-E/V-F carry NO root mapping — they are criteria of their owning child node (1:1 with the reference).
    CriterionMapping("invoice_reconciles", TaskId("d2_pricing")),
]

# ─── Decompose root — save children directly (no FSM event loop needed) ──────
# Store criterion mappings on root first
root_task.criterion_mappings = tuple(criterion_mappings)
engine._graph.save_task(root_task)

# Save each child task
for child_id, spec, assignee, *_ in children:
    child_task = Task(id=child_id, spec=spec, assignee=assignee, parent_id=TaskId("billing"))
    engine._graph.save_task(child_task)

# ─── Dependency edges Dep1..Dep10 ────────────────────────────────────────────
# Direction: from_id = the upstream capability; to_id = the downstream capability
# (from_id's output feeds to_id's input — i.e. to_id depends on from_id's output)
# Dep is CRITERIA-CONTENT (§2.2): a dependency = a criterion on the CONSUMER (to_id) referencing the
# producer (from_id)'s output — the glue. The DepEdge is DERIVED from these (graph.dep_edges()). This
# offline builder writes the criterion directly (no event loop); live callers go through the FSM.
def declare_dep(from_id, to_id, glue=""):
    t = engine._graph.get_task(to_id)
    crit = Criteria(name=f"dep__{from_id}", description=glue, depends_on=from_id)
    t.spec = Spec(t.spec.description, t.spec.criteria + (crit,), t.spec.accepted_risks, t.spec.risk_components)
    engine._graph.save_task(t)


# Dep1: D5 proration → D6 tax  (tax base = prorated amount, not gross)
declare_dep(
    TaskId("d5_proration"), TaskId("d6_tax"),
    glue=(
        "Dep1 — Tax on the prorated amount (tax base = net, not gross): tax must be computed on the "
        "prorated amount, not the full-period price. The proration output is the taxable base; computing "
        "tax on the gross plan price over-charges tax on a mid-cycle change. Shared artifact: the net "
        "taxable amount on the invoice."
    ),
)

# Dep2: D8 credit → D6 tax (credit-vs-tax ordering; then D6 tax → D4 total)
declare_dep(
    TaskId("d8_credit"), TaskId("d6_tax"),
    glue=(
        "Dep2 — Tax base after credit application (credit-vs-tax ordering): whether account credit reduces "
        "the taxable base or only the post-tax payable must be a defined order, applied consistently. The "
        "wrong order computes tax on an amount the customer never effectively pays (or under-taxes). Shared "
        "artifact: what the tax line is computed on once credit is in play."
    ),
)

# Dep3: D5 proration → D2 pricing (then both feed D4 total)
# mid-cycle plan change = credit old at old rate + charge new at new rate, netted
declare_dep(
    TaskId("d5_proration"), TaskId("d2_pricing"),
    glue=(
        "Dep3 — Mid-cycle plan change: credit old + charge new at correct rates: an upgrade/downgrade "
        "mid-period must credit the unused portion of the old plan at the old rate AND charge the "
        "used/remaining portion of the new plan at the new rate, netted on one invoice — not charge the "
        "full new plan, not forget the old-plan credit. Shared artifact: the single net proration "
        "credit+debit pair on the change event."
    ),
)

# Dep4: D8 credit → D4 invoice total (credit application reduces invoice total)
declare_dep(
    TaskId("d8_credit"), TaskId("d4_invoice"),
    glue=(
        "Dep4 — Credit application reduces the invoice total: available account credit must be applied to "
        "reduce the amount charged to the payment method, drawing down the balance by exactly the applied "
        "amount (no credit created or lost). Consumption is single-apply even under parallel invoice runs "
        "— the same credit can't be spent twice. Shared artifact: the credit-applied line on the invoice "
        "and the corresponding balance debit."
    ),
)

# Dep5: D9 refund → D8 credit (refund routing & mixed-tender split)
declare_dep(
    TaskId("d9_refund"), TaskId("d8_credit"),
    glue=(
        "Dep5 — Refund routing & mixed-tender split (card portion to card, credit portion to balance): a "
        "refund must go either back to the original payment method or to account credit (per policy), and "
        "exactly once. On a mixed-tender charge (part paid from balance/credit, part captured to the card), "
        "the refund must split by tender — the card-paid portion returns to the card and the credit-paid "
        "portion returns to balance. Shared artifact: the refund disbursement(s) and their per-tender "
        "destination."
    ),
)

# Dep6: D9 refund → D6 tax (refund reverses proportional tax)
declare_dep(
    TaskId("d9_refund"), TaskId("d6_tax"),
    glue=(
        "Dep6 — Refund reverses the tax portion correctly: a refund of a taxed charge must reverse the "
        "proportional tax as well as the base (a partial refund reverses a proportional slice of the tax "
        "line). Refunding only the base leaves the customer credited for tax they paid; refunding the gross "
        "as if untaxed over-refunds. Shared artifact: the tax slice of the refunded amount."
    ),
)

# Dep7: D2 currency → D4 total (currency & rounding consistency across all line items)
# Also spans D5 proration and D6 tax — edges represented from D2 as the currency-origin
declare_dep(
    TaskId("d2_pricing"), TaskId("d4_invoice"),
    glue=(
        "Dep7 — Currency & rounding consistency across all line items (one rounding regime, one currency): "
        "every line item (base, proration, credit, tax) must be in the same currency and rounded under one "
        "defined regime so the rounded parts reconcile to the rounded total (no sub-cent leakage from "
        "rounding each part independently). Shared artifact: the rounding/currency convention applied "
        "uniformly across D2, D4, D5, D6."
    ),
)

# Dep8: D1 lifecycle → D5 proration (lifecycle transition × proration boundary)
declare_dep(
    TaskId("d1_lifecycle"), TaskId("d5_proration"),
    glue=(
        "Dep8 — Lifecycle transition × proration boundary (pause/cancel/reactivate billing consequence): "
        "pause, cancel, and reactivate each have a billing consequence relative to the period boundary — "
        "cancel mid-period = refund/credit the unused portion or run-to-period-end; pause = stop accrual "
        "and shift the anchor/extend the period on resume; reactivate = resume billing from the correct "
        "anchor without double-charging the already-paid period. Shared artifact: the period/anchor "
        "accounting across the transition."
    ),
)

# Dep9: D1 trial state → D7 charge/dunning (trial→paid conversion; first real charge can fail)
declare_dep(
    TaskId("d1_lifecycle"), TaskId("d7_charge_dunning"),
    glue=(
        "Dep9 — Trial→paid conversion × dunning (first real charge can fail): the trial→paid transition "
        "triggers the first real charge, which can be declined — so conversion must route through the "
        "dunning/retry path (stay in a grace/past_due state, retry, not silently grant paid access on a "
        "failed first charge), and must not charge during the trial. Shared artifact: the "
        "conversion-triggered first invoice and its success/failure handling."
    ),
)

# Dep10: D7 charge/dunning → D8 credit (credit consumed then card charge fails → credit restored)
declare_dep(
    TaskId("d7_charge_dunning"), TaskId("d8_credit"),
    glue=(
        "Dep10 — Credit consumed then card charge fails → credit restored, never lost: when an invoice "
        "draws down balance/credit (Dep4) and then the card charge for the remaining amount fails, the "
        "consumed credit must be rolled back / restored to the balance (and re-applied on the next retry), "
        "not silently burned. A reversing ledger entry. Shared artifact: the credit draw-down entry and its "
        "compensating restore on charge failure."
    ),
)

# ─── Trigger a final check recompute (no event loop — do it manually) ────────
engine._recompute_checks(TaskId("billing"))

# ─── Run checks ──────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("get_checks('billing'):")
print("=" * 70)
checks = engine.get_checks(TaskId("billing"))
any_fail = False
for c in checks:
    status = "SKIPPED" if c.skipped else ("PASS" if c.passed else "FAIL")
    detail = f" — {c.details}" if c.details and not c.passed else ""
    print(f"  [{status}] {c.check_name}{detail}")
    if not c.skipped and not c.passed:
        any_fail = True

if any_fail:
    print("\n*** FAILURES DETECTED — fix the transcription script ***")
    sys.exit(1)
else:
    print("\nAll non-skipped checks PASS.")

# ─── Projection ──────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("project('billing'):")
print("=" * 70)
projection = engine.project(TaskId("billing"))
sys.stdout.buffer.write(projection.encode("utf-8", errors="replace") + b"\n")

# ─── Summary ────────────────────────────────────────────────────────────────
root = engine.get_task(TaskId("billing"))
child_list = engine.get_children(TaskId("billing"))
dep_list = engine.get_dependencies()
sibling_deps = [
    e for e in dep_list
    if any(c.id == e.from_id for c in child_list)
    and any(c.id == e.to_id for c in child_list)
]
print("\n" + "=" * 70)
print("Summary:")
print(f"  DB path:        {os.path.abspath(DB_PATH)}")
print(f"  Subtasks (D):   {len(child_list)}")
print(f"  Dep edges:      {len(sibling_deps)}")
print(f"  Root criteria:  {len(root.spec.criteria)}")
print(f"  ACCEPTED_RISKS: {len(root.spec.accepted_risks)}")
print("\nTo view in the UI:")
print(
    "  GFSO_STORAGE=sqlite GFSO_DB_PATH=data/t01_reference.db GFSO_NO_SEED=1 "
    "python -m gfso.cli serve"
)

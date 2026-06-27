# BLIND JUDGE VERDICT — T01, candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Subscription lifecycle FSM — States: {trialing, active, grace_period, past_due, paused, canceled}; all transitions must be declared and exhaustive" (cand D8) | state machine driving billing |
| D2 | D | — | COVERED | "Represent each plan as (amount, currency, billing_period ∈ {monthly, annual})" (cand D1) | price + period |
| D3 | D | — | COVERED | "compute billing periods as half-open intervals [start, end) anchored to a declared timezone; derive next-period boundary" (cand D1) | cand fuses D2+D3; credited by truth-maker (Appendix). Clock=timezone anchor; clamp via V18 |
| D4 | D | — | COVERED | "Build invoice as Σ(line_items) + tax − applied_credits" (cand D3) | assembly hub |
| D5 | D | — | COVERED | "Proration calculator — Compute proration_factor = days_remaining / days_in_current_period" (cand D2) | |
| D6 | D | — | COVERED | "Compute tax_amount = taxable_base × rate(country, plan_type, effective_date) ... determine taxable_base per country as either tax-inclusive (back-compute net) or tax-exclusive (gross-up)" (cand D4) | incl/excl present |
| D7 | D | — | COVERED | "Charge & dunning engine — Issue every charge attempt with an idempotency key; build dunning schedule ... transition subscription to a declared terminal state after max retries" (cand D6) | |
| D8 | D | — | COVERED | "Credit ledger — Maintain running account_balance = Σcredit_ledger_entries − Σdebit_ledger_entries" (cand D5) | |
| D9 | D | — | COVERED | "Refund processor — Compute full_refund ... partial_refund = explicitly specified amount ≤ net paid" (cand D7) | |
| Dep1 | Dep | FM-1 | COVERED | "Each proration line (credit and charge) carries its own independent tax computation" (cand Dep-1) | tax keyed to prorated line amounts, not gross plan price |
| Dep2 | Dep | FM-1,2 | COVERED | "if a credit reduces the invoice amount the taxable base must be recomputed on the reduced amount before tax is finalized" (cand Dep-14) | credit-vs-tax base/order defined |
| Dep3 | Dep | FM-1 | COVERED | "apply to credit (old_plan_price) and charge (new_plan_price); for annual↔monthly direction, use price-per-day = plan_price / days_in_period" (cand D2) | credit old + charge new at correct rates |
| Dep4 | Dep | FM-1,2 | COVERED | "apply credits before the charge attempt; enforce balance ≥ 0" (cand D5) + "the credit debit must not be re-applied" (cand Dep-23) | apply-and-decrement; single-apply leg via Dep-23 |
| Dep5 | Dep | FM-1,2 | NOT-COVERED | | cand names "select refund destination (original payment method vs. account credit) explicitly" (D7) but never the **mixed-tender split** (card-paid→card, credit-paid→balance). Per reference Appendix settled rule, naming "refund to card or credit" without the per-tender split **fails Dep5** |
| Dep6 | Dep | FM-1 | COVERED | "A refund on a taxed invoice must include the proportional tax portion, not only the pre-tax amount" (cand Dep-12) | |
| Dep7 | Dep | FM-1,2 | COVERED | "A single rounding strategy ... applied consistently to all monetary division operations" (cand V26) + "All line items, tax, and credits on one invoice share the same currency" (cand V5) | one currency + one regime |
| Dep8 | Dep | FM-1 | COVERED | "A single paused interval must shift the annual renewal date by the exact pause duration" (cand Dep-10) | lifecycle×proration/anchor; also cand Dep-6/Dep-9/Dep-25 |
| Dep9 | Dep | FM-1 | COVERED | "If the payment gateway is unavailable at trial end, the subscription must be routed into dunning retry logic, not transitioned to canceled" (cand Dep-16) | trial-conversion first charge can fail→dunning; no-charge-in-trial via V13/V14 |
| Dep10 | Dep | FM-1,2 | COVERED | "if a charge attempt fails and is retried, the credit debit must not be re-applied ... ledger shows a double debit; account balance goes negative" (cand Dep-23) | binds credit draw-down to charge across failure+retry so credit not lost/double-counted |
| V-I1 | V | FM-1 | COVERED | "account_balance = Σcredit_ledger_entries − Σdebit_ledger_entries at all times; every credit or debit event has a corresponding ledger row" (cand V3) | conservation / no mint-or-vanish |
| V-I2 | V | FM-1 | COVERED | "Processing the same charge event twice produces exactly one charge record; no duplicate revenue entry and no double-charge" (cand V2) | |
| V-I3 | V | FM-1 | COVERED | "invoice_total = Σ(line_items) + tax − applied_credits at finalization" (cand V1) | |
| V-I4 | V | FM-1,2 | COVERED | "The tax rate applied to an invoice is the rate effective at invoice issue date, not at period start or payment date" (cand V6) | |
| V-I5 | V | FM-1 | COVERED | "Seal as an immutable document on finalization" (cand D3) + "the document is immutable thereafter — no retroactive mutation" (cand V1) | append-only / reversal not edit (write-off→bad-debt entry, Dep-28) |
| V-I6 | V | FM-1 | COVERED | "Total refunds on an invoice cannot exceed total net amount collected (gross charges minus all prior partial refunds on the same invoice)" (cand V8) | + non-negative charge via V10/V11 |
| V-I7 | V | FM-1 | NOT-COVERED | | entitlement↔payment coupling ("no paid access without a successful charge") absent; cand **excludes entitlement** (N5 "Product catalog / feature entitlement is out of scope"). V19 is the dunning terminal (→V-F3), not entitlement-grant-on-payment |
| V-I8 | V | FM-1,2 | COVERED | "Every subscription in {trialing, active, past_due} has exactly one open billing period; none has zero or more than one" (cand V9) | exactly-once/period; deterministic ordering via V17 + D8 "silent overwrite and dual-fire at renewal are both invalid" |
| V-E1 | V | FM-3 | COVERED | "At a scheduled plan-change firing at the renewal boundary, exactly one invoice topology must be declared: (a) a single invoice ... or (b) a closing invoice ... plus a separate opening invoice" (cand D3) | old-vs-new-period rule at the boundary instant |
| V-E2 | V | FM-3 | COVERED | "For the n-th plan change in one period, old_plan_price must equal the price of the (n−1)-th plan, not the original plan's price" (cand D2) | stacked prorations compose |
| V-E3 | V | FM-3 | NOT-COVERED | | no sub-day / very-short-remainder / last-day proration case named (V12 is the day-1 full-period case, the opposite boundary) |
| V-E4 | V | FM-3 | NOT-COVERED | | tax-exempt / zero-rate jurisdiction / B2B reverse-charge not named as a defined zero-tax rule. V21 guards null tax "in a taxable jurisdiction" but does not define the exempt path |
| V-E5 | V | FM-3 | COVERED | "No invoice, no line items, and no refund attempt are present in the output when a subscription is canceled while still in trial" (cand V14) | + trial conversion at trial_end (D8) |
| V-E6 | V | FM-3 | COVERED | "When applied credits fully cover the invoice, amount_due = 0 and no charge attempt is issued" (cand V10) | |
| V-E7 | V | FM-3 | NOT-COVERED | | smallest-unit / zero-decimal-currency (JPY) / half-cent boundary values not named (V26 is regime-consistency = Dep7, not the boundary values) |
| V-E8 | V | FM-3,4 | COVERED | "When cancellation and reactivation timestamps fall on the same calendar day, their ordering is determined by timestamp; the subscription is not left in an inconsistent state" (cand V17) | ordering corner with stated rule; also Dep-5 cancel-during-dunning |
| V-F1 | V | FM-7 | NOT-COVERED | | no reconciliation/confirmation channel for an ambiguous/timed-out charge before retry; cand relies on idempotency keys (=V-I2) and treats "pending" as an input outcome (N1), not a reconcile-before-retry rule. Per Appendix, bare idempotency ≠ V-F1 |
| V-F2 | V | FM-5 | NOT-COVERED | | no **plan-price** point-in-time pinning / grandfathering of a committed period. D4 has a versioned tax-rate table (the V-I4 half), but the V-F2 keep-reason (plan-price snapshot) is absent |
| V-F3 | V | FM-6 | COVERED | "After all dunning retries are exhausted, the subscription is in a declared terminal state; it is not left active with no collection path and dunning does not run indefinitely" (cand V19) | bounded terminal |
| V-F4 | V | FM-1 | COVERED | "per-line rounding on a multi-line invoice accumulates penny errors; V1 fails by $0.01; a partial refund individually satisfies V8 but over-refunds by the rounding residual" + "invoice_total = Σ(rounded line_items) + rounded_tax − applied_credits must hold exactly" (cand V26) | names independent-rounding-breaks-reconciliation + over-refund-by-residual; credited per Appendix rounding-triplet merge rule |
| N1 | N | FM-1 | NOT-COVERED | | proration-basis & rounding-**policy as an assumed external input** not declared; cand specifies proration time-based (D2) and rounding in-scope (V26), not a parameterized exclusion |
| N2 | N | FM-1 | NOT-COVERED | | tax rates / jurisdiction / nexus "supplied by an external tax engine" not declared as a scope exclusion (D4 reads a rate table but does not exclude rate/jurisdiction/nexus determination) |
| N3 | N | FM-1 | COVERED | "Payment gateway communication — Sending charge requests to the gateway is infrastructure; this scope receives only the outcome (success / failed / pending) as input" (cand N1) | |
| N4 | N | FM-1 | COVERED | "Posting to the general ledger is downstream of invoice creation; GL consumes finalized invoices. In only if revenue-recognition rules (ASC 606) ..." (cand N4) | |
| N5 | N | FM-1 | COVERED | "Detecting abnormal charge patterns is a separate system; billing logic does not gate on fraud scores" (cand N6) | fraud excluded (core of ref N5) |
| N6 | N | FM-1 | COVERED | "Discounts and coupon codes that modify the billed amount are not listed in the task's capability set and are out of scope" (cand N8) | |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D3 | 3 | 2 | V18 "Feb 29 annual anniversary ... rolled to Feb 28"; Dep-18 "use the actual period length ... not a constant 365" |
| Dep3 | 3 | 2 | V24 "annual→monthly downgrade credit rate"; V25 "upgrade invoice contains both the full annual charge line and the remaining monthly-days credit line" |
| Dep4 | 2 | 1 | Dep-22 "proration credit ... placed by exactly one mechanism: either as a negative line item ... or as a ledger entry" |
| Dep8 | 7 | 6 | Dep-6 cancel×annual proration; Dep-9 resume-charge covers remaining days; Dep-25 additive multi-pause extension; Dep-11 pause×dunning past_due gate; Dep-31 pause-extension service-days exclusion; Dep-29 annual→monthly anchor |
| Dep9 | 3 | 2 | Dep-2 trial-end×credit consumed; Dep-3 trial-end triggers full annual charge; Dep-32 trial-end no-payment-method (one folded) |
| V-I1 | 2 | 1 | Dep-13 "A refund issued as account credit must write a ledger entry" |
| V-I4 | 2 | 1 | V21 "Every finalized invoice in a taxable jurisdiction carries a non-null, correctly computed tax_amount" |
| V-I5 | 2 | 1 | Dep-28 "write-off ... must atomically trigger a bad-debt ledger entry; a void transition must not" |
| V-I6 | 2 | 1 | Dep-19 "refundable base ... is invoice_total − applied_credits (net amount charged), not the gross" |
| V-I8 | 3 | 2 | V4 "No two billing periods for the same subscription overlap"; D8 scheduled-change "silent overwrite and dual-fire at renewal are both invalid" |
| V-E1 | 3 | 2 | V12 "A plan change on day 1 ... proration credit = 0, new-plan charge = full period"; Dep-30 renewal-boundary topology × Dep-4 applicability |
| V-E2 | 2 | 1 | Dep-20 "Credits from the first plan change must be reflected ... before computing the second proration charge" |
| V-E5 | 2 | 1 | V13 "A zero-length trial produces the same result as an immediate paid subscription" |
| V-E6 | 3 | 2 | V11 "When credits exceed the invoice total, the excess is added to account balance"; V28 "Tax on a zero-amount invoice"; Dep-26 zero-amount non-initiation (one folded) |
| V-E8 | 3 | 2 | Dep-5 "Cancellation during active dunning must declare whether the unpaid invoice is voided or remains collectible"; V20 "No charge record is created for a subscription whose status is canceled" |

**Total ballast points ≈ 27.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| Dep-4 "An outstanding unpaid invoice must be resolved ... before or alongside any new plan charge when the subscription is in past_due" | UNMATCHED — human review |
| Dep-7 "Unused account credits at cancellation must be assigned one declared fate: refunded to customer, forfeited, or held for reactivation" | UNMATCHED — human review |
| Dep-15 "Account-level credits apply across all subscriptions; dunning on one subscription must not trigger cancellation of other ... subscriptions" | UNMATCHED — human review (multi-subscription; reference is single-subscription) |
| Dep-17 "Tax country is re-evaluated at reactivation date, not inherited from the canceled subscription record" | UNMATCHED — human review (reference treats jurisdiction as external N2) |
| Dep-21 "A plan change must not be finalized until any pending charge attempt ... has settled" | UNMATCHED — human review (concurrency; reference scopes T01 as sequential not race) |
| Dep-24 "mid-active-period billing-country change ... exactly one policy must be declared" | UNMATCHED — human review (country-change; jurisdiction is external N2) |
| Dep-27 "two concurrent refund requests both pass V8 individually before either commits ... over-refund" | UNMATCHED — human review (concurrency atomicity) |
| V7 "Every charge attempt is traceable to exactly one invoice; no orphaned charge attempt exists" | UNMATCHED — human review |
| V22 "No refund record is created against a charge attempt that has not yet reached a terminal gateway state" | UNMATCHED — human review |
| V23 "No credit balance decrement is attributed to a subscription with status = canceled" | UNMATCHED — human review |
| V27 "A plan-change request where new_plan_id = current_plan_id must be rejected or treated as a no-op" | UNMATCHED — human review |
| N2 "Email / notification dispatch ... is a side effect of state transitions, not calculation logic" | UNMATCHED — human review |
| N3 "Payment method storage / tokenization — The card-token vault is infrastructure" | UNMATCHED — human review |
| N5 "Product catalog / feature entitlement is out of scope" | UNMATCHED — human review (reference scopes entitlement IN, as V-I7) |
| N7 "Multi-currency FX rates — Out if all plans are denominated in a single currency" | UNMATCHED — human review (reference deliberately folds FX into Dep7, not a NEGLECTED item) |

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 9/9   Dep = 9/10   V = 14/20   N = 4/6
  by FM tag:     FM-1 = 21/25   FM-2 = 6/7   FM-3 = 5/8   FM-4 = 1/1   FM-5 = 0/1   FM-6 = 1/1   FM-7 = 0/1
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 27
  unmatched candidate points (human-review flag):    total = 15
```

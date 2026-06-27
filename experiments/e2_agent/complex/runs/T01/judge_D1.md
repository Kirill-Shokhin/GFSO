# BLIND JUDGE VERDICT — T01 / candidate D1

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note (missing leg / which candidate points) |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Subscription lifecycle FSM — States: {trialing, active, past_due, paused, canceled}; all transitions must be declared and exhaustive" | cD8 |
| D2 | D | — | COVERED | "Represent each plan as (amount, currency, billing_period ∈ {monthly, annual})" | cD1 (price+period leg) |
| D3 | D | — | COVERED | "compute billing periods as half-open intervals [start, end) anchored to a declared timezone; derive next-period boundary as prev.end = next.start with no gap and no overlap" | cD1 (period-boundary leg); cV18 (Feb-29 clamp) → ballast |
| D4 | D | — | COVERED | "Invoice assembly — Build invoice as Σ(line_items) + tax − applied_credits" | cD3 |
| D5 | D | — | COVERED | "Proration calculator — Compute proration_factor = days_remaining / days_in_current_period ... apply to credit (old_plan_price) and charge (new_plan_price)" | cD2; cDep-18 (leap-year denominator) → ballast |
| D6 | D | — | COVERED | "Tax computation ... determine taxable_base per country as either tax-inclusive (back-compute net) or tax-exclusive (gross-up)" | cD4 |
| D7 | D | — | COVERED | "Charge & dunning engine — Issue every charge attempt with an idempotency key; build dunning schedule ... transition subscription to a declared terminal state after max retries" | cD6 |
| D8 | D | — | COVERED | "Credit ledger — Maintain running account_balance = Σcredit_ledger_entries − Σdebit_ledger_entries; write a ledger row on every credit or debit event" | cD5 |
| D9 | D | — | COVERED | "Refund processor — Compute full_refund ... partial_refund ... select refund destination (original payment method vs. account credit)" | cD7 |
| Dep1 | Dep | FM-1 | COVERED | "Each proration line (credit and charge) carries its own independent tax computation" — tax computed on the prorated lines, not the full plan price | cDep-1 (candidate frames it as per-line vs net, but names the proration×tax base pair + breakage) |
| Dep2 | Dep | FM-2 | COVERED | "if a credit reduces the invoice amount the taxable base must be recomputed on the reduced amount before tax is finalized ... tax computed on gross then credit applied" | cDep-14 |
| Dep3 | Dep | FM-1 | COVERED | "A monthly→annual upgrade invoice contains both the full annual charge line and the remaining monthly-days credit line; neither is absent" | cV25 (credit-old + charge-new netted); cV24 (downgrade credit rate) → ballast |
| Dep4 | Dep | FM-2 | COVERED | "apply credits before the charge attempt" (credit reduces the charge; debit ledger row decrements balance) | cD5; missing the parallel-run single-apply / no-double-spend nuance (FM-2 leg), but the core "apply balance to lower the charge" is named. cDep-2, cDep-13 → ballast |
| Dep5 | Dep | FM-2 | NOT-COVERED | | Mixed-tender split (card-paid→card, credit-paid→balance) absent. Appendix binds: naming only "refund destination (card vs credit)" fails Dep5. cD7 names destination only |
| Dep6 | Dep | FM-1 | COVERED | "A refund on a taxed invoice must include the proportional tax portion, not only the pre-tax amount" | cDep-12 |
| Dep7 | Dep | FM-2 | PARTIAL | "Currency consistency — All line items, tax, and credits on one invoice share the same currency" | currency leg met; MISSING leg: one rounding regime / rounding defined once so parts reconcile (no rounding content anywhere in candidate) |
| Dep8 | Dep | FM-1 | COVERED | "Paused days must shift the annual renewal date by the exact pause duration" | cDep-10 (anchor shift); cDep-9 (resume charge), cDep-6 (cancel annual proration), cV15 (pause day-1) → ballast |
| Dep9 | Dep | FM-1 | COVERED | "If the payment gateway is unavailable at trial end, the subscription must be routed into dunning retry logic, not transitioned to canceled" | cDep-16 (first-conversion-charge-can-fail → dunning); cDep-3 → V-E5 |
| Dep10 | Dep | FM-2 | NOT-COVERED | | Credit-consumed-then-card-fails → restore/roll-back (reversing entry) absent; no candidate point asserts it |
| V-I1 | V | FM-1 | COVERED | "account_balance = Σcredit_ledger_entries − Σdebit_ledger_entries at all times; every credit or debit event has a corresponding ledger row" | cV3 (value conserved / every movement has a counterpart) |
| V-I2 | V | FM-1 | COVERED | "Charge idempotency — Processing the same charge event twice produces exactly one charge record; no duplicate revenue entry and no double-charge" | cV2 |
| V-I3 | V | FM-1 | COVERED | "invoice_total = Σ(line_items) + tax − applied_credits at finalization" | cV1 (total leg) |
| V-I4 | V | FM-1, FM-2 | COVERED | "The tax rate applied to an invoice is the rate effective at invoice issue date, not at period start or payment date" | cV6 |
| V-I5 | V | FM-1 | COVERED | "seal as an immutable document on finalization" (corrections via "issue a credit note for every refund") | cD3 + cD7 → ballast |
| V-I6 | V | FM-1 | COVERED | "Refund ≤ net paid — Total refunds on an invoice cannot exceed total net amount collected" | cV8; non-negative-charge leg carried by zero/negative-invoice criteria. cDep-19 → ballast |
| V-I7 | V | FM-1 | NOT-COVERED | | Entitlement↔payment coupling absent: no "no paid access without a successful charge / revoke on dunning give-up." Candidate has no entitlement/access concept |
| V-I8 | V | FM-1, FM-2 | COVERED | "Active subscription ↔ open period — every subscription in {trialing, active, past_due} has exactly one open billing period; none has zero or more than one" | cV9 (exactly-once per period); cV4 (no overlap) → ballast |
| V-E1 | V | FM-3 | COVERED | "Same-day plan change — A plan change on day 1 of the billing period produces: proration credit = 0, new-plan charge = full period (no division-by-zero, no 100% credit on the old plan)" | cV12 (boundary-instant rule defined) |
| V-E2 | V | FM-3 | COVERED | "multiple plan changes in one period — Credits from the first plan change must be reflected in the credit balance before computing the second proration charge" | cDep-20 (stacked prorations compose, net conserved) |
| V-E3 | V | FM-3 | NOT-COVERED | | Sub-day / very-short-remainder proration + rounding-artifact case absent (no rounding content) |
| V-E4 | V | FM-3 | NOT-COVERED | | Tax-exempt / zero-rate jurisdiction rule absent |
| V-E5 | V | FM-3 | COVERED | "Cancellation during trial — No invoice, no line items, and no refund attempt are present ... when a subscription is canceled while still in trial" | cV14 + cD8 (trial_end anchored, one trial-converted event); cV13, cDep-3 → ballast |
| V-E6 | V | FM-3 | COVERED | "Zero-amount invoice — When applied credits fully cover the invoice, amount_due = 0 and no charge attempt is issued" | cV10; cV11 (negative invoice → excess to balance) → ballast |
| V-E7 | V | FM-3 | NOT-COVERED | | Currency/rounding boundary (sub-cent, zero-decimal currency, half-cent) absent |
| V-E8 | V | FM-3, FM-4 | COVERED | "No charge to a canceled subscription ... even if a dunning retry job was enqueued before the cancellation" (cancel-during-dunning corner with stated resolution) | cV20; truth-maker credits any one corner. NOTE: FM-4 substance (backdated change → correcting memo) is itself absent, but item scores COVERED on the FM-3 corner per its truth-maker. cV17, cDep-5 → ballast |
| V-F1 | V | FM-7 | NOT-COVERED | | Ambiguous/timed-out charge → reconciliation channel (gateway query/webhook) before retry absent. Candidate has idempotency (V-I2) and pending-charge gating (cV22/cDep-21) but not the ambiguous-outcome resolution — appendix binds |
| V-F2 | V | FM-5 | NOT-COVERED | | Plan-price point-in-time pinning at invoice generation absent. Candidate covers tax-rate versioning only (=V-I4 half); appendix: do not credit the tax half for V-F2 |
| V-F3 | V | FM-6 | COVERED | "Dunning terminal state — After all dunning retries are exhausted, the subscription is in a declared terminal state ... dunning does not run indefinitely" | cV19 |
| V-F4 | V | FM-1 | NOT-COVERED | | Rounding-residual allocation across split line items absent (no rounding content) |
| N1 | N | FM-1.b | NOT-COVERED | | Proration/rounding policy as a stated external input not declared |
| N2 | N | FM-1.b | NOT-COVERED | | Tax rates/jurisdiction/nexus supplied by external tax engine not declared (candidate treats the rate table as in-scope) |
| N3 | N | FM-1.b | COVERED | "Payment gateway communication — Sending charge requests to the gateway is infrastructure; this scope receives only the outcome (success / failed / pending) as input" | cN1 |
| N4 | N | FM-1.b | COVERED | "In only if revenue-recognition rules (ASC 606) determine when a charge line is booked" — GL/rev-rec downstream | cN4 |
| N5 | N | FM-1.b | COVERED | "Fraud detection — Detecting abnormal charge patterns is a separate system; billing logic does not gate on fraud scores" | cN6 (fraud leg of N5) |
| N6 | N | FM-1.b | NOT-COVERED | | Coupons / promotional discounts out-of-scope (distinct from account credits) not declared |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D3 | 2 | 1 | cV18 "Feb 29 annual anniversary ... rolled to Feb 28" (vs primary cD1 period boundaries) |
| D5 | 2 | 1 | cDep-18 "D2 must use the actual period length ... not a constant 365" (vs primary cD2) |
| Dep3 | 2 | 1 | cV24 "Annual→monthly downgrade credit rate ... annual_price × (days_remaining / days_in_year)" (vs primary cV25) |
| Dep4 | 3 | 2 | cDep-2 "existing account credit must be consumed before the first charge attempt"; cDep-13 "all subsequent invoices must consume the resulting balance" (vs primary cD5) |
| Dep8 | 4 | 3 | cDep-9 "the charge covers only the days remaining at pause"; cDep-6 "Immediate cancellation of an annual plan must apply a declared ... refund"; cV15 "Pause on day 1 ... full period ... no charge for the paused interval" (vs primary cDep-10) |
| V-I5 | 2 | 1 | cD7 "issue a credit note for every refund" (vs primary cD3 immutable seal) |
| V-I6 | 2 | 1 | cDep-19 "refundable base ... is invoice_total − applied_credits (net amount charged), not the gross invoice total" (vs primary cV8) |
| V-I8 | 2 | 1 | cV4 "No overlapping active periods" (vs primary cV9) |
| V-E5 | 3 | 2 | cV13 "Zero-day trial ... no trial-converted event is emitted"; cDep-3 "trial-conversion event triggers a full annual charge" (vs primary cV14) |
| V-E6 | 2 | 1 | cV11 "Negative invoice — ... the excess is added to account balance and no outbound payment is triggered" (vs primary cV10) |
| V-E8 | 3 | 2 | cV17 "Same-day cancellation and reactivation ... ordering is determined by timestamp"; cDep-5 "Cancellation during active dunning must declare whether the unpaid invoice is voided or remains collectible" (vs primary cV20) |

**Total ballast points = 16.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| cDep-4 "An outstanding unpaid invoice must be resolved (paid, voided, or merged) before or alongside any new plan charge when the subscription is in past_due" | UNMATCHED — human review |
| cDep-7 "Unused account credits at cancellation must be assigned one declared fate: refunded to customer, forfeited, or held for reactivation" | UNMATCHED — human review |
| cDep-8 "On reactivation, any unpaid invoice from the prior dunning cycle must be explicitly handled (revived, written off, or merged) before a new invoice is created" | UNMATCHED — human review |
| cDep-11 "A subscription in past_due must not enter pause until payment is resolved, or pausing must continue dunning retries without interruption" | UNMATCHED — human review |
| cDep-15 "Account-level credits apply across all subscriptions; dunning on one subscription must not trigger cancellation of other, healthy subscriptions on the same account" | UNMATCHED — human review |
| cDep-17 "Tax country is re-evaluated at reactivation date, not inherited from the canceled subscription record" | UNMATCHED — human review |
| cDep-21 "A plan change must not be finalized until any pending charge attempt on the current subscription has settled (success or failure)" | UNMATCHED — human review |
| cV7 "Charge attempt ↔ invoice linkage — Every charge attempt is traceable to exactly one invoice; no orphaned charge attempt exists" | UNMATCHED — human review |
| cV16 "Resume on boundary day of max pause window ... treated as a valid resume; no auto-cancellation is triggered" | UNMATCHED — human review |
| cV21 "Tax completeness at finalization — Every finalized invoice in a taxable jurisdiction carries a non-null, correctly computed tax_amount" | UNMATCHED — human review |
| cV22 "No refund against a pending charge ... that has not yet reached a terminal gateway state" | UNMATCHED — human review |
| cV23 "Credits not consumed by canceled subscription — No credit balance decrement is attributed to a subscription with status = canceled" | UNMATCHED — human review |
| cN2 "Email / notification dispatch ... is a side effect of state transitions, not calculation logic" | UNMATCHED — human review |
| cN3 "Payment method storage / tokenization — The card-token vault is infrastructure" | UNMATCHED — human review |
| cN5 "Product catalog / feature entitlement ... is out of scope; calculation needs only plan price and billing period" | UNMATCHED — human review |
| cN7 "Multi-currency FX rates — Out if all plans are denominated in a single currency" | UNMATCHED — human review |

**Total unmatched candidate points = 16.**

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 9/9   Dep = 7/10   V = 13/20   N = 3/6
  by FM tag:     FM-1 = 15/20   FM-2 = 4/7   FM-3 = 5/8   FM-4 = 1/1   FM-5 = 0/1   FM-6 = 1/1   FM-7 = 0/1
  PARTIAL counts: D = 0   Dep = 1   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 16
  unmatched candidate points (human-review flag):    total = 16
```

# search_2 — New Holes in D1 (T01)

Pass 2. Items D1 does not already cover. Each has a distinct falsifier.

---

**H1. Rounding / monetary precision** — No component or invariant declares the rounding strategy for monetary division (proration_factor × price, tax rate × base) — per-line vs. per-invoice application, and which rounding mode (half-up, banker's rounding). *Falsifier: per-line rounding on a multi-line invoice accumulates penny errors; invoice_total = Σ(line_items) + tax − applied_credits fails V1 by $0.01; a partial refund passes V8 individually but the rounded total over-refunds.*

**H2. Invoice lifecycle states** — D3 models assembly and immutability at finalization but has no state model for invoices (draft → open → finalized → voided → written-off). Dunning (Dep-5 voided vs. collectible), cancellation (Dep-6 annual refund), and reactivation (Dep-8 old debt) all require distinguishing void from write-off, but neither state nor its transitions are declared. *Falsifier: a written-off invoice is treated as voided and removed from the dunning ledger without emitting a bad-debt ledger entry; a voided invoice is retried by dunning because no terminal state stops it.*

**H3. Proration credit disposition — ledger entry vs. direct line item** — D2 computes the proration credit but no Dep seam between D2 and D5 declares whether the credit is placed directly as a negative line item on the new invoice (immediate offset) or written as a ledger entry in D5 for future application. *Falsifier: credit written to the ledger AND placed as a line item on the same invoice double-credits the customer; credit written only to the ledger but not applied to the current invoice leaves the customer charged the full new-plan price this period.*

**H4. Scheduled plan change × intervening lifecycle event** — D8 declares "plan-change effective date = next renewal (no proration)" but no seam or FSM transition handles what happens to a pending scheduled change when the subscription is paused, enters past_due, or is canceled before the scheduled renewal date. *Falsifier: a downgrade scheduled at next renewal survives cancellation; on reactivation the scheduled change fires against the new billing period and wrongly prorates the new subscription.*

**H5. Credit application idempotency across D6 retries (D5 × D6)** — D6 carries an idempotency key for the charge attempt, and D5 writes a ledger row for every credit event, but no seam declares that the credit-debit against the invoice is tied to the charge idempotency key. On a dunning retry, the credit application path may re-execute. *Falsifier: first charge attempt debits credits from D5 then fails; retry path re-runs credit application and debits again; ledger shows double debit; account balance goes negative; V3 fails silently because balance-check runs before the second debit is committed.*

**H6. Mid-active-period billing-country change (D4 → D3)** — Dep-17 covers reactivation × country change. No seam covers a customer updating their billing country while the subscription is active (not canceled). Two policies must be declared and only one chosen: (a) new rate applies only from next invoice (current open invoice unaffected), or (b) current open invoice tax is recalculated. *Falsifier: policy (b) retroactively mutates a finalized invoice, violating V1; policy (a) applied without declaration allows an implementer to choose either path, producing different tax amounts for identical inputs.*

**H7. Multiple pause/resume cycles — additive period extension** — V15 and D8 model a single pause/resume. No component or invariant declares that two or more pause/resume cycles within the same billing period extend the period by the sum of all pause durations. *Falsifier: second resume resets the extension to only the second pause duration; customer loses credit for the first pause interval and is charged for days they did not receive service.*

**H8. Coupon / discount — missing scope exclusion (N)** — Discounts and coupon codes that modify the billed amount before proration or tax are not listed in T01's capabilities and are not declared as a scope exclusion in N. *Falsifier: an implementer adds discount logic without recognizing it is out of scope; applying a percentage discount after proration_factor is computed produces a different result than applying it before; the scope boundary is silently violated with no declared "why out" or pull-back condition.*

**H9. Same-plan "change" as no-op** — No component, invariant, or FSM transition declares that a plan-change request where new_plan_id = current_plan_id must be rejected or treated as a no-op producing no invoice and no ledger entry. *Falsifier: the plan-change code path executes normally; D2 computes proration_factor × old_price as credit and new_price as charge; the net result is a $0 invoice with two equal and opposite lines — but D6 may still initiate a $0 charge attempt (violating V10) and D3 creates an invoice that complicates the audit trail.*

**H10. Plan change during trial — FSM gap** — D8's FSM models trial_end → active conversion and plan-change while active, but has no declared transition for a plan change while the subscription is in the trialing state. Three policies are possible and only one must be chosen: (a) plan change takes effect immediately, trial converts now; (b) plan change is staged for trial_end; (c) plan change applies to the new plan with the original trial end date preserved. *Falsifier: plan change during trial silently converts the subscription to active (no trial_converted event), billing the customer for a period they were promised free; or trial end fires a second trial_converted event on a subscription already marked active.*

**H11. D3 → D6 zero-amount invoice non-initiation seam** — V10 states the outcome (no charge attempt when amount_due = 0) as a criterion, but there is no Dep seam capturing the D3 → D6 handoff with its own mechanism and falsifier. *Falsifier: D6 receives the finalized invoice, skips the amount_due check, and issues a $0 authorization to the gateway; some gateways accept and log $0 charges as valid transactions, creating a charge record that violates V7 (every charge attempt must be traceable to a chargeable invoice) because the corresponding invoice has no receivable.*

**H12. Refund attempt idempotency** — D7 models refund amount computation and credit note issuance but declares no idempotency key for the refund attempt itself. V8 enforces total refunds ≤ net paid as a post-hoc invariant but does not prevent two concurrent refund requests from both passing the V8 check before either commits to the ledger. *Falsifier: a refund request times out at the gateway and the caller retries; two refund records are created, each individually passing V8 (each ≤ net paid); together they exceed net paid; the over-refund is only caught by reconciliation, not by any billing-logic gate.*

**H13. Tax on a zero-amount invoice (credits cover full invoice)** — V10 and Dep-14 interact at this edge: when applied credits fully reduce amount_due to $0, D4 must still declare whether tax = $0 (customer paid nothing, no taxable supply) or tax = the computed amount (taxable supply occurred, covered by a credit instrument). *Falsifier: tax reported as $0 on a fully-credit-covered invoice in a jurisdiction that treats credits as payment means a taxable supply went unreported; tax authority audit reveals the discrepancy; conversely, reporting non-zero tax on a $0 invoice may require a separate tax credit note not modeled in D7.*

---

## Count

| Category | New items |
|----------|-----------|
| Missing D components        | 0 |
| Missing Dep seams           | 6 (H3, H5, H6, H7, H11, H12) |
| Missing V / global invariants | 3 (H1, H9, H13) |
| Missing N entries           | 1 (H8) |
| FSM / lifecycle gaps        | 2 (H2, H4, H10) |
| **Total new holes**         | **13** |

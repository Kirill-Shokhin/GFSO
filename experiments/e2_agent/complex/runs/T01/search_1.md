# Search pass 1 — T01 Subscription Billing Logic

---

## 1. Domain Primitives (10)

**Plan price** — Each plan has a canonical price expressed as amount + currency + billing period (monthly or annual) — *currency mismatch or period mismatch causes wrong charge amount.*

**Billing period** — A billing period is a half-open interval [start, end) with an explicit timezone anchor — *DST boundary or timezone drift inserts a free day or double-bills a day.*

**Proration factor** — Days remaining in current period divided by total days in the current period, computed in billing timezone — *February, 31-day months, and leap years each give a different denominator; off-by-one is the bug.*

**Invoice line item** — A single quantity × unit price × period-attribution entry that traces back to exactly one subscription period — *orphaned line items not tied to a period cause revenue leakage with no audit trail.*

**Invoice** — An immutable sealed document after finalization; total = sum(line items) + tax − applied credits — *mutable invoice allows retroactive tampering of the audit trail.*

**Tax amount** — Tax computed per invoice against the taxable base using the rate effective at invoice issue date — *wrong effective date picks a stale or future rate after a tax law change.*

**Credit note** — A negative-value document that offsets a prior invoice when a refund is issued — *refund recorded only as a ledger debit without a credit note breaks double-entry bookkeeping.*

**Account balance** — Running ledger balance: credit events add, charge events subtract — *balance drifts from the sum of ledger entries if events are applied out of order or without a corresponding ledger write.*

**Charge attempt** — A single payment-gateway request with an explicit outcome (success / failure / pending) — *missing idempotency key causes a double-charge on network retry.*

**Dunning schedule** — Ordered list of retry intervals and escalation actions, each anchored to the charge-failure timestamp — *schedule not anchored to failure time allows indefinite or incorrectly-timed retries.*

---

## 2. Lifecycle / State (10)

**Subscription status state machine** — Valid states: trialing → active → past_due → paused → canceled; all transitions must be explicit and exhaustive — *implicit or missing transitions leave status inconsistent with billing events.*

**Trial start / end anchoring** — Trial end is computed from trial start timestamp, not from subscription creation timestamp — *signup delay shifts the trial-end date, charging the customer earlier than communicated.*

**Trial conversion event** — At trial end the subscription emits exactly one "trial converted" event that triggers the first real charge — *no explicit event causes conversion to be skipped if trial end falls on a non-business day or gateway is unavailable.*

**Period boundary determination** — Next period start = previous period end (no gap, no overlap) — *rounding or day-counting bug inserts a free day or bills a day twice.*

**Pause state entry** — Pause begins at an explicit timestamp; whether it is immediate or at the next period boundary is a declared policy — *wrong default gives the customer access they did not pay for, or denies access they did.*

**Pause state exit (resume)** — Resume is triggered by a scheduled end-of-pause date or a manual action; billing resumes from the resume date — *resume anchored to original period start re-bills the paused days.*

**Period extension on pause** — Paused days either extend the current billing period or start a fresh period on resume; policy must be declared — *two conformant implementations diverge on the next renewal date.*

**Cancellation effective date** — Cancel is either immediate or at end-of-period; proration and refund logic differ for each path — *undeclared default applies the wrong path silently.*

**Reactivation anchor** — On reactivation of a canceled subscription, new period start = reactivation date — *reactivation anchored to the original-start date charges or credits a wrong amount on the first new invoice.*

**Plan change effective date** — Plan change is either immediate (proration applies) or at next renewal (no proration); the two paths are mutually exclusive — *proration applied to a "change at renewal" generates an incorrect credit.*

---

## 3. Calculation Components (10)

**Proration credit calculation** — Credit = old_plan_price × (days_remaining / days_in_current_period) — *using calendar days vs billing-period days produces different amounts in months of different lengths.*

**Proration charge calculation** — Charge = new_plan_price × (days_remaining / days_in_current_period) — *upgrade recorded without a corresponding credit double-bills the customer.*

**Annual-to-monthly proration** — Days remaining in the annual period must be mapped to the annual price per day, not monthly price per day — *dividing annual price by 12 then prorating gives a systematically different amount than dividing by days_in_year.*

**Tax calculation per country** — Tax amount = taxable_base × rate(country, plan_type, effective_date) from a versioned rate table — *unversioned rate table applies a new rate to already-finalized invoices after a tax law change.*

**Tax base determination** — Tax base calculation requires knowing whether product price is tax-inclusive or tax-exclusive per country — *treating EU tax-inclusive prices as tax-exclusive inflates stated price and reports wrong net revenue.*

**Credit application order** — Credits are applied before or after tax computation; policy must be explicit and applied uniformly — *inconsistent order inflates tax in cases where credits are subtracted after the taxable base is established.*

**Credit balance floor** — Account balance cannot go below zero as a result of a credit application — *negative balance passes undetected until the payment gateway rejects a negative-amount charge.*

**Partial refund amount** — Partial refund = an explicitly specified amount ≤ net amount paid on the invoice; never re-derived from the current plan price — *re-deriving after a plan change gives the wrong refund if the plan has changed since the original charge.*

**Full refund amount** — Full refund = total amount paid on the invoice (gross charges minus any prior partial refunds on the same invoice) — *issuing a second full refund on a partially-refunded invoice over-refunds the customer.*

**Refund destination selection** — Refund to original payment method vs. refund to account credit are two distinct code paths; selection is explicit — *always refunding to payment method fails silently when the payment method has expired.*

---

## 4. Global Invariants (9)

**Invoice total invariant** — invoice_total = sum(line_items) + tax − applied_credits must hold at finalization and must never be mutated afterward — *credit applied post-finalization breaks the total without regenerating the document.*

**Idempotency of charge events** — Processing the same charge event twice must produce exactly one charge record — *retry without idempotency key creates duplicate revenue and a customer-facing double-charge.*

**Ledger balance consistency** — account_balance = sum(all credit ledger entries) − sum(all debit ledger entries) at all times — *crediting the balance without writing a ledger entry creates a phantom balance that reconciliation cannot explain.*

**No overlapping active periods** — Two billing periods for the same subscription must not overlap in time — *plan change that creates a new period without closing the old one bills the customer for two concurrent periods.*

**Currency consistency** — All line items, tax, and credits on one invoice must share the same currency — *mixed-currency invoice silently produces an incorrect total when entries are summed.*

**Tax-period consistency** — The tax rate applied to an invoice is the rate effective at the invoice issue date, not at period start or payment date — *rate change mid-period produces wrong tax if the period-start rate is used instead.*

**Charge attempt ↔ invoice linkage** — Every charge attempt must be traceable to exactly one invoice — *orphaned charge attempt means revenue was collected with no corresponding invoice.*

**Refund ≤ net paid** — Total refunds on an invoice cannot exceed total amount collected (charges minus prior refunds) — *over-refund is possible if refund validation is against the gross invoice total rather than net paid.*

**Active subscription ↔ open period** — Every subscription in trialing / active / past_due state has exactly one open billing period — *active subscription with no open period never generates a charge.*

---

## 5. Cross-Component Interaction Seams (21)

**Plan-change × proration × tax** — Mid-period plan change produces a credit line and a new-plan charge line; each line carries its own tax; tax must not be computed on the combined net — *computing tax on the net proration amount gives wrong tax in jurisdictions with minimum thresholds or tiered rates.*

**Trial-end × credit balance** — If account balance > 0 at trial conversion, credits must be consumed before the first real charge is attempted — *first charge ignores existing credits; customer is charged more than owed.*

**Trial-end × annual plan** — First charge after trial conversion uses the annual price; no day-offset from the trial period is applied to the annual billing amount — *trial-day proration applied to the annual price produces a partial-year charge on the first invoice.*

**Dunning × plan-change** — If subscription is past_due and customer upgrades, the outstanding unpaid invoice must be resolved (paid, voided, or merged) before or alongside the new plan charge — *upgrade creates a new invoice while old invoice remains unpaid; which one dunning pursues becomes ambiguous.*

**Dunning × cancellation** — Cancellation during dunning must declare whether the unpaid invoice is voided or remains collectible — *implicit void loses revenue; implicit keep blocks reactivation by requiring payment of an aged invoice.*

**Cancellation × proration (annual plan)** — Immediate cancellation of an annual plan: the remaining period may or may not generate a refund; policy must be declared and applied consistently — *undeclared policy gives different outcomes depending on which code path is reached.*

**Cancellation × credits** — Unused account credits at cancellation: refunded, forfeited, or held for reactivation; policy must be declared — *no policy causes credits to silently vanish or block account closure.*

**Reactivation × dunning debt** — Reactivating a subscription that was canceled while in dunning: the old unpaid invoice must be explicitly handled (revived, written off, or merged) — *reactivation creates a new invoice while the old debt is silently written off or counted twice.*

**Pause × billing period** — Mid-period pause: days elapsed before pause were already due; on resume the charge must cover only the remaining days, not the full period — *resume issues a full-period charge, double-billing the pre-pause days.*

**Pause × annual plan** — Paused days must shift the annual renewal date by the exact pause duration — *renewal fires on original anniversary ignoring pause duration, cutting the customer's paid term short.*

**Pause × dunning** — A subscription in past_due state cannot enter pause until payment is resolved, or pausing must continue dunning retries — *pausing a past_due subscription halts retries; the unpaid invoice ages silently with no collection action.*

**Refund × tax** — Refund of a taxed invoice must include the proportional tax portion — *partial refund of the pre-tax amount leaves the customer under-refunded by the tax fraction.*

**Refund × credit balance** — Refund issued as account credit must increase the ledger balance; subsequent invoices must consume it — *credit created by the refund not reflected in the ledger causes future charges to ignore it.*

**Credit balance × tax** — If credit reduces the invoice amount, tax must be recomputed on the reduced base where jurisdiction rules require it — *tax computed on gross, credit applied after = customer pays tax on an amount they were credited back.*

**Annual × monthly co-existence** — Customer holds two active subscriptions simultaneously; account-level credit balance applies across both; dunning on one must not cancel the other — *dunning logic that cancels all account subscriptions cancels a healthy subscription alongside the delinquent one.*

**Plan-change × annual-to-monthly downgrade** — Credit for remaining annual days is computed as annual_price × (days_remaining / days_in_year), not as unused-full-months × monthly_price — *unused-months calculation under-credits the customer by partial-month fractions.*

**Plan-change × monthly-to-annual upgrade** — Annual charge is issued immediately; a credit for the remaining monthly days must be issued on the same invoice — *annual charge without the monthly-days credit double-bills the customer for the overlap.*

**Trial × gateway-down at conversion** — If the payment gateway is unavailable at trial end, the first charge attempt fails; subscription must retry via dunning, not be canceled immediately — *gateway-down marks subscription past_due or canceled instead of queuing a retry.*

**Cancellation × reactivation × country change** — Customer reactivates from a different billing country; tax country re-evaluated at reactivation, not inherited from the canceled record — *old tax country used on the first post-reactivation invoice produces wrong tax.*

**Proration × leap year** — Annual plan proration uses days_in_year; a period spanning Feb 29 has 366 days; the denominator must match the actual period — *using 365 as a constant for an annual period containing a leap day is an off-by-one error.*

**Credit application × partial refund** — If a credit was applied to reduce an invoice, the refundable base is the net amount charged (invoice_total − applied_credit), not the gross invoice total — *refund issued against gross total refunds more than the customer actually paid.*

---

## 6. Edge / Boundary Cases (15)

**Zero-amount invoice** — After credits fully cover the invoice, amount due = 0; no charge attempt is made — *zero-amount charge attempt triggers a gateway rejection or an unnecessary transaction fee.*

**Negative invoice** — Credits exceed invoice total; excess rolls over to account balance; no outbound payment is triggered — *negative invoice enters a payout code path that does not exist, or leaves a dangling balance that never clears.*

**Same-day plan change** — Plan changed on day 1 of the period: proration credit = 0, new-plan charge = full period — *division-by-zero or 100%-credit applied to the old plan when days_remaining = days_in_period.*

**Plan change on last day of period** — Proration factor ≈ 0 for both credit and charge; behaviorally equivalent to "change at renewal" — *micro-transaction clutter from a near-zero credit and charge pair; may need a threshold to suppress.*

**Zero-day trial** — Trial length = 0 is equivalent to immediate paid subscription; must not emit a "trial converted" event — *zero-day trial emits conversion event; first charge applied twice.*

**Cancel during trial** — No charge has occurred; cancellation generates no invoice, no line items, no refund — *cancellation logic attempts to prorate a zero-amount charge, producing invalid zero-value line items.*

**Pause on day 1 of period** — Entire period is paused; on resume, the full period must be provided with no charge for the paused interval — *day-1 pause followed by full-period charge on resume double-bills the entire period.*

**Resume on last day of pause window** — If pause has a maximum allowed duration, resuming on the boundary day must be treated as valid, not expired — *boundary resume treated as expired triggers auto-cancellation instead of resume.*

**Reactivation same day as cancellation** — Both events carry timestamps on the same calendar day; ordering must be determined by timestamp, not date — *same-day reactivation leaves subscription in an inconsistent state when only calendar date is used.*

**Multiple plan changes in one period** — Two plan changes before next renewal; credits from the first change must be reflected in the balance before computing the second — *each change computed against the original plan price; accumulated credits not considered; customer over-charged.*

**Annual plan with Feb 29 anniversary** — Annual renewal scheduled on Feb 29; next non-leap year must roll to Feb 28 — *system attempts to schedule Feb 29 in a non-leap year; date-arithmetic exception thrown.*

**Country change mid-period** — Customer updates billing country during an active period; new tax rate applies from the next invoice, not retroactively — *tax retroactively recalculated on already-finalized invoices; immutability invariant violated.*

**Dunning max retries reached** — After all retries exhausted, subscription transitions to a declared terminal state — *no terminal dunning state causes the loop to run indefinitely or leave the subscription active with no collection path.*

**Charge in flight during plan change** — Plan change requested while a charge attempt is pending; outcome depends on whether the charge succeeds or fails — *plan change recorded before the charge result arrives; if the charge fails, plan is upgraded with no payment.*

**Grace period before dunning** — Some products offer a brief grace window after a failed charge before dunning starts; this is a modeled state, not an implicit delay — *grace period not modeled as a state causes dunning to start immediately or never, depending on scheduler timing.*

---

## 7. Silent Failure Modes (10)

**Credit applied without ledger entry** — Account balance updated in memory or cache; ledger row not written — *balance vs. ledger-sum reconciliation diverges over time; discovered only at audit.*

**Tax omitted on upgrade charge** — Upgrade proration charge issued at net-of-credit; no tax line added to the invoice — *tax-exclusive-country invoice passes validation but creates a compliance gap.*

**Proration credit in wrong currency** — Plan price is in USD; credit line issued in local currency without conversion — *currency mismatch passes invoice-schema validation but overcharges the customer after conversion.*

**Dunning retry fires on canceled subscription** — Dunning job runs against a subscription whose status changed to canceled after the job was enqueued — *customer charged post-cancellation; dunning retry must re-check subscription status at execution time.*

**Tax finalized before rate retrieved** — Invoice total locked asynchronously before tax service responds; tax amount arrives late and is not applied to the total — *invoice total and tax-line amount are inconsistent; customer charged wrong amount.*

**Proration computed against wrong period** — Proration uses next-period dates instead of current-period dates — *credit or charge spans wrong dates; customer over- or under-credited with no visible error.*

**Double-invoice on trial conversion** — Trial-end scheduler and billing scheduler both fire at the same instant; two invoices created for the same conversion event — *trial conversion event not idempotency-guarded; customer charged twice.*

**Pause not recorded in period ledger** — Subscription paused and resumed correctly; paused days not written as a ledger entry — *audit log cannot reconstruct why the renewal date shifted; compliance exposure.*

**Refund before charge settles** — Charge attempt is still pending in the gateway; refund issued on the ledger before the charge settles — *charge settles after refund; net balance goes negative; customer receives more than paid.*

**Account-level credits consumed by canceled subscription** — Credits shared across subscriptions; a canceled subscription continues to consume balance that should serve a live one — *unexpected zero-invoices on the live subscription; credits disappear with no user action.*

---

## 8. Scope Boundaries (7)

**Payment gateway communication (OUT)** — Sending the charge request to the gateway is infrastructure, not calculation logic — *safely out: calculation logic is gateway-agnostic; pulled back in only if retry timing is governed by gateway response codes, which IS in scope as the dunning-schedule input signal.*

**Email / notification dispatch (OUT)** — Sending dunning emails or billing notices is not calculation — *safely out: notifications are side effects of state transitions; pulled back in only if email-send failure is required to gate a billing state change.*

**Payment method storage / tokenization (OUT)** — Vault of card tokens is infrastructure — *safely out: calculation receives "charge succeeded / failed" as input; pulled back in if payment method type affects tax treatment (e.g., B2B purchase order vs. consumer card).*

**Accounting / GL export (OUT)** — Posting to the general ledger is downstream of invoice creation — *safely out: GL export consumes finalized invoices; pulled back in if revenue-recognition rules (ASC 606) determine when a charge line is booked, affecting invoice timing.*

**Product catalog / feature entitlement (OUT)** — What features a plan grants is not billing logic — *safely out: calculation needs only plan price and billing period; pulled back in if entitlements affect proration (e.g., seat-based or usage-based billing).*

**Fraud detection (OUT)** — Detecting abnormal charge patterns is a separate system — *safely out: billing logic does not gate on fraud scores; pulled back in if a fraud-flagged charge must be voided before invoice finalization.*

**Multi-currency FX rates (BOUNDARY)** — If all plans are denominated in a single currency, out of scope; if plans are offered in multiple currencies, FX conversion rules for applying credits across currencies are in scope — *pulled back in as soon as a credit earned in one currency must be applied to an invoice in another.*

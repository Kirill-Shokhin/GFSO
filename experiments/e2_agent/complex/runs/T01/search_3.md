# search_3 — New holes relative to D2

Pass 3. D2 has 72 items (D×8, Dep×28, V×28, N×8). Listed below are requirements that are
genuinely absent or internally inconsistent in D2 and carry a distinct falsifier.

---

**H1. Grace period as a distinct FSM state**
D6 says "model grace period as an explicit subscription state"; D8's FSM states are
{trialing, active, past_due, paused, canceled} — grace_period is absent.
*Falsifier: past_due and grace_period are conflated; dunning fires immediately after a missed
payment instead of after the grace window; the customer is denied the declared grace period.*

**H2. Reactivation — first new-period invoice specification**
D8 anchors reactivation to reactivation_date, and Dep-8 requires the old dunning debt be
resolved, but no component specifies what is billed on reactivation: a full new period from
reactivation_date, a proration to the next natural renewal, or some other amount.
*Falsifier: reactivation charges a full annual amount even when the original renewal would
have fired in three days; or charges a prorated amount against an arbitrary anchor; both are
silent unless an explicit rule is declared.*

**H3. Multi-plan-change in one period — proration basis for the second change**
D2 computes proration_credit using old_plan_price, and Dep-20 identifies the bug when credits
are not reflected between changes. But neither D2 nor Dep-20 declares the rule: old_plan_price
for the n-th change must equal the (n−1)-th plan's price, not the original plan's price.
*Falsifier: second plan change computes its credit against the original plan price; first
intermediate plan's price is ignored; credit is wrong in both directions.*

**H4. Competing scheduled plan change — second request before first fires**
D8 declares that any pending scheduled plan change must be disposed on lifecycle transitions
(pause, past_due, cancellation), but says nothing about a new plan-change-at-renewal request
arriving while a prior scheduled change is already pending.
*Falsifier: second schedule silently overwrites the first with no audit record; or both fire
at the renewal boundary producing two consecutive plan-change events on the same invoice.*

**H5. Annual→monthly downgrade — new monthly billing period anchor**
V24 specifies the correct proration credit amount for an annual→monthly downgrade. No component
specifies when the first monthly billing period starts: from the change date, from the original
annual anniversary, or from the next natural month boundary.
*Falsifier: monthly billing period anchored to the original annual anniversary; the customer's
next monthly charge fires nine months in the future instead of one month; or the first monthly
charge is for a full month starting at the change date but the second fires before that month
elapses.*

**H6. Invoice topology when a scheduled plan change fires at the renewal boundary**
D3 requires every line item attributed to exactly one billing period. When a downgrade scheduled
at renewal fires, it is unspecified whether the system produces (a) a single invoice carrying
the new plan's charge for the new period, or (b) a closing invoice for the last old-period day
plus a separate opening invoice for the new period. This choice determines whether Dep-4
(outstanding invoice must be resolved before a new plan charge) applies at renewal-boundary
plan changes or only to mid-period changes.
*Falsifier: Dep-4 is enforced at renewal when (b) is chosen, blocking a routine scheduled
downgrade; or ignored at renewal when (a) is chosen, allowing a past_due renewal+downgrade
to produce two concurrent open invoices.*

**H7. Pause during active dunning — pause extension must exclude dunning days**
Dep-11 allows a past_due subscription to continue dunning retries while paused. If that path
is chosen, the additive pause extension that shifts the renewal date (Dep-10, Dep-25) should
cover only days the customer genuinely did not receive service, not days during which a dunning
retry was being processed. No component specifies this exclusion.
*Falsifier: subscription is past_due and paused for five days; dunning succeeds on day five;
resume extends the renewal date by five days; customer gains five paid days they were already
being collected against during the dunning window.*

**H8. Trial end with no payment method on file**
Dep-16 specifies the FSM path when the gateway is unavailable at trial end (→ dunning retry).
A distinct case is when no payment method exists at trial end: the gateway is available but
there is nothing to charge. The FSM transition is unspecified (past_due? a new "payment method
required" state? immediate cancellation?).
*Falsifier: trial ends with no payment method; system transitions to canceled instead of
preserving the subscription for the customer to add a payment method; or transitions to
active with no charge attempt ever issued.*

**H9. Max pause duration exceeded — declared state transition**
V16 tests the boundary of the max pause window, implying a maximum exists. D8's FSM policy
section never declares what state transition occurs when that maximum is exceeded: auto-cancel,
forced resume (and charge), or hold in paused with no further action.
*Falsifier: max pause window elapses; no declared transition; subscription remains in paused
indefinitely — no billing, no cancellation, no dunning; the customer retains access and the
merchant collects nothing.*

---

**Total genuinely new holes: 9**

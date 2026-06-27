# T04 — Search pass 2 (gap analysis against D1)

Input: task T04.md + canonical basis D1.md.
Scope: items genuinely absent or wrongly scoped in D1. Items already covered — even partially — are omitted.

---

## Missing subtasks / components

**Translation step (functional → presentation CCY)** — Translate each entity's functional-currency trial balance to presentation currency: P&L at period-average rate, balance sheet at closing rate, equity at historical rate; post the cumulative translation adjustment (CTA) to OCI as the balancing amount. *Falsifier: presentation-CCY column in the TB (D-13) has no documented population step; CTA not computed; V-14 asserts the distinction exists but no D-step produces the translated numbers.*

**Interface batch completion check** — Before the SL↔GL reconciliation (D-7), confirm that all sub-ledger-to-GL interface jobs ran to successful completion with zero errored or suspended records; obtain batch-run log signed off by IT or controller. *Falsifier: one overnight batch aborted silently after posting 40 % of records; D-7 reconciliation shows a difference that is attributed to timing rather than the broken job; root cause is never found.*

**Consolidation-level topside entries** — Post and review consolidation-layer policy-harmonization journals (e.g., LIFO-reserve elimination, useful-life harmonization, group-level provisions) in the consolidation-adjustment ledger before TB extraction; obtain approval for each topside. *Falsifier: V-17 acknowledges the consolidation-adjustment ledger exists, but no D-step posts to it; policy differences between entities remain in the consolidated TB without disclosure.*

---

## Missing interaction seams

**Rate table lock → bank reconciliation (functional-CCY column)** — The locked rate table must be available before D-9 computes the functional-currency equivalent of foreign-currency bank balances; the same rate used in revaluation must be used in the reconciliation to ensure the adjusted book balance equals the post-revaluation GL cash balance. *Breaks if absent: D-9 uses an unlocked or different rate to convert the bank statement; the functional-CCY adjusted-book figure does not agree to the GL balance after D-10 revaluation, creating a spurious unreconciled difference.*

**FX revaluation (D-10) → foreign-currency bank reconciliation sign-off (D-9)** — For accounts held in a foreign currency, D-10 changes the GL functional-currency cash balance after D-9 may already have been drafted; the functional-currency reconciliation (V-22) must be re-verified or performed after D-10 completes, not before. *Breaks if absent: D-9 reconciles functional-CCY using the pre-revaluation GL balance; after D-10 the GL balance changes; the signed reconciliation is stale and the cash balance on the signed-off TB is wrong.*

**IC accrual posting (D-8) → IC balance confirmation scope (D-11)** — If one entity accrues an IC service obligation that the counterparty has not yet recognised, D-11 will see an asymmetry; confirmation must explicitly cover timing differences caused by IC accruals (not just matched invoices), and resolution must distinguish a genuine discrepancy from an agreed accrual. *Breaks if absent: IC accrual in entity A treated as an unexplained out-of-balance in D-11; investigation time wasted; or worse, the accrual is reversed to force agreement, eliminating a real obligation.*

**IC interest accrual (D-8) → IC elimination (D-12)** — Interest income accrued in the lending entity and interest expense accrued in the borrowing entity are IC revenue/expense items that must appear in the IC entity matrix and be eliminated in D-12; D-8 posts them and D-12 must eliminate both legs. *Breaks if absent: IC interest expense and income both appear in the consolidated P&L; group profit is understated (or overstated) by the same amount with no netting.*

**Confirmed IC balance version → IC elimination (D-12)** — D-12 must run against the exact balance snapshot that was confirmed and agreed in D-11; any correction posted after D-11 sign-off requires a formal re-confirmation step before D-12 proceeds. *Breaks if absent: entity submits a corrected balance after D-11 concludes; D-12 eliminates the pre-correction amount; a residual IC difference appears in the consolidated TB that matches the size of the correction but is attributed to FX.*

---

## Missing global invariants / V criteria

**Each entity's TB nets to zero before consolidation** — Verify that every in-scope entity's trial balance nets to zero in its functional currency individually, before consolidation adjustments are applied; entity-level errors must not be masked by offsetting errors in another entity. *Falsifier: two entities each have a $200k imbalance in opposite directions; consolidated TB nets to zero; entity-level errors undetected until statutory filing.*

**Consolidated equity movement reconciliation** — Opening consolidated equity + period net income + OCI movements (CTA, long-term IC FX, hedging) + dividends declared + capital transactions = closing consolidated equity; verified as a formal reconciliation before sign-off. *Falsifier: CTA computed in the translation step is posted to OCI but never tied into the equity roll; equity movement note in the financial statements does not reconcile.*

**CTA / OCI balance movement reconciliation** — The net movement in each OCI component (CTA, IAS 21 §32 IC FX, IAS 29 restatement gains) agrees to the sum of the individual journal entries posted to those components during the period; running OCI balance agrees to cumulative posted amounts. *Falsifier: a translation rate changed mid-run; revaluation and translation both post to OCI but the CTA account has an extra debit with no matching journal; cumulative OCI drift undetected.*

**All journals in final state at hard close** — At the moment of hard close, every journal in the close period is in approved/posted status; no journal is left in draft, pending-approval, or error state; a completeness check is a hard prerequisite to D-14 sign-off. *Falsifier: large non-standard accrual stuck in pending-approval workflow; controller signs off the TB without knowing the approval is outstanding; accrual never posts.*

**Auto-reversal date correctness for all accrual entries** — Every journal posted with an auto-reversal flag carries a reversal date equal to the first day of N+1; the reversal-date field is validated at posting time and confirmed by a period-end report listing all staged reversals and their dates. *Falsifier: a recurring accrual template has a hard-coded reversal date from a prior month; reversal posts within period N; the accrual nets to zero in N and is absent from N+1 opening.*

**Revaluation run atomicity / completion status** — The FX revaluation job must report a completion status (success/failure/partial); any run that did not reach full-completion status must be treated as invalid and re-run; partial postings from an interrupted run must not stand as the close-period revaluation. *Falsifier: revaluation job times out after processing 600 of 900 open items; job scheduler marks it "completed with warnings"; controller treats warnings as informational; 300 open items unvalued at closing rate and V-25 re-run never triggered.*

**Rate freshness / staleness threshold** — Each currency's rate in the locked table must be sourced from a date no earlier than the close date (or, for non-trading-day close dates, the immediately preceding trading day); a staleness check is part of the rate-table lock sign-off. *Falsifier: feed gap over a long weekend; rate for a minor currency is 4 days stale at lock; revaluation uses a rate from before a central-bank announcement; FX gain/loss materially misstated.*

**Currency-rate presence for every active currency** — Before locking the rate table, verify that every currency code appearing in any open monetary item has a corresponding entry in the rate table; missing rates must produce a blocking error, not a silent zero-rate or skip. *Falsifier: a newly onboarded entity transacts in a currency not yet configured in the feed; revaluation silently skips those items; monetary exposure in that currency not remeasured.*

**GR/IR aging threshold enforcement** — GR/IR items aged beyond a defined threshold (e.g., 90 days) must be escalated, reclassified, or written off at close; the clearing account zero-net criterion (V-34) is necessary but not sufficient if old items are offset by new ones. *Falsifier: $300k GR/IR item aged 6 months offset by a new $300k item in the opposite direction; account nets to zero; old item never investigated; possible missed vendor invoice or phantom goods receipt.*

**Non-cash item GL tagging complete** — As the N-5 exception brings non-cash item tagging in scope, every journal line that is non-cash (depreciation, amortisation, unrealised FX, accruals without cash settlement) carries the designated non-cash indicator flag in the GL; completeness verified by running a report of non-cash-flag counts against expected categories before hard close. *Falsifier: new depreciation asset class added mid-year; its journals do not carry the non-cash tag; indirect-method cash flow statement incorrectly treats depreciation as a cash item.*

---

## Missing edge / boundary cases

**Mid-period entity acquisition** — A subsidiary acquired intra-period must be consolidated only from the acquisition date; the opening balance sheet at acquisition date is the purchase price allocation (PPA); P&L contribution runs from acquisition date only; IC eliminations apply only to post-acquisition transactions. *Falsifier: acquired entity consolidated from period start; pre-acquisition revenue included in group P&L; goodwill not recognised (PPA skipped).*

**Sub-consolidation cycles in multi-level group** — Where a sub-holding entity must produce its own consolidated TB before being fed into the parent consolidation, each consolidation level must complete its own IC elimination and produce a clean TB before the next level runs; the bottom-up ordering in D-12 must be explicit about which legal entity serves as the consolidated reporting unit at each level. *Falsifier: sub-holding's own IC eliminations are skipped; raw entity-level balances fed directly into ultimate-parent consolidation; eliminations at ultimate-parent level attempt to remove transactions already partially eliminated at sub-holding level, or miss them entirely.*

**Post-close period re-open under system constraint** — If a system upgrade or data migration forces reopening a hard-closed period, the re-open must generate a complete audit log (who authorised, what changed, timestamps), the TB must be re-extracted and re-signed, and the prior signed TB must be flagged as superseded; there is no silent re-open path. *Falsifier: DBA applies a hotfix directly to the database; GL balances change; the original signed TB remains in circulation and does not match the live ledger.*

---

## Wrong scope decisions

**Functional currency change (V-45 criteria exist, no D-step or N-scope treatment)** — V-45 specifies what correct behaviour looks like for a mid-period functional currency change, but there is no D-step handling the restatement work and no N-exclusion explicitly calling it out; a functional currency change is a significant event requiring dedicated close sub-steps (restate at date of change, split-period reporting, disclosure) that cannot be handled by the standard D-1–D-14 sequence alone. *Scope risk: a functional currency change occurs; the close proceeds through D-1–D-14 without triggering a formal restatement workflow; the resulting TB is produced at the wrong functional currency for part of the period.*

**Deferred tax journal entry (N-1 exception acknowledged but no D-step)** — N-1 explicitly keeps IAS 12 deferred tax journal entries in scope as an accrual-type step, but D-8 does not enumerate deferred tax as one of the accrual categories and there is no D-step or V criterion for the deferred tax computation, the temporary-difference schedule, or the journal entry; the exception is declared but not operationalised. *Scope risk: deferred tax provision omitted from the close journal; tax expense in the consolidated P&L is materially wrong; the auditor finds the gap that the close process itself was supposed to catch.*

---

## Count summary

| Category | New holes |
|---|---|
| Missing subtasks (D) | 3 |
| Missing interaction seams (Dep) | 5 |
| Missing global invariants / V | 9 |
| Missing edge / boundary cases (V) | 3 |
| Wrong scope decisions (N) | 2 |
| **Total** | **22** |

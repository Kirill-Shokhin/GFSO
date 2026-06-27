# T04 — Search pass 3 (gap analysis against D2)

New holes only — items genuinely absent from D2's D/Dep/V/N coverage.

---

## Missing dependency seams

**Dep-new-1: IC elimination (D-12) → translation (D-15)**
Translation must run on post-elimination functional balances; no dep currently orders D-12 before D-15.
*Falsifier: D-15 runs before D-12; presentation-CCY column translated from IC-inflated functional amounts; subsequent functional-currency elimination has no effect on the already-translated presentation column; IC revenue/expense survives in the presentation-CCY TB.*

**Dep-new-2: FX revaluation (D-10) → translation (D-15)**
D-15 translates functional balances to presentation; those balances must be post-revaluation; no dep currently orders D-10 before D-15.
*Falsifier: D-15 runs before D-10; presentation-CCY column derived from pre-revaluation functional amounts; the full closing-rate exposure is present in functional CCY but absent from presentation CCY; the two columns diverge for all monetary items.*

**Dep-new-3: Consolidation topside entries (D-17) → translation (D-15)**
Policy-harmonisation topsides are posted in functional currency; if D-15 runs first those entries are never translated and appear only in the functional-CCY column.
*Falsifier: D-15 runs before D-17; topside for LIFO-reserve elimination posts in EUR functional; presentation-CCY column omits the adjustment; functional and presentation columns differ by the topside amount with no CTA to explain it.*

**Dep-new-4: Sub-holding's own IC elimination complete → parent-level IC elimination (D-12)**
V-67 states the criterion but no Dep enforces the ordering: each sub-holding must finish its own elimination before being fed into the next consolidation level.
*Falsifier: sub-holding passes raw entity-level balances to parent; parent D-12 attempts to eliminate transactions already partially processed or never processed at the sub-holding level; double-elimination or missed elimination; residuals misattributed to FX.*

---

## Missing subtask

**D-new-1: Derivatives and hedge accounting close step**
Mark all open derivative contracts to fair value at period-end; split the fair-value movement into effective portion (OCI) and ineffective portion (P&L) per the designated hedge relationship; reclassify the effective OCI amount to P&L when the hedged item affects P&L in the same period (cash-flow hedge settlement or expiry); produce a hedge-effectiveness test result per relationship; post the resulting journals and retain the supporting test workpaper.
V-61 references hedging as an OCI component but no D subtask, no Dep seam, and no V criterion covers the mark-to-market mechanics, effectiveness split, or OCI reclassification trigger. Without this step, derivative fair-value movements are unposted and the OCI balance is incomplete.
*Falsifier: cash-flow hedge matures in period N; settlement gain of $2M sits in OCI from prior period; no reclassification journal is triggered; P&L understated by $2M; OCI overstated by $2M; both errors persist on the TB.*

---

## Missing V criteria

**V-new-1: Sub-ledger lock is system-enforced, not advisory**
For each sub-ledger (AR, AP, inventory, FA, payroll), the lock applied in D-2 through D-6 must be system-enforced: a posting attempt to the locked period is rejected by the system, not merely flagged for manual review. V-9 covers GL period-status enforcement but does not extend to sub-ledger locks.
*Falsifier: AR sub-ledger lock is a manual flag; operator posts a late cash receipt to the locked period; AR balance increases; sub-ledger ↔ GL reconciliation (D-7) was already signed off; discrepancy not re-detected; GL control account and sub-ledger diverge silently.*

**V-new-2: Prior-period unrealised IC profit released when goods sold externally**
V-30 covers elimination of unrealised profit on current-period intragroup transfers but not the mirror requirement: when goods transferred intragroup in a prior period are sold to an external party in the current period, the previously eliminated profit must be released back into consolidated cost of sales. Without an explicit criterion, the prior-period elimination entry remains permanently, understating the group's cost recovery.
*Falsifier: subsidiary transferred goods at $100k markup in N-1; parent sold the goods externally in N; the $100k elimination debit from N-1 remains in opening consolidated inventory; consolidated cost of sales in N is overstated by $100k relative to actual group cost; group margin understated.*

**V-new-3: Historical exchange-rate record maintained per equity component for translation**
D-15 requires equity components to be translated at historical rates; this is only possible if the system records the exchange rate at the date each equity event occurred (share issuance, retained-earnings layer, other reserves). No V criterion verifies that this rate-history record exists, is complete, and is used.
*Falsifier: an entity issued shares in three tranches at different rates; the system uses a single blended rate labelled "historical"; CTA absorbs the difference silently; the CTA balance cannot be reconciled to individual equity transactions; auditor cannot verify translation.*

**V-new-4: Goods in transit cut-off — receiving entity accrual complete**
Where title passes at point of shipment (FOB shipping point or equivalent), inventory in transit at period-end is the receiver's asset and liability; the receiving entity must record an accrual for goods shipped but not yet physically received. D-4 covers goods movements and D-8 covers accruals and GR/IR, but neither explicitly addresses this cut-off rule.
*Falsifier: supplier ships $500k of goods on the 30th under FOB shipping point terms; goods arrive on the 3rd of next month; receiving entity posts no accrual; inventory and payables both understated by $500k; cut-off error undetected because GR/IR only triggers on system goods-receipt.*

**V-new-5: Post-elimination IC residual above materiality threshold blocks TB sign-off**
V-28 requires a post-elimination IC difference report but accepts residuals with documentation; V-5 imposes a materiality-triggered investigation before elimination but has no post-elimination equivalent. A material residual remaining after D-12 should be a blocking condition for D-14 sign-off, not merely a documented item.
*Falsifier: $400k IC elimination residual exists after D-12; classified as "FX difference — under review" and documented; TB signed; residual sits in consolidated equity with no resolution timeline; auditor finds unexplained balance six weeks later.*

**V-new-6: Intragroup fixed-asset transfer — consolidated depreciation adjusted to cost basis**
V-30 covers elimination of unrealised profit at the point of intragroup fixed-asset transfer but not the ongoing consequence: the consolidated depreciation charge must be based on the transferring entity's original cost, not the inflated transfer price paid by the receiving entity. Without this, the over-depreciation (on the markup) inflates consolidated operating expense every period for the remaining asset life.
*Falsifier: subsidiary sells machine (cost $800k, NBV $600k) to parent at $900k; $300k unrealised profit eliminated at consolidation in month of transfer; parent depreciates $900k over 3 years = $25k/month; consolidated depreciation should be based on $800k = $22.2k/month; $2.8k/month over-depreciation runs silently for 36 months; cumulative error $100k.*

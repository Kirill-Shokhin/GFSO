# T04 — BLIND JUDGE VERDICT — candidate D1

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Post all invoices, credit notes, cash receipts, and write-offs with transaction date ≤ cutoff; lock the AR sub-ledger to the close period" (D-2; same pattern D-3..D-6) | sub-ledger close/freeze; per-Appendix split into AR/AP/Inv/FA/Payroll maps to D1 |
| D2 | D | — | COVERED | "Confirm payroll journal (gross pay, employer taxes, net pay, deductions) fully posted to GL"; "reconcile total balance to its GL control account" (D-6 / D-7) | posting sub-ledger totals to GL present (folded into the sub-ledger passes) |
| D3 | D | — | COVERED | "Post standard recurring accruals, non-standard manual accruals (with documented approvals), GR/IR accruals, prepaid amortisation… deferred revenue recognition" (D-8); "One-off estimates include documented business rationale, quantification methodology, and approver sign-off" (V-33) | (a) timing via D-8; (b) judgmental estimates/provisions via "non-standard manual accruals" + V-33 |
| D4 | D | — | COVERED | "apply closing rate… post unrealized FX gain/loss" (D-10); "partial payment realises gain/loss on the settled portion only" (V-23) | unrealized leg (D-10) + realized-on-settlement leg (V-23) both present |
| D5 | D | — | PARTIAL | "Eliminate IC AR/AP, revenue/expense, loans/receivables/payables, and investment/equity per the IC entity matrix" (D-12); "parent investment eliminated against post-elimination subsidiary equity" (V-29) | MISSING LEG: NCI computation (minority% × sub net assets). (a) IC + investment-elimination present; NCI not computed (and N-7 excludes "full minority interest computation") |
| D6 | D | — | COVERED | "match GL cash entries to bank lines… signed reconciliation (adjusted bank balance = adjusted book balance) per account" (D-9) | bank/sub-ledger recon to independent source |
| D7 | D | — | COVERED | "extract TB with transaction-CCY, functional-CCY, and presentation-CCY columns… verify zero-net" (D-13); "obtain controller sign-off; lock period (Hard-Close state)" (D-14) | TB assembly + sign-off (the hub) |
| D8 | D | — | COVERED | "Unrealised profit on inventory or fixed assets transferred between group entities is eliminated; only profit realised through external sale is recognised" (V-30) | IC profit-in-inventory, distinct from D5 |
| Dep0 | Dep | FM-1 | NOT-COVERED | | no opening-balance roll-forward from prior close, no P&L→retained-earnings close-out anywhere; V-10 is prior-period archive/comparatives, not the opening seam |
| Dep1 | Dep | FM-1 | COVERED | "Post all invoices… with transaction date ≤ cutoff; lock the AR sub-ledger to the close period" (D-2..D-6); "Sub-ledger lock (D-2/D-3) precedes accrual GR/IR scan" (Dep-7) | cutoff/freeze before the ledger feeds up |
| Dep2 | Dep | FM-2 | COVERED | "For each sub-ledger, reconcile total balance to its GL control account at line-item level" (D-7); "reconciliation performed at individual-line level" (V-20) | GL control = sub-ledger detail (shared artifact) |
| Dep3 | Dep | FM-1 | COVERED | "reversal lands in period N, netting out the accrual before TB is extracted" (Dep-14); accruals (D-8) sequenced before TB (D-13), "accruals… complete in GL" (Dep-3) | adjusting entries in GL before TB struck |
| Dep4 | Dep | FM-1 | COVERED | "Bank reconciliation sign-off (D-9) → TB sign-off (D-14)… Breaks: TB signed off with unverified cash balance" (Dep-13); "resolve all differences before proceeding" (D-7) | recon cleared before sign-off |
| Dep5 | Dep | FM-1 | COVERED | "FX revaluation (D-10) → IC elimination (D-12)… IC balances used for elimination must be post-revaluation balances… elimination on pre-revaluation balances" (Dep-8) | reval precedes consolidation (hard ordering seam) |
| Dep6 | Dep | FM-1 | COVERED | "IC elimination journals in GL (D-12) → trial balance extraction (D-13)… partially eliminated or unconsolidated view circulated as the consolidated TB" (Dep-11) | IC nets before consolidated TB |
| Dep7 | Dep | FM-2 | COVERED | "Confirm IC pairs… identify and resolve… all out-of-balance amounts before elimination" (D-11); "every IC transaction in entity A has a corresponding entry in entity B… before D-12" (V-5) | two-sided IC agreement before elimination; unmatched leaves residual |
| Dep8 | Dep | FM-2 | COVERED | "One rate table, locked before D-10, governs all currency-dependent steps (revaluation, translation, IC FX difference); no partial updates" (V-6) | single shared rate table feeds every consumer |
| Dep9 | Dep | FM-1 | COVERED | "All sub-ledger batches + accruals + payroll + depreciation complete in GL → FX revaluation (D-10)… late postings… not covered by revaluation; monetary exposure mis-stated" (Dep-3) | post precedes revaluation (stale balance) |
| Dep10 | Dep | FM-1 | COVERED | "assign auto-reversal dates to first day of N+1" (D-8); "Reversals are staged at D-14 hard close and released only when N+1 opens" (Dep-14) | accrual reversal carries to next period |
| Dep11 | Dep | FM-2 | COVERED | "partial payment realises gain/loss on the settled portion only; remaining open item continues to be revalued" (V-23) | realized-FX vs unrealized-revaluation must not double-count |
| V-I1 | V | FM-1 | COVERED | "Every journal entry in every sub-ledger and the GL has debits = credits" (V-1) | defining hub invariant |
| V-I2 | V | FM-2 | COVERED | "Sum of debit balances = sum of credit balances… verified independently in each currency column (transaction, functional, presentation)" (V-37) | per-currency balance, distinct from aggregate |
| V-I3 | V | FM-1 | COVERED | "TB includes every legal entity… verify zero-net in all currency columns" (D-13); presentation column nets to zero post-elimination (V-37) | consolidated/group TB nets to zero |
| V-I4 | V | FM-4+FM-1 | COVERED | "Every journal line carries exactly one period; no single entry spans two periods" (V-2) | each transaction in exactly one period |
| V-I5 | V | FM-1 | COVERED | "post-elimination IC difference report shows zero residual in all IC accounts (or residuals documented)" (V-28); "IC entity matrix complete and current" (V-16) | elimination completeness, exactly-once |
| V-I6 | V | FM-2 | COVERED | "gain/loss from each step posts to separate designated accounts" (V-14); "COA explicitly marks each account as monetary (revalue at closing rate) or non-monetary (historical rate)" (V-11) | uniform convention per item type + difference isolated to one line |
| V-I7 | V | FM-1 | PARTIAL | "Every journal line carries a unique, non-reusable ID; reversals reference the original entry ID; source document reference present" (V-40) | MISSING LEG: reproducibility (same inputs → same TB) not asserted; lineage leg met |
| V-I8 | V | FM-1 | COVERED | "All sub-ledger batches + accruals + payroll + depreciation complete in GL" (Dep-3); "TB includes every legal entity, every segment… and every account with any activity or balance" (V-38) | full posting roster complete, none silently dropped |
| V-I9 | V | FM-1 | COVERED | "A second revaluation run in the same period reverses and replaces the first; net revaluation balance is unchanged after re-run" (V-25) | idempotency under re-submission (re-run ≠ double-post) |
| V-I10 | V | FM-1 | COVERED | "Any non-zero suspense balance at hard close requires documented resolution; IC FX differences routed to suspense must be allocated before period lock" (V-51) | suspense/clearing drained to zero before TB |
| V-I11 | V | FM-1 | COVERED | "Sub-ledger-to-GL account mapping table is version-controlled; tested after any COA change; a broken mapping causes posting to a suspense account (detectable)" (V-19) | CoA mapping integrity (total, suspense identified) |
| V-I12 | V | FM-2 | PARTIAL | "Each legal entity has exactly one designated functional currency" (V-12) | MISSING LEG: consolidation hierarchy single-rooted/acyclic DAG not asserted; functional-currency leg met |
| V-E1 | V | FM-3+FM-2 | COVERED | "establish three rate types (spot/transaction, period-average, closing)" (D-1); "COA explicitly marks each account as monetary (revalue at closing rate) or non-monetary (historical rate)" (V-11) | rate-selection boundary per item type |
| V-E2 | V | FM-3 | COVERED | "Subsidiary sold intra-period consolidated only up to disposal date; IC eliminations apply only to that sub-period" (V-47) | partial-period entity, only in-scope slice consolidates |
| V-E3 | V | FM-4 | NOT-COVERED | | no pre-sign-off late-entry correction cascade (re-post→re-reval→re-eliminate→re-TB on a live, still-open close); V-8 is post-lock, ordering Deps are not the cascade |
| V-E4 | V | FM-3 | NOT-COVERED | | no rounding-residual / plug rule for sub-unit FX-translation differences anywhere |
| V-E5 | V | FM-3 | COVERED | "Inventory GL account balance reflects actual cost for all positions including negative quantities; negative inventory not suppressed to zero" (V-53) | negative/credit balance on a normally-debit account not dropped/suppressed |
| V-E6 | V | FM-3 | NOT-COVERED | | missing/stale-rate boundary is flagged (V-18/V-44 falsifiers) but NO defined fallback/hold rule (prior rate / hold close / flag) — truth-maker requires the fallback |
| V-E7 | V | FM-3 | COVERED | "AR and AP revalued at individual open-item level… remaining open item continues to be revalued" (V-23); "apply closing rate at open-item level (AR/AP)" (D-10) | revalue gross open-item FC positions, not net functional balance |
| V-F1 | V | FM-4 | NOT-COVERED | | no global "out-of-order pass yields a balanced-but-WRONG TB + dependency-ordering gate" statement; V-9 is period-status enforcement, not the ordering-gate/wrong-but-balanced insight |
| V-F2 | V | FM-3 | COVERED | "unusual movements investigated and explained; zero-net check alone is not sufficient for sign-off" (V-54) | balanced ≠ correct; independent analytic check beyond balance |
| V-F3 | V | FM-7 | COVERED | "any entry in a locked period requires formal authorization… flags the TB version as restated… any re-open produces an auditable record with sign-off" (V-8) | post-sign-off controlled re-open + audit-logged channel |
| N1 | N | FM-1 | NOT-COVERED | | FX rate source not declared an out-of-scope upstream assumption; candidate brings rate sourcing IN scope (D-1) instead of excluding it |
| N2 | N | FM-1 | COVERED | "Tax calculation is a downstream process fed by the pre-tax TB; out of scope" (N-1) | tax/statutory downstream out of scope |
| N3 | N | FM-1 | NOT-COVERED | | no declared assumption that source transactions are validly recorded / fraud detection is a separate upstream controls scope |
| N4 | N | FM-1 | NOT-COVERED | | accounting policy / CoA / GAAP-vs-IFRS not declared a fixed out-of-scope input (candidate treats CoA & dual-GAAP as in-scope mechanics) |
| N5 | N | FM-1 | NOT-COVERED | | hyperinflation/hedge/complex instruments not declared N/A-or-upstream; candidate handles hyperinflation IN scope (V-48), hedge/instruments unmentioned |
| N6 | N | FM-1 | COVERED | "Cash flow statement preparation — Derived from TB and disclosure notes; out of scope" (N-5) | cash-flow statement downstream out of scope |

## 6.2 Ballast list (duplicate candidate points → one reference item)

| ref-id | # candidate points mapped | ballast (count − 1) | duplicate candidate phrases |
|---|---|---|---|
| D1 | 5 | 4 | D-2 AR, D-3 AP, D-4 Inventory, D-5 Fixed-asset, D-6 Payroll sub-ledger close+lock (Appendix: split expected, not penalized — counted only) |
| D4 | 5 | 4 | D-10 reval; Dep-5 + V-27 (FC accruals classified monetary for reval); Dep-12 + V-24 (reval posting date = close period) |
| D6 | 4 | 3 | D-9 bank rec; Dep-6 (cash posted before rec); V-21 (signed/retained rec); V-22 (multi-CCY both currencies) |
| D3 | 3 | 2 | D-8 accruals; V-32 (accrual cutoff rule); V-33 (non-standard accrual documentation) |
| D7 | 2 | 1 | D-13 TB extraction; D-14 TB review/sign-off/hard close |
| D5 | 2 | 1 | D-12 IC elimination; V-29 (investment elimination bottom-up) |
| Dep2 | 2 | 1 | D-7 sub-ledger↔GL recon; V-20 (line-item recon retained) |
| Dep4 | 2 | 1 | Dep-4 (recon clean before reval); Dep-13 (bank rec sign-off before TB sign-off) |
| Dep7 | 3 | 2 | D-11 IC confirmation; Dep-9 (IC confirm before elim); V-5 (IC symmetry before elim) |
| Dep8 | 4 | 3 | V-6 single locked rate table; Dep-1, Dep-2 (rate lock before reval / IC); V-18 (rate provenance/immutability) |
| Dep10 | 2 | 1 | Dep-14 (auto-reversal release at N+1); V-36 (reversal posts to same accounts) |
| V-I5 | 2 | 1 | V-28 (zero IC residual report); V-16 (IC matrix complete/current) |
| V-I6 | 2 | 1 | V-14 (translation distinct, separate accounts); V-11 (monetary/non-monetary convention) |
| V-I7 | 6 | 5 | V-40 lineage (primary); V-3 (frozen functional amount), V-26 (reval run report), V-39 (TB version immutable), V-42 (IC elim workpaper), V-43 (scope file archived) |
| V-I10 | 2 | 1 | V-51 suspense to zero; V-34 (GR/IR clearing to zero) |
| V-I11 | 2 | 1 | V-19 mapping version-controlled; V-46 (new GL account in all tables) |
| V-E1 | 2 | 1 | D-1 (three rate types); V-44 (date/timezone, stale closing rate) |
| V-E2 | 2 | 1 | V-47 (disposal pro-rata); Dep-10 (scope file current) |
| V-F3 | 2 | 1 | V-8 (hard-close re-open channel); V-10 (prior-period locked in archive) |

**Total ballast points = 35.**

## 6.3 Unmatched candidate points (map to NO reference item)

| candidate phrase (verbatim) | flag |
|---|---|
| V-4 "Every state change to every journal… recorded with actor, timestamp, and reason; deletions are logical only (no physical deletes)" | UNMATCHED — human review |
| V-7 "Accrual journals carry a distinct journal type from actual invoices; the distinction is queryable at journal-type level" | UNMATCHED — human review |
| V-9 "Period status transitions (Open → Soft-Close → Hard-Close → Archived) are system-enforced; posting to a locked period is rejected by the system" | UNMATCHED — human review |
| V-13 "Every journal line carries transaction-CCY amount, functional-CCY amount, and presentation-CCY amount; none may be null" | UNMATCHED — human review |
| V-15 "FX differences on IC monetary items where repayment is not planned or likely (IAS 21 §32) are posted to OCI, not P&L" | UNMATCHED — human review |
| V-17 "Statistical/memo ledgers are separate from the primary ledger; consolidation-adjustment ledger is separate from both; TB is drawn from a documented ledger set that excludes statistical" | UNMATCHED — human review |
| V-31 "Intragroup declared dividend: IC receivable/payable eliminated; WHT payable to an external tax authority is not eliminated" | UNMATCHED — human review |
| V-35 "A scan of open POs, long-term contracts, and prior-month accrual schedule confirms no new obligation is omitted; reliance solely on prior-period roll-forward is not acceptable" | UNMATCHED — human review |
| V-45 "Functional currency change mid-period… requires restatement at the date of change; prior-period comparative retains original functional currency" | UNMATCHED — human review |
| V-48 "Non-monetary items of a hyperinflationary-economy entity are restated to current purchasing power before translation (IAS 29)" | UNMATCHED — human review |
| V-49 "Entity maintaining two sets of books feeds only one into the consolidated TB; mappings are separate and non-overlapping" | UNMATCHED — human review |
| V-50 "IC transaction where the transaction currency matches neither entity's functional currency… three rate pairs explicitly applied" | UNMATCHED — human review |
| V-52 "Depreciation run exception report reviewed; newly added asset classes producing zero depreciation confirmed intentional or corrected before FA lock" | UNMATCHED — human review |
| N-2 "Payroll processing (gross-to-net, withholding calculations) occurs in a separate system… out of scope" | UNMATCHED — human review |
| N-3 "Inter-cost-centre allocations for management P&L are a post-close analytics step… out of scope" | UNMATCHED — human review |
| N-4 "Budget vs. actual variance reporting — Analytics layer downstream of TB… out of scope" | UNMATCHED — human review |
| N-6 "External audit execution — Auditors' own procedures are out of scope" | UNMATCHED — human review |
| N-7 "Ultimate-parent goodwill allocation, full minority interest computation… and legal-entity statutory filings are out of scope" | UNMATCHED — human review |
| N-8 "Transfer pricing compliance — Whether IC prices are arm's-length is a tax/TP matter… out of scope" | UNMATCHED — human review |

**Total unmatched candidate points = 19.**

> Note (not scored): V-41 "Journals above materiality threshold require a second approver (preparer ≠ approver)" is an authority-plane (`Del`/SoD) statement — per §1/§3 neither credited nor penalized; excluded from the unmatched tally.

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/8   Dep = 11/12   V = 16/22   N = 2/6
  by FM tag:     FM-1 = 17/23   FM-2 = 7/8   FM-3 = 5/7   FM-4 = 1/3   FM-5 = n/a   FM-6 = n/a   FM-7 = 1/1
  PARTIAL counts: D = 1   Dep = 0   V = 2   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 35
  unmatched candidate points (human-review flag):    total = 19
```

# BLIND JUDGE VERDICT — T04 / candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Post all invoices, credit notes, cash receipts, and write-offs with transaction date ≤ cutoff; lock the AR sub-ledger to the close period" (D-2; D-3/D-4/D-5/D-6 parallel) | split AP/AR/payroll all map to D1 (Appendix granularity rule) |
| D2 | D | — | COVERED | "All sub-ledger-to-GL interface jobs must complete successfully before D-7" (Dep-20) | names sub-ledger→GL posting/interface |
| D3 | D | — | COVERED | "Post standard recurring accruals, non-standard manual accruals (with documented approvals), GR/IR accruals, prepaid amortisation, interest accruals, deferred revenue recognition, and deferred tax journal entries" (D-8) | (a) timing clear; (b) judgmental via "non-standard manual accruals (with documented approvals)" + deferred tax (V-65) + V-33 one-off estimates w/ methodology |
| D4 | D | — | COVERED | "post unrealized FX gain/loss to designated accounts" (D-10) + "partial payment realises gain/loss on the settled portion only" (V-23) | unrealized (D-10) + realized producer (V-23) |
| D5 | D | — | PARTIAL | "Eliminate IC AR/AP, revenue/expense, loans/receivables/payables, and investment/equity per the IC entity matrix" (D-12) | leg (a) IC + investment/equity elimination MET; missing leg = NCI computation (minority% × sub net assets) — candidate scopes "full minority interest computation" OUT (N-7) |
| D6 | D | — | COVERED | "produce signed reconciliation (adjusted bank balance = adjusted book balance) per account" (D-9) | bank + sub-ledger↔GL recon |
| D7 | D | — | COVERED | "obtain controller sign-off; lock period (Hard-Close state); log close event" (D-14) | hub TB assembly + sign-off |
| D8 | D | — | COVERED | "Unrealised profit on inventory or fixed assets transferred between group entities is eliminated; only profit realised through external sale is recognised" (V-30) | distinct from D5; filed as criterion (§2.4) |
| Dep0 | Dep | FM-1 | NOT-COVERED | | no opening-balance roll-forward from prior close / P&L close-out to retained earnings; the seam a parts-list never mentions |
| Dep1 | Dep | FM-1 | COVERED | "a posting attempt to the locked period is rejected by the system, not merely flagged for manual review" (V-68) + "Sub-ledger lock (D-2/D-3) precedes accrual GR/IR scan" (Dep-7) | freeze-before-post + cutoff filter |
| Dep2 | Dep | FM-2 | COVERED | "reconcile total balance to its GL control account at line-item level" (D-7) | control = sub-ledger detail |
| Dep3 | Dep | FM-1 | COVERED | "every journal in the close period is in approved/posted status … a hard prerequisite to D-14 sign-off" (V-55) | adjustments posted before TB |
| Dep4 | Dep | FM-1 | COVERED | "Bank reconciliation sign-off (D-9) → TB sign-off (D-14) — D-9 must be signed off before D-14 TB sign-off" (Dep-13) | recon clears before close |
| Dep5 | Dep | FM-1 | COVERED | "FX revaluation (D-10) → IC elimination (D-12) — D-10 must complete before D-12" (Dep-8) | reval precedes consolidation |
| Dep6 | Dep | FM-2→FM-1 | COVERED | "IC elimination journals in GL (D-12) → trial balance extraction (D-13) — D-12 must be complete before D-13" (Dep-11) | IC nets before TB |
| Dep7 | Dep | FM-2 | COVERED | "before D-12, every IC transaction in entity A has a corresponding entry in entity B; difference above materiality … triggers formal investigation" (V-5) | two-sided IC match before elimination |
| Dep8 | Dep | FM-2 | COVERED | "One rate table, locked before D-10, governs all currency-dependent steps (revaluation, translation, IC FX difference)" (V-6) | single shared rate table |
| Dep9 | Dep | FM-1 | COVERED | "D-2 through D-8 (all postings) must be in GL before D-10 runs" (Dep-3) | post precedes revaluation |
| Dep10 | Dep | FM-1 | COVERED | "Every journal posted with an auto-reversal flag carries a reversal date equal to the first day of N+1" (V-62) | accrual reversal carries to next period |
| Dep11 | Dep | FM-2 | NOT-COVERED | | realized/unrealized no-double-count netting not separately asserted; V-23 (the only realized-FX statement) is consumed by D4's realized leg (one-defect-one-place); no distinct "they net / prior reval reverses on settlement" seam |
| V-I1 | V | FM-1 | COVERED | "Sum of debit balances = sum of credit balances applied to raw (un-netted) amounts" (V-37) | debits=credits / TB nets zero |
| V-I2 | V | FM-2 | COVERED | "debits = credits in both transaction currency and functional currency" (V-1) | per-currency balance |
| V-I3 | V | FM-1 | COVERED | "Every in-scope entity's trial balance nets to zero in its own functional currency before consolidation … entity-level imbalances must not be masked by offsetting imbalances in another entity" (V-59) | consolidated/group nets to zero |
| V-I4 | V | FM-4+FM-1 | COVERED | "Every journal line carries exactly one period; no single entry spans two periods" (V-2) | period cutoff integrity |
| V-I5 | V | FM-1 | COVERED | "post-elimination IC difference report shows zero residual in all IC accounts (or residuals documented)" (V-28) | elimination completeness, both directions |
| V-I6 | V | FM-2 | COVERED | "Translation … is a separate computational step from revaluation … gain/loss from each step posts to separate designated accounts" (V-14) + "P&L at period-average rate, balance sheet at closing rate, equity components at historical rates" (D-15) | uniform convention + CTA/FX isolation |
| V-I7 | V | FM-1 | PARTIAL | "Every journal line carries a unique, non-reusable ID; reversals reference the original entry ID; source document reference present" (V-40) | lineage leg MET; missing leg = reproducibility (same inputs → same TB) not asserted |
| V-I8 | V | FM-1 | COVERED | "confirm that all sub-ledger-to-GL interface jobs ran to successful completion with zero errored or suspended records" (D-16) | posting roster complete, none dropped |
| V-I9 | V | FM-1 | NOT-COVERED | | source-posting idempotency absent; V-25 idempotency is reval-job-specific, not "re-running a feeder produces no net change / source doc posts exactly once" |
| V-I10 | V | FM-1 | COVERED | "Any non-zero suspense balance at hard close requires documented resolution; IC FX differences routed to suspense must be allocated before period lock" (V-51) | suspense/clearing drain to zero |
| V-I11 | V | FM-1 | COVERED | "Sub-ledger-to-GL account mapping table is version-controlled; tested after any COA change; a broken mapping causes posting to a suspense account (detectable)" (V-19) | mapping integrity total/unambiguous |
| V-I12 | V | FM-2 | PARTIAL | "Each legal entity has exactly one designated functional currency" (V-12) | functional-currency leg MET; missing leg = consolidation hierarchy acyclic/single-rooted well-formedness not asserted as a guard |
| V-E1 | V | FM-3+FM-2 | COVERED | "COA explicitly marks each account as monetary (revalue at closing rate) or non-monetary (historical rate)" (V-11) + D-15 closing/average/historical per item type | rate-selection boundary |
| V-E2 | V | FM-3 | COVERED | "A subsidiary acquired intra-period is consolidated only from the acquisition date" (V-66) + "Subsidiary sold intra-period consolidated only up to disposal date" (V-47) | partial-period entity |
| V-E3 | V | FM-4 | COVERED | "any correction posted after D-11 sign-off requires a formal re-confirmation step before D-12 proceeds" (Dep-19) + "functional-currency reconciliation … must be re-verified or performed in full after D-10 completes" (Dep-16) | pre-sign-off late entry forces dependency-ordered re-run |
| V-E4 | V | FM-3 | NOT-COVERED | | no rounding-residual / plug rule for multi-decimal FX translation |
| V-E5 | V | FM-3 | COVERED | "Inventory GL account balance reflects actual cost for all positions including negative quantities; negative inventory not suppressed to zero" (V-53) | sign/negative-balance not dropped |
| V-E6 | V | FM-3 | COVERED | "a missing rate produces a blocking error, not a silent zero-rate or skip" (V-56) | missing/stale rate fallback |
| V-E7 | V | FM-3 | NOT-COVERED | | no "revalue gross foreign positions, not net functional" statement; D-10 open-item reval is consumed by D4 |
| V-F1 | V | FM-4 | NOT-COVERED | | per-edge ordering carried on Dep edges; no distinct global ordering-gate criterion ("out-of-order yields balanced-but-wrong TB + dependency gate") |
| V-F2 | V | FM-3 | COVERED | "zero-net check alone is not sufficient for sign-off; unusual movements investigated and explained" (V-54) | balanced-but-wrong false-PASS guard |
| V-F3 | V | FM-7 | COVERED | "the re-open must generate a complete audit log … the TB must be re-extracted and re-signed; the prior signed TB must be flagged as superseded" (V-58) + V-8 | post-sign-off controlled reopen channel |
| N1 | N | FM-1 | NOT-COVERED | | candidate brings rate sourcing/validation in-scope (D-1, V-18, V-56); never declares FX rate source assumed authoritative / out of scope |
| N2 | N | FM-1 | COVERED | "Tax calculation is a downstream process fed by the pre-tax TB; out of scope" (N-1) | tax filing/statutory out of scope |
| N3 | N | FM-1 | NOT-COVERED | | no declared assumption that source transactions are validly recorded / fraud-detection upstream |
| N4 | N | FM-1 | NOT-COVERED | | no declared exclusion that accounting policy / CoA / GAAP-vs-IFRS basis is a fixed input |
| N5 | N | FM-1 | NOT-COVERED | | candidate brings hedge (D-19) and hyperinflation (V-48) in-scope rather than declaring them N/A or upstream |
| N6 | N | FM-1 | COVERED | "Cash flow statement preparation — Derived from TB and disclosure notes; out of scope" (N-5) | cash-flow statement downstream |

> Authority-plane (NOT scored, §1/§3): candidate V-41 "Dual authorisation on material journals … (preparer ≠ approver)" — ignored, neither credited nor penalized.

## 6.2 Ballast list

| ref-id | # candidate points | ballast | duplicate candidate phrases |
|---|---|---|---|
| D1 | 6 | 5 | D-2, D-3, D-4, D-5, D-6 sub-ledger closes + V-52 depreciation-all-classes |
| D3 | 5 | 4 | D-8 + V-32 (cutoff rule), V-33 (non-standard documented), V-35 (completeness beyond repeat), V-65 (deferred tax) |
| D4 | 7 | 6 | D-10 + V-23, V-25 (idempotent), V-27 (foreign accruals monetary), Dep-5, V-63 (atomicity), V-26 (run report) |
| D5 | 4 | 3 | D-12 + V-29 (investment elim bottom-up), V-31 (IC dividend), Dep-18 (IC interest) |
| D6 | 3 | 2 | D-9 + V-21 (bank recon signed), V-22 (multi-ccy recon) |
| D7 | 2 | 1 | D-13 (extraction) + D-14 (review/sign-off) |
| D8 | 3 | 2 | V-30 + V-69 (prior-period release), V-73 (FA-transfer depreciation) |
| Dep1 | 2 | 1 | V-68 + Dep-7 |
| Dep2 | 2 | 1 | D-7 + V-20 (line-item recon retained) |
| Dep4 | 2 | 1 | Dep-13 + Dep-4 (recon→reval) |
| Dep7 | 4 | 3 | V-5 + D-11, Dep-9, Dep-17 |
| Dep8 | 5 | 4 | V-6 + D-1, Dep-1, Dep-2, Dep-15 |
| Dep10 | 3 | 2 | V-62 + Dep-14, V-36 (reversal same accounts) |
| V-I2 | 2 | 1 | V-1 + V-13 (three-amount line) |
| V-I4 | 3 | 2 | V-2 + V-24 (reval posting period), V-71 (goods-in-transit cutoff) |
| V-I5 | 5 | 4 | V-28 + V-72 (residual blocks sign-off), V-16 (IC matrix), Dep-26, V-67 (sub-consol bottom-up) |
| V-I6 | 9 | 8 | V-14 + D-15, V-15, V-60, V-61, V-70, Dep-21, Dep-23, Dep-24 |
| V-I7 | 6 | 5 | V-40 + V-4 (audit trail), V-3 (frozen functional), V-39 (TB immutable), V-42 (IC workpaper), V-43 (scope file archived) |
| V-I10 | 3 | 2 | V-51 + V-34 (GR/IR zero), V-64 (GR/IR aging) |
| V-I11 | 2 | 1 | V-19 + V-46 (new GL account in tables) |
| V-E1 | 3 | 2 | V-11 + V-50 (three rate pairs), V-44 (date/timezone/rate) |
| V-E2 | 3 | 2 | V-66 + V-47, Dep-10 (scope file current) |
| V-E3 | 2 | 1 | Dep-19 + Dep-16 |
| V-E6 | 2 | 1 | V-56 + V-18 (rate provenance/staleness) |
| V-F3 | 2 | 1 | V-58 + V-8 (hard close final/logged) |
| **TOTAL** | | **65** | |

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| D-17 "Consolidation-level topside entries … policy-harmonisation journals" | UNMATCHED — human review |
| D-18 "Functional-currency change restatement (conditional)" | UNMATCHED — human review |
| D-19 "Derivatives and hedge accounting close step" | UNMATCHED — human review |
| Dep-6 "AR/AP cash entries posted to GL → bank reconciliation (D-9)" | UNMATCHED — human review |
| Dep-12 "FX revaluation journals in GL (D-10) → trial balance extraction (D-13)" | UNMATCHED — human review |
| Dep-22 "Consolidation topside entries (D-17) → TB extraction (D-13)" | UNMATCHED — human review |
| Dep-25 "Consolidation topside entries (D-17) → translation (D-15)" | UNMATCHED — human review |
| Dep-27 "Derivatives/hedge accounting complete (D-19) → TB extraction (D-13)" | UNMATCHED — human review |
| V-7 "Accrual/actual type segregation … distinct journal type" | UNMATCHED — human review |
| V-9 "Posting controls system-enforced … period status transitions" | UNMATCHED — human review |
| V-10 "Prior-period data locked in archive … comparative columns pull from archive" | UNMATCHED — human review |
| V-17 "Ledger scope defined … statistical/memo separate from primary" | UNMATCHED — human review |
| V-38 "TB entity and account completeness" | UNMATCHED — human review |
| V-45 "Functional currency change mid-period handled correctly" | UNMATCHED — human review |
| V-48 "Hyperinflationary entity treated separately (IAS 29)" | UNMATCHED — human review |
| V-49 "Dual-book entity: only one set feeds consolidation" | UNMATCHED — human review |
| V-57 "Non-cash item GL tagging complete … indirect-method cash flow" | UNMATCHED — human review |
| N-2 "Payroll gross-to-net computation … separate system" | UNMATCHED — human review |
| N-3 "Management reporting cost-centre allocations" | UNMATCHED — human review |
| N-4 "Budget vs. actual variance reporting" | UNMATCHED — human review |
| N-6 "External audit execution … out of scope" | UNMATCHED — human review |
| N-7 "Statutory consolidation above immediate group" | UNMATCHED — human review |
| N-8 "Transfer pricing compliance" | UNMATCHED — human review |

## 6.4 Score block

```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/8   Dep = 10/12   V = 16/22   N = 2/6
  by FM tag:     FM-1 = 19/27   FM-2 = 6/8   FM-3 = 5/7   FM-4 = 2/3   FM-5 = n/a   FM-6 = n/a   FM-7 = 1/1
  PARTIAL counts: D = 1   Dep = 0   V = 2   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 65
  unmatched candidate points (human-review flag):    total = 23
```

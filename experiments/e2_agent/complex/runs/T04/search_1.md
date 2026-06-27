# T04 — Month-End Close (Multi-Currency) — Search Pass 1

---

## DP — Domain Primitives

DP-1 **Chart of accounts structure** — COA must distinguish monetary vs. non-monetary accounts, and mark which accounts are subject to FX revaluation — *falsifier: revaluation routine picks up wrong accounts (e.g., fixed assets revalued at closing rate instead of historical).*

DP-2 **Functional currency per entity** — Each legal entity has exactly one designated functional currency; all P&L and balance sheet amounts ultimately expressed in it — *falsifier: entity posts transactions without a functional currency setting, producing untranslatable balances.*

DP-3 **Transaction currency** — Every journal line carries three amounts: transaction CCY, functional CCY, presentation CCY; none may be null — *falsifier: sub-ledger stores only transaction amount, GL receives no functional-currency amount, revaluation has no base to work from.*

DP-4 **Presentation currency** — The group reporting currency is distinct from any entity's functional currency; translation is a separate step from revaluation — *falsifier: revaluation gain/loss and translation difference are commingled in the same P&L line.*

DP-5 **Exchange rate types** — At minimum three rate types required: spot/transaction rate (booking), period-average rate (income statement translation), closing rate (balance sheet revaluation) — *falsifier: all transactions use closing rate, overstating/understating income translated amounts.*

DP-6 **Exchange rate source and snapshot** — Rates come from a named authoritative source (ECB, Bloomberg, etc.) locked to a specific timestamp for the period; ad-hoc overrides require approval — *falsifier: two runs of revaluation use different rate tables, producing non-reproducible results.*

DP-7 **Sub-ledger catalogue** — Enumerated set of sub-ledgers feeding the GL: AR, AP, inventory/cost, fixed assets, payroll, treasury/bank; each with its own posting mapping — *falsifier: a sub-ledger (e.g., lease sub-ledger) is not in catalogue and posts directly to GL with no reconciliation point.*

DP-8 **Journal entry structure** — Minimum fields per line: entry ID, legal entity, account, cost centre/segment, transaction date, posting date, period, transaction CCY, transaction amount, functional CCY, functional amount, source document reference, preparer, batch ID — *falsifier: entries lack period tag, reposting to wrong period is undetectable.*

DP-9 **Intercompany entity matrix** — An explicit register of all intercompany pairs, the accounts they use for IC receivables/payables/revenue/expense, and the elimination accounts — *falsifier: a new IC relationship is not in the matrix and escapes elimination.*

DP-10 **Ledger type distinction** — Statistical/memo ledgers and consolidation-adjustment ledgers are separate from the primary ledger; trial balance draws only from defined ledger set — *falsifier: memo entries inflate reported balances.*

---

## LS — Lifecycle / State

LS-1 **Period status machine** — Defined states: Open → Soft-Close (sub-ledgers locked, GL open) → Hard-Close (GL locked) → Archived; transitions are irreversible except via documented override — *falsifier: postings continue to a "closed" period because status is a flag with no enforcement.*

LS-2 **Sub-ledger lock date** — Sub-ledgers (AR, AP, inventory, FA) are locked to the close period before GL work begins; any attempt to post to a locked period is rejected — *falsifier: vendor invoice back-dated after AP lock inflates payables without triggering revaluation.*

LS-3 **GL posting cutoff** — A hard posting cutoff date exists beyond which no new primary journals are accepted in the period under close — *falsifier: payroll journal arrives after FX revaluation and after trial balance extraction, making TB stale.*

LS-4 **Auto-reversal scheduling** — Accrual journals destined for reversal carry a reversal date (first day of N+1); reversals are created at close time but posted only when N+1 opens — *falsifier: reversal is posted in period N, netting out the accrual before TB is extracted.*

LS-5 **Re-open procedure** — A formal process exists for re-opening a hard-closed period (requires CFO sign-off, produces an audit event); the trial balance version is flagged as restated — *falsifier: period is silently re-opened and corrected without audit record.*

LS-6 **Comparative period availability** — Prior-period TB data is locked/read-only once archived; comparative columns on current TB pull from archive, not from live ledger — *falsifier: prior-period restatement corrupts comparative column without disclosure.*

---

## CO — Components

### CO-A: Sub-Ledger Completeness and Posting

CO-A1 **AR sub-ledger completeness** — All invoices, credit notes, cash receipts, and write-offs with transaction date ≤ cutoff are posted before AR lock; ageing runs on locked data — *falsifier: invoice dated last day of month arrives after lock, revenue/receivable understated.*

CO-A2 **AP sub-ledger completeness** — All vendor invoices, debit memos, and payment runs with date ≤ cutoff are posted; GR/IR (goods received / invoice received) account must match — *falsifier: GR posted, invoice not yet received → accrual double-counts if GR/IR not checked.*

CO-A3 **Inventory / cost sub-ledger** — All goods movements (receipts, shipments, adjustments, cost revaluation) with date ≤ cutoff posted; inventory valuation report ties to GL inventory account — *falsifier: inventory count adjustment posted after close → COGS and inventory both mis-stated.*

CO-A4 **Fixed asset sub-ledger** — Depreciation run, additions, disposals, and impairment completed before FA lock; net book value per sub-ledger ties to GL fixed-asset control account — *falsifier: disposal in sub-ledger not mirrored in GL control → asset balance inflated.*

CO-A5 **Payroll sub-ledger** — Payroll journal (gross pay, employer taxes, net pay, employee deductions) fully posted before close; payroll clearing account nets to zero — *falsifier: payroll delayed → wage expense and accrued-payroll liability both understated.*

CO-A6 **Sub-ledger to GL mapping rules** — Each sub-ledger transaction type maps to a GL account via a maintained, version-controlled mapping table; mapping is tested after any COA change — *falsifier: COA account renamed breaks mapping; sub-ledger posts to suspense.*

CO-A7 **Sub-ledger ↔ GL control account reconciliation** — A formal report reconciles total balance per sub-ledger to the GL control account balance; differences are explained and resolved before moving to next step — *falsifier: sub-ledger and GL agree at total but line-item netting errors exist, invisible to revaluation.*

### CO-B: Bank / Sub-Ledger Reconciliation

CO-B1 **Bank statement completeness** — Bank statement for all bank accounts, for the full calendar month through cutoff date, is obtained and loaded — *falsifier: statement cut a day early misses last-day settlements.*

CO-B2 **Outstanding checks / uncleared payments** — Checks issued but not yet cleared are tracked as timing differences; aged uncleared items require explanation — *falsifier: uncleared check from prior month not tracked; cash GL overstated.*

CO-B3 **Deposits in transit** — Cash deposited before cutoff not yet on bank statement listed as in-transit; must appear in both GL and reconciliation — *falsifier: deposit posted in GL but not matched to bank → double-count when bank posts next day.*

CO-B4 **Bank charges and interest** — Bank fees and interest debit/credit on statement are posted to GL before reconciliation completes (or noted as reconciling item) — *falsifier: bank charge not posted → unexplained variance in cash account.*

CO-B5 **Bank recon sign-off** — Each bank account has a signed, dated reconciliation showing adjusted bank balance = adjusted book balance; retained as audit evidence — *falsifier: recon "completed" but not signed; auditor cannot rely on it.*

CO-B6 **Multi-currency bank accounts** — Foreign-currency bank accounts are reconciled in transaction currency AND functional currency; FX difference between statement date balance and GL balance is explicitly a revaluation item — *falsifier: bank recon done in transaction currency only; functional-currency cash balance unchecked.*

### CO-C: FX Revaluation

CO-C1 **Monetary account identification** — Rules determine which GL accounts are monetary (revalue at closing rate): cash, AR, AP, intercompany balances, loans, bonds payable; non-monetary (use historical rate): inventory, PP&E, equity — *falsifier: prepaid expense (non-monetary) revalued → spurious FX gain/loss.*

CO-C2 **Closing rate selection** — Closing rate = last available rate on the last business day of the period; documented and agreed before revaluation run — *falsifier: system picks rate from a day with a data gap (holiday); wrong rate applied to all balances.*

CO-C3 **Open-item vs. balance revaluation** — AR/AP are revalued at open-item level (each unpaid invoice revalued individually) so realized gain/loss on settlement is correctly split from unrealized; cash accounts revalued at account balance level — *falsifier: AR revalued as account total → settlement of one invoice produces wrong realized gain calculation.*

CO-C4 **Unrealized FX gain/loss posting** — Revaluation journal posts to designated unrealized FX G/L account (P&L or OCI depending on item type); the offsetting balance-sheet account is the asset/liability being revalued — *falsifier: revaluation journal posts to wrong P&L line; misclassified as operating income.*

CO-C5 **Translation reserve (OCI) vs. P&L routing** — Long-term intercompany monetary items qualifying under IAS 21 §32 route FX difference to OCI, not P&L; all other monetary items route to P&L — *falsifier: long-term IC loan FX difference hits P&L, overstating/understating reported profit.*

CO-C6 **Revaluation reversal on settlement** — When a revalued item is settled, the accumulated unrealized gain/loss is reversed and a realized gain/loss is booked; net position = actual transaction gain — *falsifier: settlement posts realized gain without reversing prior unrealized → gain double-counted.*

CO-C7 **Revaluation run report** — System generates a report listing each account/open item, prior balance, closing rate, revalued balance, and gain/loss amount; retained as evidence — *falsifier: revaluation runs silently; no way to audit which items were included.*

CO-C8 **Multi-run idempotency** — If revaluation is run twice in a period, the second run reverses and replaces the first (not cumulative) — *falsifier: two runs produce double the gain/loss; trial balance is wrong.*

### CO-D: Intercompany Elimination

CO-D1 **IC transaction matching** — Each IC AR entry in entity A is matched to an IC AP entry in entity B using a common IC reference or agreement number — *falsifier: matching uses account code only; two unrelated IC transactions net against each other.*

CO-D2 **IC revenue / expense elimination** — Matched IC revenue and expense are eliminated at consolidation level so only external revenues remain — *falsifier: IC management fee posted in both entities' P&L and not eliminated → group profit inflated.*

CO-D3 **IC loan / receivable / payable elimination** — Intercompany loans, receivables, and payables eliminate to zero in consolidated TB; elimination entry = Dr IC payable, Cr IC receivable — *falsifier: IC loan eliminated on one side only → consolidated BS has unexplained balance.*

CO-D4 **IC investment / equity elimination** — Parent's investment in subsidiary is eliminated against subsidiary's equity; any remaining differential = goodwill or acquisition adjustment — *falsifier: investment not eliminated → consolidated equity double-counts subsidiary net assets.*

CO-D5 **IC out-of-balance investigation** — Before elimination, the system identifies unmatched IC pairs (entity A posted, entity B did not); investigation and correction are completed or explained — *falsifier: unmatched IC pair silently left; elimination cannot complete; TB off by that amount.*

CO-D6 **IC FX difference handling** — When two entities book the same IC transaction in different functional currencies, a rate difference arises at close; this difference must be explicitly identified, allocated (to one entity or to a consolidation adjustment), and eliminated — *falsifier: IC FX difference lands in a suspense account; group OCI is unexplained.*

CO-D7 **Intragroup profit elimination** — Unrealised profit on inventory or fixed assets transferred between group entities is eliminated; only realised (external) profit is recognised — *falsifier: subsidiary sells inventory to parent at markup; markup included in consolidated profit even though goods not yet sold externally.*

CO-D8 **Consolidation scope file** — An up-to-date register of which entities are in-scope for elimination; additions and disposals in the period reflected before elimination runs — *falsifier: entity acquired mid-period not added to scope; its IC transactions not eliminated.*

CO-D9 **Multi-level IC (chain eliminations)** — Where A owns B owns C, eliminations are layered (B-C first, then A-B); order matters for investment/equity elimination — *falsifier: A-B eliminated before B-C; B's equity still includes C's IC profit.*

### CO-E: Accruals and Deferrals

CO-E1 **Accrual cutoff rule** — Expenses (revenue) are recognised in the period the obligation (right) arises, regardless of invoice / cash date; the rule is documented and consistently applied — *falsifier: utility invoice arriving in N+1 for N consumption is booked in N+1 → period-N expense understated.*

CO-E2 **Standard recurring accruals** — A maintained schedule of recurring accruals (rent, insurance, interest, maintenance) auto-generates journals each period; the schedule is reviewed for continued applicability — *falsifier: contract cancelled but accrual schedule not updated; over-accrual accumulates.*

CO-E3 **Non-standard manual accruals** — One-off estimates (e.g., legal provision, restructuring) require documented rationale, approver sign-off, and a quantification methodology — *falsifier: large provision booked without documentation; auditor cannot validate estimate.*

CO-E4 **GR/IR accrual** — Goods received but invoice not yet received (GR/IR) are accrued using PO price; GR/IR clearing account must net to zero or show only legitimate timing items — *falsifier: GR/IR not cleared → payables accrual overlaps AP sub-ledger; payables double-counted.*

CO-E5 **Revenue accrual / deferred revenue** — Revenue earned but not yet invoiced (accrued revenue) and invoiced but not yet earned (deferred revenue) are correctly classified; recognition matches contractual or IFRS 15 milestones — *falsifier: subscription revenue fully recognised on invoicing; deferred portion missing → revenue overstated.*

CO-E6 **Prepaid expense amortisation** — Prepaid balances are amortised on their documented schedules; schedule total ties to prepaid GL account balance — *falsifier: prepaid schedule not updated when contract term changes; wrong amortisation rate persists.*

CO-E7 **Interest accrual** — Accrued interest on all borrowings and investments is calculated using effective interest method (or as contracted) for the exact days in period — *falsifier: day-count convention wrong (30/360 vs. actual/365); interest systematically mis-stated.*

CO-E8 **Accrual completeness check** — A checklist scan of open POs, long-term contracts, and prior-month accrual schedule is performed to confirm nothing is omitted — *falsifier: accrual process relies only on repeat from last month; new obligation missed.*

### CO-F: Trial Balance

CO-F1 **Zero-net check** — Sum of all debit balances equals sum of all credit balances; this is a necessary (not sufficient) condition for correctness — *falsifier: TB extraction script nets debits and credits before summing; an entry with wrong sign passes undetected.*

CO-F2 **Entity and segment completeness** — TB includes every legal entity, every segment/cost centre, and every account with any activity or balance in the period — *falsifier: dormant entity with a residual IC balance excluded; group equity understated.*

CO-F3 **Ledger scope definition** — TB is drawn from a defined, documented ledger set (e.g., primary + consolidation-adjustment, excluding statistical); ledger set is agreed before extraction — *falsifier: consolidation-adjustment ledger accidentally excluded; IC eliminations missing.*

CO-F4 **Currency columns** — TB shows transaction-currency column, functional-currency column, and presentation-currency column; each nets to zero independently — *falsifier: functional-currency column does not net to zero, indicating a translation or revaluation posting error.*

CO-F5 **Comparative period column** — TB includes prior-period comparative balances from locked archive; any restatement of prior period is flagged — *falsifier: comparative column pulls from current (restated) ledger; readers cannot see change.*

CO-F6 **TB version control** — Each extracted TB is stamped with extraction timestamp, ledger version, and rate table version; stored immutably — *falsifier: TB re-extracted after a correction but old version circulated; multiple versions in circulation.*

---

## GI — Global Invariants

GI-1 **Double-entry integrity at all times** — Every journal entry, in every sub-ledger and the GL, must have debits = credits in both transaction currency and functional currency; enforced by the system, not by manual review — *falsifier: sub-ledger allows single-sided entry under "auto-offset" logic; GL control account wrong.*

GI-2 **Period tagging non-negotiable** — Every entry has exactly one period; cross-period allocations must use two opposite entries in separate periods — *falsifier: an amortisation spreads a single entry across two periods; neither period is correct.*

GI-3 **Functional currency amount always present** — Even if posted in transaction currency, the functional currency equivalent is stored at posting time using the applicable rate; it is never re-derived retroactively — *falsifier: rate table update retroactively changes functional amounts; prior TB restated without notice.*

GI-4 **Audit trail completeness** — Every state change to every journal (creation, approval, modification, reversal, deletion) is recorded with actor, timestamp, and reason; deletions are logical, not physical — *falsifier: an entry is physically deleted; auditor cannot reconstruct the original.*

GI-5 **Intercompany symmetry** — At close, before elimination, every IC transaction has a corresponding entry in the counterparty at the same amount (translated to each entity's functional currency); difference > materiality threshold triggers investigation, not silent carry-forward — *falsifier: IC asymmetry of $500 carried to suspense every month; cumulative balance never investigated.*

GI-6 **Rate table consistency within a close** — A single, locked rate table is used for the entire close sequence (revaluation, translation, IC matching); no partial rate updates mid-close — *falsifier: rate table updated between revaluation run and IC elimination run; eliminated balance differs from revalued balance.*

GI-7 **Separation of estimate from actuals** — Accruals (estimates) are segregated from actual invoices at journal-type level; management can distinguish accrual-heavy periods from invoice-heavy — *falsifier: payroll accrual posted with type "invoice"; accrual reversal creates apparent duplicate payment.*

GI-8 **Hard close is final** — After hard close, the ledger is read-only; any correction requires a formal journal in the subsequent period or a documented re-open event — *falsifier: system allows a "quiet edit" of a hard-closed entry; TB can be altered post-sign-off.*

---

## CS — Cross-Component Interaction Seams

CS-1 **Sub-ledger posting → Bank Reconciliation** — All cash-movement entries from AR receipts and AP payments must be in the GL before bank recon runs; the recon matches GL cash entries to bank lines — *falsifier: last-day payment runs not posted when recon starts; recon shows false uncleared items that resolve themselves later, masking real ones.*

CS-2 **Sub-ledger lock → Accrual completeness** — The GR/IR and open-PO scan for accruals must read from the locked sub-ledger snapshot; if AP sub-ledger is locked after accruals are posted, accruals may double-count GR/IR — *falsifier: AP sub-ledger locked after accrual run; GR/IR accrual and actual AP invoice both in period.*

CS-3 **All postings complete → FX Revaluation** — Revaluation reads open item and account balances; it must run only after ALL sub-ledger batches, accruals, payroll, depreciation are in the GL — *falsifier: depreciation posted after revaluation; asset depreciation in functional CCY not matched by revaluation of the same-period balance movement.*

CS-4 **FX Revaluation → Intercompany Elimination** — IC balances used for elimination must be the post-revaluation balances (at closing rate); elimination must run after revaluation — *falsifier: elimination runs first using pre-revaluation balances; post-revaluation IC balances don't zero out; residual OCI entry unexplained.*

CS-5 **Sub-ledger → GL control account → FX Revaluation** — The GL control account balance must equal the sub-ledger total before revaluation; if not reconciled, revaluation operates on a wrong starting number — *falsifier: sub-ledger/GL difference of $10k exists; revaluation applies closing rate to inflated balance; FX gain overstated.*

CS-6 **Accruals (foreign CCY) → FX Revaluation** — Accruals posted in foreign currency are monetary items; they must appear in the revaluation run and be marked as auto-reversing — *falsifier: EUR accrual on USD functional entity not included in revaluation filter; EUR exposure in P&L but not in FX line.*

CS-7 **FX Revaluation → Trial Balance (P&L completeness)** — Unrealised FX gain/loss journals from revaluation must be in the GL before TB extraction; the FX P&L line is a revaluation output, not a manual entry — *falsifier: revaluation job posting date set to N+1 (DST or timezone bug); FX P&L absent from period-N TB.*

CS-8 **Intercompany Elimination → Trial Balance (consolidated scope)** — The consolidated TB includes elimination journals; extracting TB before elimination completes produces an unconsolidated view that may be mistaken for the consolidated view — *falsifier: elimination still running when TB extracted; partially eliminated TB circulated as final.*

CS-9 **Bank Reconciliation → Cash in Trial Balance** — The GL cash balance on TB must equal the reconciled bank balance plus/minus documented reconciling items; bank recon sign-off is a prerequisite for TB sign-off — *falsifier: TB signed off, but bank recon still open; cash balance unverified.*

CS-10 **Depreciation (FA sub-ledger) → FX Revaluation** — For entities with FC-denominated assets (rare), depreciation charge in functional currency and the asset's net book value in functional currency must both be final before revaluation touches any related monetary items (e.g., loans to finance the asset) — *falsifier: depreciation finalized in transaction CCY only; functional-CCY NBV wrong, affecting any loan-to-asset ratio calculation.*

CS-11 **Auto-reversal scheduling → Next-period opening** — Reversals created at hard-close are staged for N+1; if the N+1 period is not yet open in the system, reversals must queue without posting; they must not land in period N — *falsifier: system opens N+1 pre-maturely to accommodate a reversal; N+1 period contaminated before N is fully closed.*

CS-12 **Rate table lock → IC FX difference calculation** — The IC FX difference calculation (CS-4 feed) depends on the same rate snapshot as the revaluation; if rates are locked after revaluation but before IC elimination, the difference can still be zero-net — but rate lock must precede both — *falsifier: rate updated between revaluation and IC difference calculation; IC FX difference is non-zero and cannot be explained.*

CS-13 **Consolidation scope file → IC Elimination → Trial Balance** — Any entity added or removed from consolidation scope must be reflected in the scope file before IC elimination runs; the scope file version must be captured in the TB metadata — *falsifier: entity disposed of mid-period still in scope file; its IC transactions eliminated even though it is no longer a subsidiary; minority interest not adjusted.*

CS-14 **Payroll accrual → AP sub-ledger clearing** — Payroll-related payables (net pay, tax payables) must clear through AP or the dedicated payroll liability account; duplicate liability if payroll journal and AP vendor payment both post to the same account — *falsifier: net pay posted to AP as vendor, and a separate payroll accrual also posts to accrued-payroll; liability double-booked.*

---

## EC — Edge / Boundary Cases

EC-1 **Month-end on weekend / public holiday** — Last business day ≠ last calendar day; rate date, bank statement cutoff, and posting cutoff rules must explicitly specify which day is used — *falsifier: closing rate is taken from Dec 30 (Friday) for a Dec 31 close; rate is one day stale.*

EC-2 **Entities in different time zones** — A 23:59 transaction in Tokyo is Jan 1 UTC; it may fall in December for a London entity; cutoff rule must reference a single canonical time zone — *falsifier: IC transaction booked in December by Tokyo, January by London; period mismatch creates unmatched IC pair.*

EC-3 **Functional currency change mid-period** — If an entity changes functional currency, a restatement at the date of change is required; the prior-period comparative must reflect original functional currency — *falsifier: functional currency changed retroactively; prior-period revaluation gains/losses re-stated without disclosure.*

EC-4 **New GL account added mid-period** — A new account created after the start of the period must be reflected in COA mapping files, revaluation rules, and elimination account tables before close — *falsifier: new IC account not in elimination table; IC transactions to that account escape elimination.*

EC-5 **Partial settlement of foreign-currency invoice** — Partial payment realises gain/loss on the settled portion; the remaining open item is still subject to revaluation; the split calculation must be per-invoice, not account-total — *falsifier: partial payment treated as full settlement; remaining open item not revalued.*

EC-6 **Entity disposed of mid-period** — Subsidiary sold intra-period: its results are consolidated up to disposal date; IC eliminations only for that sub-period; gain/loss on disposal recognised in group P&L — *falsifier: subsidiary included for full period; excess profit and IC balances not prorated.*

EC-7 **Negative inventory position** — Inventory goes negative intra-period (over-shipment); cost sub-ledger must handle negative quantities; GL inventory account may carry a credit balance pending correction — *falsifier: negative inventory valued at zero; cost of sales understated.*

EC-8 **Long-term IC monetary item (IAS 21 §32)** — Repayment not planned or likely: FX difference goes to OCI (group equity), not P&L; requires explicit tagging per agreement — *falsifier: IC loan tagged as short-term; FX swings hit group P&L volatility incorrectly.*

EC-9 **Hyperinflationary entity (IAS 29)** — Entity in hyperinflationary economy restates all non-monetary items to current purchasing power before translation; standard revaluation rules do not apply — *falsifier: hyperinflationary entity processed through standard FX revaluation; balance sheet understates real values.*

EC-10 **Dual-book entity (local GAAP + IFRS)** — Entity maintains two sets of books; only one set feeds the consolidated TB; the other feeds statutory filings; mappings must be separate and non-overlapping — *falsifier: IFRS and local-GAAP depreciation both flow into consolidation; asset balance double-counted.*

EC-11 **Intragroup dividend declared but not paid** — Declared dividend creates IC receivable/payable that must be eliminated; if withholding tax applies, the tax payable to external authority is not eliminated — *falsifier: entire IC dividend entry eliminated including the external WHT payable; tax liability disappears from consolidated BS.*

EC-12 **Multi-hop IC chain (A → B → C)** — Three-entity chain requires bottom-up elimination order; B-C eliminated before A-B to avoid residuals in B's equity — *falsifier: A-B eliminated first; B still carries C's un-eliminated investment; A's elimination is against wrong equity figure.*

EC-13 **Zero-balance accounts with disclosure requirement** — Some accounts must appear on TB even with zero balance (e.g., authorised share capital); TB extraction must not suppress zero-balance lines for accounts on a disclosure list — *falsifier: zero-balance line suppressed; statutory note on share capital cannot be completed.*

EC-14 **Back-dated error discovered after period lock** — A material error in a locked period must be corrected either via a prior-period adjustment (with comparatives restated) or a current-period adjustment with disclosure; the mechanism must be defined in the close procedure — *falsifier: error corrected silently in current period; comparatives not restated; auditor notices inconsistency.*

EC-15 **Intercompany transaction with multiple currencies** — Entity A (USD functional) invoices Entity B (GBP functional) in EUR; three currencies involved; each entity translates to functional currency; consolidation translates to presentation currency; three rate pairs required — *falsifier: system assumes IC transactions are in one of the two entities' functional currencies; EUR transaction mismapped.*

---

## SF — Silent Failure Modes

SF-1 **Revaluation posts to wrong period** — Revaluation job uses system date rather than close period date; if run on the first day of N+1, it posts to N+1 — *detected by: checking revaluation journal posting date against close period.*

SF-2 **IC elimination misses an account pair** — Matching logic uses exact account code; if one entity uses account 1300 and counterpart uses 1300A (mapped but with a suffix), the pair is unmatched — *detected by: IC difference report showing residual in 1300 after elimination.*

SF-3 **Accrual reversal posts to wrong account** — Reversal uses the reverse of the original entry; if original entry was corrected but reversal template was not, reversal hits a different account — *detected by: comparing original accrual account vs. reversal account in the auto-reversal log.*

SF-4 **Sub-ledger and GL agree in total but not in detail** — Batch netting: 100 sub-ledger lines are netted to one GL journal; sub-ledger total = GL total, but individual line offsets are lost — *detected by: drilling from GL journal to source sub-ledger lines and confirming each line posts correctly.*

SF-5 **Trial balance nets to zero but contains offsetting errors** — Two entries of opposite-sign errors in different accounts cancel each other; TB zero-sum check passes — *detected by: analytic review of individual account movements against expectations.*

SF-6 **Stale rate in rate table** — One currency rate was not updated for the period (data feed gap); system uses last available rate from a prior period — *detected by: rate table audit log showing rate effective date for each currency.*

SF-7 **Bank recon carries old unresolved items** — Uncleared items from prior months are rolled forward without investigation; reconciliation "balances" but with growing aged items — *detected by: ageing report of reconciling items; items > 30 days flagged.*

SF-8 **Consolidation scope not updated** — New subsidiary included in operational reporting but not in elimination scope file; its IC transactions unchecked — *detected by: comparing legal entity register to elimination scope file before each close.*

SF-9 **IC FX difference routed to suspense** — System cannot automatically allocate IC FX difference; it posts to a suspense account; suspense is not reviewed — *detected by: suspense account balance report; any non-zero balance at hard close requires resolution.*

SF-10 **Depreciation run completes with excluded asset class** — A new asset class was added that does not match any depreciation rule; assets in that class produce zero depreciation silently — *detected by: depreciation run exception report listing assets with zero depreciation by class.*

SF-11 **FX revaluation is non-idempotent due to a bug** — Running revaluation twice accumulates gain/loss instead of replacing it; extra entries hidden in revaluation account — *detected by: comparing net revaluation balance before and after a second run; should be unchanged.*

SF-12 **Accrual in foreign currency not flagged as monetary** — Accrual journal is posted without a currency tag that marks it as monetary; revaluation filter excludes it; functional-currency balance drifts — *detected by: revaluation filter test against all open accrual accounts; confirm each is classified monetary.*

---

## OR — Ordering / Sequencing

OR-1 **Step 1: Rate table lock** — Exchange rates for the close period are finalised and locked; no further updates — required before any currency-dependent step — *falsifier: rate updated after revaluation; earlier postings use different rate than later ones.*

OR-2 **Step 2: Sub-ledger cutoff and lock** — All sub-ledgers (AR, AP, inventory, FA, payroll) are locked to the close period; lock date enforced by system — *falsifier: sub-ledger entries arrive after accrual run; accrual double-counts.*

OR-3 **Step 3: Sub-ledger ↔ GL control account reconciliation** — Before GL work begins, each sub-ledger total is reconciled to its GL control account; differences resolved — *falsifier: GL control wrong entering revaluation; revaluation operates on incorrect balance.*

OR-4 **Step 4: Accruals and deferrals posting** — All accruals (standard recurring + non-standard), GR/IR, prepaid amortisation, interest accrual, deferred revenue recognition are posted; auto-reversal dates set — *falsifier: accruals missed because GL work (revaluation) began before accrual run.*

OR-5 **Step 5: Depreciation and payroll posting** — FA depreciation and payroll journals confirmed in GL — *falsifier: depreciation missed; asset balance overstated entering revaluation (though depreciation itself is not revalued, the net monetary exposure may change).*

OR-6 **Step 6: Bank reconciliation completion** — All bank accounts reconciled; remaining items documented; GL cash balance confirmed — *falsifier: cash balance not confirmed before trial balance; TB cash is unreliable.*

OR-7 **Step 7: FX Revaluation** — Revaluation runs against complete, locked, reconciled balances; revaluation report reviewed — *falsifier: revaluation premature; subsequent accrual posting not revalued.*

OR-8 **Step 8: IC balance confirmation and investigation** — IC pairs confirmed across entities; out-of-balance items investigated and corrected (or explained) — *falsifier: elimination runs on unconfirmed balances; residual errors blamed on FX difference.*

OR-9 **Step 9: Intercompany elimination** — Elimination journals posted in consolidation ledger; multi-level order followed (bottom-up for investment/equity) — *falsifier: elimination order wrong; investment-in-subsidiary includes un-eliminated lower-tier IC profit.*

OR-10 **Step 10: Trial balance extraction** — TB extracted after all journals (including eliminations) are in GL; extraction parameters (ledger set, period, currency) documented — *falsifier: TB extracted before final elimination batch; incomplete view circulated.*

OR-11 **Step 11: Trial balance review and sign-off** — Controller reviews TB: zero-net check, analytical review of movements, investigation of unusual items; sign-off documented — *falsifier: TB signed off without analytic review; material accrual omission undetected.*

OR-12 **Step 12: Hard close (period lock)** — GL period locked; no further postings without formal override; lock event logged — *falsifier: period left soft-closed; late entries arrive and alter signed-off TB.*

OR-13 **Step 13: Auto-reversal posting for N+1** — Staged reversals released into N+1 period once it opens; confirmed they did not land in period N — *falsifier: reversal date miscalculated; reversal in N offsets accrual; TB already wrong before sign-off.*

OR-14 **Sequencing constraint: revaluation after elimination is wrong** — Elimination must follow revaluation, not precede it; any workflow that reverses these steps is non-compliant — *falsifier: workflow configuration allows elimination before revaluation; IC balances at mixed rates.*

---

## AU — Auditability

AU-1 **Journal entry unique ID and lineage** — Every journal line carries a unique, non-reusable ID; reversals reference original entry ID; source document reference (invoice #, bank ref, etc.) present — *falsifier: two journals have same ID due to batch import conflict; impossible to trace individual entries.*

AU-2 **Dual authorisation on material journals** — Journals above materiality threshold require a second approver (not the preparer); approval timestamps recorded — *falsifier: large manual accrual approved by preparer alone; segregation of duties violation.*

AU-3 **Rate table provenance** — Rate table records source URL or data feed, extraction timestamp, and approver sign-off; rates are immutable after lock — *falsifier: auditor cannot verify rate used in revaluation because table has been overwritten.*

AU-4 **Sub-ledger ↔ GL reconciliation retained** — The reconciliation report (per sub-ledger, per period) is stored as a versioned artefact linked to the close period — *falsifier: reconciliation run but not saved; auditor must re-run it and cannot guarantee it matches what was done.*

AU-5 **Bank reconciliation retained with signatory** — Signed bank recon per account stored; name of preparer and reviewer, date, version of bank statement used — *falsifier: bank recon overwritten by next month's run; prior period evidence lost.*

AU-6 **Accrual schedule with rationale** — Each non-standard accrual entry accompanied by a calculation note and business rationale in the journal header or an attached workpaper — *falsifier: accrual booked for "month-end provision" with no quantification; auditor cannot validate.*

AU-7 **FX revaluation run report retained** — Report listing each revalued item/account, rate used, prior balance, revalued balance, gain/loss; stored per run — *falsifier: auditor needs to verify FX line in income statement; no per-item trace available.*

AU-8 **IC elimination workpaper** — Workpaper shows each matched IC pair, elimination journal, and any residual with explanation; stored per close — *falsifier: elimination "completed" but no record of which pairs matched; scope creep or omissions undetectable.*

AU-9 **Trial balance version log** — Each TB extraction is versioned; the final signed-off version is immutable; any subsequent extraction (e.g., after a correction) creates a new version number — *falsifier: corrected TB overwrites original; auditor cannot see what was changed.*

AU-10 **Hard-close event log** — System log records: who initiated hard close, timestamp, period locked, any overrides applied — *falsifier: period was re-opened and re-closed; no record of the interim state.*

AU-11 **Post-close adjustment log** — Any entry in a locked period (via override) generates an exception report and requires documented approval at CFO or above level — *falsifier: controller quietly adjusts a locked period; auditor sees adjusted numbers without knowing a correction occurred.*

AU-12 **Consolidation scope version** — The legal entity register used for each close (in-scope, out-of-scope, new entries, disposals) is archived per period — *falsifier: scope file updated for next month's close before current month's evidence is archived; scope history lost.*

---

## SB — Scope Boundaries

SB-1 **Tax provision (current and deferred): OUT** — Tax computation is a separate downstream process feeding off the pre-tax TB; it is not part of the close mechanics — *pulled back in if: the entity books deferred tax journals as part of close (IAS 12 entries), in which case deferred tax accrual IS a close step.*

SB-2 **Payroll computation (gross pay calculation): OUT** — Payroll processing (gross-to-net, tax withholding calculations) is a separate system; only the payroll journal entry output is in scope — *pulled back in if: payroll system is integrated and payroll journal is auto-generated; then posting and reconciliation of the payroll journal are in scope.*

SB-3 **Management reporting allocations and recharges: OUT** — Inter-cost-centre allocations for management P&L are a separate step after close; they do not affect the statutory TB — *pulled back in if: recharges generate real IC invoices between legal entities; then they are IC transactions subject to elimination.*

SB-4 **Budget vs. actual variance reporting: OUT** — Analytics layer downstream of the TB; does not affect close correctness — *pulled back in if: budget data lives in the same ledger and a poorly-designed extraction could commingle actuals and budget.*

SB-5 **Cash flow statement preparation: OUT** — Cash flow is derived from the TB and note disclosures; it is a reporting output, not a close input — *pulled back in if: an indirect-method cash flow requires identifying non-cash items; those items must be correctly tagged in the GL as part of close.*

SB-6 **External audit execution: OUT** — Auditors review the close artefacts; designing their procedures is not in scope — *pulled back in: audit trail design (AU-1 through AU-12) and artefact retention ARE in scope because the close must produce auditable records.*

SB-7 **Statutory consolidation above group level (e.g., ultimate parent): OUT** — The task covers entity-level and immediate-group IC elimination; statutory consolidation with minority interest, goodwill allocation beyond what is required for IC elimination is partially out — *pulled back in if: the task requires the consolidated TB to be the final statutory product, in which case goodwill and minority interest computations are in scope.*

SB-8 **Intercompany pricing / transfer pricing compliance: OUT** — Whether IC prices are arm's-length is a tax/TP question; the close assumes IC prices are set; it only ensures they are eliminated — *pulled back in if: TP adjustments are booked as close-period journals; then they are in scope as a specific journal type.*

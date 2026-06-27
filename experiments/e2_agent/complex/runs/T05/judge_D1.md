# BLIND JUDGE VERDICT — T05 / candidate D1

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Define per-endpoint SLIs ... p50/p99/p999 latency targets per endpoint class; error-rate target ...; error-budget arithmetic (shared, verified formula); window type (rolling vs calendar)" | SLIs + targets + budget + window |
| D2 | D | — | COVERED | "Instrument: request latency histograms ...; saturation signals (CPU, memory, thread pool ...); per-downstream-dependency p99 + error rate" | signal collection pass (cand D3) |
| D3 | D | — | COVERED | "Define fast-burn (1 h window, ~14× rate) and slow-burn (6 h window, ~6× rate) alert pairs" | budget-burn alerting pass (cand D2/D4) |
| D4 | D | — | COVERED | "Admission control at ingress/gateway layer; ... graceful degradation responses"; "HPA metric selection ..."; "Per-dependency independent circuit breakers" | full actuator set: shed+autoscale+failover+rate-limit+degrade (cand D5/D6/D7) |
| D5 | D | — | COVERED | "incident declaration thresholds (explicit P1/P2 criteria ...)"; "war room / incident bridge pre-defined" | triage→mitigate (runbook-linked)→restore (cand D8) |
| D6 | D | — | PARTIAL | "24/7 on-call rotation with no gaps (primary/secondary/incident commander roles explicit); escalation timeout enforcement" | rotation+escalation leg met; **missing leg: break-glass / emergency-access reachable when SSO is part of the outage** |
| D7 | D | — | COVERED | "post-incident review triggered automatically for P1/P2 or budget-gate breach"; "runbook currency (reviewed and updated after each incident)" | postmortem + feed-back into regime |
| D8 | D | — | COVERED | "node autoscaler buffer (spare node capacity or pre-provisioning to avoid Pending pods)"; "pre-scaling for known predictable spikes" | standing headroom/provisioning (cand D6) |
| D9 | D | — | COVERED | "fallback strategy per dependency (tested in drills, with own SLI)"; "multi-region/AZ failover procedure (automated where possible, regularly tested)" | drills/exercise before needed (cand D7) |
| Dep1 | Dep | FM-1 | COVERED | "A sustained error rate at 2–3× background level triggers an alert before budget is fully exhausted" | fire-before-breach per SLI (cand V3 + D2) |
| Dep2 | Dep | FM-1 | COVERED | "alert-to-runbook linkage for every actionable alert" | alert→specific response wiring (cand D4) |
| Dep3 | Dep | FM-2 | COVERED | "Shedding reduces accepted RPS; if HPA uses RPS as its scaling signal, shedding causes scale-down exactly when capacity is most needed" | autoscale↔shed/admission on shared overload signal + signal-ownership fix (cand Dep1) |
| Dep4 | Dep | FM-2 | COVERED | "Client retries multiply effective RPS to a degraded dependency; amplification can push a partially degraded dependency into full failure"; back-pressure: "retry budget ...; exponential backoff with full jitter on retries" | retry storm + back-pressure (cand Dep4 + D7) |
| Dep5 | Dep | FM-2 | COVERED | "Traffic rerouted to failover region may exceed pre-provisioned capacity; failover region autoscaler starts cold and scale-out takes minutes" | failover lands on cold/under-warmed target + sized/pre-provisioned standby (cand Dep14) |
| Dep6 | Dep | FM-2 | COVERED | "asymmetric cooldowns (scale-up fast: 30–60 s; scale-down slow: 5–10 min)"; "hysteresis/flap suppression (persist N windows before fire, clear M windows before resolve)" | threshold↔autoscale flapping + hysteresis/cooldown band (cand D6 + D4) |
| Dep7 | Dep | FM-2 | NOT-COVERED | | failover-decision oscillation / split-brain with fencing/quorum/cooldown guard not named ("active-active vs active-passive ... consistency tradeoffs" does not assert the flip-loop coupling or its guard) |
| Dep8 | Dep | FM-2 | COVERED | "Shed (429) requests excluded from SLI denominator; reported availability exceeds actual user-experienced availability" | shedding/degradation games the SLI; SLI must see shed/degraded user (cand Dep10+Dep11) |
| Dep9 | Dep | FM-2 | COVERED | "Per-dependency independent circuit breakers ...; bulkhead isolation ...; fallback strategy per dependency" | degrading dependency contained before cascade (cand D7) |
| Dep10 | Dep | FM-1 | COVERED | "alert ownership and routing to on-call rotation; ... escalation timeout in alerting system (primary non-ack → secondary → incident commander)" | ownership-routed escalation within time bound |
| Dep11 | Dep | FM-1, FM-7 | COVERED | "runbook currency (reviewed and updated after each incident)"; "post-incident review triggered automatically for P1/P2 or budget-gate breach" | incident→postmortem→regime-update loop closes |
| Dep12 | Dep | FM-1, FM-5 | COVERED | "error budget exhaustion governance enforced in CI/CD pipeline (not policy-document only)" | budget gates releases/change velocity (cand D8/D2/Dep16) |
| V-I1 | V | FM-2 | NOT-COVERED | | no global "no mitigation breaks the SLO via another axis" spanning invariant; only per-pair couplings + V12 (mitigation cost *documented*, not non-breach enforced) |
| V-I2 | V | FM-1 | COVERED | "A breach on a low-volume critical endpoint triggers an alert even when aggregate metrics are within target" | roster: no SLI silently breaches (cand V2) |
| V-I3 | V | FM-4 | COVERED | "escalation timeout enforcement in alerting system (not just process)" | fail propagates to a responder/mitigation in bounded time |
| V-I4 | V | FM-3 | COVERED | "real-time burn rate as a continuously tracked metric (not computed only at alert time)"; "error-budget arithmetic (shared, verified formula); window type (rolling vs calendar)" | honest/monotonic budget accounting over window |
| V-I5 | V | FM-4 | NOT-COVERED | | per-loop damping is scored at Dep6; no aggregate "the regime as a whole converges / doesn't oscillate" assertion |
| V-I6 | V | FM-1 | COVERED | "24/7 on-call rotation with no gaps (primary/secondary/incident commander roles explicit)" | gap-free coverage over all time |
| V-I7 | V | FM-1 | COVERED | "request prioritization by business criticality (high-priority shed last)" | criticality shed-order, core path last |
| V-I8 | V | FM-6 | NOT-COVERED | | SLO target never checked for feasibility against composed hard-dependency critical-path SLOs (target ≤ critical-path product) |
| V-E1 | V | FM-4 | COVERED | "The design explicitly addresses bursts shorter than scale-out time; documented reliance on pre-provisioning + load shedding, not reactive autoscaling" | spike outruns scale-up → shed/queue (cand V6) |
| V-E2 | V | FM-6 | COVERED | "fallback strategy per dependency (tested in drills, with own SLI)" | full-outage fallback / degraded-mode rule |
| V-E3 | V | FM-3 | COVERED | "Per-dependency, per-endpoint signals exist such that degradation of a subset of a dependency's endpoints fires an alert" | gray/partial failure targeted detection (cand V7) |
| V-E4 | V | FM-7 | NOT-COVERED | | no alert-storm grouping/dedup/dependency-aware suppression (one root cause → one incident) |
| V-E5 | V | FM-7 | COVERED | "escalation timeout in alerting system (primary non-ack → secondary → incident commander)" | responder-unreachable → timed escalation to reachable backup |
| V-E6 | V | FM-5 | COVERED | "maintenance-window suppression narrowly scoped to affected components only" | planned-change window silencing that still distinguishes a real breach |
| V-E7 | V | FM-2 | NOT-COVERED | | no cross-incident arbitration / prioritization across ≥2 simultaneous incidents (separate IC per incident, split responders) |
| V-F1 | V | FM-1, FM-6 | COVERED | "Loss of telemetry itself triggers an alert (absence of data ≠ good data)"; "New alert rules are validated ... before going live" | missing/dead/late alert guarded by alert-on-no-data + test (cand V5/V15) |
| V-F2 | V | FM-3, FM-7 | NOT-COVERED | | no "mitigation masks defect / recurring auto-fix must trigger root-cause" claim |
| V-F3 | V | FM-3 | COVERED | "synthetic/canary probes (external, realistic requests, scheduled)" | SLI validated against real user experience (client-side/synthetic) |
| V-F4 | V | FM-7 | NOT-COVERED | | no action-item tracking-to-completion guard (owner+deadline+closure; un-closed items block) |
| N1 | N | — | NOT-COVERED | | whole-region DR/multi-region failover NOT excluded — candidate puts multi-region failover IN scope (D7/Dep14) |
| N2 | N | — | COVERED | "Multi-quarter demand forecasting and hardware procurement are out" | capacity/cost ceiling is a fixed input, raising it upstream (cand N5) |
| N3 | N | — | NOT-COVERED | | no exclusion declaring underlying service code/architecture quality assumed-fixed (rebuild out, surfaced via postmortem) |
| N4 | N | — | COVERED | "Authentication failures, credential compromise, and non-volumetric attacks are out. In-scope pull-back: admission control and shedding responses to volumetric DDoS ... in scope" | DDoS/abuse decisioning is a separate security regime (cand N3) |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | duplicate candidate phrases |
|---|---|---|---|
| D1 | 2 | 1 | D1 "Define per-endpoint SLIs ..."; V1 "SLI unambiguity — any two engineers reach the same pass/fail verdict" |
| D3 | 2 | 1 | D2 "fast-burn ... and slow-burn ... alert pairs"; D4 "Multi-window burn-rate alerts (fast + slow, per D2)" |
| Dep6 | 2 | 1 | D6 "asymmetric cooldowns ..."; D4 "hysteresis/flap suppression (persist N windows before fire, clear M windows before resolve)" |
| Dep8 | 2 | 1 | Dep10 "HTTP-200 degraded responses ... counted as 'good' in SLI"; Dep11 "Shed (429) requests excluded from SLI denominator" |
| Dep12 | 3 | 2 | D2 "graduated error-budget depletion gates at defined thresholds ... triggering governance responses"; D8 "error budget exhaustion governance enforced in CI/CD pipeline"; Dep16 "Budget-threshold deployment freeze ... enforced in CI/CD" |
| V-F1 | 3 | 2 | V5 "Loss of telemetry itself triggers an alert"; V15 "Alert rule validity is tested before deployment"; V8 "Circuit breaker stuck open is detectable" |

**Total ballast = 8.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| Dep8 "Per-replica bulkhead state → LB routing — ... LB has no visibility into per-replica bulkhead utilization; routes to already-exhausted instances" | UNMATCHED — human review |
| Dep13 "Scale-event noise suppression → Genuine saturation visibility — ... OOM kills or memory pressure during scale-out go undetected" | UNMATCHED — human review |
| Dep15 "Circuit half-open probe → LB routing — ... circuit never closes on those replicas" | UNMATCHED — human review |
| Dep17 "Incident commander role → Status-page communication — ... extended customer-facing silence during active incident" | UNMATCHED — human review |
| V9 "Traffic shape change without volume change is handled — ... payload 3× larger; RPS unchanged; CPU-based HPA blind" | UNMATCHED — human review |
| V10 "Test/staging traffic excluded from SLI" | UNMATCHED — human review |
| V11 "Health-check traffic is never shed — Load-shedding logic explicitly exempts health-check and readiness-probe requests" | UNMATCHED — human review |
| V13 "SLO targets reviewed on a defined cadence — ... stale targets are not acceptable" | UNMATCHED — human review |
| N1 "Deployment orchestration tooling — Canary/blue-green deployment mechanics and rollback tooling are out" | UNMATCHED — human review |
| N2 "Data durability and backup/restore — RPO, backup mechanics, and data recovery procedures are out" | UNMATCHED — human review |
| N6 "Correctness / data quality SLO — Whether the service returns correct results is out of scope ... a declared SLI gap" | UNMATCHED — human review |

**Total unmatched = 11.** (Authority-plane / SoD statements — D8 "role separation between incident mitigation and customer communication", "incident commander roles explicit" — ignored per §1, neither credited nor penalized.)

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 8/9   Dep = 11/12   V = 12/19   N = 2/4
  by FM tag:     FM-1 = 9/9   FM-2 = 6/9   FM-3 = 3/4   FM-4 = 2/3   FM-5 = 2/2   FM-6 = 2/3   FM-7 = 2/5
  PARTIAL counts: D = 1   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 8
  unmatched candidate points (human-review flag):    total = 11
```

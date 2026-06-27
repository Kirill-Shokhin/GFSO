# BLIND JUDGE VERDICT — T05 / candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Define per-endpoint SLIs ... p50/p99/p999 latency targets per endpoint class; error-rate target ... error-budget arithmetic (shared, verified formula); window type" | SLI + targets/windows + budget |
| D2 | D | — | COVERED | "Instrument: request latency histograms ...; saturation signals ...; per-downstream-dependency p99 + error rate; ... synthetic/canary probes" | signal collection / instrumentation |
| D3 | D | — | COVERED | "Define fast-burn (1 h window, ~14× rate) and slow-burn (6 h window, ~6× rate) alert pairs" | budget-burn alerting |
| D4 | D | — | COVERED | "Admission control at ingress/gateway" (D5); "HPA metric selection" (D6); "Per-dependency independent circuit breakers ... failover procedure" (D7) | shed+autoscale+failover+rate-limit+degrade = the actuator set |
| D5 | D | — | COVERED | "incident declaration thresholds (explicit P1/P2 criteria ...); ... role separation between incident mitigation and customer communication" + "runbook currency" | incident-handling pass |
| D6 | D | — | PARTIAL | "24/7 on-call rotation with no gaps (primary/secondary/incident commander roles explicit); escalation timeout enforcement in alerting system" | rotation+escalation legs met; MISSING break-glass / emergency-access reachable when SSO/auth is part of the outage |
| D7 | D | — | COVERED | "post-incident review triggered automatically for P1/P2 or budget-gate breach" + "runbook currency (reviewed and updated after each incident)" | learning pass that feeds back into the regime |
| D8 | D | — | COVERED | "node autoscaler buffer (spare node capacity or pre-provisioning to avoid Pending pods)"; "pre-scaling for known predictable spikes" | standing headroom (distinct from D4-autoscale) |
| D9 | D | — | COVERED | "fallback strategy per dependency (tested in drills, with own SLI)"; "multi-region/AZ failover procedure (automated where possible, regularly tested)" | drill/exercise of mitigation paths |
| Dep1 | Dep | FM-1 | COVERED | "A sustained error rate at 2–3× background level triggers an alert before budget is fully exhausted" (V3) | alert fires before budget burn |
| Dep2 | Dep | FM-1 | COVERED | "alert-to-runbook linkage for every actionable alert" (D4) | alert→specific mitigation wiring |
| Dep3 | Dep | FM-2 | COVERED | "Load shedding → Autoscaler signal — Shedding reduces accepted RPS; if HPA uses RPS as its scaling signal, shedding causes scale-down exactly when capacity is most needed" (Dep1) | autoscale↔shed double-correction on shared overload signal; arbiter = decouple HPA from shed signal |
| Dep4 | Dep | FM-2 | COVERED | "service enters degraded mode at 60% capacity; downstream clients detect partial responses and retry 3×; effective inbound load rises to 180%" (Dep20) + "retry budget ...; exponential backoff with full jitter" (D7) | retry-storm-vs-overload + back-pressure guard |
| Dep5 | Dep | FM-2 | COVERED | "Traffic rerouted to failover region may exceed pre-provisioned capacity; failover region autoscaler starts cold ... latency SLO breaches in failover region during an otherwise successful failover" (Dep14) | failover lands load on cold/under-warmed target; cache-warmth angle also in Dep6 |
| Dep6 | Dep | FM-2 | COVERED | "asymmetric cooldowns (scale-up fast: 30–60 s; scale-down slow: 5–10 min)" (D6) + "hysteresis/flap suppression (persist N windows before fire, clear M windows before resolve)" (D4) | threshold↔hysteresis flapping + dwell/cooldown band |
| Dep7 | Dep | FM-2 | NOT-COVERED |  | failover-decision oscillation / split-brain (dual-primary) + fencing/quorum/cooldown guard absent (Dep23 covers *circuit* oscillation, a different decision) |
| Dep8 | Dep | FM-2/FM-3 | COVERED | "Shed (429) requests excluded from SLI denominator; reported availability exceeds actual user-experienced availability" (Dep11); "HTTP-200 degraded responses ... counted as 'good' in SLI" (Dep10) | shedding/degradation games the SLI |
| Dep9 | Dep | FM-2 | COVERED | "Per-dependency independent circuit breakers ...; timeout hierarchy ...; bulkhead isolation (separate thread pools/connection pools/semaphores per dependency); fallback strategy per dependency" (D7) | degrading dependency contained before cascade |
| Dep10 | Dep | FM-1 | COVERED | "alert ownership and routing to on-call rotation" (D4) + "every alert rule's routing target resolves to a real, currently on-call person or rotation; stale team aliases ... detected before they silently swallow an alert" (V18) | page reaches the resolver (no silent swallow) |
| Dep11 | Dep | FM-1/FM-5/FM-7 | COVERED | "runbook currency (reviewed and updated after each incident)" + "post-incident review triggered automatically" (D8) | incident→postmortem→regime-update loop closes (tracked-to-completion guard tested separately at V-F4) |
| Dep12 | Dep | FM-1/FM-5 | COVERED | "Budget-threshold deployment freeze ... enforced in CI/CD" (Dep16); "error budget exhaustion governance enforced in CI/CD pipeline" (D8) | error budget gates releases/change velocity |
| V-I1 | V | FM-2 | NOT-COVERED |  | no SPANNING "no mitigation breaks the SLO via another axis" invariant; cross-axis harms appear only as isolated instances (scored on Dep edges / unmatched) |
| V-I2 | V | FM-1 | COVERED | "The fast-burn (1 h / ~14×) and slow-burn (6 h / ~6×) alert pair is verified to cover all burn rates that would exhaust the budget ...; no burn rate falls in an undetected gap" (V20) | roster completeness — no SLI silently breaches |
| V-I3 | V | FM-4 | COVERED | "the buffer must be wide enough that the alert-to-remediation latency (diagnosis + action) does not itself consume the gap and allow an external breach before mitigation completes" (D11) | bounded time-to-mitigate relative to budget burn |
| V-I4 | V | FM-3 | COVERED | "real-time burn rate as a continuously tracked metric (not computed only at alert time)" (D2) | track budget burn over the window (credit phrase) |
| V-I5 | V | FM-4 | NOT-COVERED |  | per-pair damping present (D4/D6 → scored on Dep6); no AGGREGATE "the control loops as a whole converge / don't oscillate" predicate |
| V-I6 | V | FM-1 | COVERED | "24/7 on-call rotation with no gaps" (D8) + "routing target resolves to a real, currently on-call person or rotation" (V18) | gap-free coverage terminating at a reachable owner |
| V-I7 | V | FM-1 | COVERED | "request prioritization by business criticality (high-priority shed last)" (D5) | criticality-ordered shedding |
| V-I8 | V | FM-6 | COVERED | "compute compound availability (product of independent dependencies); confirm the service's own SLO target is at or below this ceiling" (D10) | target feasibility vs composed critical path |
| V-E1 | V | FM-4 | COVERED | "The design explicitly addresses bursts shorter than scale-out time; documented reliance on pre-provisioning + load shedding, not reactive autoscaling" (V6) | spike outruns scale-up → shed/queue |
| V-E2 | V | FM-6 | COVERED | "fallback strategy per dependency (tested in drills, with own SLI)" (D7) | full-outage fallback (distinct from slow-dep circuit-break) |
| V-E3 | V | FM-3 | COVERED | "Per-dependency, per-endpoint signals exist such that degradation of a subset of a dependency's endpoints fires an alert. Falsifier: DB read replica degraded; aggregate DB error rate below threshold; no alert" (V7) | partial/gray failure, targeted detection |
| V-E4 | V | FM-7 | NOT-COVERED |  | alert grouping / dependency-aware suppression / dedup of one-root-cause storm absent (Dep22 names a storm but no dedup rule; D14 is chronic fatigue governance, not acute grouping) |
| V-E5 | V | FM-7 | COVERED | "escalation timeout in alerting system (primary non-ack → secondary → incident commander)" (D4) | responder-unreachable → timed escalation to reachable backup |
| V-E6 | V | FM-5 | COVERED | "maintenance-window suppression narrowly scoped to affected components only" (D4) | silence expected burn while a real breach elsewhere still fires |
| V-E7 | V | FM-2 | NOT-COVERED |  | concurrent multi-incident arbitration (rank ≥2 incidents, split responders, separate IC) absent |
| V-F1 | V | FM-1/FM-6 | COVERED | "Loss of telemetry itself triggers an alert (absence of data ≠ good data)" (V5) + "New alert rules are validated ... before going live" (V15) | alert can be missing/dead + alert-on-no-data + test-the-alerts guards |
| V-F2 | V | FM-3/FM-7 | NOT-COVERED |  | "mitigation masks the defect (recurring auto-fix), force root-cause/learning" absent (D12 escalates degraded-mode on duration but does not force root-cause) |
| V-F3 | V | FM-3 | COVERED | "synthetic/canary probes (external, realistic requests, scheduled)" (D3) | validate SLI against real user experience (distinct from Dep8 shedding) |
| V-F4 | V | FM-7 | NOT-COVERED |  | "prevention action-items tracked to completion (owner + deadline + closure)" absent; only "post-incident review triggered" + runbook update (the loop-existing = Dep11), not the follow-through guard |
| N1 | N | FM-1 | NOT-COVERED |  | candidate puts multi-region IN scope (D15, D7 failover); whole-region DR is never declared out-of-scope |
| N2 | N | FM-1 | COVERED | "Multi-quarter demand forecasting and hardware procurement are out. In-scope pull-back: the scale ceiling and minimum pre-provisioned capacity values that bound autoscaling" (N5) | capacity ceiling = fixed input, raising it upstream |
| N3 | N | FM-1 | NOT-COVERED |  | "the underlying service code/architecture is assumed fixed; rebuilding it is out" not declared (N6 correctness-SLO is a different exclusion) |
| N4 | N | FM-1 | COVERED | "Security incident response (non-volumetric) ... out. In-scope pull-back: admission control and shedding responses to volumetric DDoS ... are in scope" (N3) | DDoS/abuse decisioning = separate security regime; loop sheds load mechanically |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | duplicate candidate phrases |
|---|---|---|---|
| Dep5 | 2 | 1 | Dep14 "failover region autoscaler starts cold"; Dep6 "After cache flush, restart, or failover, all concurrent requests miss and simultaneously hit DB/origin" |
| Dep6 | 2 | 1 | D6 "asymmetric cooldowns"; D4 "hysteresis/flap suppression (persist N windows ...)" |
| Dep8 | 3 | 2 | Dep11 "Shed (429) requests excluded from SLI denominator"; Dep10 "HTTP-200 degraded responses ... counted as 'good'"; V17 "rate of actively shed requests ... a named, dashboarded metric" |
| Dep12 | 3 | 2 | Dep16 "Budget-threshold deployment freeze ... enforced in CI/CD"; D8 "error budget exhaustion governance enforced in CI/CD pipeline"; D2 "graduated error-budget depletion gates ... triggering governance responses" |
| V-E1 | 3 | 2 | V6 "bursts shorter than scale-out time"; Dep21 "HPA creates pods that stay Pending ... 3–5 min"; V14 "Autoscaler reaching max_replicas ... fires a signal distinct from normal scaling" |
| V-E3 | 2 | 1 | V7 "degradation of a subset of a dependency's endpoints fires an alert"; V2 "A breach on a low-volume critical endpoint triggers an alert even when aggregate metrics are within target" |
| V-E6 | 2 | 1 | D4 "maintenance-window suppression narrowly scoped"; Dep7 "Broad suppression scoped to a component masks simultaneous unrelated failures" |
| V-F1 | 4 | 3 | V5 "Loss of telemetry itself triggers an alert"; V15 "New alert rules are validated ... before going live"; V16 "A known synthetic condition ... fire an alert on a defined interval"; Dep19 "notification delivery chain ... can fail independently ... no dead man's switch" |

**Total ballast = 13.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| D9 "Design the CDN layer as a first-class part of the operating regime ... TTL and stale-while-revalidate policy per content type" | UNMATCHED — human review |
| D12 "the maximum permissible duration before degraded mode itself becomes an incident requiring escalation" | UNMATCHED — human review |
| D13 "the telemetry pipeline is itself a single point of failure for the entire operating regime and must be treated as one" | UNMATCHED — human review |
| D14 "per-shift page-count target ...; a defined process and cadence for retiring alerts that have not fired ... in N months" | UNMATCHED — human review |
| D15 "specify whether SLO measurement is global ..., per-region independent, or both" | UNMATCHED — human review |
| Dep2 "New pods have higher latency until JIT cache warms ...; p99 spikes during scale-out" | UNMATCHED — human review |
| Dep3 "Fast-fail (503/fallback) responses from open circuits consume error budget" | UNMATCHED — human review |
| Dep4 "Client retries multiply effective RPS to a degraded dependency; amplification can push a partially degraded dependency into full failure" | UNMATCHED — human review |
| Dep5 "if HPA_max × N > DB max_connections, scale-out itself causes connection exhaustion" | UNMATCHED — human review |
| Dep8 "LB has no visibility into per-replica bulkhead utilization; routes to already-exhausted instances" | UNMATCHED — human review |
| Dep9 "Parent times out and retries while child is still processing first request; 2× load per request" | UNMATCHED — human review |
| Dep12 "the act of preparing for a spike burns budget before the load arrives" | UNMATCHED — human review |
| Dep13 "genuine saturation occurring simultaneously is also suppressed ... OOM kills ... go undetected" | UNMATCHED — human review |
| Dep15 "LB may route the half-open probe to a different replica ...; circuit never closes on those replicas" | UNMATCHED — human review |
| Dep17 "If mitigation and customer communication are the same person, status updates lag" | UNMATCHED — human review (authority/comms plane) |
| Dep18 "synthetic probes are shed and generate probe-failure alerts indistinguishable from user-facing degradation" | UNMATCHED — human review |
| Dep22 "Reactive in-incident actions ... produce metric anomalies that fire new alerts ... flooding the responder" | UNMATCHED — human review |
| Dep23 "An intermittent dependency ... causes the circuit breaker to open, enter half-open, probe, see another failure, re-open, repeat indefinitely" | UNMATCHED — human review |
| Dep24 "shedding always activates after the breach is already occurring" (lagging activation signal) | UNMATCHED — human review |
| Dep25 "A canary instance with a latency regression ... is included in the aggregate SLI; no circuit halts the canary rollout" | UNMATCHED — human review |
| Dep26 "terminationGracePeriodSeconds ... shorter than the maximum in-flight request duration ... hard-killed and return 503s" | UNMATCHED — human review |
| Dep28 "every instance failure carries a guaranteed (interval × threshold × traffic-share) error burn before the LB acts" | UNMATCHED — human review |
| V1 "Given the same metric data, any two engineers reach the same pass/fail verdict for each SLO" | UNMATCHED — human review |
| V4 "Cross-region latency overhead is explicitly modeled; if failover adds latency that breaches the SLO, this is documented as an accepted consequence" | UNMATCHED — human review |
| V8 "An alert fires if any circuit remains open longer than a defined duration after the dependency's own health metric recovers" | UNMATCHED — human review |
| V9 "shape changes that increase per-request processing time trigger a response before SLO breach" | UNMATCHED — human review |
| V10 "Synthetic test traffic does not dilute error rates or inflate the SLI denominator" | UNMATCHED — human review |
| V11 "Load-shedding logic explicitly exempts health-check and readiness-probe requests from all shedding tiers" | UNMATCHED — human review |
| V12 "Each runbook step that itself burns error budget (e.g., rolling restart) has its error cost quantified" | UNMATCHED — human review |
| V13 "Review schedule and trigger conditions are specified; stale targets are not acceptable" | UNMATCHED — human review |
| V19 "a distinct operating mode for when error budget is already at 0% at incident start" | UNMATCHED — human review |
| V21 "The pod termination grace period ... is explicitly verified to be ≥ the maximum expected in-flight request duration" | UNMATCHED — human review |
| V22 "the error-budget debit period and the incident duration ... extend to CDN TTL expiry, not to origin recovery time" | UNMATCHED — human review |
| N1 "Canary/blue-green deployment mechanics and rollback tooling are out" | UNMATCHED — human review |
| N2 "RPO, backup mechanics, and data recovery procedures are out" | UNMATCHED — human review |
| N4 "Browser-side retry logic and client error handling are out" | UNMATCHED — human review |
| N6 "Whether the service returns correct results is out of scope for this operating regime (latency + error-budget only)" | UNMATCHED — human review |
| N7 "Whether remaining error budget carries forward across window resets ... are out" | UNMATCHED — human review |

**Total unmatched candidate points = 38.**

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 8/9   Dep = 11/12   V = 13/19   N = 2/4
  by FM tag:     FM-1 = 11/13   FM-2 = 6/9   FM-3 = 4/5   FM-4 = 2/3   FM-5 = 3/3   FM-6 = 3/3   FM-7 = 2/5
  PARTIAL counts: D = 1   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 13
  unmatched candidate points (human-review flag):    total = 38
```

# T05 — Search Pass 2: New Holes in D1

Only items not already covered by D1 with a distinct falsifier.

---

## New Dep seams (cross-component interaction holes)

**Dep-A. Synthetic probe → load-shedding exemption gap** — Synthetic/canary probes (D3) are real business-logic requests, not health checks; D5 exempts only health-check/readiness traffic from shedding (V11), leaving synthetic probes subject to admission control; when shedding activates, probes are shed and generate probe-failure alerts that appear identical to user-facing degradation. *Falsifier: load test triggers shedding; synthetic probes shed; probe alert fires; responder investigates an apparent user-visible outage that is entirely shed synthetic traffic, delaying discovery of the real cause.*

**Dep-B. Alerting delivery path → silent escalation failure** — The notification delivery chain (metric rule fires → alertmanager routes → PagerDuty/on-call system delivers) can fail independently of the metric pipeline; V5 detects scrape loss, but alerting system unavailability is a distinct failure layer; no dead man's switch exists at the delivery end. *Falsifier: PagerDuty integration misconfigured after a credential rotation; burn-rate alert fires; nobody paged; SLO fully exhausted before a customer complaint surfaces the failure.*

**Dep-C. Degraded-200 responses → downstream retry amplification** — Dep10 captures SLI accounting of HTTP-200 degraded responses; this seam is different: downstream services or clients that detect degradation (schema mismatch, missing fields, empty arrays) treat it as a soft error and retry; retries multiply inbound load on the already-degraded service. *Falsifier: service enters degraded mode at 60% capacity; downstream clients detect partial responses and retry 3×; effective inbound load rises to 180% of capacity; original degradation is amplified into full overload.*

**Dep-D. HPA decision → cluster autoscaler → node provision gap** — D6 lists "node autoscaler buffer" as a mitigation design requirement but does not model the interaction as a seam: when all existing nodes are saturated, HPA creates pods that stay Pending until the cluster autoscaler provisions new nodes (3–5 min on typical cloud); during this window, no new capacity exists and SLO breach proceeds unchecked. *Falsifier: traffic spike exhausts all node capacity; HPA scales; pods Pending; no node-provision alert distinct from normal HPA activity; responder sees autoscaler "working" while latency SLO is breaching.*

**Dep-E. In-incident runbook step → secondary alert storm** — D4 covers planned maintenance-window suppression, which is pre-scoped and pre-approved; distinct from reactive in-incident suppression: a responder executing a runbook action (rolling restart, connection pool flush, rate-limit change) produces metric anomalies that fire new alerts from existing rules, flooding the responder with secondary pages while they are heads-down on the primary incident. *Falsifier: on-call executes rolling restart per runbook; 12 new alerts fire across saturation and error-rate rules; primary burn-rate signal is buried; responder loses track of incident state.*

**Dep-F. Circuit breaker oscillation on intermittent dependency** — V8 covers a circuit stuck open after the dependency recovers; this seam is distinct: an intermittent dependency (5–10% transient failures) causes the CB to open, enter half-open, probe, see another failure, re-open, repeat indefinitely; no alert fires because the CB never satisfies "stuck open after recovery." *Falsifier: dependency has intermittent failures; CB oscillates every 30 s for 3 hours; service alternates between full serving and fallback with no stable state; no alert; budget drains from CB-open 503s.*

**Dep-G. Pre-breach overload signal → shedding activation timing** — D5 requires "activation threshold tuned to avoid premature or late activation" but does not specify that the trigger signal must be a leading indicator of SLO breach rather than the SLO metric itself; if shedding is triggered by p99 crossing the SLO threshold (a lagging signal), it always activates after the breach is already occurring. *Falsifier: shedding threshold set to fire when p99 = SLO target; by the time shedding activates and request volume drops, p99 has already been above target for 90 s; every spike causes a mandatory SLO breach before shedding can help.*

**Dep-H. Canary deployment slice → SLI contamination** — N1 correctly excludes deployment tooling but declares the SLO effect of deployments in scope; no seam captures the interaction: a canary instance with a latency regression or elevated error rate is included in the aggregate SLI; there is no circuit that halts the canary rollout when its per-slice contribution to burn rate crosses a threshold. *Falsifier: canary at 5% traffic has 20% error rate; aggregate error rate rises 1%; burn rate doubles; nobody attributes it to the rollout; rollout continues; budget depletes.*

---

## New V criteria (verifiable predicate holes)

**V-A. Alerting pipeline end-to-end heartbeat (dead man's switch)** — A known synthetic condition is configured to fire an alert on a defined interval; if the notification is not delivered within a tolerance window, an independent escalation path is triggered. *Falsifier: alertmanager webhook silently misconfigured; all alert rules evaluate correctly; no notifications ever leave the system; team unaware for days.*

**V-B. Shed volume is a first-class real-time metric** — The rate of actively shed requests (requests/second rejected by admission control) is a named, dashboarded metric that can itself be alerted on; not the same as D5's "observability for degraded-mode rate," which covers degraded responses (200s), not rejected requests (429s). *Falsifier: load shedding active at 40% of inbound traffic for 25 minutes; accepted RPS dashboard looks normal; nobody knows 40% of users are receiving 429s.*

**V-C. Alert routing targets are verified as valid and current** — A check (automated or on-cadence manual) confirms that every alert rule's routing target resolves to a real, currently on-call person or rotation; stale team aliases and defunct email groups are detected before they silently swallow an alert. *Falsifier: team renamed after reorg; alert routing rules point to old team alias; alias resolves to empty group; all pages for that service silently dropped.*

**V-D. Zero-budget incident policy is explicitly specified** — The design defines a distinct operating mode for when error budget is already at 0% at incident start: who has authority to override the deployment freeze, what the escalation tier is, and whether normal SLO alerting thresholds change. *Falsifier: major incident begins with 0% budget remaining; on-call has no policy guidance; two engineers disagree on whether to freeze all changes or emergency-deploy a fix; resolution delay burns additional goodwill.*

---

## New D components (design holes)

**D-A. CDN operating regime** — N4 explicitly declares CDN configuration in scope (TTL, stale-while-revalidate, error pass-through), but no D component designs it; the CDN layer determines user-perceived SLO independently of the origin service and must have its own signal instrumentation, health checks, failover configuration, and cache-invalidation procedure defined as part of the operating regime. *Falsifier: origin recovers from an incident; CDN serves cached 503s for TTL duration; user-perceived outage extends hours past origin recovery; no CDN health signal in the monitoring suite.*

**D-B. Dependency SLO composition / achievable SLO ceiling** — No component establishes that the service's own SLO target is achievable given its dependency SLO contracts; if the service depends on three 99.9% dependencies, its compound achievable availability is ~99.7% regardless of internal engineering; the SLO target must be designed against this ceiling, not set aspirationally. *Falsifier: service promises 99.95%; three critical dependencies are each 99.9%; every dependency error surfaces as a service error; SLO unachievable by construction; team spends quarters chasing a mathematically impossible target.*

**D-C. Internal vs. external SLO buffer** — No component designs the practice of an internal alerting/operating target tighter than the customer-facing SLO (e.g., internal 99.95% alert threshold vs. 99.9% external SLA); without this buffer, alert-to-remediation latency guarantees that every internal alert fires after the external SLO is already breached. *Falsifier: internal and external targets identical; burn-rate alert fires; responder takes 10 minutes to diagnose; external SLO was already in breach at alert time; no margin existed.*

**D-D. Degraded-mode secondary SLO and maximum duration** — D5 designs graceful degradation responses but no component defines a secondary operating envelope for degraded mode: what latency/error-rate targets apply when degradation is active, and what is the maximum permissible duration before degraded mode itself becomes an incident requiring escalation. *Falsifier: graceful degradation activates at 09:00; no time limit or secondary SLO defined; service runs in degraded mode for 8 hours; no escalation triggered; users experience reduced functionality all day; post-incident review reveals the degradation was never declared as an incident.*

**D-E. Telemetry pipeline resilience design** — D3 specifies what to instrument; V5 detects scrape loss; but no component designs the resilience of the monitoring infrastructure itself: HA configuration for the time-series database, scrape agent redundancy, retention behavior during partial scrape failure, and alertmanager HA mode; the monitoring system is a single point of failure for the entire operating regime. *Falsifier: time-series database disk fills; writes rejected; dashboards stale; alert rules evaluate on last-known values; service degrades without any alert firing; discovered via customer report.*

---

## New N scope clarification

**N-A. SLO window boundary and budget-reset policy** — D1 (SLO spec) requires documenting window type with rationale, but does not scope the policy for what happens at window boundaries: whether remaining budget carries over, whether an in-progress incident is treated as spanning two windows, and how the well-known perverse incentive (defer fixes near end of calendar window since budget resets) is acknowledged and mitigated. *In-scope pull-back*: budget reset that interacts with an active incident (incident started in window N, resolved in window N+1 with budget already reset) requires an explicit handling rule; otherwise incident declaration thresholds become ambiguous across the boundary.

---

## Summary

| Category | New items |
|---|---|
| Dep (new seams) | 8 (A–H) |
| V (new criteria) | 4 (A–D) |
| D (new components) | 5 (A–E) |
| N (scope clarification) | 1 (A) |
| **Total new holes** | **18** |

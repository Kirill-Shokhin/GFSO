# T05 — Search Pass 1 (exhaustive enumeration, no prior decomposition)

---

## Group 1: SLO Primitives (9 items)

**SLI definition** — Each SLO must be backed by a precisely-specified SLI (what counts as a "good" event: status code range, latency threshold per endpoint class, exclusion of health-check traffic). *Falsifier: two engineers given the same metric data reach different pass/fail verdicts because "good request" is ambiguous.*

**Latency SLO targets** — Explicit p50/p99/p999 targets per distinct service tier/endpoint class; a single p99 for a mixed workload masks bimodal distributions. *Falsifier: p99 meets target but p999 exceeds it for a large-payload subset with no alert.*

**Error-rate SLO target** — Fraction of bad events per rolling window defined in advance; "error" must enumerate: 5xx, timeouts, circuit-open responses, partial-content failures. *Falsifier: circuit-breaker fallbacks return 200 with empty payload; counted as success; budget looks healthy while users see degraded data.*

**Error budget calculation** — Budget = (1 − target) × total_requests over rolling window; arithmetic must be verified and shared (not per-team estimates). *Falsifier: ops team and SLO dashboard disagree on remaining budget by >5% due to differing window implementations.*

**SLO window type** — Explicit choice between rolling window (continuous) vs calendar (reset at month end) with documented rationale; each has different burn-rate alerting math. *Falsifier: alerts calibrated for rolling window deployed against calendar-month budget; alerts fire at wrong times at window boundaries.*

**Burn-rate definition** — Rate at which error budget is being consumed relative to the window; fast burn (1 h, high multiplier) and slow burn (6 h, lower multiplier) required for multi-window alerting. *Falsifier: only fast-burn alert exists; slow steady degradation consumes 100% of budget before any page fires.*

**Degraded-response SLI classification** — Responses that succeed but violate the latency target must count against the latency SLO; responses that return degraded content must have an explicit SLI verdict (pass/partial/fail). *Falsifier: fallback responses counted as "good"; error budget does not reflect actual user experience.*

**Per-endpoint vs aggregate SLO** — High-volume cheap endpoints can dominate aggregate metrics and hide SLO breaches on critical low-volume endpoints (checkout vs homepage). *Falsifier: checkout p99 doubles but aggregate p99 unchanged; no alert fires.*

**SLO review cadence** — Targets must be revisited periodically against actual traffic patterns; stale targets lead to either over-alerting or missed breaches. *Falsifier: targets set at launch never revised; service capacity doubled but targets never tightened; team accepts avoidable user pain.*

---

## Group 2: Monitored Signals (18 items)

**Request latency histograms** — Instrumented at handler level as histograms (not summaries), with sufficient bucket resolution to compute accurate p99/p999. *Falsifier: summary-type metric computed per-process cannot be aggregated across replicas; fleet p99 is wrong.*

**Request error rate** — Per-endpoint count of 4xx (client-distinguishable from server errors), 5xx, and application-level errors; must separate retriable from non-retriable. *Falsifier: 4xx inflates error rate; operator acts on false signal or tunes threshold too loose to hide real 5xx.*

**Request volume (RPS / QPS)** — Traffic rate as a leading indicator; sudden drop is as meaningful as sudden spike (silent failure of upstream). *Falsifier: upstream silently stops sending; service metrics look healthy; no alert fires.*

**Saturation signals** — CPU, memory, thread-pool utilization, file-descriptor counts, connection-pool depth per service instance; saturation precedes latency/error degradation. *Falsifier: CPU saturates; p99 begins rising; no alert fires until SLO breach because only latency alert exists.*

**Dependency latency & error rate** — Per-downstream-dependency p99 and error rate tracked independently; aggregate service health does not expose which dependency is failing. *Falsifier: DB latency doubles; service latency increases; no dependency-level alert fires; operator wastes time diagnosing wrong layer.*

**Queue depth / backlog** — For any async path or bounded queue: current depth, max depth, consumer lag; queue saturation precedes request refusal. *Falsifier: queue fills silently; producer continues accepting; latency spikes only visible when queue overflows.*

**Database/cache connection pool exhaustion** — Pool utilization percentage and wait-queue depth tracked; exhaustion causes request queuing hidden behind service latency. *Falsifier: pool at 100%; requests queue behind pool waits; latency SLO breached before any saturation alert fires.*

**Cache hit rate** — Hit ratio per cache tier; hit rate drop indicates either a cold cache (after restart/failover) or a cardinality explosion in cache keys. *Falsifier: cache failover causes hit rate to drop to 0; thundering herd hits DB; latency SLO breaches; no early-warning cache signal exists.*

**Circuit breaker state** — Open/closed/half-open state per dependency circuit; open circuits change error semantics (fast-fail vs slow timeout). *Falsifier: circuit flips open; latency drops (fast-fail) masking error-rate rise; operator reads latency improvement as false positive.*

**Synthetic/canary probes** — Externally-injected realistic requests run on a scheduled interval against production or a traffic-equivalent target; validate end-to-end path that internal metrics may miss. *Falsifier: internal metrics healthy; TLS certificate expired on a specific path; only external users see errors; no alert fires.*

**DNS resolution health** — Resolution time and failure rate for all service dependencies; DNS failure is a total-blackout dependency failure mode rarely instrumented. *Falsifier: DNS TTL expires; resolver has partial failure; service begins failing a subset of DNS lookups; no metric exists; errors appear as flaky dependency timeouts.*

**TLS certificate expiry** — Days-to-expiry monitored with early-warning threshold (30 d, 7 d, 1 d); expiry causes complete service failure with no application-layer warning. *Falsifier: certificate expires; all traffic fails; no certificate metric existed; on-call has no runbook context.*

**Load balancer rejection/queue signals** — Connections queued or rejected at LB layer before reaching service; LB queue is a leading indicator of overload invisible inside the service. *Falsifier: LB queue fills; service-side RPS looks normal (only accepted requests visible); no overload detected until LB starts rejecting.*

**GC pause / runtime pause signals** — JVM/Go/etc. GC pause duration and frequency; long pauses cause latency spikes uncorrelated with application logic. *Falsifier: GC pressure builds; p99 exhibits periodic spikes; no GC metric exists; investigation time wasted on wrong layer.*

**Autoscaler headroom signal** — Current replica count vs max replica ceiling; approaching ceiling means no scale-out capacity remains. *Falsifier: autoscaler at max; traffic spike arrives; no alert; operator unaware scaling has been neutralized.*

**Error budget burn rate (real-time)** — Live burn rate tracked as a metric, not just computed at alert time; enables dashboards and early-trend awareness. *Falsifier: burn rate visible only in alert conditions; on-call cannot see trend during incident to judge response urgency.*

**Upstream traffic shape signals** — Request size distribution, batch size, streaming vs unary mix; shape changes can break SLO without volume change. *Falsifier: batch size quadruples; processing time per request doubles; volume unchanged; autoscaler does not trigger; latency SLO breaches.*

**Node / host health signals** — Instance-level CPU steal, disk I/O latency, memory pressure; instance-level issues cause fleet-aggregate latency tail inflation. *Falsifier: one noisy-neighbor host doubles its disk I/O latency; 10% of requests routed there breach p999; fleet p99 unchanged; no host-level metric fires.*

---

## Group 3: Alerting Thresholds (12 items)

**Multi-window multi-burn-rate alerting** — At minimum: fast-burn (1 h window, ~14× burn rate) and slow-burn (6 h window, ~6× burn rate) alert pairs, each firing independently; covers both sudden outages and slow leaks. *Falsifier: only a single p99 threshold alert exists; slow burn at 2× rate exhausts budget in 15 days silently.*

**Alert severity tiers** — At least three tiers: page (immediate human response required), ticket (next business day), informational (dashboard only); miscategorization causes alert fatigue or missed incidents. *Falsifier: saturation alert is paging but not actionable overnight; on-call ignores it; real page is missed.*

**Hysteresis / flap suppression** — Thresholds require the condition to persist for N consecutive windows before firing and to clear for M windows before resolving; eliminates flapping alerts. *Falsifier: metric oscillates at threshold boundary; on-call receives 50 alerts/hour; real incident buried in noise.*

**Dependency degradation thresholds** — Independent thresholds for each dependency's error rate and latency; these fire before the service's own SLO alert, enabling proactive mitigation. *Falsifier: dependency threshold absent; service SLO alert fires first; mitigation lag is the full dependency→service propagation time.*

**Saturation leading-indicator thresholds** — Alert at 70–80% saturation (CPU, pool, queue) before service degradation begins; must be tuned to typical headroom per resource type. *Falsifier: threshold at 95%; saturation hits 100% instantaneously; no warning window; SLO breaches before alert fires.*

**Error budget depletion gates** — Explicit thresholds at, e.g., 50%, 75%, 90% budget consumed triggering graduated responses (no new deployments, freeze risky changes, incident declaration). *Falsifier: budget consumed to 0% with no governance response; team discovers it at month-end review.*

**Maintenance-window alert suppression scope** — Suppression narrowly scoped to affected components only; broad suppression during maintenance masks unrelated failures. *Falsifier: full-service suppression during DB maintenance; network partition starts; no alert fires; detected only by user reports.*

**Alert ownership** — Every alert has an unambiguous owner team and on-call rotation; ownerless alerts are silently dropped or create routing confusion. *Falsifier: new alert added with no routing rule; fires to default sink; nobody responds.*

**Alert-to-runbook linkage** — Every actionable alert links to a runbook with specific diagnosis steps and response procedures. *Falsifier: alert fires; on-call must reverse-engineer cause from metric name; MTTR extended by investigation time.*

**Escalation timeout in alerting system** — If primary on-call does not acknowledge within N minutes, alert automatically escalates to secondary and incident commander. *Falsifier: primary on-call asleep/offline; alert acknowledged timeout never configured; incident runs 30 minutes with no responder.*

**Predictive / trend alerts** — Alerts that fire when projected burn rate will exhaust budget within X hours even if current rate is below page threshold. *Falsifier: burn rate constant at 3×; will exhaust budget in 10 days; no predictive alert; team only reacts at 90% depletion.*

**Synthetic probe alert thresholds** — Separate threshold for canary/synthetic probe failure (consecutive failures, not single); synthetic probes have inherent flakiness that must not page on a single miss. *Falsifier: single synthetic failure pages; on-call investigates non-issue 3 times/week; real alert eventually ignored.*

---

## Group 4: Load Shedding (10 items)

**Admission control at entry point** — Rate limiting applied at the ingress/gateway layer before requests reach application logic; protects against volumetric overload regardless of origin. *Falsifier: no entry-point rate limit; overload causes all replicas to saturate simultaneously; autoscaler cannot respond in time.*

**Request prioritization / tiering** — Requests classified by business criticality (e.g., payment > read-only browse > batch export); low-priority shed first under overload. *Falsifier: batch export jobs consume all capacity during spike; high-priority checkout requests fail.*

**Graceful degradation responses** — Under overload, return reduced but valid responses (cached, stale, simplified) rather than errors where the SLI permits it; must not silently degrade without observability. *Falsifier: service returns stale data silently; users unaware; no metric tracks degraded-mode response rate.*

**Backpressure signaling** — 429 / Retry-After responses returned to callers with correct semantics; callers must honor backpressure rather than immediately retrying. *Falsifier: caller ignores 429 and retries immediately; rejected requests amplify overload.*

**Health-check traffic exemption** — Load-shedding logic must never shed health-check or readiness-probe requests; shedding health checks causes load balancer to remove healthy instances, concentrating traffic. *Falsifier: health check hits rate limit; LB marks instance unhealthy; fleet shrinks; remaining instances saturate further.*

**Shedding activation threshold** — Explicit trigger condition for enabling shed mode (CPU %, queue depth, latency p95 threshold); must not activate too eagerly (causes unnecessary degradation) or too late (SLO already breaching). *Falsifier: shed mode activates at 40% CPU for a bursty service; normal traffic spikes trigger degraded mode; users experience unnecessary impact.*

**Per-client / per-tenant fairness** — Under aggregate load limit, ensure one high-volume caller cannot starve all others; token bucket or fair-queue per client. *Falsifier: one misconfigured client sends 10× normal rate; all other clients receive 429 while misbehaving client consumes quota.*

**Shedding ↔ SLO accounting** — Shed (rejected) requests count against error budget if they represent real user demand; shedding must not look like "health" in SLO math. *Falsifier: shed requests excluded from SLI denominator; error budget appears healthy while user error rate is high.*

**Controlled overload vs hard rejection** — Under moderate overload, queuing with bounded depth (and measurable wait) preferred over immediate rejection; at hard ceiling, immediate rejection with clear signal. *Falsifier: unbounded queue grows silently; requests eventually timeout with no 429 signal to callers; latency SLO breaches before any shedding activates.*

**Dependency-directed shedding** — When a specific downstream is degraded, shed requests that require that dependency before they consume resources processing to the point of failure. *Falsifier: requests processed fully, DB call made, DB fails at the end; CPU wasted; latency SLO impacted without benefit.*

---

## Group 5: Autoscaling (11 items)

**HPA metric selection** — Autoscaler driven by the signal that is causally closest to SLO breach (request latency, RPS, queue depth) rather than CPU alone; CPU-based scaling lags for I/O-bound or memory-bound services. *Falsifier: CPU-based HPA; I/O-bound service saturates thread pool; CPU stays low; no scale-out; latency SLO breaches.*

**Scale-up cooldown (short) vs scale-down cooldown (long)** — Asymmetric cooldowns: scale up fast (30–60 s), scale down slow (5–10 min); prevents thrashing and ensures capacity is available for second-wave spikes. *Falsifier: symmetric 3-min cooldown; first spike triggers scale-out; scale-down starts immediately on resolution; second spike arrives before new pods ready.*

**Scale ceiling and downstream capacity** — Max replica count set to respect downstream limits (DB connections, downstream rate limits, network egress); scaling past downstream capacity trades service overload for dependency overload. *Falsifier: HPA max replicas unconstrained; traffic spike causes 10× scale-out; DB connection pool exhausted; latency worse than before scaling.*

**Scale floor (minimum replicas)** — Minimum replica count set above single-instance to prevent cold-start latency on any traffic; must ensure no single point of failure. *Falsifier: min=1; instance fails; replacement starts cold; all traffic to cold instance; latency spike during pod restart.*

**Pod warm-up / pre-warming** — New instances have higher latency until JIT cache warms, in-memory caches populate, connection pools fill; readiness probe must gate on warm state, not just process start. *Falsifier: readiness probe passes at process start; LB routes traffic to cold pod; p99 spikes during scale-out event.*

**Pre-scaling for predictable spikes** — Known traffic patterns (daily peaks, scheduled jobs, marketing events) should trigger proactive scaling before load arrives, not reactive scaling during. *Falsifier: daily 9am traffic spike triggers reactive autoscaler; 2-min scale-out time causes 2-min latency breach every morning.*

**Node autoscaler lag** — If cluster node pool must also scale, node provisioning adds minutes; pod scaling must have sufficient buffer or pre-existing spare node capacity. *Falsifier: cluster at node ceiling; HPA orders new pods; nodes unavailable; pods Pending; scale-out never completes; SLO breaches.*

**Autoscaling signal freshness** — Autoscaler polling interval and metric aggregation window must be short enough to react to spikes; too long an interval makes autoscaler react after SLO breach. *Falsifier: HPA polls every 60 s; spike saturates service in 20 s; autoscaler fires after SLO already breached.*

**Vertical vs horizontal tradeoff** — VPA adjusts resource requests/limits; HPA adjusts replica count; running both simultaneously can conflict (VPA evicts pods that HPA just placed). *Falsifier: VPA and HPA both active; VPA evicts pod for resize; HPA simultaneously scaling; pod churn causes unnecessary latency spikes.*

**Scale-out ↔ connection pool management** — New replicas must acquire their connection pool share without exhausting the pool ceiling; pool sizing must be co-designed with max replica count. *Falsifier: scale-out from 10 to 50 replicas; each pod opens 20 DB connections; DB max_connections=500; exceeded; DB rejects connections.*

**Autoscaling observability** — Scale events (up/down, reason, duration) logged and alerted on; autoscaler hitting ceiling must generate a signal distinct from normal scaling activity. *Falsifier: autoscaler silently at max_replicas for 6 hours; operator unaware scaling has been neutralized; presents as "service is coping" until it isn't.*

---

## Group 6: Failover, Circuit Breaking, and Retry (14 items)

**Circuit breaker per dependency** — Each downstream dependency has an independent circuit breaker; shared circuit breakers conflate distinct failure modes. *Falsifier: one circuit covers two dependencies; healthy dependency B opens circuit when A fails; unnecessary fast-fail for B traffic.*

**Circuit breaker state transitions** — Explicit thresholds for open (error rate or latency threshold over window), half-open probe (single test request), and close-on-success semantics; must be documented per dependency. *Falsifier: circuit never exits open state because half-open probe threshold is too strict; service stuck in degraded mode after dependency recovers.*

**Timeout hierarchy** — Per-hop timeout set such that parent timeout > child timeout + network round-trip; prevents parent timeout firing while child is still processing (duplicate work, resource waste). *Falsifier: parent 500 ms, child 600 ms; parent times out; retries; child still processing first request; 2× DB load; cascade.*

**Retry budget** — Maximum total retries per request and per time window; retry budget prevents retry storms from amplifying load on a degraded dependency by 10–100×. *Falsifier: unlimited retries with backoff; 1000 clients each retry 3×; degraded dependency receives 3000 RPS instead of 1000; pushed into full failure.*

**Exponential backoff with jitter** — Retry delays use exponential backoff with full jitter to spread retry load in time; synchronized backoff creates synchronized retry storm. *Falsifier: fixed 1-s retry delay; 500 clients all retry at t=1 s, t=2 s simultaneously; dependency receives synchronized load pulses.*

**Bulkhead isolation** — Separate thread pools / connection pools / semaphores per dependency; dependency A exhausting its thread pool must not affect requests to dependency B. *Falsifier: single shared thread pool; dependency A slowdown fills all threads; requests to healthy dependency B also queue and fail.*

**Fallback strategy per dependency** — Each dependency has a defined fallback: stale cache, default value, reduced response, or explicit error; fallback must be tested in drills and have its own SLI. *Falsifier: circuit opens; fallback code path never exercised in production; fallback has a bug; causes a different failure class.*

**Multi-region / multi-AZ failover** — Traffic can be rerouted to an alternate region or AZ within a defined RTO; failover procedure is automated where possible and tested regularly. *Falsifier: failover procedure exists in runbook but never practiced; during real incident, operator makes error; RTO exceeded.*

**Failover ↔ latency budget** — Cross-region failover adds network latency (20–100 ms); if latency SLO is tight, this may breach the latency target even on a successful failover. *Falsifier: latency SLO = 100 ms p99; cross-region adds 60 ms; failover succeeds but latency SLO breaches; unrecognized as expected consequence.*

**Dependency health check depth** — Health probes to dependencies must exercise the actual dependency path (query DB, cache GET) not just TCP connectivity; shallow checks produce false-healthy signals. *Falsifier: health check = TCP port open; application DB user locked out; TCP healthy; service routes to "healthy" dependency; all requests fail.*

**Connection draining on failover** — In-flight requests must complete (or timeout) before an instance is removed from the load balancer pool during failover/restart; abrupt removal causes in-flight errors. *Falsifier: pod terminated; LB still routing; 500 ms of in-flight requests receive connection reset; error spike on every deployment.*

**Cascading failure prevention** — When multiple dependencies degrade simultaneously, the mitigation sequence must not assume failures are independent; cascading must be detectable and halted at a chokepoint. *Falsifier: auth service slow → all downstream services wait on auth → all connections consumed → full outage; no chokepoint detection.*

**Idempotency for safe retries** — Retried operations must be safe to re-execute; non-idempotent operations (writes, payments) require deduplication keys or must not be retried. *Falsifier: payment request retried on timeout; charge applied twice; error budget looks fine; customer charged twice.*

**Active-active vs active-passive clarity** — The failover topology must be explicitly chosen and documented with consistency tradeoffs; active-active may produce split-brain; active-passive has RTO lag. *Falsifier: team believes topology is active-active; actual configuration is active-passive; failover takes 90 s instead of expected 0 s; SLO breached.*

---

## Group 7: Escalation Path (8 items)

**On-call rotation coverage** — 24/7 coverage with explicit primary, secondary, and incident commander roles; gaps in rotation mean alerts fire with no responder. *Falsifier: alert fires at 3am Saturday; primary on-call has no backup configured; alert unacknowledged for 45 min.*

**Escalation timeout enforcement** — If primary does not acknowledge within N minutes, automated escalation to secondary; if secondary does not acknowledge within M minutes, page incident commander. *Falsifier: primary unreachable; no escalation timeout configured; incident runs for 1 hour before someone notices on Slack.*

**Runbook currency** — Runbooks reviewed and updated after each incident; stale runbooks direct responder to wrong system state. *Falsifier: runbook says "restart pod X"; pod X renamed 6 months ago; responder wastes 10 min finding the right resource.*

**Incident declaration threshold** — Explicit criteria for declaring a P1/P2 incident (e.g., >X% error budget burned in Y hours, or customer-impacting outage); below threshold = alert-driven response; above = incident process. *Falsifier: major outage handled as a "degraded alert"; no incident commander; uncoordinated parallel actions by multiple engineers cause additional failures.*

**Status page / external communication** — Automated or manual customer-facing status update triggered at incident declaration; customers unaware of incident increase support volume and create noise. *Falsifier: 30-min outage; no status page update; support tickets flood in; support team escalates separately; duplicates incident response effort.*

**War room / incident bridge** — Predefined communication channel (video bridge, Slack incident channel) opened on declaration; dispersed responders waste time on coordination friction. *Falsifier: responders working in separate DMs; conflicting actions taken; one engineer's mitigation reverses another's.*

**Post-incident review trigger** — Any P1/P2 or error-budget gate breach triggers a scheduled blameless post-mortem; learning loop closes. *Falsifier: incidents resolved; PIR never scheduled; same failure mode recurs in 3 months.*

**Error budget exhaustion governance** — When budget reaches defined thresholds (e.g., <10% remaining), automatic freeze on non-emergency deployments, mandatory SRE sign-off on changes. *Falsifier: team deploys new feature at 5% budget remaining; deploy-induced incident burns last 5%; SLO missed for the month.*

---

## Group 8: Cross-Component Interaction Seams (17 items)

**Load-shedding signal ↔ autoscaler** — Load shedding reduces accepted RPS; autoscaler reads RPS as the scaling signal; shedding thus causes autoscaler to scale down exactly when capacity is most needed. *Falsifier: shedding active; RPS signal drops; HPA scales down; shed lifted; service immediately overloaded with fewer replicas.*

**Autoscaler ↔ latency SLO during scale-out** — New pods have cold-start latency (JIT warmup, empty caches); p99 spikes during scale-out events even though capacity is increasing. *Falsifier: traffic spike; scale-out fires; p99 breaches SLO during pod warmup; alert fires; responder acts on symptom not cause.*

**Circuit breaker open ↔ error budget** — Circuit open causes fast-fail responses (usually 503/fallback) which themselves consume error budget; a mitigation that protects latency SLO may accelerate error-budget depletion. *Falsifier: circuit opens to protect latency; error budget drains at 50× rate via 503s; team celebrates latency stability while missing error-rate SLO breach.*

**Retry storm ↔ dependency overload** — Client retries amplify request rate to a degraded dependency; amplification can push a partially degraded dependency into full failure. *Falsifier: DB at 80% capacity; 500 clients retry once each; DB receives 1000 RPS instead of 500; crosses failure threshold; full outage.*

**Autoscaling ↔ DB connection pool exhaustion** — Horizontal scale-out multiplies open DB connections; if each replica opens N connections and max_connections/N < HPA max_replicas, scale-out itself causes DB failure. *Falsifier: HPA max=100 pods × 20 connections = 2000; DB max_connections=1500; scale-out beyond 75 pods causes connection refusals.*

**Cache miss thundering herd ↔ DB / origin overload** — After cache flush, restart, or failover, all concurrent requests miss cache and simultaneously hit DB/origin; DB receives spike proportional to request concurrency. *Falsifier: cache restart during traffic spike; all 10K concurrent users miss; DB receives 10K simultaneous queries; DB latency spikes 100×; SLO breaches.*

**Alert suppression window ↔ concurrent failure** — Maintenance suppression applied to a component masks simultaneous failures in other components if suppression scope is too broad. *Falsifier: DB maintenance suppression covers entire service; network partition starts during window; no alert fires; incident discovered by customer report 45 min later.*

**Bulkhead exhaustion ↔ load balancer routing** — Bulkheads isolate thread pools per replica; if LB does not know which replicas have available bulkhead capacity, it routes to already-exhausted instances. *Falsifier: 3 of 10 replicas have bulkhead full; LB round-robins; 30% of requests slow-fail immediately; fleet appears degraded at 30% error rate while 70% capacity is idle.*

**Timeout cascade ↔ latency SLO** — Parent service sets timeout shorter than child service timeout plus network latency; parent times out and retries while child is still processing; duplicate work and resource exhaustion. *Falsifier: parent=200 ms; child=500 ms; parent retries after 200 ms; child still working; 2× DB load per request; cascade under moderate traffic.*

**Graceful degradation ↔ SLI accounting** — Degraded responses (stale data, reduced content) may pass HTTP-200 and be counted as "good" in the SLI even though latency or content SLO is violated. *Falsifier: degraded mode active for 2 hours; all responses are 200; error budget shows no consumption; latency SLO also showing fine because degraded path is fast; real user impact invisible.*

**Pre-scaling ↔ error budget** — Pre-scaling may trigger a deployment or configuration change that itself introduces errors; the act of preparing for a spike burns budget. *Falsifier: pre-scaling script has a bug; triggers before the predicted spike; 5 min of errors drain 20% of remaining budget.*

**Autoscaler ↔ alert suppression (scale-event noise)** — Scale events generate CPU/memory noise that can trigger saturation alerts; if these are suppressed during scaling, genuine saturation during scale-out is also missed. *Falsifier: scale-out suppresses saturation alerts; actual node memory pressure occurs simultaneously; OOM kills during scale-out go undetected.*

**Load shedding ↔ SLO accounting (shed requests)** — Shed requests (429) must be counted in SLI as failures if they represent real user demand; if excluded from the SLI denominator, budget looks better than reality. *Falsifier: 15% of requests shed; counted as "outside SLI"; reported availability = 99.9%; actual user-experienced availability = 84.9%.*

**Failover ↔ autoscaler in destination region** — Traffic rerouted to failover region may exceed its pre-provisioned capacity; if autoscaler in failover region has not pre-scaled, it starts cold and latency SLO breaches in failover region too. *Falsifier: failover to region B; region B at min replicas for standby; scale-out takes 2 min; 2-min latency breach during "successful" failover.*

**Circuit breaker half-open ↔ load balancer** — During half-open probe, only one request is let through; if LB distributes to a different instance than the one with the open circuit, probing never occurs and circuit stays open. *Falsifier: 10 replicas each have independent circuit state; half-open probe succeeds on instance 3; instances 1, 2, 4–10 still open; 90% of traffic still fast-failing.*

**Error budget gate ↔ deployment pipeline** — Deployment freeze triggered at budget threshold must be enforced in the CI/CD pipeline, not just a policy document; manual processes are bypassed under pressure. *Falsifier: policy says "no deploys at <10% budget"; engineer manually deploys hot-fix during incident; deploy causes new failure; budget hits 0.*

**Escalation path ↔ incident communication loop** — If incident commander and status-page updater are the same person, communication delays occur while they are deep in mitigation; roles must be separate. *Falsifier: solo on-call handles both mitigation and communication; customers get no status update for 40 min while engineer is heads-down.*

---

## Group 9: Edge and Boundary Cases (13 items)

**Spike faster than autoscaler response time** — Traffic spike duration shorter than scale-out time (e.g., 30-second burst); autoscaler has no time to respond; only pre-provisioned capacity and load shedding protect the SLO. *Falsifier: 30-second burst event assumed to be handled by autoscaling; no pre-provisioning; SLO always breaches on burst.*

**Exact SLO threshold (flapping)** — Metric oscillating at or near SLO threshold causes repeated alert fire/resolve cycles; alert fatigue and ignored pages result. *Falsifier: p99 = 199 ms target; metric oscillates 198–201 ms; alert fires 20× in an hour; on-call trains themselves to ignore it.*

**Budget window boundary** — At month-end (calendar window) or after a large reset, behavior of alerting math changes; burn-rate alerts calibrated for mid-window state may over- or under-fire at boundaries. *Falsifier: rolling window budget resets after a 30-day period of good performance; alert thresholds calibrated to "normal" budget; behave incorrectly for 48 hours after large reset.*

**Partial dependency failure** — Some endpoints of a dependency are degraded while others are healthy; aggregate dependency health metric masks the degraded endpoints. *Falsifier: DB read replica degraded; write primary healthy; aggregate DB error rate = 5% (below threshold); read-heavy traffic SLO breaches; no alert fires.*

**All-dependencies fail simultaneously** — Cascading failure where multiple independent dependencies degrade at the same time (e.g., shared infrastructure event); bulkheads per dependency do not help when all are exhausted. *Falsifier: network event degrades DB and cache simultaneously; bulkheads exhausted in parallel; no single dependency circuit open protects against the combined failure.*

**Metric collection failure** — Telemetry agent, scraper, or metric pipeline fails; no data is treated as "good" by many monitoring systems; false healthy signal. *Falsifier: Prometheus scrape fails; metric shows last-known-good value; no alert fires; outage runs undetected.*

**Silent data corruption** — Dependency returns 200 with malformed or incorrect data; no error in error-rate SLI; latency normal; users receive wrong results. *Falsifier: data corruption goes undetected for hours; SLO appears healthy; no SLI covers correctness; only detected by user reports.*

**New service version cold-start during canary** — Canary deployment of new version during a traffic spike; new version has slower startup; canary instances cold during peak. *Falsifier: canary deployed at peak; canary instances 3× slower than expected; 5% of traffic routed to canary breaches latency SLO; canary not correctly isolated from SLO accounting.*

**Single region total failure** — Complete loss of primary region (not just degradation); requires full traffic shift to another region; DNS TTL and client caching delay traffic migration. *Falsifier: region fails; DNS failover initiated; clients with cached DNS continue to primary for TTL duration; increased error rate for TTL minutes after failover.*

**On-call knowledge gap** — Alert fires for a system the current on-call is unfamiliar with; runbook insufficient; escalation path unclear. *Falsifier: new on-call rotation starts; complex system alert fires; engineer has no domain knowledge; runbook assumes expertise; MTTR 5× longer.*

**Error budget at exactly zero** — Budget completely exhausted; governance action should trigger; system behavior at exactly zero is edge condition requiring explicit handling. *Falsifier: budget reaches exactly 0%; system does not trigger governance action; monitoring shows "0% remaining" as informational only; no deployment freeze.*

**Traffic shape change without volume change** — Request payload size, complexity, or upstream routing pattern changes; volume-based autoscaling does not respond; latency SLO breaches. *Falsifier: API migrated to accept larger payloads; processing time 3× higher; RPS unchanged; CPU-based HPA sees nothing; pool exhaustion.*

**Test/staging traffic leaking into production metrics** — Synthetic tests or load tests included in SLI calculations; inflate denominator and dilute error rates; SLO appears healthier than it is. *Falsifier: load test runs against production; 50% of requests from test harness; error rate appears halved; SLO passes; real user error rate at 2×.*

---

## Group 10: Silent Failure Modes (10 items)

**Metric collection agent failure** — Telemetry pipeline fails silently; monitoring system shows stale last-known-good values or gaps; no alerting on collection failure itself. *Falsifier: metric agent OOMed at 2am; dashboard shows "no data" not "good"; no alert for metric gap; 6-hour outage detected by customer complaint.*

**Alert rule deployment without testing** — New alert rule with a logic error (wrong metric name, wrong threshold unit) deployed; rule never fires or always fires; neither detected automatically. *Falsifier: alert deployed with inverted condition (fires when healthy); silenced immediately by on-call; real condition never fires.*

**Circuit breaker stuck open** — Circuit breaker opens during incident but never re-enters half-open state; service continues in degraded/fallback mode indefinitely after dependency recovers. *Falsifier: DB recovers; circuit breaker stuck open; service returns fallback responses for 2 more hours; no alert exists for "circuit open duration > threshold".*

**Autoscaler at ceiling, no alert** — Autoscaler reaches max_replicas but traffic continues growing; no alert for "autoscaler at max"; operators assume scaling is handling load. *Falsifier: HPA at max=50 for 3 hours during sustained traffic growth; saturation climbing; nobody paged; first signal is SLO breach.*

**Slow burn exhausting budget without paging** — Error budget burns at a rate below fast-burn alert threshold but above zero; budget fully consumed before any page fires if slow-burn alert is missing. *Falsifier: error rate 0.05% over target; fast-burn threshold not met; no slow-burn alert; 15 days later, full budget consumed; no incident response.*

**Fallback returning wrong data type** — Fallback path returns a default value that is technically a valid HTTP 200 but causes downstream logic failures (null ID, empty list where non-empty expected). *Falsifier: circuit open; fallback returns empty user list; downstream billing service skips all users; no error in metrics; silent revenue loss.*

**Runbook action causes new failure** — Runbook mitigation step (e.g., "restart service X") causes a brief error spike that is not anticipated; responder triggers additional SLO burn. *Falsifier: runbook says "rolling restart"; pod restarts cause 30 s of 503s; SLO burns further; responder unaware the mitigation itself has a cost.*

**Gradual disk fill on log/metric storage** — Monitoring or logging storage fills gradually; scraping begins to fail silently; observability degrades before any alert fires on the storage itself. *Falsifier: metric storage 95% full; writes begin failing; scraper returns empty metrics; dashboards appear healthy; outage undetectable.*

**On-call rotation gap (holiday / off-boarding)** — Engineer removed from on-call rotation without replacement; paging system has no escalation for unmapped time slot; alerts fire with no recipient. *Falsifier: engineer off-boarded Friday; rotation has gap Saturday–Sunday; incident fires; no page received by anyone.*

**Synthetic probe measuring wrong endpoint** — Canary probe target drifted (URL change, region switch) and now tests a non-production endpoint; production failures go undetected by the synthetic. *Falsifier: production domain changed; synthetic still testing old domain which returns 200 (redirect or old service); real traffic failing; synthetic shows healthy.*

---

## Group 11: Scope Boundaries (6 items)

**Deployment / rollout safety** — Canary and blue-green deployment mechanics are adjacent to the operating regime but deployment rollback criteria, deployment gates on error budget, and the impact of deployments on SLO are IN scope. *Why out (mechanics) / pull-back (budget gates)*: Deployment orchestration tooling is out; but deployment freeze at budget thresholds is a core operating regime decision and must be included.*

**Data durability / backup recovery** — Loss of persisted data and backup restore procedures are out of scope; the SLO concerns latency and error-rate, not data integrity or RPO. *Pull-back condition*: if data loss causes a service restart that triggers a latency/error SLO breach (e.g., cold-start), the restart mitigation is in scope.*

**Security incident response** — Authentication failures, DDoS, and credential compromise are out of scope unless the attack vector directly degrades latency/error-rate SLO (volumetric DDoS). *Pull-back condition*: rate-limiting and traffic scrubbing responses to DDoS that affect the operating regime (admission control, shedding) are in scope.*

**Client-side / CDN behavior** — CDN caching, client retry logic, and browser-side error handling affect observed latency and errors at the user level; CDN configuration (TTL, error pass-through) is in scope as it directly determines user-perceived SLO. *Pull-back condition*: CDN misconfiguration serving stale 503s is an operating-regime failure mode and must be covered.*

**Capacity planning (long-horizon)** — Multi-quarter demand forecasting and hardware procurement are out of scope; but the maximum scale ceiling and minimum pre-provisioned capacity that bound autoscaling behavior are in scope. *Pull-back condition*: if scale ceiling is derived from a capacity planning decision, the ceiling value and its review cadence are in-scope operating regime inputs.*

**Correctness / data quality SLO** — Whether the service returns correct results is out of scope for this operating regime (latency + error-budget only); however, requests that return incorrect data without an HTTP error code that slip past the SLI definition create a silent failure mode that must be acknowledged as a known gap and explicitly declared out of scope with its boundary marked. *Pull-back condition*: if correctness failures are detectable as latency anomalies (e.g., fallback path is faster) they become in-scope as a latency signal.*

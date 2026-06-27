# T05 — Search pass 3: new holes in D2

D2 is dense and well-constructed. After a hard exhaustive pass, 8 genuinely new requirements surface. Each has a distinct falsifier not already captured by any existing D/Dep/V/N item.

---

## New Dep — cross-component interaction seams

**Dep-A. HPA scale-down → terminationGracePeriodSeconds → in-flight request kills**
Routine HPA scale-down sends SIGTERM to a pod; if `terminationGracePeriodSeconds` (or the preStop hook duration) is shorter than the maximum in-flight request duration, those requests are hard-killed and return 503s that consume error budget. Distinct from D7's "connection draining on failover/restart" (D7 scopes it to failover/restart events; this is normal steady-state autoscaler activity governed by a Deployment-spec parameter, not a failover procedure). *Falsifier: p99 request latency = 8 s; terminationGracePeriodSeconds = 5 s; every scale-down event systematically kills ~1–2% of in-flight requests; nobody attributes the error burst to autoscaling.*

**Dep-B. CDN error-cache TTL post-origin-recovery → error-budget accounting gap**
After origin recovers, the CDN continues serving cached 5xx responses for up to the error-cache TTL. Those CDN-sourced errors are real user-visible failures that should consume error budget. D9 frames the TTL/recovery coordination as a *mitigation* ("so stale 503s are not served beyond TTL after origin recovers") but does not surface the seam as an accounting gap: if incident resolution is declared at origin-recovery time, the CDN error tail is omitted from error-budget debits and post-mortem duration. Distinct from Dep25 (canary contamination) and from D9's mitigation text. *Falsifier: origin 5xx for 2 min; CDN error-TTL = 10 min; origin recovers at T+2; team closes incident at T+2; CDN serves 5xx to users until T+10; 8 min of real errors missing from budget debit and from duration used to compute burn rate.*

**Dep-C. LB health-check detection window → quantified error window per failed instance**
Between a pod entering an unhealthy state and the load balancer removing it from rotation (health-check interval × consecutive-failure threshold), all traffic routed to that pod produces errors. D4 covers consecutive-failure count to avoid false positives from a single miss, but does not model the window as a mandatory error-budget cost: every instance failure carries a guaranteed (interval × threshold × traffic-share) error burn before the LB acts. Distinct from D4's synthetic probe threshold (external synthetic probes and LB-layer pod health checks are separate systems with independent polling intervals). *Falsifier: LB health-check interval = 10 s, threshold = 3; each instance failure guarantees 30 s of 100% error rate for that instance's traffic share; fleet has 5 instances so a correlated failure burns ~6% of daily budget in 30 s; this cost is nowhere modeled or pre-quantified in runbooks.*

---

## New V — criteria

**V-A. Burn-rate alert pair coverage completeness**
The fast-burn (1 h / ~14×) and slow-burn (6 h / ~6×) alert pair must be verified to cover all burn rates that would exhaust the budget before the end of the review period. A burn rate that falls between the two window/threshold pairs (e.g., ~7–8×) may be detected by neither if the window and threshold are not co-designed for coverage completeness. No existing V checks the pair mathematically for gap-free coverage. *Falsifier: a sustained 7× burn rate (budget exhausted in ~3 days) falls in the unverified gap between fast-burn threshold and slow-burn window; 3 days of budget drain with no alert firing.*

**V-B. terminationGracePeriodSeconds ≥ p99 in-flight request duration**
A decidable criterion: the pod termination grace period (and any preStop hook) is explicitly verified to be ≥ the maximum expected in-flight request duration for every service, so that no routine HPA scale-down event can kill in-flight requests. Corresponds to Dep-A. No existing V covers the scale-down lifecycle. *Falsifier: terminationGracePeriodSeconds reduced during a "performance tuning" pass; systematic 503 bursts at every scale-down event; root cause not obvious from dashboards.*

**V-C. CDN error-cache TTL is included in error-budget debit window and incident duration**
A decidable accounting criterion: when CDN error caching is configured, the error-budget debit period and the incident duration used in post-mortem analysis extend to CDN TTL expiry, not to origin recovery time. D9 specifies coordination as a mitigation; this V specifies that the measurement itself is correct when the mitigation is imperfect or absent. *Falsifier: post-mortem calculates burn rate over origin-recovery window; CDN tail doubles actual user-facing error duration; burn-rate calculation understates true impact; root-cause fix is deprioritized.*

---

## New D — components

**D-A. Alert volume / fatigue governance**
A distinct design component for the total alert health of the on-call regime: per-shift page-count target (distinct from per-alert hysteresis in D4); actionability ratio (fraction of pages requiring a decision vs auto-resolve); a defined process and cadence for retiring alerts that have not fired or have auto-resolved without action in N months; a review trigger when per-shift page count exceeds a threshold. Distinct from D4 (which tunes individual alert rules) and D8 (which structures the rotation). *Falsifier: service accretes 2 years of feature releases; alert count doubles; on-call spends 35% of shift acknowledging informational noise; a genuine burn-rate alert fires during a noise burst; responder ack-dismisses it reflexively; SLO breaches before the signal is re-noticed.*

**D-B. Multi-region SLO aggregation policy**
For a service deployed across multiple regions, the design must specify whether SLO measurement is global (traffic-weighted aggregate across regions), per-region independent, or both; what the error-budget policy is when one region breaches while others are healthy; and how failover-redirected traffic in one region affects the SLO measurement of the receiving region. D1 specifies per-endpoint SLIs and window policy but does not address the regional aggregation dimension. D7 specifies failover topology. Neither specifies the measurement policy. *Falsifier: EU region sustains 5× burn rate; US region is healthy; global aggregate SLO passes; EU customers experience SLO breach for hours without any budget alert firing or incident declared.*

---

## Summary

| Category | New items |
|---|---|
| Dep | 3 (A, B, C) |
| V | 3 (A, B, C) |
| D | 2 (A, B) |
| **Total** | **8** |

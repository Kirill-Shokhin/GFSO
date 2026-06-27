# Search pass 3 — T02 new holes against D2

D2 is dense and well-covered. The remaining holes are real but narrow.

---

## New Dep seams

**S1 — Shadow/canary → Promotion gate (online score closure)**
D-10 exists as a component and Dep-8 wires offline eval → promotion, but there is no seam connecting the shadow arm's empirical online metrics back into the promotion gate. Shadow deployment is currently observational: the online delta can be known yet promotion can still proceed unconditionally.
*Falsifier: shadow arm records online AUC 0.62 while offline AUC is 0.94; promotion to production succeeds because the gate only checks Dep-8 (offline eval report); the gap that the task explicitly requires to be detected (offline score predicts online behavior) is not enforced.*

**S2 — Serving transform path → Monitoring (post-transform feature visibility)**
Dep-6 logs the raw inference request plus prediction. Drift monitoring on raw inputs detects distributional shift in what arrives at the endpoint. It cannot detect a transform-level bug (wrong column order, scaler applied to wrong column, version mismatch that slipped past Dep-4) because that bug leaves raw inputs unchanged while corrupting the feature vector fed to the model. Monitoring needs the post-transform feature vector (or a stable hash of it) to close this gap.
*Falsifier: serving transform swaps two numeric columns due to a code change; raw input distribution is identical; monitoring reports "no drift"; wrong predictions continue until manual investigation locates the serving-transform discrepancy.*

---

## New V criteria

**S3 — Serving endpoint readiness probe (load-before-traffic gate)**
Dep-14 covers the SLA for reloading after promotion. V-35 covers per-request latency. Neither covers the window between "endpoint process started / new version initiated" and "model + transform artifact are fully in memory." During that window an eager load balancer routes requests that hit an uninitialized state. A readiness probe (503 until loaded) closes this gap; it is distinct from Dep-14 which governs steady-state SLA, not the initialization fence.
*Falsifier: promote v2; load balancer sends traffic during the 20-second model deserialisation window; endpoint returns "model not loaded" or stale v1 predictions with no readiness signal visible to the LB.*

**S4 — Registry artifact physical retention guard**
V-13 and V-42 together define the promotion state machine and rollback reachability. They establish that the state machine must allow re-promotion. They do not prevent a background cleanup/GC job from physically deleting the serialized artifact files for "retired" versions, leaving the state machine in a valid rollback state but the artifact gone.
*Falsifier: v2 is promoted; v1 enters "retired" state; a retention policy or garbage-collection job deletes v1's artifact files after 7 days; v2 causes an incident on day 10; operator initiates state-machine rollback to v1; registry entry exists, artifact fetch returns 404.*

**S5 — Label encoding consistency (training ↔ accuracy monitoring)**
V-3 (schema consistency end-to-end) covers input feature schema. Accuracy monitoring requires matching predicted labels against ground-truth labels when they arrive (V-31). If training encodes the target as integer class indices {0, 1, 2} but monitoring ingests ground-truth labels as string class names {"cat", "dog", "bird"}, the matching step silently fails or produces nonsense accuracy values — independently of any feature drift.
*Falsifier: training encodes labels as 0/1; ground-truth delivery stream uses "positive"/"negative" strings; accuracy monitor attempts numeric comparison; every record appears as a mismatch; accuracy is reported as 0% permanently with no schema-mismatch alert.*

**S6 — Idempotent run registration**
V-11 (pipeline run identity) and V-12 (data version/hash) establish that each run has a unique ID and content-addressed data. They do not specify what happens when the same job is re-submitted with identical data hash and config (e.g., after a transient infrastructure failure). Without a guard, the registry accumulates duplicate entries sharing the same data version and transform artifact, which corrupts lineage queries and can double-count promotion comparisons.
*Falsifier: a transient scheduler failure retries the pipeline run; two registry entries are created with the same data hash, same transform artifact, and marginally different wall-clock times; a downstream query for "latest model trained on dataset v7" returns two candidates; promotion comparison is ambiguous.*

---

## Wrong scope decision

**S7 — Feature store exclusion: SLA-gated boundary missing from N-6**
N-6 correctly excludes a feature store, stating it is needed only if features are shared across models or pre-computed for latency. However, V-35 (serving latency SLA) is already in scope. N-6's "why out" does not state the dependency: if inline transform computation cannot meet V-35's budget, the feature store exclusion is no longer safe. The current wording leaves V-35 and N-6 as independent items, hiding the condition that would pull the feature store back in scope.
*Falsifier: inline transform involves heavy NLP preprocessing; p99 latency is 800 ms against a 100 ms SLA (V-35 violated); feature store is rejected because "N-6 excludes it" without the evaluator recognising that V-35 breach is exactly the condition that overrides N-6.*

---

**Total new holes: 7**

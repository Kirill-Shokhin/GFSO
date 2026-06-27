# BLIND JUDGE VERDICT — T02 / candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note (missing leg / which candidate points) |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "reads raw data, enforces schema contract (column names, dtypes, nullability, allowed ranges, label presence); emits a validated, versioned dataset or hard failure" | cand-D1 |
| D2 | D | — | COVERED | "applies stateful (fit-then-transform) and stateless operations; must be serializable; fit state must be persisted as a versioned artifact" | cand-D2 |
| D3 | D | — | COVERED | "partitions validated data into three non-overlapping, non-contaminated sets; respects temporal order for time-series data; stratifies for classification" | cand-D3 |
| D4 | D | — | COVERED | "consumes train partition + fitted transform artifact; produces serialized model artifact" | cand-D4 |
| D5 | D | — | COVERED | "evaluates model on test partition only; reports primary and secondary metrics (including per-class for imbalanced data)" | cand-D5 |
| D6 | D | — | COVERED | "stores model artifact + fitted transform artifact + hyperparameters/architecture config + schema version + evaluation report as a single versioned bundle" | cand-D6 |
| D7 | D | — | COVERED | "loads the exact frozen transform artifact from the registry for the deployed model version; applies it to incoming requests" | cand-D7 |
| D8 | D | — | COVERED | "loads model from registry, applies serving transforms, validates incoming request schema, returns prediction; handles single-sample and batch requests" | cand-D8 |
| D9 | D | — | COVERED | "tracks input feature distribution, prediction distribution, and (when labels arrive with correct lag handling) accuracy metrics; ... emits alerts on significant drift, on stale models, and on zero traffic" | cand-D9 |
| D10 | D | — | COVERED | "routes a defined fraction of production traffic to a newly promoted candidate in parallel with the current production model; compares offline and online metrics empirically" | cand-D10 |
| Dep1 | Dep | FM-2/FM-1 | COVERED | "a separately re-fitted transform at serving time will differ even if the code is identical; ... predictions silently differ" | cand-Dep2 (train/serve transform identity); also cand-D7 "byte-identical to training-time transform" |
| Dep2 | Dep | FM-1 | COVERED | "the model's forward/backward pass must consume strictly training-partition rows; ... model sees test rows during weight updates; offline metric is inflated" | cand-Dep13 (partition isolation) |
| Dep3 | Dep | FM-1 | COVERED | "transform fitting must happen strictly after splitting and must receive only training-partition rows; any code path that passes test or val rows to fit() introduces leakage" | cand-Dep1 (fit-on-train-only) |
| Dep4 | Dep | FM-1 | NOT-COVERED |  | label join / per-example label-to-feature alignment correctness (right entity, right time) is absent; candidate has only "label presence" (D1), not join correctness |
| Dep5 | Dep | FM-2/FM-1 | COVERED | "stores model artifact + fitted transform artifact + ... as a single versioned bundle" (cand-D6); falsifier: "registry stores model weights but not the associated transform artifact" | matched-pair co-versioning |
| Dep6 | Dep | FM-1 | COVERED | "the serving path must load the transform artifact bundled with the deployed model version, not the latest artifact in the registry" | cand-Dep4; rollback via cand-D6 promotion state machine |
| Dep7 | Dep | FM-2/FM-1 | COVERED | "the serving endpoint validates incoming request feature columns (names, count, dtype) against the trained model schema before calling the transform or model" | cand-V22 |
| Dep8 | Dep | FM-2/FM-1 | N/A | — (candidate computes features inline; cand-N6 "this pipeline defines and computes features inline") | reference appendix: Dep8 is N/A when no precomputed feature store is in the design — omission is not a hole; excluded from denominator |
| Dep9 | Dep | FM-1 | COVERED | "the fitted transform artifact must be applied in transform-only mode (no refit) to val and test partitions before evaluation; evaluating raw features against a model trained on transformed features silently distorts metrics" | cand-Dep12 (eval through the same fitted/serving transform) |
| Dep10 | Dep | FM-1 | COVERED | "features computed from historical windows ... must use only data available at the exact prediction timestamp ... is time-leakage" | cand-V45; also cand-D3 "respects temporal order" |
| Dep11 | Dep | FM-2/FM-1 | COVERED | "the metric evaluated offline must be a valid proxy for the metric monitored online; mismatched evaluation windows or feature distributions make the offline score uninformative" | cand-Dep11 |
| Dep12 | Dep | FM-7/FM-1 | COVERED | "ground-truth label arrival is delayed after prediction; ... prediction timestamps must be recorded to enable label matching" | cand-V35; logging via cand-Dep6 |
| Dep13 | Dep | FM-1 | COVERED | "partitions validated data into three non-overlapping, non-contaminated sets" (same validated source, disjoint) | cand-D3 |
| Dep14 | Dep | FM-5/FM-7/FM-1 | COVERED | "drift alerts must propagate to an actionable trigger that initiates a new pipeline run; without this connection, monitoring is decorative" | cand-Dep7; re-eval gate via cand-Dep8 |
| V-I1 | V | FM-1 | COVERED | "no fit() call anywhere in the pipeline receives test-partition rows, directly or indirectly; verified by tracing all fit() call sites" | cand-V1 (global no-leakage) |
| V-I2 | V | FM-2 | COVERED | "given the same fitted artifact and same input, transform output is byte-identical in dev, staging, and production" | cand-V2 (parity) |
| V-I3 | V | FM-1 | COVERED | "model hyperparameters and architecture configuration are persisted as part of the versioned registry bundle ...; training is reproducible given the same data and transform" | cand-V43; lineage via cand-V11 "unique run ID links the data snapshot, transform artifact, model artifact, and evaluation report" |
| V-I4 | V | FM-2 | COVERED | "the feature schema (column names, dtypes, order) at ingestion, training, evaluation, and serving is identical; schema hashes match at all pipeline stages" | cand-V3 |
| V-I5 | V | FM-1 | COVERED | "the exact dataset used in each run is identified by content hash or immutable snapshot reference; silent dataset mutations are detectable" | cand-V12; also cand-Dep4 "not the latest artifact in the registry" |
| V-I6 | V | FM-2 | NOT-COVERED |  | decision-threshold / calibration parity (threshold set at eval carried unchanged to serving) is absent |
| V-I7 | V | FM-4 | NOT-COVERED |  | candidate has individual gates (cand-Dep15 validated-output-only into split; cand-Dep3 registry requires eval report; cand-V13 only validated models serve) but no GLOBAL fail-closed / gate-on-every-upstream spanning predicate |
| V-I8 | V | FM-4 | COVERED | "must not silently accumulate duplicate entries ... which would corrupt lineage queries and promotion comparisons" (idempotent re-run on transient failure without corrupting lineage) | cand-V16 |
| V-I9 | V | FM-4 | COVERED | "model artifact and its associated transform artifact are always retrieved and deployed together; no code path loads one without the other" | cand-V4; concurrency via cand-V29 readiness probe + cand-V40 thread-safety |
| V-E1 | V | FM-3 | COVERED | "the categorical encoder has an explicit, configured policy (error / unknown token / frequency-based fallback) for categories not seen during training" | cand-V19 |
| V-E2 | V | FM-3 | COVERED | "when one sample in a multi-sample batch request fails transform validation or schema check, the failure policy ... is defined and enforced" (missing required column rejected at inference) | cand-V42; also cand-V22 serving validation |
| V-E3 | V | FM-3 | COVERED | "class frequencies in val and test partitions approximate the overall distribution within a defined tolerance" (stratified split); cand-D3 "stratifies for classification" | cand-V6 |
| V-E4 | V | FM-6 | NOT-COVERED |  | cold-start / insufficient-data FALLBACK (baseline model / hold serving) absent; candidate only aborts (cand-V17 empty batch, cand-V20 single-class) — abort ≠ declared fallback |
| V-E5 | V | FM-3 | COVERED | "a constant feature column is caught at validation or transform fit; StandardScaler division by zero must not silently produce NaN/inf features" | cand-V28; also cand-V17 empty batch |
| V-F1 | V | FM-5 | COVERED | "monitoring covers both input feature distribution AND prediction output distribution; input stability alone does not detect concept drift" | cand-V33; staleness via cand-V8 "model older than a defined staleness threshold triggers a monitoring alert" |
| V-F2 | V | FM-3 | COVERED | "evaluation reports per-class precision, recall, and F1 in addition to aggregate metrics; aggregate accuracy alone is insufficient for imbalanced datasets" | cand-V21 |
| V-F3 | V | FM-7 | COVERED | "the registry state machine supports re-promoting a previously-production or validated model back to production ...; a 'retired' state with no re-promotion path leaves operators without a rollback path during incidents" | cand-V46 (incident rollback channel for the owner) |
| V-F4 | V | FM-3 | NOT-COVERED |  | feedback-loop bias (model's own outputs contaminate future training labels; exposure/propensity logging or declare-and-bound) is absent |
| N1 | N | FM-1 | COVERED | "the pipeline starts from already-labeled data; annotation is upstream of ingestion" | cand-N3 |
| N2 | N | FM-1 | NOT-COVERED |  | serving infra / autoscaling / latency-throughput SLOs are not declared out of scope; candidate instead places "Serving latency SLA" (cand-V39) IN scope |
| N3 | N | FM-1 | COVERED | "the task asks for stage logic and connections, not a scheduler specification ... orchestration tools are infrastructure; the logical design is independent of the scheduler" | cand-N8 |
| N4 | N | FM-1 | NOT-COVERED |  | "model architecture/algorithm family is a given input" not declared; cand-N1 excludes HPO (hyperparameter search) only — a narrower concern, not the model-family-given assumption |
| N5 | N | FM-1 | NOT-COVERED |  | data privacy / PII / security / compliance out-of-scope declaration is absent |
| N6 | N | FM-1 | COVERED | "the pipeline is batch-trained; the served model does not update weights from online traffic" (regime declared = batch) | cand-N2 |
| N7 | N | FM-1 | COVERED | "simultaneous routing of live traffic across multiple competing models requires a separate routing and evaluation layer ... only multi-model production routing is excluded" (design written for a single production model) | cand-N5 |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D5 | 2 | 1 | cand-Dep10 "evaluation must use the test partition, not val; the partition identity must be recorded" |
| D9 | 2 | 1 | cand-V24 "zero serving traffic detection" |
| D10 | 2 | 1 | cand-Dep16 "the shadow arm's empirically measured online metrics must feed back into the promotion gate" |
| Dep1 | 2 | 1 | cand-D7 "output must be byte-identical to training-time transform for the same input" |
| Dep2 | 2 | 1 | cand-V25 "Duplicate row deduplication before split" |
| Dep3 | 2 | 1 | cand-V14 "the transform artifact's fit state is frozen after initial fit on the training partition" |
| Dep5 | 2 | 1 | cand-V9 "the fitted transform artifact includes the fit parameters ... not merely the transform code" |
| Dep6 | 3 | 2 | cand-Dep14 "the serving endpoint must detect and reload it within a defined SLA"; cand-V13 "Model promotion state machine ... only validated models may serve" |
| Dep10 | 2 | 1 | cand-D3 "respects temporal order for time-series data" |
| Dep11 | 3 | 2 | cand-V36 "Monitoring reference distribution"; cand-V47 "Monitoring reference window recency" |
| Dep12 | 4 | 3 | cand-Dep6 "every inference request and its prediction must be durably logged"; cand-V34 "Logging durability under load"; cand-V30 "Label encoding consistency (training ↔ accuracy monitoring)" |
| Dep14 | 4 | 3 | cand-Dep8 "promotion logic must compare the candidate ... using a defined threshold"; cand-V44 "Retraining data freshness on drift trigger"; cand-Dep3 "a model artifact may enter the registry only after a valid evaluation report" |
| V-I1 | 2 | 1 | cand-V32 "Target leakage detection ... features unavailable at inference is a leak" |
| V-I2 | 3 | 2 | cand-V26 "Dtype consistency across train and serve"; cand-Dep5 "transforms must emit features in the exact column order and dtype the model expects" |
| V-I3 | 4 | 3 | cand-V11 "Pipeline run identity"; cand-V10 "Split reproducibility"; cand-V5 "Offline metric traceability" |
| V-I4 | 2 | 1 | cand-Dep9 "Ingestion schema → Training schema (schema evolution)" |
| V-I8 | 2 | 1 | cand-V23 "Training divergence detection ... abort, not register a corrupt model artifact" |
| V-I9 | 3 | 2 | cand-V29 "Serving endpoint readiness probe"; cand-V40 "Transform artifact thread-safety at serving" |
| V-E2 | 3 | 2 | cand-V18 "All-null feature column policy"; cand-V41 "Out-of-distribution input handling" |
| V-E5 | 4 | 3 | cand-V17 "Empty batch rejection"; cand-V20 "Single-class training batch detection"; cand-V31 "Non-positive log-transform input validation" |
| V-F1 | 2 | 1 | cand-V8 "Stale model alert" |
| V-F3 | 2 | 1 | cand-V15 "Registry artifact physical retention guard" |

Total ballast = 35.

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| cand-Dep17 "drift monitoring needs the post-transform feature vector (or a stable hash of it) in addition to the raw request" | UNMATCHED — human review |
| cand-V7 "the label column is never present in the serving feature vector; its absence is enforced at the serving endpoint" | UNMATCHED — human review |
| cand-V27 "transforms and model forward pass handle both single-row and large-batch inputs without shape errors or silent broadcasting bugs" | UNMATCHED — human review |
| cand-V37 "the checksum or hash of the serialized model artifact is validated when loaded from the registry" | UNMATCHED — human review |
| cand-V38 "model output is constrained to a domain-valid range (probabilities in [0, 1], regression within defined bounds)" | UNMATCHED — human review |
| cand-V39 "the combined serving-transform + model forward-pass must complete within a defined per-request time budget" | UNMATCHED — human review |
| cand-N1 "Hyperparameter optimization (HPO) — excluded unless the task requires production-grade competitive model performance" | UNMATCHED — human review |
| cand-N4 "Distributed training — excluded; training is a black box to the pipeline logic" | UNMATCHED — human review |
| cand-N6 "Feature store — excluded ... this pipeline defines and computes features inline" | UNMATCHED — human review |
| cand-N7 "Explainability (SHAP, LIME) — excluded; a separate concern from pipeline correctness" | UNMATCHED — human review |

Total unmatched = 10.

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 10/10   Dep = 12/13   V = 14/18   N = 4/7
  by FM tag:     FM-1 = 19/23   FM-2 = 6/7   FM-3 = 5/6   FM-4 = 2/3   FM-5 = 4/4   FM-6 = 0/1   FM-7 = 3/3
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 35
  unmatched candidate points (human-review flag):    total = 10
```

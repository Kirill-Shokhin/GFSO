# BLIND JUDGE VERDICT — T02 / candidate D1

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "reads raw data, enforces schema contract (column names, dtypes, nullability, allowed ranges, label presence); emits a validated, versioned dataset or hard failure" | rejects non-conforming via hard failure |
| D2 | D | — | COVERED | "applies stateful (fit-then-transform) and stateless operations; must be serializable; fit state must be persisted as a versioned artifact" | feature transform pass |
| D3 | D | — | COVERED | "partitions validated data into three non-overlapping, non-contaminated sets" | split pass |
| D4 | D | — | COVERED | "consumes train partition + fitted transform artifact; produces serialized model artifact" | training pass on train split |
| D5 | D | — | COVERED | "evaluates model on test partition only; reports primary and secondary metrics" | offline-eval pass on holdout |
| D6 | D | — | COVERED | "stores model artifact + fitted transform artifact + schema version + evaluation report as a single versioned bundle" | registry/versioning pass |
| D7 | D | — | COVERED | "loads the exact frozen transform artifact from the registry for the deployed model version; applies it to incoming requests" | serving transform path |
| D8 | D | — | COVERED | "loads model from registry, applies serving transforms, ... returns prediction" | inference/serving endpoint |
| D9 | D | — | COVERED | "tracks input feature distribution, prediction distribution, and ... accuracy metrics; ... emits alerts on significant drift" | monitoring pass |
| D10 | D | — | NOT-COVERED | | online pre-promotion validation (shadow/canary/champion-challenger) absent; candidate N5 explicitly scopes out "A/B testing / shadow mode". Per reference appendix an explicit out-of-scope declaration is "not penalized", but the truth-maker (a candidate compared to incumbent on live traffic before cutover) is not satisfied → scored NOT-COVERED |
| Dep1 | Dep | FM-1, FM-2 | COVERED | "the transform artifact passed to training must be the exact object persisted in the registry; a separately re-fitted transform at serving time will differ even if the code is identical" | headline train/serve skew seam (reinforced by D7 byte-identical, cDep5, V24) |
| Dep2 | Dep | FM-1 | COVERED | "partitions validated data into three non-overlapping, non-contaminated sets" (falsifier: "test rows appear in the training partition") | partition isolation / no peeking |
| Dep3 | Dep | FM-1 | COVERED | "transform fitting must happen strictly after splitting and must receive only training-partition rows" | fit-on-train-only |
| Dep4 | Dep | FM-1 | NOT-COVERED | | no label-join/alignment-to-correct-entity/time anywhere in candidate |
| Dep5 | Dep | FM-1, FM-2 | COVERED | "model artifact and its associated transform artifact are always retrieved and deployed together; no code path loads one without the other" | model↔preprocessor co-versioning |
| Dep6 | Dep | FM-1 | COVERED | "the serving path must load the transform artifact bundled with the deployed model version, not the latest artifact in the registry" | registry version↔serving binding |
| Dep7 | Dep | FM-1, FM-2 | COVERED | "the serving endpoint validates incoming request feature columns (names, count, dtype) against the trained model schema before calling the transform or model" | ingestion/training schema = inference request schema |
| Dep8 | Dep | FM-1, FM-2 | N/A | | conditional seam (feature store). Candidate N6 excludes feature store ("this pipeline defines and computes features inline") → per reference appendix omission is NOT a hole. Excluded from denominator |
| Dep9 | Dep | FM-1 | NOT-COVERED | | candidate never asserts offline eval runs *through the serving transform path*; V2 (env-reproducible transform) and D7 (frozen artifact) gesture but eval-mirrors-inference-path is not stated |
| Dep10 | Dep | FM-1 | COVERED | "respects temporal order for time-series data" | temporal/point-in-time split (conditional; raised) |
| Dep11 | Dep | FM-1, FM-2 | COVERED | "the metric evaluated offline must be a valid proxy for the metric monitored online" | eval↔monitoring metric alignment (reinforced by V32, D9 "compares against stored training-time reference distributions") |
| Dep12 | Dep | FM-1, FM-7 | COVERED | "accuracy metrics must not be computed until labels arrive; prediction timestamps must be recorded to enable label matching" | prediction-logging → delayed-label join |
| Dep13 | Dep | FM-1 | COVERED | "rows duplicated across the train/test boundary cause artificial metric inflation; a deduplication policy is applied before splitting" | same-source split (D3) + row-disjointness → valid estimate |
| Dep14 | Dep | FM-1, FM-5, FM-7 | COVERED | "drift alerts must propagate to an actionable trigger that initiates a new pipeline run" (+ cDep8: "a degraded candidate must not be promotable") | monitoring → retrain/promote trigger with re-eval gate |
| V-I1 | V | FM-1 | COVERED | "no fit() call anywhere in the pipeline receives test-partition rows, directly or indirectly" | global no-leakage / honest score |
| V-I2 | V | FM-2 | COVERED | "given the same fitted artifact and same input, transform output is byte-identical in dev, staging, and production" | global train/serve parity |
| V-I3 | V | FM-1 | COVERED | "each pipeline execution has a unique run ID that links the data snapshot, transform artifact, model artifact, and evaluation report; lineage is traceable across runs" | reproducibility/lineage (+ V5, V10) |
| V-I4 | V | FM-2 | COVERED | "the feature schema (column names, dtypes, order) at ingestion, training, evaluation, and serving is identical; schema hashes match at all pipeline stages" | one consistent contract end-to-end |
| V-I5 | V | FM-1 | COVERED | "the exact dataset used in each run is identified by content hash or immutable snapshot reference; silent dataset mutations are detectable" | immutability/version-pinning (+ Dep4 "not the latest", V14) |
| V-I6 | V | FM-2 | NOT-COVERED | | no decision-threshold/calibration parity (carry calibrated cutoff to serving) anywhere |
| V-I7 | V | FM-4 | COVERED | "a model artifact may enter the registry only after a valid evaluation report is attached" (+ V13: "only validated models may serve production traffic") | fail-closed gating across stages (borderline: expressed at multiple seams, not one global predicate) |
| V-I8 | V | FM-4 | NOT-COVERED | | no crash/resume atomicity, atomic publish, or "no half-written artifact" predicate |
| V-I9 | V | FM-4 | NOT-COVERED | | no concurrent atomic (model,transform) hot-swap / no-half-swapped-state predicate |
| V-E1 | V | FM-3 | COVERED | "the categorical encoder has an explicit, configured policy (error / unknown token / frequency-based fallback) for categories not seen during training" | unseen-category/OOV at serving |
| V-E2 | V | FM-3 | COVERED | "validates incoming request schema, returns prediction" (falsifier: "online endpoint returns a prediction for a request missing a required feature column without error") | missing/malformed feature at inference (reject branch) |
| V-E3 | V | FM-3 | COVERED | "class frequencies in val and test partitions approximate the overall distribution within a defined tolerance" (+ D3 "stratifies for classification") | class imbalance → stratified split |
| V-E4 | V | FM-6 | NOT-COVERED | | no cold-start / insufficient-data → fallback/baseline (V15 hard-fails on empty, but provides no fallback) |
| V-E5 | V | FM-3 | COVERED | "a constant feature column is caught at validation or transform fit; StandardScaler division by zero must not silently produce NaN/inf features" | degenerate numeric boundaries (+ V15 empty batch, V25 single-row) |
| V-F1 | V | FM-5 | COVERED | "a production endpoint serving a model older than a defined staleness threshold triggers a monitoring alert" (+ V29: "input stability alone does not detect concept drift") | silent staleness / concept drift |
| V-F2 | V | FM-3 | COVERED | "evaluation reports per-class precision, recall, and F1 in addition to aggregate metrics; aggregate accuracy alone is insufficient for imbalanced datasets" | good aggregate hides broken segment / per-slice eval |
| V-F3 | V | FM-7 | NOT-COVERED | | only the automated drift→retrain trigger (Dep14) present; no distinct human/incident feedback+rollback channel for non-pre-defined defects |
| V-F4 | V | FM-3 | NOT-COVERED | | no feedback-loop bias / model's outputs contaminate future training labels / exposure-propensity logging |
| N1 | N | FM-1 | COVERED | "the pipeline starts from already-labeled data; annotation is upstream of ingestion" (cand N3) | label quality assumed upstream |
| N2 | N | FM-1 | NOT-COVERED | | no serving-infra / autoscaling / latency-throughput SLO exclusion |
| N3 | N | FM-1 | COVERED | "the task asks for stage logic and connections, not a scheduler specification ... orchestration tools are infrastructure" (cand N8) | orchestration engine is a given |
| N4 | N | FM-1 | NOT-COVERED | | no "model architecture/algorithm family is a given input" exclusion (cand N1 HPO ≠ architecture choice) |
| N5 | N | FM-1 | NOT-COVERED | | no data-privacy/PII/security/compliance exclusion |
| N6 | N | FM-1 | COVERED | "the pipeline is batch-trained; the served model does not update weights from online traffic" (cand N2) | serving/training regime declared (batch) |
| N7 | N | FM-1 | COVERED | "the pipeline serves a single production model at a time" (cand N5) | single-model / single-task assumed |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D5 | 2 | 1 | cDep10 "evaluation must use the test partition, not val; the partition identity must be recorded" |
| Dep1 | 3 | 2 | cDep5 "any reordering or coercion applied at training must be replicated identically at serving"; V24 "dtype coercions ... between training and serving must not shift predictions beyond a defined tolerance" |
| Dep5 | 2 | 1 | V9 "the fitted transform artifact includes the fit parameters ... not merely the transform code or spec" |
| Dep11 | 2 | 1 | V32 "the input and output distributions from training ... are stored and versioned alongside the model" |
| Dep12 | 3 | 2 | cDep6 "every inference request and its prediction must be durably logged before the response is returned"; V30 "the inference-to-monitoring logging path must be durable under high traffic; queue overflow must be detectable" |
| Dep14 | 2 | 1 | cDep8 "promotion logic must compare the candidate model's report against the current production model's report using a defined threshold; a degraded candidate must not be promotable" |
| V-I1 | 2 | 1 | V28 "features that are derived from or correlated with the label only at training time ... are identified and excluded" |
| V-I3 | 3 | 2 | V5 "every promoted model's evaluation report is traceable to the exact dataset version (by hash) and split indices"; V10 "split indices are persisted; re-running the split on a modified dataset is detectable" |
| V-I4 | 2 | 1 | cDep9 "if the ingestion schema is updated ... the training pipeline must detect the mismatch and fail or re-derive the schema" |
| V-I5 | 2 | 1 | V14 "the transform artifact's fit state is frozen after initial fit ...; any subsequent refit must produce and register a new versioned artifact" |
| V-I7 | 3 | 2 | V13 "only validated models may serve production traffic"; V21 "training must detect NaN or inf loss and abort, not register a corrupt model artifact" |
| V-E5 | 5 | 4 | V15 "Empty batch rejection"; V16 "All-null feature column policy"; V25 "Single-sample and batch inference"; V27 "Non-positive log-transform input validation" |
| V-F1 | 2 | 1 | V29 "monitoring covers both input feature distribution AND prediction output distribution; input stability alone does not detect concept drift" |

**Total ballast = 20.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| V7 "the label column is never present in the serving feature vector; its absence is enforced at the serving endpoint" | UNMATCHED — human review |
| V18 "if only one class is present after splitting/filtering, training detects this and aborts with a clear error" | UNMATCHED — human review |
| V22 "monitoring distinguishes 'no requests received' (traffic alert) from 'predictions are healthy' ... zero traffic is not silently reported as healthy" | UNMATCHED — human review |
| N1 "Hyperparameter optimization (HPO) — excluded unless the task requires production-grade competitive model performance" | UNMATCHED — human review |
| N4 "Distributed training — excluded; training is a black box to the pipeline logic" | UNMATCHED — human review |
| N6 "Feature store — excluded ... this pipeline defines and computes features inline" | UNMATCHED — human review (justifies Dep8 N/A) |
| N7 "Explainability (SHAP, LIME) — excluded; a separate concern from pipeline correctness" | UNMATCHED — human review |

**Total unmatched = 7.**

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 9/10   Dep = 11/13   V = 12/18   N = 4/7
  by FM tag:     FM-1 = 18/23   FM-2 = 6/7   FM-3 = 5/6   FM-4 = 1/3   FM-5 = 2/2   FM-6 = 0/1   FM-7 = 2/3
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 20
  unmatched candidate points (human-review flag):    total = 7
```

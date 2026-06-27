# Search pass 1 — T02 (supervised ML pipeline, end-to-end)

## A. Domain primitives

A1. **Raw labeled dataset** — source data has both feature columns and a label column; both must be present and typed correctly before any downstream step. *Falsifier: pipeline accepts a label-free file without error at ingestion.*

A2. **Schema definition** — an explicit, versioned contract for column names, dtypes, allowed ranges, nullability, and label cardinality; serves as the single source of truth for validation at every stage. *Falsifier: a column rename passes ingestion silently.*

A3. **Fitted transform artifact** — stateful transformers (scalers, encoders, imputers) are fit objects, not just function specs; the fit state must be persisted and versioned alongside the model. *Falsifier: pipeline stores only transform code, not fit parameters.*

A4. **Model artifact** — serialized weights/parameters, architecture spec, and the framework version used to produce them. *Falsifier: loading the artifact in a different framework version silently changes predictions.*

A5. **Split indices** — the exact row assignments to train/val/test; reproducibility requires saving these, not just the random seed, since data may change. *Falsifier: re-running the split on slightly different data produces different train/test assignments without detection.*

A6. **Offline evaluation report** — a structured, persisted record of metrics on the held-out test set, tied to a specific model version and dataset version. *Falsifier: evaluation report exists but is not linked to a dataset hash, so it cannot be reproduced.*

A7. **Serving schema** — the feature schema expected at inference time (label column absent); must be derived from and consistent with the training schema. *Falsifier: serving accepts a request with the label column present and uses it.*

---

## B. Lifecycle / state

B1. **Pipeline run identity** — each pipeline execution has a unique ID linking data snapshot, transform artifact, model artifact, and evaluation report. *Falsifier: two runs produce artifacts with no shared lineage identifier.*

B2. **Data version / hash** — the exact dataset used for a run is identified by content hash or immutable snapshot reference. *Falsifier: retrain on "same" dataset that was silently appended; offline metric changes but the registry entry claims the same dataset.*

B3. **Model promotion state machine** — models move through defined states (candidate → validated → production → retired); only validated models may serve production traffic. *Falsifier: a candidate model with no evaluation report can be set to production.*

B4. **Transform fit-state lifecycle** — transformers are fit exactly once, on the training partition only; fit state is frozen after that. *Falsifier: adding new training data triggers a re-fit without issuing a new versioned artifact.*

B5. **Rollback state** — a prior production model + its transform artifact can be restored and must produce identical predictions to its original deployment. *Falsifier: rollback loads correct model weights but wrong transform artifact.*

---

## C. Components

C1. **Ingestion & schema validation** — reads raw data, enforces schema contract (types, nullability, ranges, label presence), emits a validated, versioned dataset or a hard failure. *Falsifier: a column with wrong dtype passes ingestion.*

C2. **Feature transforms** — applies stateful (fit-then-transform) and stateless operations; fitting must use only training rows; transform must be serializable. *Falsifier: fit is called on the full dataset before splitting.*

C3. **Train/val/test split** — partitions validated data into three non-overlapping sets; for time-ordered data the split must respect temporal order; stratification for classification. *Falsifier: test rows appear in the training partition.*

C4. **Training** — consumes train partition + fitted transforms; produces model artifact; detects divergence (NaN/inf loss) and fails fast. *Falsifier: training completes and registers a model when loss is NaN.*

C5. **Offline evaluation** — evaluates model on test partition only; reports primary and secondary metrics; writes a persisted, versioned report. *Falsifier: evaluation runs on val partition and is reported as test-set performance.*

C6. **Model registry / versioning** — stores model artifact + transform artifact + schema version + evaluation report as a single versioned bundle; supports promotion, retirement, and retrieval by version tag. *Falsifier: registry stores model weights but not the associated transform artifact.*

C7. **Serving transform path** — loads the exact frozen transform artifact from the registry and applies it to incoming requests; must be identical in logic and parameter state to the training-time transform. *Falsifier: serving re-fits or re-initializes the transformer from scratch on incoming data.*

C8. **Online inference** — loads model from registry, applies serving transforms to request, returns prediction; handles single-sample and batch requests. *Falsifier: online endpoint returns a prediction for a request missing a required feature column without error.*

C9. **Monitoring** — tracks input feature distribution, prediction distribution, and (when labels arrive) accuracy metrics; emits alerts on significant drift. *Falsifier: monitoring reports "healthy" when input distribution has shifted substantially.*

---

## D. Global invariants

D1. **No test contamination** — no fit() call anywhere in the pipeline may receive test-partition rows as input, directly or indirectly. *Falsifier: trace all fit() calls; any that receive test indices violates this.*

D2. **Transform reproducibility across environments** — given the same fitted artifact and same input, transform output is byte-identical in dev, staging, and prod. *Falsifier: apply same input in two environments; outputs differ.*

D3. **Schema consistency end-to-end** — the feature schema at ingestion, at training, at evaluation, and at serving must be identical (same columns, same dtypes, same order). *Falsifier: log schema hash at each stage; hashes differ.*

D4. **Version bundle atomicity** — model artifact and its transform artifact are always retrieved and deployed together; there is no code path that loads one without the other. *Falsifier: a code path loads model artifact v2 with transform artifact v1 without raising an error.*

D5. **Offline metric traceability** — every promoted model's offline evaluation report is traceable to the exact dataset version and split used. *Falsifier: re-running evaluation on a different data snapshot produces a different number; the original number is unrecoverable.*

D6. **Label distribution preservation across splits** — class frequencies in val and test partitions approximate the overall distribution within a defined tolerance. *Falsifier: a binary classification dataset with 90/10 imbalance produces a test set with 50/50 distribution.*

D7. **Serving label exclusion** — the label column is never present in the serving feature vector; its absence must be enforced, not assumed. *Falsifier: serving pipeline silently drops the label column rather than rejecting a request that includes it.*

D8. **Stale model alert** — a production endpoint serving a model older than a defined staleness threshold triggers a monitoring alert. *Falsifier: model is 30 days old, no alert fires.*

---

## E. Cross-component interaction seams

E1. **Split → Transform fit (pre-split fitting causes leakage)** — transform fitting must happen strictly after splitting and must receive only training indices. *Falsifier: move fit() call to before the split; offline accuracy improves suspiciously without model change.*

E2. **Transform fit → Training (mismatched transform state)** — the transform artifact passed to training must be the same object that is later stored in the registry for serving. *Falsifier: retrain without saving the transform artifact; serving uses a separately re-fitted transform.*

E3. **Training → Registry (gate on evaluation)** — a model artifact should only enter the registry after passing offline evaluation; the evaluation report is a required field of the registry entry. *Falsifier: a model artifact can be registered with an empty evaluation report.*

E4. **Registry → Serving transform path (artifact version mismatch)** — the serving path must load the transform artifact that was bundled with the deployed model version, not the latest artifact in the registry. *Falsifier: deploy model v1; update registry with v2 transform; serving silently uses v2 transform with v1 model.*

E5. **Serving transform path → Online inference (feature order and dtype)** — transforms must emit features in the exact column order and dtype the model expects; any reordering or coercion applied in training must be replicated in serving. *Falsifier: swap two feature columns in the serving path; linear/NN model silently produces wrong predictions.*

E6. **Online inference → Monitoring (prediction and input logging)** — every inference request and its prediction must be durably logged before the response is returned (or at minimum, failure to log must be detectable). *Falsifier: kill the logging sink mid-load; predictions are served with no log entries, monitoring reports healthy.*

E7. **Monitoring → Retraining trigger (actionable alert loop)** — drift alerts must propagate to an actionable trigger that initiates a new pipeline run; without this seam, monitoring is decorative. *Falsifier: inject synthetic drift; no retraining trigger fires.*

E8. **Offline evaluation metrics → Online monitoring metrics (proxy validity)** — the offline metric must be a valid proxy for the metric monitored online; mismatched evaluation windows or feature distributions make the offline score uninformative. *Falsifier: offline AUC is 0.95; online AUC measured on first week of traffic is 0.60 with no concept drift.*

E9. **Ingestion schema → Training schema (schema evolution propagation)** — if the ingestion schema is updated (new column, renamed column), the training pipeline must detect the mismatch and fail or re-derive the schema, not silently train on a stale schema. *Falsifier: rename a column in the raw data; training runs successfully on old schema, producing a model that fails at serving.*

E10. **Offline evaluation → Model promotion decision (promotion gate)** — promotion logic must compare the candidate model's evaluation report against the current production model's report using a defined threshold; without this comparison, degraded models can be promoted. *Falsifier: a candidate model with lower test AUC than production is successfully promoted.*

E11. **Split → Offline evaluation (eval on correct partition)** — evaluation must use the test partition, not val; the partition used must be recorded in the evaluation report. *Falsifier: evaluation report does not record which partition was used.*

E12. **Monitoring (delayed ground truth) → Accuracy metrics (label arrival lag)** — accuracy-based monitoring requires ground truth labels that may arrive long after predictions; the pipeline must record prediction timestamps, match labels when they arrive, and avoid computing accuracy before labels are available. *Falsifier: accuracy metric is computed at prediction time using a stale or zero label set, reporting 0% accuracy or fabricated numbers.*

---

## F. Edge / boundary cases

F1. **Empty ingestion batch** — zero-row input must produce a hard failure, not a zero-row model. *Falsifier: pass empty CSV; pipeline completes and registers a model.*

F2. **All-null feature column** — a column with 100% missing values must be rejected or handled by explicit policy (drop, constant impute), not silently produce NaN-filled features. *Falsifier: all-null column passes ingestion; model trains with NaN inputs.*

F3. **Unseen categorical level at serving time** — encoder must have an explicit policy (error, unknown token, frequency-based fallback) for categories not seen during training. *Falsifier: serving receives an unseen category; encoder raises an unhandled exception or silently maps it to an existing class.*

F4. **Single-class training batch** — if only one class is present after filtering/splitting, training must detect and abort. *Falsifier: training completes on a single-class dataset; classifier predicts 100% on one class with no alert.*

F5. **Extreme class imbalance** — evaluation must report per-class precision/recall/F1, not only aggregate accuracy, which would be misleading. *Falsifier: 99/1 class imbalance; evaluation report shows only 99% accuracy.*

F6. **Feature column added or removed between training artifact and serving request** — schema mismatch must be detected at serving time, before the model is called. *Falsifier: add a column to serving request; inference silently drops or ignores it.*

F7. **Model training divergence (NaN/inf loss)** — training must detect numerical divergence and fail fast rather than registering a corrupt model. *Falsifier: inject NaN features; training completes and the model produces NaN predictions in production.*

F8. **Zero serving traffic** — monitoring must distinguish "no requests received" from "predictions healthy"; alerting on zero traffic separately. *Falsifier: traffic drops to zero; monitoring reports "healthy" because no anomalous predictions observed.*

F9. **Duplicate rows** — duplicates spanning the split boundary (same row in train and test) cause artificial metric inflation; deduplication policy must be explicit and applied before splitting. *Falsifier: duplicate every row; offline AUC improves noticeably with no model change.*

F10. **Float32 vs float64 dtype mismatch** — training may use float64; serving may receive float32 (or vice versa); implicit coercions can shift predictions for sensitive models. *Falsifier: train with float64, serve with float32; predictions differ beyond tolerance.*

F11. **Label column present in serving request** — serving schema must explicitly reject or ignore the label column to prevent accidental target leakage at inference time. *Falsifier: send serving request with label column; model uses it as a feature.*

F12. **Single-sample vs large-batch inference** — transforms and model forward pass must handle both without shape errors or silent broadcasting bugs. *Falsifier: send a single-row request; transform raises a shape error expecting 2D input.*

F13. **Pipeline run on a dataset with no variance in a feature column** — a constant column causes zero-variance scalers (e.g., StandardScaler) to produce NaN or inf; must be caught at validation or transform fit. *Falsifier: constant column passes through; scaler divides by zero silently.*

---

## G. Silent failure modes

G1. **Transform fit before split** — no error is raised; offline metric is optimistically biased; detected only by comparing to a correctly-split baseline. *Falsifier: deliberately fit on full data; offline AUC rises above expected range.*

G2. **Wrong transform artifact loaded at serving** — feature schema is identical, so no type error; predictions are wrong without any exception. *Falsifier: swap transform artifact; no serving error, but predictions differ from training-time predictions on same inputs.*

G3. **Feature column reordering at serving** — tree models may be robust (if they use column names); linear/NN models silently produce wrong predictions if they index by position. *Falsifier: permute two feature columns in serving request; check prediction difference.*

G4. **Log-transform of non-positive values** — log(0) or log(-x) silently produces -inf or NaN, propagated through the model without an error. *Falsifier: inject zero or negative values into a log-transformed feature; inspect model output for NaN.*

G5. **Target leakage feature** — a feature that is derived from or correlated with the label only at training time (e.g., post-event signal) makes the model look good offline but fail online. *Falsifier: compare feature availability at training time vs at inference time; any feature unavailable at inference is a leak.*

G6. **Input-only drift monitoring** — model output distribution changes due to concept drift; input features look stable; output drift goes undetected. *Falsifier: inject synthetic concept drift (same inputs, shifted labels); monitoring does not alert.*

G7. **Registry stores model without evaluation report** — model is promoted; no alert, no error; degraded model serves production. *Falsifier: register model without report; promotion succeeds.*

G8. **Async logging queue overflow** — high traffic saturates the logging queue; log entries are dropped silently; monitoring data is incomplete; drift goes undetected. *Falsifier: saturate logging endpoint; check log completeness; no alert fired.*

G9. **Evaluation metric computed on val set, reported as test** — val set was used for early stopping or hyperparameter tuning; test metric is overly optimistic; no flag raised. *Falsifier: audit metric computation code path; confirm it uses test indices only.*

G10. **Monitoring without baseline distribution** — drift detection requires a reference distribution; if no training distribution is stored, drift cannot be computed, and monitoring silently does nothing meaningful. *Falsifier: deploy with no reference distribution stored; drift monitor reports "no drift" always.*

---

## H. Scope boundaries

H1. **Hyperparameter optimization (HPO)** — borderline IN: if included, must use val set only and must be completed before test evaluation; if excluded, must be noted as a gap for production quality. *Pull in if: the task requires a production-grade pipeline competitive on benchmark data.*

H2. **Online / continual learning** — OUT for a batch-trained pipeline; the served model does not update weights from online traffic. *Pull in if: concept drift response requires weight updates, not just retraining triggers.*

H3. **Data labeling / annotation** — OUT: upstream of ingestion; the task starts from already-labeled data. *Pull in if: the pipeline is responsible for acquiring labels (active learning, human-in-the-loop).*

H4. **Distributed training** — OUT for pipeline logic; the training component is a black box from the pipeline's perspective. *Pull in if: model scale requires multi-node training affecting artifact format or versioning.*

H5. **A/B testing / shadow mode** — OUT for a single-model pipeline; only one model serves production. *Pull in if: the task requires comparing a candidate model against production on live traffic before promotion.*

H6. **Feature store** — borderline OUT: this pipeline defines and computes features inline; a feature store would be needed if features are shared across models or pre-computed for low-latency serving. *Pull in if: online feature freshness or cross-model reuse is required.*

H7. **Explainability (SHAP, LIME)** — OUT for core pipeline correctness; a separate concern. *Pull in if: regulatory or audit requirements mandate per-prediction explanations.*

H8. **Data pipeline orchestration / scheduling** — OUT for the logic design; the task asks for stage logic and connections, not a scheduler specification. *Pull in if: the task requires automated periodic retraining with dependency management.*

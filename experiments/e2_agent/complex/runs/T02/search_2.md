# Search pass 2 — T02 new holes vs D1

---

1. **Transform → val/test inference-mode seam** — fitted transform artifact must be applied in inference mode (no refit) to val and test partitions before any evaluation or early-stopping; evaluating raw (untransformed) features against a model trained on transformed features silently inflates error metrics. *Falsifier: skip transform application to test partition; offline metric appears better than it should, then collapses in production.*

2. **Split → Training data boundary seam** — model forward/backward pass must consume strictly training-partition rows; unlike Dep-1 (which covers fit() on transforms), this covers the model receiving val or test rows during gradient updates — a separate, unlisted leakage path. *Falsifier: pass full dataset to the training loop and rely on transform-fit guard alone; model sees test rows during weight updates; offline metric is inflated.*

3. **Serving endpoint model reload / hot-swap policy** — after a new model version is promoted to production in the registry, the serving endpoint must detect and hot-reload it within a defined SLA; absent this, the old model serves forever post-promotion with no alert. *Falsifier: promote v2 to production; serving endpoint continues returning v1 predictions indefinitely with no error or alert.*

4. **Model artifact integrity check on load** — checksum or hash of the serialized model artifact is validated when loaded from the registry; a silently corrupted file raises a detectable error rather than producing garbage predictions. *Falsifier: corrupt 4 bytes of the model file in the registry; serving loads without error and returns numerically wrong predictions.*

5. **Prediction output range validity** — model output is constrained to a domain-valid range (probabilities in [0, 1], regression within defined bounds); violations are enforced or at minimum logged before the response is returned. *Falsifier: a numerical edge case produces a probability of 1.7; the serving endpoint returns it without error; downstream consumers treat it as valid.*

6. **Serving latency SLA** — the combined serving-transform + model forward-pass must complete within a defined per-request time budget; no latency criterion or enforcement point is specified anywhere. *Falsifier: deploy a transform that loads from disk on every request; p99 latency is 10 s; no SLA violation is raised.*

7. **Transform artifact thread-safety at serving** — the in-memory loaded transform artifact must be safe for concurrent requests; sklearn Pipelines carry mutable internal state that can silently corrupt under concurrent access. *Falsifier: send 100 simultaneous requests; a fraction of responses contain wrong feature values with no error logged.*

8. **Out-of-distribution input detection / clipping policy** — feature values at serving that fall outside a defined range relative to the training distribution (e.g., beyond N σ or declared domain bounds) must be flagged, clipped, or rejected; unconstrained extrapolation silently corrupts model output with no alert. *Falsifier: send a numeric feature value of 10⁶ (training max was 100); scaler outputs a 10 000 σ value; model predicts extreme nonsense; monitoring does not alert.*

9. **Partial batch failure semantics** — when one sample in a multi-sample batch request fails transform validation or schema check, the failure policy (fail-all vs. return-partial-with-error) must be defined and enforced consistently. *Falsifier: send a 100-row batch where row 42 has a missing required column; the entire batch is silently dropped with a 500 error; caller cannot identify which rows failed.*

10. **Shadow / canary deployment for offline→online correlation** — N-5 excludes A/B testing, but the task explicitly requires specifying how "the offline score predicts online behavior"; a shadow or canary deployment is the minimum mechanism needed to empirically verify that claim; the scope exclusion is wrong for this requirement. *Falsifier: offline AUC is 0.94; production AUC is 0.62; no mechanism exists to detect the gap prior to full rollout.*

11. **Training hyperparameter and config versioning** — model hyperparameters and architecture configuration must be persisted as a versioned artifact linked to the model in the registry; without this, training is not reproducible even when the same data and transform artifact are used. *Falsifier: re-train with identical data and transform; model produces different behavior because learning-rate and depth used originally are unrecorded.*

12. **Retraining data freshness on drift trigger** — when monitoring fires a drift-triggered retraining run (Dep-7), the new pipeline execution must ingest fresh or updated data; silently reusing the same historical dataset cannot address concept drift. *Falsifier: drift trigger fires; retraining runs on the same frozen snapshot; trained model is identical to the one that drifted; alert fires again immediately.*

13. **Point-in-time correctness for temporal aggregation features** — features computed from historical windows (rolling counts, running averages, cumulative statistics) must use only data available at the exact prediction timestamp; using a window that bleeds future rows is time-leakage not covered by Dep-1 (transform fit) or V-28 (target leakage). *Falsifier: compute a 7-day rolling average using rows from day T+1 through T+7; offline AUC is 0.97; online AUC is 0.55.*

14. **Model rollback mechanism** — the registry state machine must support re-promoting a previously-production (or validated) model back to production after a bad promotion; the current state machine reaches "retired" with no named re-promotion or rollback path. *Falsifier: v2 is promoted and causes a production incident; operator attempts rollback to v1; registry has no rollback operation; v1's state is "retired" with no path back to production.*

15. **Ingestion → Split explicit seam** — the split stage must receive only the post-validated, versioned dataset emitted by ingestion; a code path that feeds raw, pre-ingestion rows directly to split produces partitions containing schema violations or unlabeled rows that bypass all ingestion checks. *Falsifier: wire split to read directly from the raw file path instead of ingestion output; a row with a missing label enters the training partition; training completes without error.*

16. **Monitoring reference window selection policy** — the reference distribution stored for drift detection (V-32) must be derived from a specified, recent data window (e.g., last N days of training data or a dedicated calibration window) rather than the full training history; using all historical training data as the reference can mask distributional shift in recent patterns. *Falsifier: training data spans 3 years; reference is the full 3-year distribution; deployment distribution matches only the last 3 months; drift monitor always reports "no drift" because the broad historical reference absorbs the shift.*

---

**New holes count: 16**

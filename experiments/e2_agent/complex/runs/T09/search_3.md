# T09 — Search pass 3

Against D2 (83 V, 19 Dep, 8 D, 5 N). Items below are genuinely new — distinct falsifiers, not restatements.

---

## New dependency seams

**S3-Dep-A: Delegator ongoing grants → delegation record scope**
After a delegation record is created, if the delegator's effective permissions shrink (role removed, grant revoked), the delegation record's declared scope may now exceed what the delegator holds. Dep14 fires only at creation; V38 intersects the *target's* current grants with the declared scope, not the delegator's current grants. There is no seam that re-validates or narrows an existing delegation record when the delegator's permissions decrease.
*Breaks if: D holds owner scope, creates delegation for support agent with scope=owner; D's role is later revoked to viewer; at token issuance V38 intersects the target's grants with scope=owner, yielding owner-level access the delegator no longer holds the right to delegate.*

**S3-Dep-B: Service-to-service calls in microservice chains → re-authorization**
Dep18 authenticates callers of the evaluator's internal API. A different gap: when service A calls service B internally on behalf of a principal, does B re-invoke the evaluator, or does it trust the forwarded claims from A? The authorization model for inter-service calls is unspecified; the token/context forwarding contract between services has no defined seam.
*Breaks if: service A (compromised or SSRF'd) calls service B forwarding principal_id=platform-admin with a crafted internal header; B trusts the forwarded claim and skips re-evaluation; A has an effective bypass of the permission model for everything B can do.*

**S3-Dep-C: Passive grant expiry event → audit writer**
When a time-bound grant expires passively (no explicit revocation action), the evaluator begins returning deny for subsequent requests (V15). But who writes the expiry event to the audit log, and via which path? The per-request evaluator→audit-writer seam (Dep6) records individual decisions, not the state-change that caused them. There is no defined seam for the expiry scheduler (or evaluator at first-deny) producing an audit record marking the grant as expired.
*Breaks if: grant G expires at T; no audit event is emitted at T; the log shows G as active with no termination record; a later forensic review cannot determine when or why access stopped working — and the distinction between expiry and revocation is invisible.*

---

## New V criteria

**S3-V-A: Principal lifecycle events in audit log**
V65 enumerates audit-required events: role assignments, role mutations, delegation creation/revocation, API key creation/revocation. It does not list principal creation, deactivation, or reactivation. These are grant-anchor events whose absence from the audit log breaks access-history reconstruction.
*Falsifier: a user account is created, then deactivated six months later; neither event appears in the audit log; a compliance review cannot establish when the account existed or who authorized its creation.*

**S3-V-B: Principal reactivation semantics — preserved grants**
V2 specifies that a deactivated principal's grants are preserved (not deleted) but inactive. No criterion defines what happens on reactivation: do preserved grants automatically become active again, or must they be explicitly re-granted? Silent automatic reactivation restores access without admin review; an undefined path leaves the principal with no grants and no recourse.
*Falsifier (silent restore): principal P is deactivated for misconduct, then reactivated six months later; all prior grants silently become active again, including elevated permissions that were the reason for the deactivation. Falsifier (undefined): P is reactivated but no re-grant path exists; the reactivation API succeeds but P cannot access anything.*

**S3-V-C: Service account deactivation in tenant offboarding cascade**
V24 lists "API keys, grants, delegations, and active sessions" as what must be revoked before the tenant record is marked deleted. Service account principals themselves are not listed. Revoking an SA's API keys is necessary but insufficient: a non-deactivated SA principal could theoretically receive a new key if the key-creation endpoint does not check the tenant-deleted flag before the cascade fully closes.
*Falsifier: tenant T is offboarded; SA-1's API keys are revoked (V24); but SA-1's principal record is not deactivated; in the narrow window before the tenant record is marked deleted, a race or a bug in the cascade order allows issuance of a new key for SA-1.*

**S3-V-D: Delegation scope bounded by delegator's tenant**
No criterion prevents a delegation record from declaring a scope that references resources outside the delegator's own tenant. All per-request evaluation is bounded by the token-derived tenant (V27), but delegation records are created objects whose scope field is not explicitly constrained to the creator's tenant at write time.
*Falsifier: a delegator in tenant A creates a delegation record with scope referencing `tenant:B:project:P:read`; the record-creation endpoint validates only that scope ≤ delegator's effective permissions (Dep14) but does not enforce tenant membership of the scope; the impersonation token carries a cross-tenant scope claim.*

**S3-V-E: Delegation creation rejected when target principal is deactivated**
V79 ensures that impersonation of a deactivated principal yields zero effective permissions at token-issuance time. But no criterion rejects the creation of a delegation record whose target is deactivated. The record creation succeeds and is live in the store; if the target is later reactivated (V-B above), the dormant delegation record silently becomes useful without any new authorization action.
*Falsifier: principal P is deactivated; admin creates delegation record for support agent S to impersonate P; creation succeeds; P is reactivated weeks later; S immediately has a valid delegation without any reauthorization by P or a tenant admin.*

**S3-V-F: Cross-tenant sharing — partial approval state and expiry**
V23 requires explicit bilateral approval from both tenant owners before a cross-tenant grant is active. No criterion defines the intermediate state when only one tenant has approved: whether it is visible to the pending tenant, whether it can be exploited, and whether it auto-expires if the second approval never arrives.
*Falsifier: tenant A approves cross-tenant share; tenant B's admin never responds; after 180 days the pending grant is in an undefined state — some implementations auto-activate on timeout (unauthorized access), others accumulate stale pending records with no cleanup path.*

**S3-V-G: Session tokens must not embed evaluated effective permission lists**
Dep8 and V70 mandate that a role change or revocation takes effect within a bounded SLA. This SLA is physically unachievable if session tokens embed evaluated effective permission lists and are validated without server-side lookup — the embedded list is stale from the moment the role changes, and can only be corrected by token revocation or re-issuance (not in scope for V70's general SLA). The design must either (a) require that tokens carry only identity claims (tenant, principal, delegation chain) and the evaluator looks up grants on every call, or (b) declare a short embedded-permission TTL strictly shorter than the revocation SLA and implement token revocation for immediate effect.
*Falsifier: session tokens embed the evaluated permission set as signed claims with a 1-hour TTL; a role is removed; V70 requires effect within 60 s; the SLA cannot be met without a token-revocation infrastructure that is not designed — the evaluator has no way to invalidate a valid signed token that has not yet expired.*

**S3-V-H: Multi-IdP per tenant — cross-IdP sub-claim collision**
Dep19 specifies an immutable mapping from a single IdP's `sub` claim to the internal principal ID and defines migration semantics. When a tenant uses multiple identity providers simultaneously, two different IdPs may issue `sub` claims that are textually identical, and the mapping must namespace by IdP issuer, not just by sub value alone.
*Falsifier: tenant configures IdP-1 and IdP-2 concurrently; IdP-1 issues `sub=12345` for user Alice; IdP-2 issues `sub=12345` for user Bob; the principal registry maps both to the same internal ID; Bob silently inherits Alice's grants.*

---

## Scope exclusion note

**S3-Scope-A: Token signing key rotation**
Signing keys used to produce and verify session tokens, impersonation tokens, and audit hash chains are security-critical operational material. Their rotation cadence and revocation path are not addressed in D6, D7, or D8. If this is excluded (analogous to N3 data-key management), it should be explicitly stated, with the pull-back condition: *pulled back in if token-signing key compromise means any principal can mint valid tokens, which is a direct access-control failure — at which point the rotation procedure is an in-scope security control.*

---

## Count

| Category | New items |
|----------|-----------|
| Dep (new seams) | 3 (S3-Dep-A through S3-Dep-C) |
| V (new criteria) | 8 (S3-V-A through S3-V-H) |
| Scope note | 1 (S3-Scope-A) |
| **Total genuinely new holes** | **11** |

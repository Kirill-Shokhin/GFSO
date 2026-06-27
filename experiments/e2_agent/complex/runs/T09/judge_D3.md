# BLIND JUDGE VERDICT — T09 / candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Principal & identity model — define principal types (user, service account, support agent), stable unique immutable IDs" | principal-exists subsystem (Appendix D1 rule) |
| D2 | D | — | COVERED | "Tenant isolation layer — design tenant-namespaced resource IDs, boundary enforcement at API and storage layers (token-derived tenant context, ORM-level predicate)" | token-context clause = tenant establishment |
| D3 | D | — | COVERED | "Permission & grant model — define permission atomicity, grant record structure … effective-permission evaluation algorithm" | also D2 Role model |
| D4 | D | — | COVERED | "effective-permission evaluation algorithm (union, deny precedence, wildcard expansion, hierarchy walk)" | the decision function (PDP) |
| D5 | D | — | COVERED | "boundary enforcement at API and storage layers (token-derived tenant context, ORM-level predicate)" | PEP components incl. data layer |
| D6 | D | — | COVERED | "Resource hierarchy — enumerate hierarchy levels and valid grant anchors, define the walk-up inheritance algorithm, reparent semantics" | |
| D7 | D | — | COVERED | "The maximum permission a principal can grant is bounded by what they themselves hold … enforced in the grant-creation handler" (V13) | admin model, authz-bounded |
| Dep1 | Dep | FM-1 | COVERED | "AuthN → permission evaluator … the evaluator rejects any caller-supplied header that would override them … evaluator trusts X-Principal-Id … → caller impersonates any principal" | decide on verified identity |
| Dep2 | Dep | FM-1 | COVERED | "a bare resource ID cannot be resolved without a tenant context. Falsifier: a GET /resources/{id} call without tenant context resolves the resource and returns data" (V19) | tenant-id must reach data |
| Dep3 | Dep | FM-1 | COVERED | "service B must re-invoke the permission evaluator … rather than trusting forwarded identity claims from A … B trusts the forwarded claim and skips re-evaluation; any action B can perform becomes accessible" (cand Dep21) | decision consulted at every PEP / no unguarded path |
| Dep4 | Dep | FM-1/FM-2 | NOT-COVERED | | no distinct assertion of app↔data-layer *consistency/agreement* (DB-doesn't-trust-app, bidirectional); data-layer enforcement already credited to D5/V-F1 |
| Dep5 | Dep | FM-1/FM-2 | COVERED | "An impersonation token's effective permissions equal the intersection of the target's current grants and the declared delegation scope; it cannot exceed either" (V38); "declared scope is constrained at write time to resources within the delegator's own tenant; a scope field referencing a resource ID in another tenant is rejected" (V87) | bounded effective identity + tenant boundary |
| Dep6 | Dep | FM-1 | COVERED | "key effective permissions = principal's current grants ∩ the key's declared scope restriction" (V46); "An API key is permanently bound to the tenant in which it was created; it cannot authenticate in another tenant" (V48) | scope as ceiling + tenant binding |
| Dep7 | Dep | FM-1/FM-2 | COVERED | "An explicit deny at any resource level overrides an allow … deny-at-ancestor beats allow-at-descendant, and deny-at-descendant beats allow-at-ancestor" (V12) | inheritance × explicit-deny precedence |
| Dep8 | Dep | FM-1 | COVERED | "hierarchy cache must be invalidated on reparent before any evaluation using the moved resource" (cand Dep3) | re-parent recomputes grants |
| Dep9 | Dep | FM-1 | COVERED | "Revoking a principal's access … terminates all derived permissions and active tokens within a defined SLA; no derived credential outlives its source grant" (V70) | no stale-cache allow after revoke |
| Dep10 | Dep | FM-1 | COVERED | "Platform operators who can access any tenant hold a distinct, audited role; every cross-tenant access is audit-logged with a stated reason" (V25) | scoped cross-tenant role |
| Dep11 | Dep | FM-1 | NOT-COVERED | | no multi-tenant-membership / one-server-pinned-active-tenant-per-request / no-A-bleed-while-active=B content |
| Dep12 | Dep | FM-1/FM-2 | NOT-COVERED | | inheritance treated only within-tenant; no "inheritance halts at the tenant root / child can't widen parent's tenant scope" rule |
| Dep13 | Dep | FM-1/FM-2 | NOT-COVERED | | no multi-PEP *policy-version coherence* artifact (all PEPs on same policy version, no stale-version divergence); candidate's role-change propagation is single-subject freshness (folds into Dep9) |
| V-I1 | V | FM-1 | COVERED | "Tenant A cannot discover the existence, name, member count, or resource list of tenant B" (V22) | isolation incl. no enumeration |
| V-I2 | V | FM-2 | COVERED | "deny entries override allows with defined precedence; resolution is deterministic across replicas" (V10) | stated total precedence |
| V-I3 | V | FM-1 | COVERED | "An absent grant means deny; the evaluator never defaults to allow on an unmatched resource or principal" (V68) | default-deny |
| V-I4 | V | FM-4 | COVERED | "Internal service-to-service calls must enforce tenant context; 'trusted internal' status does not exempt a call from the tenant_id predicate" (V74) | complete mediation / no layer exempt |
| V-I5 | V | FM-1 | COVERED | "No finite sequence of valid API calls allows a principal to acquire effective permissions exceeding those explicitly granted to it" (V67) | least privilege / no escalation |
| V-I6 | V | FM-3 | COVERED | "For any authorization evaluation, the grant set considered is bounded to the tenant derived from the authenticated token" (V27) | verified tenant context per evaluation |
| V-I7 | V | FM-1 | COVERED | "Both allow and deny authorization decisions are recorded in the audit log" (V59); fields incl. "real_principal_id" (V60); "append-only" (V58); "hash-chained or signed" (V61) | every access audited, tamper-evident, real actor |
| V-E1 | V | FM-3 | COVERED | "Cross-tenant resource sharing requires an explicit bilateral grant approved by both tenant owners" (V23) | shared/global resources as explicit rule |
| V-E2 | V | FM-3 | COVERED | "Support-staff impersonation requires either explicit tenant-owner consent … or a documented break-glass procedure with dual approval; both paths produce audit records" (V44) | support impersonation, scoped+audited |
| V-E3 | V | FM-3 | COVERED | "Moving a resource to a new parent recalculates inherited grants; existing instance-level grants require explicit reconfirmation" (V33); deleted-resource grants tombstoned (V78) | moved/orphaned resource |
| V-E4 | V | FM-3 | COVERED | "the audit-read and audit-export endpoints must derive tenant context from the authenticated token, not from a caller-supplied filter parameter … GET /audit?tenant_id=other-tenant … returns another tenant's records" (cand Dep16) | client-supplied tenant param ≠ token → reject |
| V-E5 | V | FM-3 | NOT-COVERED | | no background-job/cron/queue/webhook-with-no-user-must-carry-scoped-principal content |
| V-E6 | V | FM-3 | NOT-COVERED | | candidate hierarchy is *resource*-level only; no nested-orgs/sub-tenants/tenant-hierarchy isolation |
| V-E7 | V | FM-3 | NOT-COVERED | | no "a `*`/broad grant is still tenant-bounded, not a tenant escape" (V11 bounds wildcard over resource *types*, a different dimension) |
| V-E8 | V | FM-3 | COVERED | "An unrecognized action string is denied, not allowed by default … a new action type is deployed; a principal with no grants for it gains access because the evaluator treats unknown actions as unconstrained" (V76) | extension-time default-deny |
| V-E9 | V | FM-3 | NOT-COVERED | | no valid-but-foreign-object-id ⇒ not-found-after-ownership-recheck / no-existence-oracle (V19 is the missing-tenant-context case, not a foreign id with context) |
| V-E10 | V | FM-3 | COVERED | "A delegated token cannot itself be used to create a further delegation; chain depth is capped at one hop" (V41) | delegation-chain depth/loop bound |
| V-E11 | V | FM-3 | COVERED | "The tenant-creation flow provisions exactly one bootstrapped admin grant via an explicitly documented, auditable platform-operator action; this path is subject to V13 (grantor-bound)" (V82) | tenant-bootstrap scoped |
| V-E12 | V | FM-3 | COVERED | "A principal cannot create a delegation targeting itself with a broader scope than it currently holds" (V43) | reflexive self-grant rule |
| V-F1 | V | FM-1 | COVERED | "Every query on tenant-owned tables carries a tenant_id predicate enforced at ORM/query-builder level, not only in business logic … a query omitting the predicate returns rows from all tenants" (V21) | single-omission-catastrophic + structural ORM guard |
| V-F2 | V | FM-3 | COVERED | "an SSRF or misconfigured internal firewall allows an arbitrary service to POST to the evaluator with crafted principal_id … the evaluator returns a legitimate allow decision" (cand Dep18) | SSRF-of-authz / confused-deputy vector + caller-auth guard |
| V-F3 | V | FM-3 | COVERED | "evaluation of a grant referencing a deleted role does not throw an exception, default to allow, or treat the grant as carrying full permissions" (V81) | fail-closed on error path |
| V-F4 | V | FM-3 | COVERED | "Resource ID matching in the permission evaluator is exact; no prefix-match … a grant for `proj:A` matches `proj:AB`" (V73) | check-X-act-on-Y / wrong-object |
| V-F5 | V | FM-7 | COVERED | "Every action taken under impersonation records both the real principal and the impersonated principal in the audit log" (V40); grant/role/lifecycle events logged (V65) | audit-gap guard: real-actor + grant-change |
| V-F6 | V | FM-3 | COVERED | "Tenant context is derived from the authenticated token, not from a caller-supplied header … a caller supplies X-Tenant-Id: other-tenant and gains access" (V20) | tenant from client-controlled source |
| V-F7 | V | FM-1 | COVERED | "Session tokens … do not embed evaluated effective permission sets. The evaluator performs a live grant lookup on every authorization call" (V90) | re-authorize each use, no checked-once-trusted handle |
| N1 | N | FM-1 | COVERED | "Authentication mechanism (OIDC, SAML, password hash, WebAuthn) — the AuthZ layer consumes a verified, signed principal-identity assertion; credential verification is out of scope" (N1) | |
| N2 | N | FM-1 | NOT-COVERED | | no transport/network-security (TLS) exclusion |
| N3 | N | FM-1 | NOT-COVERED | | no datastore-faithfully-applies-scoping / SQL-injection-substrate exclusion |
| N4 | N | FM-1 | COVERED | "Token signing key rotation — the rotation cadence and revocation path for keys used to sign session tokens, impersonation tokens, and audit hash chains are operational key-management concerns" (N6) | secret/key/token custody |

## 6.2 Ballast list (clusters with >1 candidate point on one ref item; long tail summarized)

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases (abbrev.) |
|---|---|---|---|
| Dep6 | 16 | 15 | V46,V47,V48,V49,V50,V51,V52,V53,V54,V55,V56,V57,V83, cand-Dep5/Dep13/Dep17 (API-key/SA cluster) |
| D3 | 12 | 11 | D2,D3 comps, V3,V4,V5,V6,V7,V8,V9,V16,V17,V18 (role/permission/grant cluster) |
| Dep5 | 11 | 10 | V37,V39,V45,V75,V79,V80,V87,V88, cand-Dep14/Dep20 (delegation cluster) |
| D6 | 10 | 9 | D5 comp, V28,V29,V30,V31,V32,V34,V35,V36, cand-Dep9 (hierarchy cluster) |
| V-I7 | 8 | 7 | V58,V60,V61,V62,V66,V69, cand-Dep6 (audit-completeness cluster) |
| Dep9 | 6 | 5 | V15,V42, cand-Dep4/Dep8/Dep12 (freshness/propagation cluster) |
| V-F5 | 5 | 4 | V65,V84, cand-Dep10/Dep22 |
| D1 | 4 | 3 | V1,V2,V85 |
| V-E1 | 3 | 2 | V89, D4 sharing-clause |
| V-E3 | 2 | 1 | V78 |
| V-E8 | 2 | 1 | V11 |
| V-I1 | 2 | 1 | V26 |
| V-I2 | 2 | 1 | cand-Dep2 |
| V-I3 | 2 | 1 | V77 |
| Dep10 | 2 | 1 | D4 platform-operator clause |
| D7 | 2 | 1 | V14 |
| N4 | 2 | 1 | N3 (encryption-at-rest/CMK) |

**Total ballast ≈ 74 points** (dominated by over-decomposition of the API-key/SA, role/permission, delegation, hierarchy, and audit clusters: the candidate carries ~127 items against ~50 reference items).

## 6.3 Unmatched candidate points (no reference item — human review)

| candidate phrase (verbatim, abbrev.) | flag |
|---|---|
| cand-Dep7 "Offboarding workflow → tenant-deletion step … revoked before the tenant record is marked deleted" | UNMATCHED — human review |
| cand-Dep11 "Cross-tenant grant use → both-tenant audit logs … the audit record must appear in both the source and the target tenant's logs" | UNMATCHED — human review |
| cand-Dep15 "Grant creation → read-your-writes consistency … visible on the replica the evaluator reads from before the grant-creation response is returned" | UNMATCHED — human review |
| cand-Dep19 "IdP sub-claim → internal stable principal ID translation … defined, immutable mapping … no silent re-bind" | UNMATCHED — human review |
| V24 "On tenant offboarding, all API keys, grants, delegations, active sessions, and service account principals are revoked/deactivated before the tenant record is marked deleted" | UNMATCHED — human review |
| V86 "service account principal records are deactivated as part of the cascade … unable to acquire a new API key after its existing keys are revoked" | UNMATCHED — human review |
| V91 "multiple identity providers concurrently … namespaces mappings by (IdP issuer, sub) pair … identical sub values from different IdPs map to distinct internal principal IDs" | UNMATCHED — human review |
| V63 "A minimum audit retention period is defined; records are not garbage-collected before it" | UNMATCHED — human review |
| V64 "Tenant admins can export their tenant's audit log in a standard machine-readable format (CEF, JSON-ND)" | UNMATCHED — human review |
| V71 "Token expiry checks accept a bounded, documented clock-skew tolerance" | UNMATCHED — human review |
| V72 "A tenant with zero members is not accessible to any platform operator without an explicit break-glass grant" | UNMATCHED — human review |
| cand-N2 "Rate limiting / abuse prevention … an operational control, not an access-control rule" | UNMATCHED — human review |
| cand-N4 "Frontend / UI access control … a UX concern, not a security control" | UNMATCHED — human review |
| cand-N5 "Billing / subscription entitlements … a separate entitlement layer" | UNMATCHED — human review |

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/7   Dep = 9/13   V = 22/26   N = 2/4
  by FM tag:     FM-1 = 17/23   FM-2 = 3/6   FM-3 = 13/17   FM-4 = 1/1   FM-5 = n/a   FM-6 = n/a   FM-7 = 1/1
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 74
  unmatched candidate points (human-review flag):    total = 14
```

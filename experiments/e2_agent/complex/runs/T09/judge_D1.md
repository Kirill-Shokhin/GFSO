# BLIND JUDGE VERDICT — T09 / candidate D1

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Principal & identity model — define principal types (user, service account, support agent)" | principal sub-system named |
| D2 | D | — | COVERED | "Tenant isolation layer — design tenant-namespaced resource IDs, boundary enforcement at API and storage layers (token-derived tenant context, ORM-level predicate)" | tenant context established + propagated |
| D3 | D | — | COVERED | "Role model — define role structure (named, versioned permission set)" ; "Permission & grant model … effective-permission evaluation algorithm" | policy/role-permission grammar |
| D4 | D | — | COVERED | "effective-permission evaluation algorithm (union, deny precedence, wildcard expansion, hierarchy walk)" | the decision function |
| D5 | D | — | COVERED | "boundary enforcement at API and storage layers (token-derived tenant context, ORM-level predicate)" | enforcement incl. data layer |
| D6 | D | — | COVERED | "Resource hierarchy — enumerate hierarchy levels and valid grant anchors, define the walk-up inheritance algorithm, reparent semantics" | ownership/hierarchy/inheritance |
| D7 | D | — | COVERED | "The maximum permission a principal can grant is bounded by what they themselves hold … enforced in the grant-creation handler" | grant-admin bounded by holder |
| Dep1 | Dep | FM-1 | COVERED | "the evaluator rejects any caller-supplied header that would override them. Breaks if: evaluator trusts X-Principal-Id or X-Tenant-Id HTTP header → caller impersonates any principal or tenant" | decide on verified identity |
| Dep2 | Dep | FM-1 | COVERED | "Internal service-to-service calls must enforce tenant context; 'trusted internal' status does not exempt a call from the tenant_id predicate" | tenant threaded through every hop |
| Dep3 | Dep | FM-1 | NOT-COVERED | | no "decision consulted at every PEP / no unguarded export/DAO" — candidate's ubiquity statements are all the *tenant filter* artifact (Dep2/V-F1), not the *decision* |
| Dep4 | Dep | FM-1,FM-2 | COVERED | "a GET /resources/{id} call without tenant context resolves the resource and returns data" (V19: "a bare resource ID cannot be resolved without a tenant context") | data layer independently requires scope, doesn't trust app |
| Dep5 | Dep | FM-1,FM-2 | COVERED | "An impersonation token's effective permissions equal the intersection of the target's current grants and the declared delegation scope; it cannot exceed either" | bounded effective identity |
| Dep6 | Dep | FM-1 | COVERED | "An API key is permanently bound to the tenant in which it was created; it cannot authenticate in another tenant" | key scoped tenant+perms |
| Dep7 | Dep | FM-1,FM-2 | COVERED | "An explicit deny at any resource level overrides an allow at the same or any ancestor level; the deny-wins rule is defined and holds across every level pair" | inheritance↔deny precedence |
| Dep8 | Dep | FM-1 | COVERED | "Moving a resource to a new parent recalculates inherited grants … Falsifier: resource moved from project A to project B silently retains all project-A inherited grants" | re-parent recompute |
| Dep9 | Dep | FM-1 | COVERED | "Revoking a principal's access … terminates all derived permissions and active tokens within a defined SLA; no derived credential outlives its source grant" | revoke reaches live decision |
| Dep10 | Dep | FM-1 | COVERED | "Platform operators who can access any tenant hold a distinct, audited role; every cross-tenant access is audit-logged with a stated reason" | scoped, audited cross-tenant role |
| Dep11 | Dep | FM-1 | NOT-COVERED | | no multi-membership active-tenant pinning (user in flat tenants {A,B}, one server-pinned active per request, no A-bleed) |
| Dep12 | Dep | FM-1,FM-2 | NOT-COVERED | | inheritance criteria (V28–V33) are within-tenant mechanics; no "inheritance halts at the tenant root / child can't widen parent's tenant scope" |
| Dep13 | Dep | FM-1,FM-2 | NOT-COVERED | | no policy-version coherence across PEPs after a rule edit (V10 "deterministic across replicas" = conflict determinism, different artifact) |
| V-I1 | V | FM-1 | COVERED | "Tenant A cannot discover the existence, name, member count, or resource list of tenant B" | headline isolation predicate |
| V-I2 | V | FM-2 | COVERED | "deny entries override allows with defined precedence; resolution is deterministic across replicas" | stated total precedence |
| V-I3 | V | FM-1 | COVERED | "An absent grant means deny; the evaluator never defaults to allow on an unmatched resource or principal" | default-deny |
| V-I4 | V | FM-4 | COVERED | "boundary enforcement at API and storage layers (token-derived tenant context, ORM-level predicate)" | complete mediation, data incl. |
| V-I5 | V | FM-1 | COVERED | "No finite sequence of valid API calls allows a principal to acquire effective permissions exceeding those explicitly granted to it" | least privilege / no escalation |
| V-I6 | V | FM-3 | COVERED | "Tenant context is derived from the authenticated token, not from a caller-supplied header; every authorization check is bounded to that tenant" | verified tenant context |
| V-I7 | V | FM-1 | COVERED | "Both allow and deny authorization decisions are recorded in the audit log" (+V60 real_principal_id, V58 append-only) | every access audited, real actor |
| V-E1 | V | FM-3 | COVERED | "Cross-tenant resource sharing requires an explicit bilateral grant approved by both tenant owners" | explicit shared/cross-tenant rule |
| V-E2 | V | FM-3 | COVERED | "Support-staff impersonation requires either explicit tenant-owner consent … or a documented break-glass procedure with dual approval; both paths produce audit records" | support-impersonation bounded+audited |
| V-E3 | V | FM-3 | COVERED | "hierarchy cache must be invalidated on reparent before any evaluation using the moved resource" | moved-resource grants recomputed |
| V-E4 | V | FM-3 | NOT-COVERED | | only client-tenant statement is V20 (credited V-I6); no separate URL/path-tenant ≠ token-tenant mismatch-reject boundary |
| V-E5 | V | FM-3 | NOT-COVERED | | no background/async/cron/queue/webhook job needing an explicit tenant-scoped principal |
| V-E6 | V | FM-3 | NOT-COVERED | | no nested orgs / sub-tenants / tenant hierarchy (D5 is *resource* hierarchy) |
| V-E7 | V | FM-3 | NOT-COVERED | | V11 limits wildcard to enumerated types; no "a `*` grant is still tenant-bounded" |
| V-E8 | V | FM-3 | COVERED | "a new resource type added later is not covered without a new or updated grant" | extension-time default-deny |
| V-E9 | V | FM-3 | NOT-COVERED | | V26 = non-guessable IDs (different mechanism); no "foreign object id → 404 after ownership re-check, no existence oracle" |
| V-E10 | V | FM-3 | COVERED | "A delegated token cannot itself be used to create a further delegation; chain depth is capped at one hop" | delegation-chain depth/loop bound |
| V-E11 | V | FM-3 | NOT-COVERED | | no tenant-provisioning / first-admin bootstrap scoped to the new tenant |
| V-E12 | V | FM-3 | COVERED | "A principal cannot create a delegation targeting itself with a broader scope than it currently holds" | reflexive self-grant |
| V-F1 | V | FM-1 | COVERED | "Every query on tenant-owned tables carries a tenant_id predicate enforced at ORM/query-builder level, not only in business logic" | structural guard, single-omission leaks |
| V-F2 | V | FM-3 | NOT-COVERED | | no confused-deputy (privileged intermediary must re-check the *caller's* grants, not its own) |
| V-F3 | V | FM-3 | NOT-COVERED | | V66 is audit-write fail-secure only; no PDP error/exception/timeout → fail-closed coupling |
| V-F4 | V | FM-3 | NOT-COVERED | | no check-X-act-on-Y / wrong-subject-or-object binding (V73 = prefix-match, a different guard) |
| V-F5 | V | FM-7 | COVERED | "Role assignments, role mutations, delegation creation/revocation, and API key creation/revocation are audit-logged with before-and-after state" | audit-gap closed (grant-changes/impersonation, tamper-evident V61) |
| V-F6 | V | FM-3 | NOT-COVERED | | only V20 (credited V-I6); no broader spoofable-source coupling (forged JWT claim / unverified subdomain) + reject-on-mismatch |
| V-F7 | V | FM-1 | COVERED | "A time-bound grant that has expired is denied, including for in-flight requests evaluated after the expiry timestamp" | re-check each use, no checked-once-trusted handle |
| N1 | N | FM-1 | COVERED | "Authentication mechanism (OIDC, SAML, password hash, WebAuthn) … credential verification is out of scope" | IdP/authn trusted, securing it excluded |
| N2 | N | FM-1 | NOT-COVERED | | no transport/network-security (TLS) exclusion |
| N3 | N | FM-1 | NOT-COVERED | | cN3 = data-at-rest encryption; no "datastore faithfully applies the scoping / no engine-level bypass / injection" exclusion |
| N4 | N | FM-1 | NOT-COVERED | | no secret/token/signing-key custody (KMS) exclusion for the credentials the model scopes (cN3 is data-at-rest CMK, different scope) |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count−1) | duplicate candidate phrases |
|---|---|---|---|
| D1 | 2 | 1 | V50 "A service account is a first-class principal with its own stable ID" |
| D6 | 4 | 3 | V28 "child resource inherits all grants of its parent"; V30 "hierarchy levels are enumerated"; V31 "walk-up inheritance algorithm … traverses to the root" |
| Dep5 | 2 | 1 | V75 "A delegation-scope restriction claim … enforced by every downstream service" |
| Dep6 | 4 | 3 | V46 "key effective permissions = principal's current grants ∩ the key's declared scope"; V47 "scope restriction cannot expand beyond the owning principal's effective permissions"; V49 "resource-bound API key is rejected … outside its declared resource set" |
| Dep9 | 8 | 7 | V2 "deactivated principal is denied all access immediately"; V9 "grant store … is the authoritative source"; V24 "On tenant offboarding, all API keys, grants, delegations, and active sessions are revoked"; V42 "Delegation revocation invalidates all derived tokens"; V53 "revoked API key is rejected by all nodes within a defined SLA"; cDep4 "token issuer verifies the delegation record via a strong-consistent read"; cDep5 "revocation must invalidate the key-to-principal cache entry at all nodes" |
| V-I1 | 5 | 4 | V3 "Custom roles are tenant-scoped"; V27 "grant set considered is bounded to the tenant"; V55 "service account from tenant A cannot be granted a role in tenant B"; V57 "list-api-keys endpoint returns only keys … within their tenant" |
| V-I3 | 2 | 1 | V76 "An unrecognized action string is denied, not allowed by default" |
| V-I4 | 2 | 1 | V77 "An unauthenticated request … cannot reach the permission evaluator" |
| V-I5 | 2 | 1 | V29 "A grant on a child resource cannot confer permissions that the granting principal does not hold on the parent" |
| V-I7 | 8 | 7 | V40 "records both the real principal and the impersonated principal"; V58 "Audit records are append-only"; V60 audit fields incl. "real_principal_id"; V62 "tenant admin can read … audit records for their own tenant only"; V66 "If an audit write fails, the associated request is denied"; V69 "No permission evaluation completes without a durable audit record"; cDep10 "real principal ID must be embedded in the impersonation token" |
| V-E2 | 3 | 2 | V37 "Impersonation is allowed only when an active delegation record … exists"; V39 "Every delegation record has a non-null, bounded expiry timestamp" |
| V-E10 | 2 | 1 | V45 "A delegation record's scope cannot be widened after creation; only narrowed or revoked" |
| V-F5 | 4 | 3 | V14 "grants cannot appear or disappear without a corresponding audit record"; V61 "Audit records are hash-chained or signed"; cDep6 "decision and matched grant ID must be passed atomically to the audit writer" |
| V-F7 | 2 | 1 | cDep8 "role's permission set changes, principals holding active sessions … refreshed within a bounded window" |

**Total ballast = 36.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| V1 "Principal IDs are stable, immutable, and never reused after deletion" | UNMATCHED — human review |
| V4 "Built-in (platform-defined) roles are immutable; custom roles are mutable with a versioned changelog" | UNMATCHED — human review |
| V5 "A grant references a specific role version; role updates do not retroactively change grantee permissions" | UNMATCHED — human review |
| V6 "Assigning a role whose permission set is empty is a no-op" | UNMATCHED — human review |
| V7 "Circular role inclusion is detected at role-definition time and rejected" | UNMATCHED — human review |
| V8 "Each permission names exactly one action on one resource type; no coarse action implies a finer one" | UNMATCHED — human review |
| V16 "A grant on a non-existent resource either fails or creates a pending grant … exact same ID and type" | UNMATCHED — human review |
| V17 "Concurrent grant modifications targeting the same principal both persist" | UNMATCHED — human review |
| V18 "A bulk grant-assignment either fully succeeds or fully rolls back" | UNMATCHED — human review |
| V26 "Tenant IDs and resource IDs are non-guessable; sequential enumeration is not a valid discovery path" | UNMATCHED — human review |
| V32 "Grants can be pinned to a specific resource instance; type-level grants cover all current and future instances" | UNMATCHED — human review |
| V34 "evaluator resolves hierarchy traversal at the maximum permitted nesting depth without timeout or stack overflow" | UNMATCHED — human review |
| V35 "Circular parent chains are detected and rejected at resource-creation time" | UNMATCHED — human review |
| V36 "Resource creation at a depth exceeding the defined maximum nesting depth is rejected" | UNMATCHED — human review |
| V51 "the SA's raw long-lived key is not distributed to engineers" | UNMATCHED — human review |
| V52 "Key rotation produces a new key while the old key remains valid for a configurable grace window" | UNMATCHED — human review |
| V54 "The raw API key value is shown only once at creation; subsequent … calls return only a masked form" | UNMATCHED — human review |
| V56 "Creating an API key with no scope restriction … there is no silent full-scope default" | UNMATCHED — human review |
| V63 "A minimum audit retention period is defined; records are not garbage-collected before it" | UNMATCHED — human review |
| V64 "Tenant admins can export their tenant's audit log in a standard machine-readable format" | UNMATCHED — human review |
| V71 "Token expiry checks accept a bounded, documented clock-skew tolerance" | UNMATCHED — human review |
| V72 "A tenant with zero members is not accessible to any platform operator without an explicit break-glass grant" | UNMATCHED — human review |
| V73 "Resource ID matching in the permission evaluator is exact; no prefix-match algorithm" | UNMATCHED — human review |
| cDep2 "evaluator reads grants from a consistent snapshot; a partial grant-removal must not be visible" | UNMATCHED — human review |
| cDep7 "all keys, sessions, and grants must be revoked before the tenant record is marked deleted; the ordering is enforced" | UNMATCHED — human review |
| cDep9 "inherited grants must be fully applied before the creation response is returned" | UNMATCHED — human review |
| cDep11 "when a cross-tenant grant is exercised, the audit record must appear in both the source and the target tenant's logs" | UNMATCHED — human review |
| cN2 "Rate limiting / abuse prevention" | UNMATCHED — human review |
| cN3 "Data encryption at rest / customer-managed keys" | UNMATCHED — human review |
| cN4 "Frontend / UI access control" | UNMATCHED — human review |
| cN5 "Billing / subscription entitlements" | UNMATCHED — human review |

**Total unmatched = 31.**

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/7   Dep = 9/13   V = 16/26   N = 1/4
  by FM tag:     FM-1 = 16/23   FM-2 = 4/6   FM-3 = 7/17   FM-4 = 1/1   FM-5 = n/a   FM-6 = n/a   FM-7 = 1/1
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 36
  unmatched candidate points (human-review flag):    total = 31
```

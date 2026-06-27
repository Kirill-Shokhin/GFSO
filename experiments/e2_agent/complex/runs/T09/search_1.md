# T09 — Search pass 1 (exhaustive, no prior decomposition)

Task: Design the access-control logic for a multi-tenant SaaS — principal/role/permission model, tenant
isolation, resource hierarchy & permission inheritance, delegation/impersonation, API-key & service-account
scoping, and the audit trail. Rules must guarantee no principal ever reaches a resource outside its grants or
its tenant.

---

## A. Domain Primitives (11)

A1. **Principal identity** — every principal (user, service account, support agent) has a unique, stable,
immutable ID that is never reused after deletion — *falsifier: deleted user re-created with the same ID
silently inherits prior grants.*

A2. **Role definition** — a role is a named, versioned, ordered set of permissions; each role is either
global (platform-defined) or tenant-scoped — *falsifier: tenant A's custom role leaks its permission list to
tenant B's role editor.*

A3. **Permission atomicity** — each permission names exactly one action on one resource type (e.g.,
`dataset.read`, `project.delete`); no coarse action implies a finer one unless explicitly listed — *falsifier:
a `write` permission silently includes `delete`, granting more than intended.*

A4. **Grant record** — a grant binds (principal, role-or-permission, resource-scope, optional expiry); the
grant is the authoritative source for access — *falsifier: access is decided from a derived cache that has
drifted from the grant store.*

A5. **Effective-permission evaluation** — effective permissions = union of all matching grants; deny entries
(if supported) override allows with defined precedence — *falsifier: conflicting grants from two roles resolve
non-deterministically, producing different answers per replica.*

A6. **Wildcard/glob expansion** — if wildcard permissions are supported, they expand only over resource types
that existed when the grant was created (or are explicitly enumerated) — *falsifier: wildcard grant covers
a new resource type added after the grant, exceeding original intent.*

A7. **Explicit deny semantics** — an explicit deny on a resource overrides an allow at the same or any
ancestor level; the deny-wins rule is defined and tested at every hierarchy level — *falsifier: deny on parent
does not block an allow on a child (or vice versa) because precedence is undefined.*

A8. **Built-in vs. custom roles** — platform-defined (built-in) roles cannot be mutated; custom roles are
mutable but versioned with a changelog — *falsifier: mutating a built-in role silently changes the effective
permissions of all principals holding it.*

A9. **Role version immutability on grant** — a grant references a role version; role updates do not
retroactively change what grantees can do without explicit re-grant or version bump — *falsifier: admin
narrows a role, expecting immediate effect, but all grantees keep the old permission set indefinitely.*

A10. **Permission inheritance direction** — a child resource inherits all grants of its parent unless
overridden; inheritance flows down only — *falsifier: a resource created under a project does not receive
the project-level viewer grant, leaving it accessible to nobody.*

A11. **Inheritance ceiling (no upward escalation)** — a grant on a child cannot confer permissions the
granting principal does not hold on the parent — *falsifier: a project-editor can grant project-owner on a
sub-resource to a third party, escalating privilege.*

---

## B. Tenant Isolation (8)

B1. **Tenant namespace** — all resource IDs are namespaced by tenant ID at the storage layer; a bare
resource ID is meaningless without a tenant context — *falsifier: a GET /resources/{id} call without a tenant
context resolves the resource and returns data.*

B2. **Tenant boundary enforcement on every call** — the tenant is derived from the authenticated token, not
from a caller-supplied header; every authorization check is bounded to that tenant — *falsifier: a caller
supplies `X-Tenant-Id: other-tenant` and gains access to that tenant's resources.*

B3. **Storage-layer tenant predicate** — every DB query that touches tenant-owned tables has a `tenant_id =
?` predicate enforced at the ORM/query-builder level, not only in business logic — *falsifier: a query
omitting the tenant predicate returns rows from all tenants to the first requester.*

B4. **Tenant metadata isolation** — tenant A cannot discover the existence, name, member count, or resource
list of tenant B — *falsifier: the list-tenants API returns all tenants to any authenticated user.*

B5. **Cross-tenant sharing is explicit and bilateral** — a resource can be shared across tenants only via an
explicit cross-tenant grant that requires both tenant owners to approve — *falsifier: any tenant admin can
make a resource accessible to another tenant unilaterally.*

B6. **Tenant offboarding cascade** — on tenant deletion, all API keys, grants, delegations, and active
sessions are revoked before the tenant record is marked deleted — *falsifier: a deleted tenant's API key
continues to authenticate for hours after deletion.*

B7. **Platform-operator (super-admin) access governance** — platform operators who can access all tenants
hold a distinct, audited role; every cross-tenant access is audit-logged with reason — *falsifier: an ops
engineer reads a tenant's data with no audit trail entry because their internal role bypasses logging.*

B8. **Tenant ID non-guessability** — tenant IDs (and resource IDs) must not be sequentially guessable;
enumeration via ID brute-force is not a valid attack path — *falsifier: tenant IDs are sequential integers;
guessing IDs ±1 reveals other tenants' existence.*

---

## C. Resource Hierarchy & Permission Inheritance (7)

C1. **Hierarchy level definitions** — the concrete levels (e.g., Organization → Tenant → Project → Dataset →
Record) are enumerated; each level is or is not a valid grant anchor — *falsifier: permissions applied at a
level that cannot own grants cause undefined behavior.*

C2. **Walk-up inheritance algorithm** — the evaluator collects grants by walking from the target resource up
to the root; the algorithm is defined for every level pair — *falsifier: a deeply nested resource (5+
levels) does not inherit an organization-level admin grant because the walk stops early.*

C3. **Scope reduction on grant creation** — when assigning a role, the assigner can grant at most what they
themselves hold on that resource (no privilege escalation by assignment) — *falsifier: a project-editor
creates an owner grant on the same project for a third party.*

C4. **Resource-instance vs. resource-type scope** — a grant can be pinned to a specific resource instance;
type-level grants cover all current and future instances of that type — *falsifier: a grant intended for a
single dataset covers all datasets of the tenant because instance pinning was not enforced.*

C5. **Resource move / reparent** — moving a resource to a new parent recalculates inherited grants; existing
instance-level grants are reviewed and require explicit reconfirmation — *falsifier: resource moved from
project A to project B silently retains all project-A inherited grants.*

C6. **Maximum hierarchy depth** — the evaluator handles resources at the maximum permitted nesting depth
without timeout or stack overflow — *falsifier: a 10-level-deep resource causes a 30 s evaluation timeout
under normal load.*

C7. **Circular hierarchy guard** — if hierarchy nodes can reference parents, circular parent chains must be
detected and rejected at creation time — *falsifier: a project set as its own grandparent causes infinite
recursion in the hierarchy walker.*

---

## D. Delegation / Impersonation (9)

D1. **Explicit delegation record** — principal D can impersonate principal U only if a delegation record
(D, U, scope, expiry) exists and is active — *falsifier: a support agent can impersonate any user without
any record existing.*

D2. **Delegation scope ≤ target's own grants** — the impersonation token's permission set is the intersection
of the target's grants and the declared delegation scope; it cannot exceed either — *falsifier: a support
agent acting as a user obtains permissions the user does not hold.*

D3. **Mandatory delegation expiry** — every delegation record has a non-null, bounded expiry timestamp; open-
ended delegations are rejected at creation — *falsifier: a delegation record with `expiry = null` is
accepted.*

D4. **Delegation audit — dual identity** — every action taken under impersonation records both the real
principal and the impersonated principal in the audit log — *falsifier: the audit log records only the
impersonated identity, hiding who actually acted.*

D5. **Delegation chain depth = 1** — a delegated token cannot itself be used to create a further delegation;
the chain is capped at one hop — *falsifier: an impersonation token is accepted as input to a
create-delegation call, enabling chained impersonation.*

D6. **Instant delegation revocation** — the delegator or a tenant admin revokes a delegation; all tokens
derived from that delegation are invalidated within a bounded latency — *falsifier: delegation revoked in the
grant store but an existing derived token remains valid until its embedded expiry.*

D7. **Self-delegation guard** — a principal cannot create a delegation targeting itself with a broader scope
than it currently holds — *falsifier: a user creates a delegation to themselves with `scope = *`, obtaining
effective owner access.*

D8. **Support impersonation consent / break-glass** — support staff impersonation requires either explicit
tenant-owner consent recorded in the system or a documented break-glass procedure with dual-approval;
both paths produce audit records — *falsifier: a support ticket causes an impersonation token to be minted
with no notification or record visible to the tenant owner.*

D9. **Delegation scope not expandable post-creation** — a delegation record's scope cannot be widened after
creation; only narrowed or revoked — *falsifier: a delegation record is updated to add new resource types
after creation, silently expanding access.*

---

## E. API Key & Service Account Scoping (12)

E1. **API key is a credential, not a principal** — an API key authenticates to the owning principal;
permissions derive from that principal's grants intersected with the key's scope restriction — *falsifier: an
API key is granted permissions directly, bypassing the owning principal's grant set.*

E2. **API key scope ≤ owner's permissions** — an API key's scope restriction can only reduce, never expand,
beyond the owning principal's current effective permissions — *falsifier: an API key is created with a scope
that includes a permission the owner does not hold.*

E3. **API key tenant binding** — an API key is permanently bound to the tenant in which it was created; it
cannot authenticate in another tenant — *falsifier: an API key created in tenant A is accepted in an API
call scoped to tenant B.*

E4. **API key resource binding** — an API key can be pinned to a set of resource instances or types; requests
for anything outside that set are denied — *falsifier: an API key created with `dataset:D1:read` can also
read dataset D2 because the resource binding is not enforced.*

E5. **Service account as first-class principal** — a service account has its own stable ID, its own role
grants, and its own audit trail; it is not a shared human account — *falsifier: multiple services share a
single user's credentials, making attribution of any action impossible.*

E6. **Human-to-SA impersonation via short-lived tokens** — when a human needs to act as a service account
for debugging, they obtain a short-lived token via an impersonation call, not the SA's raw key — *falsifier:
the SA's long-lived key is distributed to engineers for ad-hoc access.*

E7. **API key rotation with grace window** — rotating a key produces a new key while the old key remains
valid for a configurable grace window; after the window the old key is revoked — *falsifier: rotation
immediately invalidates the old key, breaking live integrations with no migration path.*

E8. **API key revocation propagation latency** — after revocation, a revoked key is rejected by all nodes
within a defined SLA (e.g., < 60 s); no cache may serve the key past its revocation — *falsifier: a revoked
API key is accepted for 5+ minutes because the auth cache has no invalidation path.*

E9. **API key secret non-returnability** — the raw key value is shown only once at creation; subsequent list
or get calls return only a masked version (e.g., `sk-****1234`) — *falsifier: the GET /api-keys/{id}
endpoint returns the full raw key value.*

E10. **Service account cross-tenant guard** — a service account from tenant A cannot be granted a role in
tenant B unless cross-tenant sharing is explicitly configured per section B5 — *falsifier: tenant B's admin
endpoint accepts a foreign service-account ID and assigns it a role without any cross-tenant approval.*

E11. **API key creation requires explicit scope declaration** — creating a key with no scope restriction is
either rejected or requires an explicit `scope: full` declaration with confirmation; there is no accidental
full-scope key — *falsifier: a key created with no `scope` field defaults to the owner's full permissions
silently.*

E12. **API key enumeration is owner-scoped** — the list-api-keys endpoint returns only keys owned by the
calling principal (or, for admins, only keys within their tenant) — *falsifier: a tenant member can list API
keys created by other members of the same tenant.*

---

## F. Audit Trail (9)

F1. **Audit log immutability** — audit records cannot be modified or deleted by any principal, including
tenant admins and platform operators; only append is permitted — *falsifier: a DELETE /audit/{id} call
succeeds for a tenant admin.*

F2. **Audit on every authorization decision** — both allow and deny decisions are recorded; the audit is not
limited to denied access — *falsifier: all successful reads are unlogged; a data exfiltration is invisible.*

F3. **Audit record minimum fields** — every record contains: `timestamp` (UTC, monotonic), `principal_id`,
`real_principal_id` (if impersonation), `tenant_id`, `resource_id`, `action`, `decision`, `grant_id`
(which grant authorized the action), `ip`, `user_agent` — *falsifier: an audit record contains no
`grant_id`; it is impossible to reconstruct why an action was allowed.*

F4. **Audit log integrity / tamper evidence** — records are hash-chained or signed so that any modification
or deletion is detectable offline — *falsifier: audit records are updated directly in the DB with no
detection mechanism.*

F5. **Audit log access control** — a tenant admin can read (not write or delete) records for their own tenant
only; a platform operator can read all; no principal can write directly — *falsifier: a tenant admin can read
another tenant's audit records by supplying a different tenant filter parameter.*

F6. **Audit log retention policy** — a minimum retention period is defined (e.g., 1 year); records are not
garbage-collected before it; the policy itself is itself audit-logged if changed — *falsifier: a nightly
cleanup job deletes records older than 30 days regardless of the configured retention policy.*

F7. **Audit log export** — tenant admins can export their tenant's audit log in a standard machine-readable
format (CEF, JSON-ND); the export is itself logged — *falsifier: there is no export endpoint; tenants can
only browse logs via the UI, making SIEM integration impossible.*

F8. **Permission-change audit** — role assignments, role mutations, delegation creation/revocation, and API
key creation/revocation are all audit-logged with before-and-after state — *falsifier: a role assignment is
performed; the audit log contains no record of the grant change.*

F9. **Audit write failure handling** — if the audit write fails, the request is denied (fail-secure) and an
operational alert fires; the failure is never silently swallowed — *falsifier: the audit service is down;
all API calls continue to succeed with no log records and no alert.*

---

## G. Cross-Component Interaction Seams (11)

G1. **AuthN → AuthZ identity seam** — the principal identity carried from the authentication layer to the
authorization evaluator must be in a tamper-proof signed token; the evaluator must reject unsigned or
self-signed claims — *falsifier: the evaluator trusts a `X-Principal-Id` HTTP header injected by the
caller, not a verified JWT claim; any caller can impersonate any principal.*

G2. **Grant store → Permission evaluator consistency seam** — the evaluator reads grants from a consistent
snapshot; a grant removal must not be partially visible to concurrent evaluations (no torn reads) — *falsifier:
a role removal is half-committed; half the replicas still see the old grant and allow access that should
be denied.*

G3. **Resource hierarchy → Permission evaluator freshness seam** — the evaluator's hierarchy cache must be
invalidated when a resource is reparented; stale hierarchy causes incorrect ancestor traversal — *falsifier:
a resource reparented from project A (where the caller has no access) to project B (where they do) is
evaluated against the old hierarchy and incorrectly denied—or vice versa.*

G4. **Delegation record → Token issuance consistency seam** — the token issuer verifies the delegation
record with strong-consistent read before minting an impersonation token; a stale replica showing a deleted
record must not be accepted — *falsifier: delegation is revoked; the token issuer reads a replica with 5 s
lag and mints a new impersonation token after revocation.*

G5. **API key → Principal resolution cache invalidation seam** — every API request resolves the raw key to
(principal, scope); revocation must invalidate this cache entry synchronously or within the defined SLA —
*falsifier: a key is revoked; the resolution cache still maps it to a valid principal for the next 10 min.*

G6. **Permission evaluator → Audit writer atomicity seam** — the authorization decision and the matched
grant ID must be passed atomically to the audit writer; if the write fails the request is blocked
(fail-secure), not silently allowed — *falsifier: audit writer unavailable; the permission evaluator returns
allow and the request succeeds with no audit record.*

G7. **Tenant offboarding → Grant/key cleanup ordering seam** — the offboarding workflow must revoke all keys
and sessions before marking the tenant deleted; the ordering is enforced, not best-effort — *falsifier:
tenant record is marked deleted first; in the window before cleanup, the tenant's API keys still
authenticate.*

G8. **Role mutation → Active session invalidation seam** — when a role's permission set changes, principals
holding active sessions with that role have their effective permissions refreshed within a bounded
window (or are forced to re-authenticate) — *falsifier: a role's write permission is removed; a session
holder continues to write for the rest of their session lifetime with no re-evaluation.*

G9. **Resource creation → Inheritance propagation seam** — a newly created resource must have its inherited
grants fully applied before the creation response is returned to the caller; no window where the resource
is accessible to its owner but not to principals who should inherit access — *falsifier: a resource is
created; the creator can access it immediately but a parent-level admin cannot for 2 s while async
inheritance propagates.*

G10. **Impersonation token → Audit dual-identity seam** — the real principal ID must be embedded in the
impersonation token at issuance time (or looked up from the delegation record at request time) so the audit
writer always has both actor IDs available — *falsifier: the impersonation token carries only the
impersonated principal's ID; the audit log records that identity alone, hiding the real actor.*

G11. **Cross-tenant grant → Both-tenant audit seam** — when a cross-tenant grant is used, the audit record
must appear in both the source and the target tenant's audit logs — *falsifier: a principal from tenant A
accesses a shared resource in tenant B; only tenant B's audit log has a record; tenant A's admin has no
visibility.*

---

## H. Global Invariants (7)

H1. **Tenant confinement** — for any authorization evaluation, the resource set considered is always bounded
to the tenant derived from the authenticated token; no grant from another tenant can influence the outcome —
*falsifier: a grant in tenant B matches a permission check for a resource in tenant A because the evaluator
queries all grants across tenants.*

H2. **Privilege non-escalation** — no finite sequence of valid API calls allows a principal to acquire
effective permissions exceeding those explicitly granted to it — *falsifier: a principal with
`role:grant-viewer` can chain two calls to assign `role:owner` to themselves.*

H3. **Deny-by-default** — an absent grant means deny; the evaluator never falls through to allow on an
unmatched resource or action — *falsifier: a new resource type is deployed; before any grants are defined,
any authenticated principal can access it.*

H4. **Audit completeness** — no code path that evaluates a permission decision can complete without producing
an audit record; this is enforced architecturally (the evaluator returns a typed decision object that the
caller must pass to the audit writer before acting) — *falsifier: a code path skips the decision object and
acts directly on a local boolean; that action is never logged.*

H5. **Least-privilege on grant creation** — the maximum permission a principal can grant is bounded by what
they themselves hold at the same or broader scope; this check is in the grant-creation handler, not only
in documentation — *falsifier: a viewer-role holder can call `create-grant` with `role=owner` and it
succeeds.*

H6. **Grant persistence and traceability** — every grant has a creation timestamp, creator principal ID, and
reason; grants do not appear or disappear without a corresponding audit record — *falsifier: a grant
disappears from the grant store with no revocation record in the audit log.*

H7. **Revocation completeness** — revoking a principal's access (role removal, key revocation, delegation
revocation) terminates all derived permissions and active tokens within the SLA; no derived credential
outlives its source grant — *falsifier: a service-account role is removed; the SA's existing JWT, minted
before the removal, continues to work until its `exp` claim.*

---

## I. Edge / Boundary Cases (11)

I1. **Empty grant set** — a freshly created principal with no grants is denied everything, including resource
enumeration — *falsifier: a newly invited user can list all projects before any role is assigned.*

I2. **Principal deactivation** — a deactivated principal is denied all access immediately; their grants are
preserved for audit but are inactive — *falsifier: a deactivated user's API key still authenticates after
account suspension.*

I3. **Grant expiry exactness** — a time-bound grant expires at the exact declared timestamp; in-flight
requests evaluated a millisecond after expiry are denied — *falsifier: a grant expired 10 s ago; a client
session that started before expiry continues to act on it.*

I4. **Role with zero permissions** — assigning a role whose permission set is empty is a no-op; the principal
gains no access and no error is raised — *falsifier: assigning an empty role throws an unhandled exception or
grants unexpected default access.*

I5. **Permission on non-existent resource** — granting permission on a resource ID that does not yet exist
either fails or is held as a pending grant that activates only when a resource with that exact ID and type
is created — *falsifier: a pending grant on resource ID `X` activates when any resource with ID `X` is
created, regardless of type.*

I6. **Concurrent grant modification** — two simultaneous grant assignments to the same principal both persist
without either overwriting the other — *falsifier: second concurrent write silently overwrites the first,
leaving the principal with only one of the two intended grants.*

I7. **Token clock skew tolerance** — expiry checks accept a small defined clock-skew tolerance (e.g., 30 s)
but reject tokens beyond it; the tolerance is bounded and documented — *falsifier: a validator with a 5-min
fast clock rejects valid tokens; or a 10-min slow clock accepts tokens that expired long ago.*

I8. **Role with circular inclusion** — if roles can include other roles, a circular dependency is detected
at role-definition time and rejected — *falsifier: role A includes role B includes role A; the evaluator
enters an infinite loop.*

I9. **Tenant with no members** — an empty tenant is not accessible to any platform operator without an
explicit break-glass grant — *falsifier: a tenant with zero members is readable by any platform operator
because the "no members" state is treated as unprotected.*

I10. **Maximum resource hierarchy depth enforcement** — the system rejects resource creation that would
exceed the defined maximum nesting depth — *falsifier: a client creates a 50-level-deep hierarchy; the
evaluator times out or stack-overflows on every request to that branch.*

I11. **Bulk grant operation atomicity** — a batch grant-assignment either fully succeeds or fully rolls back;
partial application is not permitted — *falsifier: a bulk role-assignment partially applies (7 of 10
principals get the role); the operation returns success; 3 principals are silently skipped.*

---

## J. Silent Failure Modes (6)

J1. **Grant-check short-circuit on prefix match** — a resource ID evaluator that matches on a string prefix
grants access to the wrong resource when two resources share a prefix — *falsifier: resources `proj:A` and
`proj:AB` are created; a grant for `proj:A` matches `proj:AB`.*

J2. **Internal APIs bypassing tenant check** — internal service-to-service calls omit the tenant context
because they are "trusted"; a compromised internal service can access any tenant's data — *falsifier: an
internal endpoint that fetches resources by ID does not enforce `tenant_id`; calling it with any valid
resource ID returns the data.*

J3. **Delegation scope not enforced in downstream services** — the impersonation token carries a scope
restriction claim, but a downstream microservice does not read that claim and treats the token as
full-permission — *falsifier: a delegation scoped to `dataset:read` allows write access when the token is
used against a microservice that ignores the scope claim.*

J4. **Default-allow on unrecognized action** — when the evaluator encounters an action string it does not
recognize (new feature not yet registered), it falls through to allow instead of deny — *falsifier: a new
action type is deployed; a principal with no grants for it gains access because the evaluator treats unknown
actions as unconstrained.*

J5. **Permission evaluator reached via unauthenticated path** — a code path skips authentication and passes
a nil or anonymous principal to the evaluator; if the evaluator has no nil-check it may apply grants
intended for a wildcard subject — *falsifier: an unauthenticated request with no `Authorization` header
reaches the evaluator and is granted access to public-wildcard-scoped resources.*

J6. **Audit log write after response sent** — the audit record is written asynchronously after the HTTP
response is dispatched; a crash between dispatch and write produces an unlogged allowed action — *falsifier:
kill the process immediately after a successful write response; the audit log has no record of the action.*

---

## K. Scope Boundaries (5)

K1. **Authentication mechanism** — the specific credential-verification mechanism (OIDC, SAML, password
hash, WebAuthn) is out of scope; the AuthZ layer consumes a verified identity claim — *safely out because
AuthZ only requires a signed principal-identity assertion. Pulled back in if the AuthZ layer also issues
tokens or performs credential validation directly.*

K2. **Rate limiting / abuse prevention** — per-principal or per-tenant rate limits are an operational
control, not an access-control rule — *safely out. Pulled back in if rate limits are used as a security
boundary (e.g., lockout after N consecutive denied checks gates access itself).*

K3. **Data encryption at rest / customer-managed keys** — storage-level encryption and key management are
separate from logical access control — *safely out. Pulled back in if customer-managed keys are the
access-control primitive (key possession = data access), making the key scope equivalent to a grant.*

K4. **Frontend / UI access control** — hiding or disabling UI elements based on role is a UX concern, not a
security control — *safely out. Pulled back in if the UI is the only enforcement point for a permission
(no API-layer check exists), at which point it becomes an in-scope security gap.*

K5. **Billing / subscription entitlements** — whether a tenant may use a feature based on their subscription
plan is a separate entitlement layer — *safely out. Pulled back in if plan entitlements gate access to
specific resource types and the entitlement check must compose with the permission-grant check in the same
evaluation chain.*

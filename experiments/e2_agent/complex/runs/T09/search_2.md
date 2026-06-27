# T09 — Search pass 2 (gap analysis against D1)

D1 is dense and well-formed. The items below are only what it is still missing or gets wrong — no restatements.

---

## Missing cross-component interaction seams (Dep gaps)

**S2-Dep-A. Grant expiry → active-session re-evaluation**
Time-bound grant expires while a principal holds an active session whose permission set was cached at session start. Dep8 covers role-mutation → session refresh; nothing covers grant-expiry → session refresh.
*Falsifier: a time-bound grant for U expires; U's existing session continues to succeed for the rest of its lifetime because the session layer only re-evaluates on role mutations, not on per-grant expiry.*

**S2-Dep-B. API key scope restriction → authoritative key-store fetch (not self-asserted token claim)**
V46/V47 state what the scope rules must be; no Dep seam specifies that the key's declared scope restriction must be retrieved from the authoritative key store at evaluation time rather than trusted as a self-asserted JWT claim.
*Falsifier: the key scope is embedded as an unsigned or user-controlled JWT field; an attacker presents a key credential with a forged `scope=owner` claim; the evaluator trusts the claim without verifying against the key store.*

**S2-Dep-C. Delegation record creation → delegator's own effective-permission check**
V13 bounds grant creation to "what the grantor holds" and is scoped to the "grant-creation handler." Delegation record creation is a distinct operation; V43 only covers self-delegation with an overscoped claim. The general case — a principal creates a delegation whose declared scope exceeds what that principal can actually authorize — is unguarded at record-creation time.
*Falsifier: U (project-viewer) creates a delegation to support agent S declaring `scope=project-owner`; record creation succeeds because no check fires against U's effective permissions; at token issuance V38 intersects with S's grants, not U's; if S holds broad grants, the resulting token grants owner-level access that U never had the right to delegate.*

**S2-Dep-D. Grant creation → read-your-writes consistency**
Dep2 covers the grant-removal direction (partial removal must not be visible). The creation direction is absent: a freshly created grant may not yet be visible on the replica the evaluator reads from.
*Falsifier: admin creates a grant for U; U immediately makes an API call; the evaluator reads a lagging replica and denies access, even though the grant now exists in the authoritative store.*

**S2-Dep-E. Audit log read / export → token-derived tenant isolation**
V62 carries the criterion (tenant admin can read only their own tenant's records). No Dep seam specifies that the audit-read and audit-export endpoints derive tenant context from the authenticated token rather than from a caller-supplied filter parameter — unlike every other data-read path in D1.
*Falsifier: tenant admin calls `GET /audit?tenant_id=other-tenant`; the endpoint uses the supplied parameter rather than the token-derived context and returns another tenant's records.*

**S2-Dep-F. API key authentication → live principal grant lookup**
V46 specifies that key effective permissions = principal's current grants ∩ key's declared scope. No Dep seam requires the key-authentication flow to perform a live grant lookup for the owning principal (rather than relying solely on the key's embedded scope claim).
*Falsifier: the key-auth flow validates the key credential and uses the key's declared scope directly as effective permissions without intersecting with the principal's current grants; after the principal's role is revoked, their API key continues to operate with the full originally-declared scope.*

**S2-Dep-G. Permission evaluator internal API → caller authentication**
All the Dep seams describe what the evaluator does with its inputs; none specify that the evaluator's internal API is itself authenticated (i.e., only authorized callers can submit authorization requests).
*Falsifier: an SSRF or misconfigured internal firewall allows an arbitrary service to POST to the evaluator with crafted `principal_id` and `resource` fields; the evaluator returns a legitimate allow decision that is then acted upon.*

**S2-Dep-H. IdP sub-claim → internal stable principal ID translation**
Dep1 requires that principal identity arrive via tamper-proof token claims. D1-D1 requires stable, immutable, non-reused principal IDs. The seam between the identity provider's subject claim and the internal principal registry (where the stable ID lives) is not defined: the mapping, its mutability, and what happens when an IdP changes a user's `sub` are absent.
*Falsifier: a user migrates to a new IdP account; their `sub` claim changes; the new claim maps to no existing principal ID and either creates a fresh principal (losing all grants) or, worse, coincidentally matches a different principal's ID (inheriting that principal's grants).*

---

## Inconsistency in existing seam

**S2-Inc-A. Dep7 omits delegation records from the offboarding cascade**
V24 (criterion) explicitly lists "API keys, grants, delegations, and active sessions" as what must be revoked before tenant deletion. Dep7 (the enforcement seam) lists only "keys, sessions, and grants" — delegation records are absent from the ordered cascade, creating a gap between the stated invariant and the seam that enforces it.
*Falsifier: tenant is offboarded; Dep7's cascade revokes keys+sessions+grants but leaves active delegation records standing; a support agent with a pre-existing delegation record requests a new impersonation token for a now-deleted tenant's user and succeeds.*

---

## Missing edge / boundary cases

**S2-Edge-A. Grant on deleted resource → dangling grant re-applies on resource re-creation**
V16 covers the pre-creation direction (grant before the resource exists). The inverse is absent: when a resource is deleted, grants targeting it should be revoked or tombstoned; otherwise re-creating a resource with the same ID silently inherits the old grants.
*Falsifier: `dataset:D1` is deleted without cleaning up its grants; `dataset:D1` is re-created by a different owner; a principal who held a grant on the old object silently has access to the new one without any explicit grant being made.*

**S2-Edge-B. Impersonation targeting a deactivated principal**
V2 says a deactivated principal's grants are "preserved for audit but are inactive." V37 checks for an active delegation record; V38 computes intersection with "the target's current grants." It is not specified whether the evaluator treats a deactivated target's grant set as empty or reads the preserved-but-inactive grants. The two components' semantics need to be explicitly reconciled.
*Falsifier: user U is deactivated; a pre-existing delegation for `S impersonates U` remains active; if the evaluator reads U's preserved (not truly zeroed) grants, S's impersonation token carries real effective permissions, accessing U's resources despite U being deactivated.*

**S2-Edge-C. Multiple concurrent delegation records for the same delegator → target pair**
D1 does not define whether more than one active delegation record for the same (delegator, target) pair is allowed, nor how the token issuer resolves the conflict if multiple records exist.
*Falsifier: two admins concurrently create delegations (A→B, scope=read) and (A→B, scope=write); both succeed; the token issuer picks the wider record or unions the scopes, giving B write access from a flow that should have been bounded to read.*

**S2-Edge-D. Role deleted entirely while active grants reference it by version**
V5 says grants reference a specific role version. D2 covers mutability and versioned changelog. Neither specifies what happens when a custom role is deleted in its entirety: whether referencing grants are also revoked, left as empty-permission grants, or cause evaluation errors.
*Falsifier: a custom role is deleted; a grant referencing a specific version of that role is evaluated; the evaluator throws an unhandled exception that defaults to allow, or silently treats the grant as full-permission rather than empty.*

**S2-Edge-E. Tenant bootstrap: who grants the first admin?**
V72 covers zero-member tenants requiring break-glass for operator access. But the tenant-creation flow itself has a bootstrapping problem: before any member holds a grant, there is no authorized grantor inside the tenant. The mechanism by which the very first admin grant is created — and who is authorized to do it — is unspecified, creating either an implicit platform-operator bypass or an undefined state.
*Falsifier: a new tenant is provisioned; the tenant has no members; the only path to add the first admin requires a platform-operator action that is either unaudited or operates outside the normal grant-creation handler, violating V13 and V25.*

---

## Ambiguous / wrong scope in existing criteria

**S2-Scope-A. V12 deny-wins rule does not resolve deny-at-ancestor vs allow-at-descendant**
V12 states: "An explicit deny at any resource level overrides an allow at the same or any ancestor level." This wording covers deny defeating allows at the SAME or HIGHER (ancestor) levels. It does not specify whether a deny placed on a PARENT overrides an explicit allow placed directly on a CHILD resource. The two complementary directions of the deny-wins rule are present for only one direction.
*Falsifier: deny is set on `project:P` for principal U; an explicit allow is granted directly on `dataset:D` (child of P) for U; because V12 does not say deny-at-parent beats allow-at-child, the allow wins; U gains access to D despite the project-level deny.*

---

## Missing component-level rule

**S2-Comp-A. Service account lifecycle independence from creating human principal**
D7 defines service accounts as first-class principals with their own IDs and key management. No rule specifies that a service account's lifecycle is independent of any human who created it — nor what happens during offboarding of the creating engineer.
*Falsifier: engineer E creates service account SA and owns the underlying provisioning record; E is offboarded; the offboarding workflow treats SA as a dependent artifact and deactivates it; a production service loses its identity and goes down.*

---

## Summary count

| Type | Count |
|------|-------|
| Missing Dep seams | 8 (S2-Dep-A through S2-Dep-H) |
| Seam inconsistency | 1 (S2-Inc-A) |
| Missing edge / boundary cases | 5 (S2-Edge-A through S2-Edge-E) |
| Wrong / incomplete scope in existing criterion | 1 (S2-Scope-A) |
| Missing component rule | 1 (S2-Comp-A) |
| **Total new holes** | **16** |

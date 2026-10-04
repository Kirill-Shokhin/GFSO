-- GFSO — the canon's formal spine (docs/applied_gfso_v4_en.md), checked in Lean 4 (§20.4).
--
-- The tiers (§20.11; a stack, not a generation order) and their modules:
--   Tier 0  AXIOMS        A1, A2                                  (definitional — see Postulates)
--   Tier 1  PRIMITIVES    T, D, Dep, Del (V derived)              Ontology
--   Tier 2  VALIDATION    L, ⊗, Thm 1                             Binarity · AndUniqueness · Compositionality
--   Tier 3  FAILURE MODES FM-1..6                                 FailureModes
--     3b    TIME          the operational axis (derived; CA2 discharged)   Time
--   Tier 4  STANDARDS     STD-1..4, the nine CHECKs (1, 1b, 2–8), Syntactic/Semantic/Pragmatic      Standards
--   Tier 5  PROTOCOL      Signals (12), States (11), Inv-1..8     Protocol · Fsm · FsmCanon · LogLanguage* (Forcing: a frozen table, no canon claim)
--   Tier 6  MEASUREMENT   Q (5), Thm 10, Thm 11                   Metrics
--   Tier 7  THEORY MODEL  S/Ŝ, Contact, Lemma 1, d1–d6            TheoryModel
--     7b    LINKS         the five links                          Links
--   beside the tiers: Grading (⪰_dom, §19.6)
--
-- CLOSURE: `Postulates` lists every postulate and how it is carried; `check_axioms.lean` prints the
-- footprints and `audit_env.lean` reports what else the environment holds, `formal/scripts/check_closure.sh`
-- being the guard (§20.4, §20.5).
import GFSO.Ontology
import GFSO.Compositionality
import GFSO.Binarity
import GFSO.AndUniqueness
import GFSO.FailureModes
import GFSO.Time
import GFSO.Standards
import GFSO.Fsm
import GFSO.FsmCanon
import GFSO.Forcing
import GFSO.LogLanguage
import GFSO.LogLanguageAgrees
import GFSO.LogLanguageLoads
import GFSO.LogLanguageLoadsNoOwner
import GFSO.LogLanguageLoadsExecutor
import GFSO.LogLanguageLoadsIssuer
import GFSO.LogLanguageReopen
import GFSO.LogLanguageLapse
import GFSO.Protocol
import GFSO.Metrics
import GFSO.Grading
import GFSO.TheoryModel
import GFSO.Links
import GFSO.Postulates

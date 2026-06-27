# BLIND JUDGE VERDICT — T08 / candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "D1. Lexer — converts raw source bytes into a typed token stream with source locations" | trivia rule via V7 (comments consumed) |
| D2 | D | — | COVERED | "D2. Parser — converts token stream into a fully-typed, location-annotated AST" | |
| D3 | D | — | COVERED | "V54. Type representation schema: distinct nodes and equality rules ... Every type in the language ... is represented as a distinct node in the type language" | AST/type data model defined (+V16 distinct AST node kinds); fold-credit per ref appendix |
| D4 | D | — | COVERED | "D3. Name / Scope Resolver — resolves every identifier-use to a unique declaration; builds and closes the symbol table; enforces scoping rules" | |
| D5 | D | — | COVERED | "D4. Type Checker — annotates every expression node with a concrete type; enforces all type rules; produces the typed AST" | + V26 missing-return-on-a-path |
| D6 | D | — | COVERED | "D5. IR Lowering — translates the typed AST into a typed intermediate representation with explicit control flow" | |
| D7 | D | — | COVERED | "D6. Code Generator — translates IR into target output (assembly / bytecode)" | |
| Dep1 | Dep | FM-1 | COVERED | "Dep1. Lexer → Parser · byte-complete token stream ... parser silently accepts a shorter token stream, producing a different program with no error" | + V2 maximal-munch |
| Dep2 | Dep | FM-1 | COVERED | "Dep4. Parser → Name Resolver · declaration vs use distinction — The AST distinguishes declaration nodes from use nodes" | AST-shape contract |
| Dep3 | Dep | FM-1 | COVERED | "V34. Every AST construct has a defined IR translation ... no construct falls through to 'unimplemented'" | end-to-end construct-coverage chain (+V40 codegen) |
| Dep4 | Dep | FM-1 | COVERED | "Dep5. Name Resolver → Type Checker · resolution complete before type checking — The type checker is not called until resolution has completed and every identifier-use node has a valid declaration link" | |
| Dep5 | Dep | FM-1, FM-2 | COVERED | "Dep3. Parser → Name Resolver · scope-boundary fidelity ... the set of such nodes exactly matches the language's scoping rules" | one scope model the resolver builds and the checker consumes via resolved links (V21); ref appendix Dep4/Dep5: do not double-hole |
| Dep6 | Dep | FM-1 | COVERED | "Dep7. Type Checker → IR Lowering · no unresolved type variables — The typed AST passed to IR lowering has no nodes with an 'inferred but not yet resolved' type marker" | type-directed lowering needs every node typed |
| Dep7 | Dep | FM-1 | COVERED | "Dep9. IR Lowering → Code Generator · use-def dominance — In the IR's CFG, every use of a value is dominated by its definition" | IR well-formedness (+Dep10 call-site, +V38 terminators) |
| Dep8 | Dep | FM-1 | COVERED | "V39. Error-typed AST nodes produce no IR instructions" | lowering gated on typing succeeding (+V50 no output on error) |
| Dep9 | Dep | FM-1 | COVERED | "V15. Every AST node produced by the parser carries the source location of its primary token" | per-stage span propagation (+cDep2 lexer position ordering; full chain in V44) |
| Dep10 | Dep | FM-1, FM-2 | COVERED | "Dep11. ... error-sentinel propagation — The error sentinel type is recognized by IR lowering (suppresses instruction emission)" | poison/error-node handoff (+V14 parser synchronize-and-continue) |
| Dep11 | Dep | FM-1, FM-2 | COVERED | "V53. Unique symbol identity throughout the pipeline — Each declared symbol ... has a globally unique ID from name resolution through code generation; no two declarations share an ID" | decl ↔ one IR symbol (+Dep14 symbol identity handoff) |
| Dep12 | Dep | FM-1, FM-2 | PARTIAL | "Dep8. Type Checker → IR Lowering · explicit coercions in typed AST — Every implicit numeric widening or coercion applied by the type checker is represented as an explicit coerce node ... IR lowering translates it to an explicit IR instruction" | MISSING leg: total source-type→IR-type mapping (every checker-legal type has a defined IR type) and cross-boundary subtyping/assignability agreement; only the coercion-conversion leg is asserted |
| V-I1 | V | FM-1 | COVERED | "V21. ... every identifier-use AST node carries an unambiguous, non-null reference to its correct declaration" | |
| V-I2 | V | FM-1 | COVERED | "V23. ... every expression node carries a concrete type; no 'pending' or 'unknown' markers remain except the error sentinel" | |
| V-I3 | V | FM-1, FM-2 | COVERED | "V37. Every IR operand has explicit non-null type ... every operand has a non-null type field" | IR well-typed |
| V-I4 | V | FM-1 | COVERED | "V44. Source location continuity throughout the pipeline — Source locations flow from token → AST node → IR instruction → diagnostic message without any stage setting a location to null" | |
| V-I5 | V | FM-4 | COVERED | "V45. ... the type invariants established by the type checker are preserved in the IR and generated code" | + V46 meaning-preservation |
| V-I6 | V | FM-1 | COVERED | "V40. Every IR instruction has a defined code-gen translation; no instruction falls through to 'unimplemented'" | totality over accepted language (+V72) |
| V-I7 | V | FM-1 | COVERED | "V52. Determinism: identical source → identical output ... the pipeline produces bit-identical output across runs" | + V74 stable diagnostic order |
| V-I8 | V | FM-4 | COVERED | "V50. No output artifact produced when any error exists" | + V51 no-discard, V49 accumulation, V48 ordering |
| V-E1 | V | FM-3 | COVERED | "V19. ... mutually recursive `f` and `g` with `f` defined first → successful compilation" | + V61 mutual struct, V31 self-containing |
| V-E2 | V | FM-3, FM-2 | COVERED | "V69. ... resolves all struct and type-alias definitions ... in a first pass before type-checking any function body" | decl-collection pre-pass; resolver pre-scan V19 + checker first-pass agree |
| V-E3 | V | FM-3 | COVERED | "V17. Two declarations of the same name in the same scope ... produce a 'redeclaration' error; shadowing in a child scope is allowed (or forbidden) per the language spec, consistently" | both legs: same-scope redecl error + shadowing distinguished |
| V-E4 | V | FM-3 | COVERED | "V57. Empty and whitespace-only source → zero errors, empty valid module" | |
| V-E5 | V | FM-3 | COVERED | "V55. Deep nesting (expressions): clean outcome or diagnostic; no crash" | + V73 control-structure nesting |
| V-E6 | V | FM-3 | COVERED | "V9. Unterminated string → diagnostic" | + V7 unterminated comment, V4 bad escape, V14 syntax recovery |
| V-E7 | V | FM-3 | COVERED | "V5. Numeric literal overflow → diagnostic ... no silent truncation or wrap" | |
| V-E8 | V | FM-3, FM-2 | COVERED | "V59. Source encoding contract ... The lexer enforces a single declared source encoding (e.g., UTF-8); every input byte sequence is classified as a valid codepoint" | "handle Unicode/UTF-8 source" credit phrase |
| V-E9 | V | FM-3 | COVERED | "V58. Zero-field struct → defined behavior" | empty-construct boundary |
| V-F1 | V | FM-4 | COVERED | "V24. ... operations on the sentinel propagate it without emitting additional errors; one root-cause defect produces O(1) diagnostics, not O(n)" | + V68 dedup |
| V-F2 | V | FM-3 | COVERED | "D8. IR Verifier — standalone checker that validates all IR well-formedness rules independently of the front-end; runs after lowering and before code generation" | independent IR-verifier backstop (+Dep13) |
| V-F3 | V | FM-1 | COVERED | "V13. ... every syntactic construct ... maps to a distinct typed AST node; no construct falls through to a generic catch-all" | exhaustiveness guard / no permissive default |
| V-F4 | V | FM-4 | COVERED | "V10. Invalid character → diagnostic and resume ... the lexer resumes on the next character" | consume-or-error-and-advance (progress on bad char) |
| N1 | N | FM-1 | COVERED | "N1. Optimization passes — constant folding, dead-code elimination, inlining, loop transformations belong to the middle-end optimizer, not the front-end" | |
| N2 | N | FM-1 | COVERED | "N5. Target-specific ABI detail — full register-assignment rules per type on specific ISAs are out of scope" | full back-end/regalloc/ABI |
| N3 | N | FM-1 | COVERED | "N8. Separate compilation / module system — importing symbols from other compiled units is out of scope; single-file or single-module compilation is assumed" | + N2 linking |
| N4 | N | FM-1 | COVERED | "N7. Macro / metaprogramming system — macro expansion, compile-time code generation, and template instantiation are out of scope" | |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D1 | 4 | 3 | V1 token taxonomy; V3 keyword priority; V6 EOF sentinel |
| D2 | 3 | 2 | V11 grammar unambiguous; V12 operator precedence |
| D3 | 2 | 1 | V16 short-circuit distinct from bitwise AST nodes |
| D4 | 2 | 1 | V20 built-in names in outermost scope |
| D5 | 13 | 12 | V25 operator rules; V26 missing return; V27 void return; V28 call arity; V29 non-callable; V30 field access; V32 assignment assignable; V33 condition bool; V62 array rules; V63 pointer rules; V64 lvalue; V66 dead-code-after-return |
| D6 | 4 | 3 | V35 short-circuit lowering; V36 unique temporaries; Dep16 struct field layout |
| D7 | 5 | 4 | V41 calling convention; V42 stack frame slots; V43 assembler-parseable; V71 external import decls |
| Dep1 | 3 | 2 | V2 maximal munch; V8 byte completeness |
| Dep2 | 2 | 1 | Dep15 type-annotation AST nodes |
| Dep4 | 2 | 1 | Dep6 symbol-table completeness |
| Dep7 | 3 | 2 | Dep10 call-site/callee agreement; V38 CFG terminator coverage |
| Dep9 | 2 | 1 | Dep2 monotonic position ordering |
| Dep10 | 2 | 1 | V14 parser error recovery |
| Dep11 | 3 | 2 | Dep12 symbol-name consistency; Dep14 symbol identity handoff |
| Dep12 | 2 | 1 | V65 numeric assignability/widening relation |
| V-I5 | 2 | 1 | V46 meaning preservation |
| V-I6 | 2 | 1 | V72 CFG traversal visits every block once |
| V-I7 | 2 | 1 | V74 diagnostic output ordered by source location |
| V-I8 | 5 | 4 | V48 phase ordering; V49 error accumulation; V51 no-discard; V67 severity taxonomy |
| V-E1 | 5 | 4 | V31 directly self-containing struct; V61 mutual struct infinite-size; V60 forward user-type ref; V70 pointer-recursive layout terminates |
| V-E2 | 2 | 1 | V18 use-before-declaration error |
| V-E3 | 2 | 1 | V22 shadow of built-in → defined behavior |
| V-E5 | 2 | 1 | V73 deep nesting (control structures) |
| V-E6 | 4 | 3 | V4 string escape diagnostic; V7 comment/unterminated-comment; V56 EOF-unclosed-delimiter |
| V-F1 | 2 | 1 | V68 diagnostic deduplication |
| V-F2 | 2 | 1 | Dep13 verified-IR guarantee |
| N3 | 2 | 1 | N2 linking |
| **TOTAL** | | **57** | |

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| "D7. Driver (orchestration layer) — sequences all phases in order, threads representations between them, accumulates all diagnostics, and suppresses output artifacts on error" | UNMATCHED — human review |
| "V47. Argument evaluation order specified and enforced ... IR lowering emits call arguments in that order consistently" | UNMATCHED — human review |
| "N3. Runtime library implementation — the implementation of built-in functions (e.g., `print`, `malloc`) is out of scope" | UNMATCHED — human review |
| "N4. Garbage collector implementation — the GC algorithm and collector are out of scope" | UNMATCHED — human review |
| "N6. Debug information format — DWARF, PDB, and other debug-info wire formats are out of scope" | UNMATCHED — human review |
| "N9. Mutability / const distinction ... This decomposition treats all declared variables as mutable" | UNMATCHED — human review |
| "N10. Global variable initializer ordering ... assumes constant-only global initializers" | UNMATCHED — human review |
| "N11. Generic / parametric types ... out of scope for the stated 'small statically-typed language'" | UNMATCHED — human review |

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/7   Dep = 11/12   V = 21/21   N = 4/4
  by FM tag:     FM-1 = 22/23   FM-2 = 6/7   FM-3 = 10/10   FM-4 = 4/4   FM-5 = n/a   FM-6 = n/a   FM-7 = n/a   (FM-5/6/7 n/a on static tasks)
  PARTIAL counts: D = 0   Dep = 1   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 57
  unmatched candidate points (human-review flag):    total = 8
```

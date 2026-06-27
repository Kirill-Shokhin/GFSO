# FROZEN BLIND JUDGE — verdict for T08 candidate

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note (missing leg / which candidate points) |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Lexer — converts raw source bytes into a typed token stream with source locations" | trivia rule via V7 "Line and block comments are silently consumed" |
| D2 | D | — | COVERED | "Parser — converts token stream into a fully-typed, location-annotated AST" | |
| D3 | D | — | COVERED | V54 "Every type ... is represented as a distinct node in the type language; type identity and structural equality rules are explicitly defined" | data model folded into parser/type-rep (also V13 typed AST node) |
| D4 | D | — | COVERED | "Name / Scope Resolver — resolves every identifier-use to a unique declaration; builds and closes the symbol table; enforces scoping rules" | |
| D5 | D | — | COVERED | "Type Checker — annotates every expression node with a concrete type; enforces all type rules; produces the typed AST" | return-path via V26 "a non-void function with a path that has no return produces a 'missing return' error" |
| D6 | D | — | COVERED | "IR Lowering — translates the typed AST into a typed intermediate representation with explicit control flow" | |
| D7 | D | — | COVERED | "Code Generator — translates IR into target output (assembly / bytecode)" | |
| Dep1 | Dep | FM-1 | COVERED | Dep1 "Lexer → Parser · byte-complete token stream ... parser silently accepts a shorter token stream, producing a different program with no error" | maximal-munch via V2; same pair, token-stream artifact, mis-tokenization → wrong parse |
| Dep2 | Dep | FM-1 | COVERED | Dep4 "The AST distinguishes declaration nodes from use nodes ... Breaks if absent: use-before-decl errors are either missed or spuriously emitted" | AST-shape contract parser→resolver (also Dep3 scope-boundary nodes) |
| Dep3 | Dep | FM-1 | COVERED | V34 "Every expression and statement form in the language has a lowering rule; no construct falls through to 'unimplemented'" | every syntactic form lowered/codegen'd, not dropped |
| Dep4 | Dep | FM-1 | COVERED | Dep5 "the type checker is not called until resolution has completed and every identifier-use node has a valid declaration link ... type checker performs lookups against an incomplete symbol table and produces wrong types silently" | |
| Dep5 | Dep | FM-1, FM-2 | NOT-COVERED | | candidate's resolution→typecheck points (Dep5/Dep6) assert binding completeness (ref Dep4); no statement that resolver and checker share ONE scope/shadowing model — the scope-agreement seam is absent. Per Appendix Dep4-vs-Dep5: Dep4 credited, this is the single (not double) hole |
| Dep6 | Dep | FM-1 | COVERED | Dep7 "The typed AST passed to IR lowering has no nodes with an 'inferred but not yet resolved' type marker ... IR lowering emits instructions with null or wrong types" | every node typed before lowering |
| Dep7 | Dep | FM-1 | COVERED | Dep9 "every use of a value is dominated by its definition; code generation assumes this invariant without re-checking ... code gen reads an undefined or stale register/slot" | IR well-formedness for codegen (also Dep10 signature agreement, V38 CFG terminators) |
| Dep8 | Dep | FM-1 | COVERED | V39 "Any AST node annotated with the error sentinel must not produce IR instructions" | lowering gated on typing succeeding (no IR for an errored node) |
| Dep9 | Dep | FM-1 | COVERED | V15 "Every AST node produced by the parser carries the source location of its primary token" | per-edge span propagation (also Dep2 lexer-position ordering) |
| Dep10 | Dep | FM-1, FM-2 | COVERED | Dep11 "The error sentinel type is recognized by IR lowering (suppresses instruction emission) and must not cause code gen to encounter a missing operand" | poison/error-node handoff the consumer skips (also V14 synchronize/continue) |
| Dep11 | Dep | FM-1, FM-2 | COVERED | V53 "Each declared symbol ... has a globally unique ID from name resolution through code generation; no two declarations share an ID" | decl ↔ one IR symbol (also Dep12 codegen reads names from symbol table) |
| Dep12 | Dep | FM-1, FM-2 | COVERED | Dep8 "Every implicit numeric widening or coercion applied by the type checker is represented as an explicit coerce node in the typed AST; IR lowering translates it to an explicit IR instruction" | checker-accepted coercions → legal explicit IR conversions (also V45 no casts absent from source) |
| V-I1 | V | FM-1 | COVERED | V21 "after resolution, every identifier-use AST node carries an unambiguous, non-null reference to its correct declaration" | every name bound (or errored) before typing |
| V-I2 | V | FM-1 | COVERED | V23 "After type checking, every expression node carries a concrete type; no 'pending' or 'unknown' markers remain except the error sentinel" | |
| V-I3 | V | FM-1, FM-2 | COVERED | V37 "Every value and operand in the IR carries an explicit type; no operand has a null or implicit type" | the IR is well-typed (also V45 type-safety preserved into IR) |
| V-I4 | V | FM-1 | COVERED | V44 "Source locations flow from token → AST node → IR instruction → diagnostic message without any stage setting a location to null, zero, or synthesized-without-propagation" | global end-to-end position preservation; soft line/col-across-newlines leg not explicit |
| V-I5 | V | FM-4 | COVERED | V45 "The type invariants established by the type checker are preserved in the IR and generated code" | later passes don't undo a prior guarantee |
| V-I6 | V | FM-1 | COVERED | V13 "Every syntactic construct has a parsing rule and maps to a distinct typed AST node; no construct falls through to a generic catch-all" | totality over accepted language |
| V-I7 | V | FM-1 | COVERED | V52 "Given identical source input, the pipeline produces bit-identical output across runs" | determinism/reproducibility |
| V-I8 | V | FM-4 | COVERED | V50 "If any phase emits at least one error, no final output artifact ... is produced" | error blocks success-output (also V51 no swallowed error, V48 phase ordering) |
| V-E1 | V | FM-3 | COVERED | V19 "the resolution pass does at least a pre-scan for function names before resolving bodies, enabling mutual and self recursion" | recursive/mutually-recursive defs (also V31 self-containing struct) |
| V-E2 | V | FM-3, FM-2 | COVERED | V18 "A name used textually before its declaration in the same scope produces a diagnostic" | use-before-decl boundary + pre-scan rule (V19); resolver/checker policy-agreement leg not explicit |
| V-E3 | V | FM-3 | COVERED | V17 "Two declarations of the same name in the same scope ... produce a 'redeclaration' error; shadowing in a child scope is allowed (or forbidden) per the language spec, consistently" | both legs: redecl error + shadowing (also V21 nearest-wins, V22 built-in shadow) |
| V-E4 | V | FM-3 | COVERED | V57 "A file with zero bytes or only whitespace produces zero tokens (plus EOF), a valid empty AST, no name-resolution or type errors, and an empty but valid IR module" | |
| V-E5 | V | FM-3 | COVERED | V55 "A deeply nested expression (e.g., 10,000 levels of parentheses) either compiles correctly or produces a clean 'nesting too deep' diagnostic; the compiler never crashes" | |
| V-E6 | V | FM-3 | COVERED | V9 "A string literal reaching EOF without a closing delimiter produces exactly one diagnostic" | error-input boundaries (also V4 bad escape, V7 unterminated comment, V56 EOF unclosed) |
| V-E7 | V | FM-3 | COVERED | V5 "An integer or float literal outside the target type's representable range produces a diagnostic ...; no silent truncation or wrap" | |
| V-E8 | V | FM-3, FM-2 | NOT-COVERED | | no candidate item addresses encoding/Unicode at the lexer: no BOM, CRLF/LF line counting, or byte-vs-codepoint offset handling |
| V-E9 | V | FM-3 | COVERED | V58 "A struct type with no fields is either accepted with a defined size ... or rejected by a defined rule; the outcome is consistent and the compiler does not crash" | empty-construct boundary (empty record); other empties (body/params/array) not named but boundary class covered |
| V-F1 | V | FM-4 | COVERED | V24 "operations on the sentinel propagate it without emitting additional errors; one root-cause defect produces O(1) diagnostics, not O(n)" | cascade/flood suppression guard |
| V-F2 | V | FM-3 | COVERED | D8 "IR Verifier — standalone checker that validates all IR well-formedness rules independently of the front-end; runs after lowering and before code generation" | independent IR-verifier backstop (the false-PASS guard) |
| V-F3 | V | FM-1 | COVERED | V40 "Every instruction in the IR has a translation to target output; no instruction falls through to 'unimplemented'" | fail-loudly exhaustiveness mechanism (also V13 no catch-all) |
| V-F4 | V | FM-4 | COVERED | V10 "the lexer resumes on the next character and produces correct surrounding tokens" | consume-or-error-and-advance on invalid char (progress guarantee) |
| N1 | N | FM-1 | COVERED | N1 "constant folding, dead-code elimination, inlining, loop transformations belong to the middle-end optimizer, not the front-end" | |
| N2 | N | FM-1 | COVERED | N5 "full register-assignment rules per type on specific ISAs are out of scope; abstract-level calling convention is in scope" | reg-alloc/ABI out of scope |
| N3 | N | FM-1 | COVERED | N8 "importing symbols from other compiled units is out of scope; single-file or single-module compilation is assumed" | single compilation unit / no modules (also N2 linking) |
| N4 | N | FM-1 | COVERED | N7 "macro expansion, compile-time code generation, and template instantiation are out of scope" | |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D1 | 5 | 4 | V1 "Token taxonomy complete"; V3 "Keyword priority over identifier"; V6 "EOF sentinel"; V7 "Comment handling" |
| D2 | 4 | 3 | V11 "Grammar unambiguous"; V12 "Operator precedence and associativity complete"; V16 "Short-circuit operators distinct from bitwise operators in AST" |
| D4 | 2 | 1 | V20 "Built-in names in outermost scope" |
| D5 | 9 | 8 | V25 operator type rules; V26 return type/missing-return; V27 void must not return; V28 call arity; V29 non-function called; V30 invalid struct field; V32 assignment assignable; V33 condition must be bool |
| D6 | 5 | 4 | V35 short-circuit→branches; V36 unique temporaries; V46 meaning preservation; V47 argument evaluation order |
| D7 | 4 | 3 | V41 calling convention; V42 stack-frame slots; V43 output parseable by assembler |
| Dep1 | 3 | 2 | V2 "Maximal-munch rule"; V8 "Byte completeness" |
| Dep2 | 2 | 1 | Dep3 "scope-boundary fidelity" |
| Dep4 | 2 | 1 | Dep6 "symbol table completeness" |
| Dep7 | 3 | 2 | Dep10 "call-site / callee-signature agreement"; V38 "CFG completeness: every path ends at a terminator" |
| Dep9 | 2 | 1 | Dep2 "monotonic position ordering" |
| Dep10 | 3 | 2 | V14 "Parser error recovery"; V49 "Error accumulation: each phase exhausts its diagnosable errors" |
| Dep11 | 2 | 1 | Dep12 "symbol-name consistency" |
| V-I8 | 3 | 2 | V48 "Phase ordering enforced; no backward dependencies"; V51 "No phase discards errors; driver list equals union" |
| V-E1 | 2 | 1 | V31 "Directly self-containing struct rejected" |
| V-E3 | 2 | 1 | V22 "Shadow of a built-in name → defined behavior" |
| V-E6 | 3 | 2 | V4 "String escape sequences correct"; V56 "EOF-unclosed delimiter → diagnostic citing opener" |
| N3 | 2 | 1 | N2 "Linking" |

Ballast total = 4+3+1+8+4+3+2+1+1+2+1+2+1+2+1+1+2+1 = **40**.

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| D7 "Driver (orchestration layer) — sequences all phases in order, threads representations between them, accumulates all diagnostics, and suppresses output artifacts on error" | UNMATCHED — human review |
| N3 "Runtime library implementation — the implementation of built-in functions (e.g., print, malloc) is out of scope" | UNMATCHED — human review |
| N4 "Garbage collector implementation — the GC algorithm and collector are out of scope" | UNMATCHED — human review |
| N6 "Debug information format — DWARF, PDB, and other debug-info wire formats are out of scope" | UNMATCHED — human review |

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/7   Dep = 11/12   V = 20/21   N = 4/4
  by FM tag:     FM-1 = 22/23   FM-2 = 5/7   FM-3 = 9/10   FM-4 = 4/4   FM-5 = n/a   FM-6 = n/a   FM-7 = n/a   (FM-5/6/7 n/a on static task)
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 40
  unmatched candidate points (human-review flag):    total = 4
```

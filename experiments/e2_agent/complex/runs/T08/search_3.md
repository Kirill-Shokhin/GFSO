# Search 3 — New Holes · T08: Compiler Front-End End-to-End Design

> Third pass against D2. Items below are genuinely new — not restatements of existing V/Dep/N entries.
> Over-included by design; audit will reduce.

---

## Genuinely New Holes

**S3-1. Type-checker internal ordering: struct/type layout pass before body checking**
The type checker must build a complete type environment (all struct definitions resolved to field lists with types) in a first pass before it begins type-checking any function body or expression. Without an explicit ordering guarantee, a function defined textually before a struct it uses would fail with a spurious "unknown field" or layout error even though the name resolver pre-scanned the struct's name (V60 + Dep6 only guarantee the name is in the symbol table, not that the layout has been computed).
*Falsifier: `fn f() -> S { let v: S; v.x } struct S { x: int }` → type-checks successfully; `S`'s layout is available when `f`'s body is checked regardless of textual order.*

**S3-2. Type-checker: recursive pointer types must not cause infinite looping in layout computation**
When the type checker computes struct field offsets and sizes (Dep16), it must treat pointer types as opaque fixed-size units and must not recursively expand the pointed-to type. Without this boundary, `struct Node { next: *Node; val: int }` causes the layout algorithm to recurse infinitely. V31 only handles value-type cycles (rejects them); pointer-to-self is valid and must terminate.
*Falsifier: `struct Node { next: *Node; val: int }` → type-checker computes Node's size as `pointer_size + int_size` without hanging or stack-overflowing.*

**S3-3. Code generator: external symbol import declarations in emitted output**
For every symbol that is referenced but not defined in the current compilation unit (built-in functions, runtime functions — e.g., `print`, `malloc`), the code generator must emit the appropriate external/import declaration in the output format (e.g., `.extern print` in assembly, an import entry in the object format). Without this, the assembler or loader sees an undefined symbol and rejects the output. N3 (runtime library is out of scope) addresses implementation; this is the code-gen side of the contract.
*Falsifier: compile a program calling `print`; pipe generated output through the target assembler; assembler does not produce "undefined symbol" error.*

**S3-4. CFG linearization: every reachable basic block emitted exactly once**
The code generator must traverse and emit instructions for every reachable basic block in the IR CFG — no block skipped, none emitted more than once. V38 ensures every block has a terminator; V40 ensures every IR instruction has a translation rule. Neither criterion guarantees that the code generator's CFG traversal actually visits all blocks (e.g., a depth-first traversal that mis-tracks visited nodes could skip a back-edge target or emit a block twice in the presence of multiple predecessors).
*Falsifier: compile a function with a loop (back-edge in the CFG); generated output contains instructions for both the loop-header block and the loop-body block; neither block appears twice.*

**S3-5. Deeply nested statements → clean diagnostic or success, no crash**
V55 specifies behavior for "deeply nested expressions" (e.g., 10,000 levels of parentheses). A distinct failure mode exists for deeply nested control structures (e.g., 10,000 nested `if` blocks or `while` loops): the recursive-descent parser and recursive IR-lowering pass can overflow the call stack. The source of nesting is syntactically different (statements, not expression groupings), and the recursion path through the compiler is different.
*Falsifier: generate a program with 1,000 nested `if (true) { ... }` structures; run compiler; expect success or a clean "nesting too deep" diagnostic, never a stack overflow crash.*

**S3-6. Global variable initialization ordering in IR and code gen**
Dep14 and Dep12 establish that global variable operands are tracked through the symbol table. If the language permits global variable declarations with non-constant initializer expressions (`let b: int = a + 1;` at top level where `a` is another global), the IR must capture a dependency ordering for global initializers, and the code generator must emit initialization code that respects it. Without this, the emitted entry code may initialize `b` before `a`, producing wrong values.
*Falsifier: `let a: int = 1; let b: int = a + 1;` at file scope → emitted initialization code sets `a` before `b`; `b` holds value 2 at program start.*
*(Weakly in scope: applies only if the language permits expression initializers on globals; safe to exclude if initializers are restricted to constants.)*

**S3-7. Diagnostic output sorted by source location**
V51 ensures no diagnostic is discarded; V67/V68 handle severity and deduplication. None specifies the ORDER in which diagnostics appear in the driver's final output. A compiler that emits diagnostics in phase-execution order (lexer errors, then parser errors, then type errors) will show a type error at line 5 after a parse error at line 50, confusing the user and making automated error-location extraction unreliable.
*Falsifier: source file with a parse error at line 10 and a type error at line 5 → the driver's final diagnostic list presents the line-5 diagnostic before the line-10 diagnostic.*

**S3-8. Missing explicit scope exclusion: generic / parametric types**
D2's N section (N1–N9) does not explicitly exclude generics or parametric polymorphism. For a "small statically-typed language" these are almost certainly out of scope, but the absence of an explicit exclusion leaves the decomposition ambiguous. If the language has generics, every phase from name resolution (type-parameter scoping) through type checking (type argument substitution, unification) through IR lowering (monomorphization or boxing) requires substantial additional machinery not covered anywhere in D2. An explicit N10 would close this ambiguity.
*Why safe to exclude: task description says "small" language with no mention of generics; re-include if the language spec adds parametric types.*

---

## Assessment

After a hard exhaustive look, D2 is very thorough. The 8 items above are the genuinely new content I can surface:

- **S3-1 through S3-5** are strong: each has a distinct failure mode not covered by any existing V/Dep entry, and a concrete falsifier that a test could check.
- **S3-6** is real but conditional on a language-spec choice (non-constant global initializers).
- **S3-7** is a real usability/contract requirement but borderline between correctness and quality-of-implementation.
- **S3-8** is a missing scope exclusion rather than a missing requirement.

No manufacturing of holes: the remaining space (error token protocol, numeric literal default types, external ABI details, SSA phi nodes, closures) is either already covered by existing entries or genuinely out of scope for the stated task.

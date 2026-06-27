# search_2.md — T08 Compiler Front-End · Second Pass

> Inputs: task statement (T08.md) + current decomposition (D1.md).
> Output: genuinely new holes only — content D1 does not already cover.

---

## Missing cross-component interaction seams

**S1. IR Verifier → Code Generator · verified-IR guarantee**
The IR Verifier (D8) produces a pass/fail verdict, but no Dep specifies what structural properties it certifies and which of those code gen trusts without re-checking. Without this seam the verifier is structurally disconnected from code gen.
*Falsifier: remove the verifier from the pipeline; code gen should break on an invariant it no longer has a guarantee for — but currently no such invariant is named, so nothing breaks detectably.*

**S2. Name Resolver → IR Lowering · symbol identity handoff**
Dep12 covers Name Resolver → Code Generator for symbol-name consistency, but IR lowering also emits symbol references (function-call targets, global variable operands). No seam says IR lowering reads names from the resolver's symbol table rather than re-deriving them from source text.
*Falsifier: rename a symbol via the resolver; IR operands still carry the pre-rename source text → linker mismatches that code gen (which does read from the table) catches but IR lowering already made wrong.*

**S3. Parser → Type Checker · type-annotation AST nodes**
Dep3 and Dep4 cover Parser → Name Resolver contracts. There is no seam for Parser → Type Checker (via the resolved AST): specifically, that every type-annotation position in the AST (variable declaration, parameter, return type, struct field) is parsed into a distinct, evaluatable type-annotation node — not a raw string or identifier — so the type checker can resolve them.
*Falsifier: parse `fn f(x: MyStruct) -> int { ... }` where `MyStruct` is a user type; if the parameter type annotation is stored as a raw identifier string rather than a type-node, the type checker silently substitutes the wrong type with no error.*

**S4. Type Checker → IR Lowering · struct field layout**
Dep7 and Dep8 cover type information (no unresolved type vars, explicit coercions). Neither covers the struct field layout — field order and computed offsets — that IR lowering needs to emit correct `getelementptr`-style memory access instructions.
*Falsifier: define a struct with three fields; IR lowering uses field index 0 for what should be field index 2 → wrong memory access with no error at lowering time.*

---

## Missing criteria

**M1. Mutual struct infinite-size rejection**
V31 rejects a struct directly containing itself. It does not cover mutually recursive value-type structs (`struct A { b: B }; struct B { a: A }`) which are equally infinite-sized.
*Falsifier: compile `struct A { b: B }; struct B { a: A }` → expect an "infinite size" or "cyclic type" error; D1 as written would not catch this.*

**M2. Forward reference for user-defined types**
V19 gives functions a pre-scan so they can be mutually recursive. No analogous rule exists for struct/type definitions. If `struct B` references `struct A` that appears later in the file, resolution either silently fails or crashes.
*Falsifier: `struct B { a: A }; struct A { x: int }` → must compile successfully (or produce a defined "unknown type" error), not a crash or silent wrong-type binding.*

**M3. Array element and index type rules**
V54 lists arrays in the type representation but no V-criterion covers: (a) array index must be an integer type → type error if not; (b) all elements of an array literal must have the same type → type error if not; (c) the type of an array-index expression `a[i]` is the element type of `a`.
*Falsifier: `a["key"]` → type error; `[1, "two", 3]` → type error; `let x: int = arr[0]` where `arr: int[]` → type-checks cleanly.*

**M4. Pointer dereference type rules**
V54 lists pointer types. No criterion says: (a) dereferencing a non-pointer type is a type error; (b) the type of `*p` where `p: *T` is `T`; (c) taking the address of an expression (`&expr`) produces a `*T` where `T` is the expression's type.
*Falsifier: `let x: int = 0; let y = *x;` → type error (deref of non-pointer); `let p: *int = ...; let v: int = *p;` → type-checks cleanly.*

**M5. Lvalue validity on assignment left-hand side**
V32 checks that the RHS type is assignable to the LHS declared type. It does not check that the LHS is a valid lvalue. Assigning to a function call result, a literal, or a type name must produce a "not an lvalue" error, not a type-mismatch error.
*Falsifier: `f() = 5;` → "not an lvalue" error, not a type error; `42 = x;` → "not an lvalue" error.*

**M6. Dead code after `return` within a basic block**
V38 says every basic block has a terminator. It does not cover the case where a `return` statement appears in the middle of a statement list; IR lowering must close the current basic block at the `return` and not emit instructions for subsequent statements in the same syntactic block (those form either dead IR or must be silently omitted).
*Falsifier: lower `{ return 1; x = 2; }` → IR for the function has exactly one basic block terminator (`return 1`); `x = 2` produces no IR instruction; verify no instruction in the same block follows the return.*

**M7. Source encoding contract**
D1's description of D1 (Lexer) says it converts "raw source bytes" but never specifies the encoding (UTF-8, ASCII, Latin-1). V10 mentions "character outside the allowed set" without defining the set. V4's `\uXXXX` escape implies Unicode awareness. The encoding contract is the foundational invariant the lexer enforces; without it, "invalid character" (V10) and identifier rules have no testable definition.
*Falsifier: feed a file with a valid UTF-8 two-byte sequence (e.g., é, U+00E9); the compiler must behave consistently — either accept it as an identifier character or produce exactly one "invalid character" diagnostic, not a crash or platform-dependent result.*

**M8. Diagnostic severity distinction**
D1 accumulates "errors" uniformly. If the language emits any warnings (e.g., unused variable, unreachable code), V50's rule "suppress output artifact if any error exists" must distinguish error severity from warning severity. No criterion defines the severity taxonomy or the rule for which severity levels suppress output.
*Falsifier: program with one unused variable (warning) and no errors → output artifact is produced; program with one type error → no output artifact. Without this criterion, a warning mis-classified as an error would wrongly suppress the artifact.*

**M9. Numeric assignability / implicit widening rule**
Dep8 says coercions are explicit in the typed AST. V32 says RHS must be "assignable" to LHS. Neither specifies the exact assignability relation: is `int` implicitly assignable to `float`? Is `i32` assignable to `i64`? The coercion insertion logic in the type checker depends on this rule, and its absence leaves Dep8 under-specified (what coercions should be inserted?).
*Falsifier: `let x: float = 1;` — must either succeed (with an implicit int→float coerce node in typed AST) or fail with a type error; the rule must be deterministic and tested.*

**M10. Diagnostic deduplication — same error, same location, at most once**
V51 says errors are never discarded and the driver list equals the union of all phase lists. It does not say the same (source-location, error-code) pair is not emitted twice by two different phases or two paths through the same phase.
*Falsifier: a single undeclared name used in an expression that is visited twice during type checking (e.g., once to check the expression, once to check a wrapping expression) → exactly one "undeclared name" diagnostic, not two.*

---

## Wrong scope decisions

**W1. Arrays and pointers: in V54 but criteria-absent**
V54 explicitly places arrays and pointer types in the type representation schema ("distinct nodes in the type language"), yet the V section has zero criteria for array or pointer operations (indexing rules M3, deref rules M4 above). If arrays and pointers are in scope (as V54 implies), they are substantially under-specified. If they are out of scope, V54 should not enumerate them and an N-entry should exclude them. This is a structural inconsistency in D1's scope boundary.
*Falsifier: D1 claims the type representation is complete (V54) while the type-checker section has no rules for operating on the types it lists — the two sections falsify each other.*

**W2. Mutability / const distinction not addressed**
D1 has no criterion and no exclusion for variable mutability. If the language distinguishes `let` (mutable) from `const` (immutable), assigning to a `const` variable must be a type error. If there is no such distinction, that should be an explicit N-entry. As written, the decomposition is silent on this question, which is load-bearing for both the type checker (V32) and IR lowering (IR value vs. memory slot representation).
*Falsifier: `const x: int = 1; x = 2;` — must either produce a "cannot assign to const" error or the language must explicitly have no const. D1 supports neither outcome with any criterion.*

---

## Count

12 new holes (S1–S4, M1–M10, W1–W2).

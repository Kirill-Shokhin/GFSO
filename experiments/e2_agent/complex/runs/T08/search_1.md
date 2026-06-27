# Search pass 1 — T08: Compiler Front-End End-to-End Design

---

## A. Domain Primitives

**A1. Token taxonomy** — every token class (keyword, identifier, integer literal, float literal, string literal, boolean literal, operator, punctuation, EOF) must be enumerated with its pattern — *falsifier: feed source containing each class; if any token is mis-classified or absent, the token stream is wrong*

**A2. Maximal-munch rule** — lexer always consumes the longest possible prefix that matches any token pattern — *falsifier: `!=` must tokenize as one NEQ token, not `!` + `=`; similarly `<=`, `++`, `->` etc.*

**A3. Keyword vs identifier priority** — reserved words must match before the identifier rule — *falsifier: `return_value` must lex as IDENT, not KW_RETURN + IDENT*

**A4. Source location on every token** — every token carries (file, line, column, byte-offset, length) — *falsifier: produce a type error on a deep expression; verify error message cites the correct source line/column*

**A5. String escape sequences** — recognized escape sequences (`\n`, `\t`, `\\`, `\"`, `\uXXXX`, etc.) must be decoded to the correct code-point; unrecognized ones must error — *falsifier: parse `"\n"` and verify the string value contains byte 0x0A, not backslash-n*

**A6. Numeric literal ranges** — integer literals that exceed the target type's maximum value must produce a diagnostic at lex or parse time, not silently wrap — *falsifier: write `99999999999999999999` (beyond 64-bit); expect a lex/parse error, not a truncated constant*

**A7. EOF sentinel token** — lexer emits exactly one EOF token as the final element and never emits tokens after it — *falsifier: call the lexer twice past EOF; it must return the same EOF token, not crash or return a new token*

**A8. Comment handling** — line comments and/or block comments are silently consumed; block comments that are unterminated (reach EOF) must produce a diagnostic — *falsifier: write `/* comment without closing`; expect an error, not silent truncation of the following source*

**A9. Grammar formalism** — the grammar must be unambiguous (or ambiguity explicitly resolved by precedence/associativity declarations); every valid program has exactly one parse tree — *falsifier: the dangling-else ambiguity (`if a if b s1 else s2`) must produce a deterministic single AST*

**A10. Operator precedence table** — all binary and unary operators have defined precedence levels and associativity (left/right); the precedence table must be complete — *falsifier: write `a + b * c`; AST must nest `b * c` under `+`, not the other way*

**A11. AST node schema** — every syntactic construct maps to a distinct AST node type with fully-specified children; no catch-all "raw" nodes remain in the output AST — *falsifier: walk the AST for any valid program and verify every node is an instance of a typed node class, never a generic untyped node*

**A12. Scope-boundary markers in AST** — every construct that opens a new scope (block, function body, for-init) has an explicit AST node that signals a scope boundary — *falsifier: a nested block `{ let x = 1; { let x = 2; } }` must produce two distinct scope-opening nodes; name resolution must not flatten them*

**A13. Type representation schema** — every type in the language (primitive, struct, array, pointer, function type, error sentinel) is represented as a distinct node in the type language; type identity and structural equality rules are defined — *falsifier: two distinct struct types with the same field names and types must be distinguishable under nominal typing; check that `type A { x: int }` and `type B { x: int }` are not equal*

---

## B. Lifecycle / State

**B1. Phase ordering invariant** — phases execute in fixed order: lex → parse → resolve → typecheck → lower → codegen; no phase reads the output of a later phase — *falsifier: inject a dependency from the type checker back into the parser; build must fail to compile or produce a wrong result*

**B2. Error-accumulation policy** — each phase collects all errors it can diagnose before passing control to the next phase; the pipeline continues through subsequent phases to collect more errors even when prior phases had errors — *falsifier: write a file with three distinct parse errors; the diagnostic list must contain all three, not just the first*

**B3. No output on error** — if any phase emits at least one error, no final output artifact (IR file, object file, executable) is produced — *falsifier: write a program with a type error; verify the output directory contains no object file*

**B4. Error-count monotonicity** — errors emitted are never silently discarded by a downstream phase; the final diagnostic list is a superset of every phase's emitted errors — *falsifier: count errors emitted by the type checker; count errors delivered to the user; they must match*

**B5. Driver / orchestration layer** — a top-level driver sequences phases, threads the intermediate representations between them, and collects all diagnostics; it is a distinct component with a defined interface — *falsifier: swap out the type checker with a no-op; the driver must still invoke the remaining phases (resolve, lower, codegen) with whatever output the no-op produces*

**B6. Determinism** — given identical source input, the pipeline produces bit-identical output across runs — *falsifier: compile the same file twice; diff the IR or object output; must be identical (modulo embedded timestamps if any)*

---

## C. Components — per-stage requirements

### C1. Lexer

**C1a. Complete coverage** — every byte of the source is consumed by exactly one token; no byte is skipped silently outside of comment/whitespace handling — *falsifier: sum token lengths (plus whitespace skipped) and compare to source length; must match*

**C1b. Unterminated string detection** — a string literal that reaches EOF without a closing delimiter produces a diagnostic on the opening delimiter's line, and the lexer does not continue emitting tokens past the EOF — *falsifier: write `"hello`; expect exactly one "unterminated string" error*

**C1c. Invalid character handling** — a source character outside the language's allowed set produces a diagnostic with its exact source position, then the lexer resumes on the next character — *falsifier: insert byte 0x01 in source; expect a diagnostic citing its column; tokens before and after must be correct*

### C2. Parser

**C2a. Full grammar coverage** — every construct in the language's reference grammar has a parsing rule; no construct silently falls through to a generic catch-all — *falsifier: enumerate all statement/expression/declaration forms; each must produce the correct typed AST node, not a generic node*

**C2b. Error recovery** — on a syntax error, the parser synchronizes (e.g., at the next statement or closing brace) and continues parsing to surface additional errors — *falsifier: write a file with syntax errors in three separate functions; all three functions' errors must appear in diagnostics*

**C2c. No AST node without a location** — every AST node produced by the parser carries at least the source location of its primary token — *falsifier: walk every node of a parsed AST; assert none has a null/zero location*

**C2d. Parenthesized expression** — a parenthesized expression `(e)` parses correctly and its AST carries the location of the outer parens, not just the inner expression — *falsifier: cause an error inside `(expr)`; verify the error cites a position inside the parens*

**C2e. Short-circuit operators represented distinctly** — `&&` and `||` must be distinct AST node types from bitwise `&` and `|`, to force correct lowering later — *falsifier: an AST for `a && b` must not be the same node type as `a & b`*

### C3. Name / Scope Resolution

**C3a. Unique declaration per scope** — two declarations of the same name in the same scope produce a "redeclaration" error; shadowing in a child scope is allowed (or forbidden by the language spec, whichever is specified) — *falsifier: write `let x = 1; let x = 2;` in the same block; expect exactly one redeclaration error*

**C3b. Use-before-declaration error** — a use of a name that appears textually before its declaration in the same scope produces a diagnostic — *falsifier: write `print(x); let x = 1;` in a block; expect a "use before declaration" error*

**C3c. Self-referential initializer detection** — a variable that references itself in its own initializer (`let x = x + 1`) must be diagnosed — *falsifier: write that pattern; expect an error, not a silently unresolved reference*

**C3d. Forward reference for functions** — functions may be called before their textual definition (mutual recursion must work); the resolution pass must do at least a pre-scan for function names before resolving bodies — *falsifier: write two mutually recursive functions `f` calls `g`, `g` calls `f`, `f` defined first; compilation must succeed*

**C3e. Built-in name environment** — primitive type names (`int`, `bool`, `float`, `string`) and any built-in functions are installed in the outermost scope before user code is resolved — *falsifier: use `int` as a type in user code without declaring it; compilation must succeed*

**C3f. Resolved link on every name-use node** — after resolution, every identifier-use AST node carries an unambiguous reference (e.g., a unique declaration ID) to its declaration; no dangling or null reference remains — *falsifier: after resolution, walk all identifier-use nodes; assert none has a null declaration pointer*

**C3g. Scope depth recorded** — each symbol table entry records the scope depth at which the name was declared, to support shadowing diagnostics and capture analysis — *falsifier: in nested scopes with the same name, verify each use resolves to the declaration at the correct depth*

### C4. Type Checker

**C4a. Every expression annotated** — after type checking, every expression node in the AST carries a concrete type (no "pending" or "unknown" types remain, except the error sentinel) — *falsifier: walk all expression nodes after type checking; assert each has a non-null, non-pending type*

**C4b. Error sentinel type** — when a sub-expression has a type error, the expression's type is set to an error sentinel; operations on the error sentinel propagate it without emitting additional errors — *falsifier: write `1 + "hello" + 2`; expect exactly one error (the `+` between int and string), not a cascade of errors on the second `+`*

**C4c. Operator type rules** — every operator has an explicit type signature; applying it to wrong-typed operands produces a diagnostic — *falsifier: write `true + 1`; expect a type error, not a silently wrong result*

**C4d. Return type checking** — every return statement's expression type must be assignable to the enclosing function's declared return type; a non-void function with a missing return on some path must be diagnosed — *falsifier: write a function declared `-> int` with a branch that has no return; expect a "missing return" error*

**C4e. Void return** — a void function must not return a value; `return expr;` in a void function is a type error — *falsifier: write `fn f() { return 1; }`; expect a type error*

**C4f. Call arity and type checking** — a function call must have the same number of arguments as the callee's parameter list, and each argument's type must match the corresponding parameter's type — *falsifier: call a two-parameter function with one argument; expect an arity error*

**C4g. Non-function call detection** — calling a non-function value as a function must be diagnosed — *falsifier: write `let x = 1; x(2);`; expect a "not callable" type error*

**C4h. Struct field access** — accessing a field on a non-struct type, or a nonexistent field on a struct type, must be diagnosed — *falsifier: write `let x: int = 0; x.field;`; expect a type error*

**C4i. Recursive type well-foundedness** — a struct that directly contains itself as a value (not via pointer) has infinite size and must be rejected — *falsifier: write `struct Node { next: Node }` (without pointer); expect an "infinite size" error*

**C4j. Assignment compatibility** — the right-hand side of an assignment must have a type assignable to the declared type of the left-hand side — *falsifier: write `let x: bool = 42;`; expect a type error*

**C4k. Condition type enforcement** — the condition of `if`, `while`, `for` must be of type `bool`; other types must be rejected (no implicit truthiness) — *falsifier: write `if 1 { ... }`; expect a type error on the condition*

### C5. IR Lowering

**C5a. Every AST construct has an IR translation** — every expression and statement form in the language has a defined lowering rule; no construct falls through to "unimplemented" — *falsifier: write a program exercising every language construct; IR lowering must complete without an "unimplemented" error*

**C5b. Short-circuit lowering** — `&&` and `||` must lower to conditional branches (not simple bitwise operations) so that the right-hand side is not evaluated when unnecessary — *falsifier: write `f() && g()` where `f()` returns false; verify in IR that `g` is only called on the true branch*

**C5c. Temporaries are unique** — every temporary value introduced during lowering has a unique name/ID; no two subexpressions share a temporary — *falsifier: lower a complex expression like `(a+b)*(a+b)`; verify the two `a+b` subexpressions produce two distinct temporaries*

**C5d. Type on every IR operand** — every value / operand in the IR carries an explicit type; no operand has a missing or implicit type — *falsifier: inspect every IR instruction; assert every operand has a non-null type field*

**C5e. Control flow completeness** — every function's IR has a control flow graph where every basic block is reachable from the entry block, and every path through the function ends at a return or an explicit "unreachable" instruction — *falsifier: lower a function with two branches; verify both branches have a terminator instruction*

**C5f. Error-typed nodes not lowered** — any AST node annotated with the error sentinel type must not produce IR instructions — *falsifier: introduce a type error; inspect the IR; verify no instructions correspond to the errored subexpression*

**C5g. Source location on IR instructions** — IR instructions carry the source location of the AST node that generated them (for debug info and error attribution) — *falsifier: trigger an IR-level validation error; verify the error message cites a source line, not an IR line number*

### C6. Code Generation

**C6a. Every IR instruction has a code-gen rule** — every instruction in the IR has a defined translation to target output; no instruction falls through to "unimplemented" — *falsifier: compile a program that exercises every IR instruction type; code gen must complete without error*

**C6b. Calling convention conformance** — function calls and function prologues/epilogues follow the target's calling convention (argument passing order, register/stack layout, return value location) — *falsifier: call a function that returns a value; verify the caller reads the return value from the correct register/stack slot*

**C6c. Stack frame correctness** — local variables are allocated at correct stack offsets; no two locals overlap — *falsifier: write a function with several locals; inspect the generated code; verify each local has a unique, non-overlapping frame slot*

**C6d. Well-formed output** — the generated code (assembly, bytecode, etc.) is parseable by the target assembler/runtime without errors — *falsifier: pipe generated output through the target assembler; it must succeed with no errors*

---

## D. Global Invariants

**D1. Source location continuity** — source locations flow from token → AST node → IR instruction → diagnostic message without any stage setting a location to null or 0 — *falsifier: find any compiler error whose message omits a source location; that is a violation*

**D2. Type-safety preservation across the pipeline** — the type invariants established by the type checker (every expression has a type; no implicit unsafe casts) are preserved in the IR and generated code; the IR must not introduce type-unsafe operations not present in the source — *falsifier: compile a well-typed program; inspect every IR cast/reinterpret instruction; each must correspond to an explicit cast in the source*

**D3. Single error per root cause** — a single root-cause defect in the source should produce O(1) errors, not O(n) cascading errors — *falsifier: introduce one type error at the base of a large expression; count the resulting diagnostics; should not grow proportionally with expression size*

**D4. No implicit semantic change across phases** — the semantics of the program as expressed in the AST must equal the semantics of the generated IR; lowering is meaning-preserving — *falsifier: run the same program through an interpreter on the AST and through the full pipeline; outputs must agree*

**D5. Unique symbol identity** — each declared symbol (variable, function, type) has a globally unique ID throughout the pipeline; two declarations never share an ID — *falsifier: compile two functions both named `f` in different scopes (or check that the error is emitted); IDs in the symbol table must be distinct*

**D6. Well-typedness of IR is checkable** — a standalone IR verifier can be run after lowering to confirm all IR well-formedness rules independently of the front-end; this verifier exists and is part of the pipeline — *falsifier: deliberately introduce an ill-typed IR instruction by hand; the verifier must catch it*

**D7. No phase silently drops errors** — the driver's final diagnostic list contains every error emitted by every phase; no phase discards its errors internally — *falsifier: instrument each phase to count emitted errors; sum across phases; compare to driver's final count; must be equal*

---

## E. Cross-Component Interaction Seams

**E1. Lexer → Parser: token stream completeness** — every source character is accounted for by a token or a discarded whitespace/comment; parser's position after consuming all tokens must equal source end — *falsifier: after parsing, sum positions of all tokens plus whitespace spans; compare to source length; any mismatch means a byte was lost or duplicated*

**E2. Lexer → Parser: monotonic position** — tokens appear in strictly non-decreasing order of start byte offset; parser must never receive a token whose position precedes the previous token's end — *falsifier: iterate the token stream and assert each token's start >= previous token's end; any violation is a lexer bug that will silently misattribute source locations*

**E3. Parser → Name Resolution: scope boundary fidelity** — the AST's scope-boundary nodes must exactly correspond to the language's scoping rules; missing a scope boundary collapses two scopes into one — *falsifier: write a program where an inner `let x` shadows an outer `let x`; if name resolution resolves the inner use to the outer decl, a scope boundary was missing*

**E4. Parser → Name Resolution: declaration vs use ordering** — the AST must distinguish declaration nodes from use nodes; name resolution must not treat a use as a declaration or vice versa — *falsifier: write `x = 1;` (use) and `let x = 1;` (declaration) of the same name; verify resolution produces a use-before-decl error only when the use precedes the decl*

**E5. Name Resolution → Type Checker: all names resolved before type checking** — the type checker must not be called until name resolution has completed and every identifier-use node has a valid declaration link; partial resolution + type checking produces wrong type lookups — *falsifier: deliberately short-circuit name resolution after processing only the first function; type-check the second; verify the type checker cannot look up names from the first function's scope*

**E6. Name Resolution → Type Checker: symbol table completeness** — the symbol table passed to the type checker must contain every declared name in the program (including forward-declared functions); a type checker query for any declared name must never return "not found" — *falsifier: write a program where function `g` is defined after `f` and `f` calls `g`; type-check `f`; the type checker must find `g`'s type in the symbol table*

**E7. Type Checker → IR Lowering: no unresolved type variables** — the typed AST handed to IR lowering must have no nodes with an "inferred but not yet resolved" type marker; all type inference must have converged before lowering begins — *falsifier: if the language has type inference, write a program where a variable's type can only be inferred from its use later in the function; after type checking, the variable's declaration node must carry a concrete type, not a variable*

**E8. Type Checker → IR Lowering: explicit coercions only** — any implicit numeric widening or coercion applied by the type checker must be represented as an explicit coercion node in the typed AST (not a silent property); IR lowering translates that node into an explicit IR instruction — *falsifier: write an expression where an `int` is passed to a `float` parameter (if the language allows it); inspect the AST for an explicit coerce node; inspect the IR for an explicit conversion instruction*

**E9. IR Lowering → Code Generation: use-def dominance** — in the IR's control-flow graph, every use of a value must be dominated by its definition; code generation assumes this and does not re-check it — *falsifier: construct an IR program where a value is used on a branch that does not pass through the definition; the IR verifier (D6) must catch this before code gen is invoked*

**E10. IR Lowering → Code Generation: call-site / callee-signature agreement** — the number and types of arguments at every call-site in the IR must exactly match the callee's IR-level parameter list; code gen trusts this without re-checking — *falsifier: write a wrapper that emits a call instruction with one fewer argument than the callee's signature; verify the IR verifier (D6) catches this; code gen must never see such an IR*

**E11. Error-sentinel propagation across stages** — the error sentinel type from the type checker must be recognized by IR lowering (to skip code emission) and must not produce spurious IR instructions or code-gen errors — *falsifier: write a program with one type error deep in a complex expression; verify the IR contains no instructions for that subexpression; verify code gen completes without a "missing operand" internal error*

**E12. Symbol table → Code Generator: mangled name consistency** — if the code generator needs symbol names (for extern calls, exports), it must read them from the same symbol table that name resolution populated, not re-derive them independently — *falsifier: compile a function named `foo`; verify the symbol in the object file matches the name the linker would expect; then rename it in the symbol table manually and rerun codegen — the emitted symbol must follow the table, not the source text*

**E13. Source location → Diagnostic system seam** — every diagnostic emitted by any phase must include a source location; the diagnostic formatter must render that location as a human-readable file/line/column — *falsifier: introduce errors at known positions; run the compiler; verify each diagnostic message contains the correct file name, line number, and column*

---

## F. Edge / Boundary Cases

**F1. Empty source file** — a file with zero bytes must produce zero tokens (only EOF), a valid empty AST, no name-resolution errors, no type errors, and an empty (but valid) IR module — *falsifier: compile an empty file; expect success with zero diagnostics and an empty IR module*

**F2. Whitespace-only file** — a file with only spaces, tabs, newlines produces the same result as an empty file — *falsifier: compile a file of 1000 spaces; same expected outcome as F1*

**F3. Maximum nesting depth** — a deeply nested expression (e.g., 10,000 levels of nested parentheses) must either compile correctly or produce a clean "nesting too deep" diagnostic, not a stack overflow crash — *falsifier: generate a deeply nested expression programmatically; run the compiler; expect either success or a clean diagnostic, never a crash*

**F4. Unterminated block at EOF** — a source file that ends inside an unclosed block `{` must produce a diagnostic citing the unclosed delimiter's position, not a crash — *falsifier: write `fn f() {`; expect a "missing `}`" diagnostic with the line of the opening brace*

**F5. Integer literal overflow** — a numeric literal that exceeds the range of the target integer type produces a diagnostic at the point of the literal, not undefined behavior in the IR — *falsifier: write `let x: i32 = 3000000000;`; expect a range error on the literal*

**F6. Zero-argument function** — a function with no parameters and a call `f()` must parse, resolve, type-check, and lower correctly — *falsifier: write and compile `fn f() -> int { return 0; }; f();`; expect success*

**F7. Self-recursive function** — a function that calls itself must type-check correctly (its own name must be in scope for the body) and lower to an IR that has a self-referential call, without infinite compilation loops — *falsifier: write `fn fact(n: int) -> int { return n * fact(n-1); }`; expect successful compilation*

**F8. Shadow built-in name** — a user declaration that shadows a built-in name (e.g., `let int = 5;`) must either be rejected with a clear error or silently allowed per language spec; the behavior must be defined and consistent — *falsifier: write `let int = 5;`; the compiler must produce a defined outcome (error or allowed), not a crash or undefined behavior*

**F9. Void function in expression context** — calling a void function inside an expression (`1 + f()` where `f` returns void) must produce a type error — *falsifier: write `fn f() {} let x = 1 + f();`; expect a type error*

**F10. Struct with zero fields** — a struct type with no fields must be accepted (or rejected) by a defined rule; its size is 0 or 1 per the ABI spec — *falsifier: write `struct Empty {}`; compiler must produce a defined outcome*

**F11. Duplicate function names** — two top-level function definitions with the same name must be rejected with a redeclaration error — *falsifier: write two `fn foo() {}` at top level; expect exactly one redeclaration error*

**F12. Operator on incompatible types** — every binary operator applied to operands of incompatible types (e.g., `"a" * 3`) must produce exactly one type error, not a crash — *falsifier: systematically try each operator with wrong-typed operands; each must yield one diagnostic*

---

## G. Silent Failure Modes

**G1. Lexer character drop** — if the lexer's regex engine has a bug that skips a character on certain inputs, the token stream is shorter than the source; the parser accepts it as a different valid program — *falsifier: assert that the sum of all token byte-spans plus whitespace equals the source byte length*

**G2. Wrong associativity in AST** — `a - b - c` under right-associativity produces `a - (b - c)`; if the parser's associativity rule is wrong, the AST is silently incorrect and no error is emitted — *falsifier: parse `8 - 3 - 2`; evaluate the AST; expect `3`, not `7`*

**G3. Resolution to wrong scope** — in a shadowing scenario with identical types, name resolution links a use to the outer declaration instead of the inner one; the type checker sees no error because types match; the semantics are wrong — *falsifier: in `let x = 1; { let x = 2; print(x); }`, verify the resolved link for the inner `print(x)` points to the inner `x` declaration, not the outer one*

**G4. Argument evaluation order not specified** — if the language does not specify argument evaluation order and code gen happens to evaluate right-to-left, calls with side effects silently produce different behavior than a left-to-right assumption — *falsifier: define the evaluation order in the spec and emit IR arguments in that order; write a test where both orders produce different values; verify the IR uses the specified order*

**G5. Dead-code call elision** — a function call whose return value is unused may be elided by an over-eager lowering pass, discarding the call's side effects — *falsifier: write `f();` (result discarded) where `f` has a side effect; verify the IR contains a call instruction for `f`*

**G6. Implicit integer widening** — if the language allows passing `int` where `int64` is expected, the widening may be silently omitted in IR, producing a zero-extended vs sign-extended difference — *falsifier: write a function that takes `int64` and pass an `int` literal; inspect the IR for an explicit sign-extension instruction*

**G7. Type annotation on IR value omitted** — if IR generation forgets to annotate a value's type (leaves it null), code gen may infer a wrong type from context or crash — *falsifier: after IR generation, verify every IR value has a non-null type; flag any value whose type is null as a silent failure*

**G8. Symbol table hash collision** — two distinct names that happen to hash to the same bucket could shadow each other in the symbol table, causing one name to resolve silently to the wrong declaration — *falsifier: use a symbol table implementation that handles collisions correctly (e.g., chaining); write a test with many similarly-named variables; verify each resolves to the correct declaration*

**G9. Location lost after lowering** — IR lowering creates new IR nodes for synthesized operations (e.g., implicit address-of) but forgets to propagate the source location; error messages downstream cite no location — *falsifier: introduce a lowering-level error on a synthesized IR node; verify the error message still cites the original source location*

**G10. Cascading type errors from a single missing import** — if a type from a module is unresolved, every use of that type produces a separate "unknown type" error rather than one root-cause error — *falsifier: remove the definition of a widely-used type; count the resulting errors; the error-sentinel propagation (D3) should suppress cascade errors*

---

## H. Scope Boundaries

**H1. Optimization passes out of scope** — constant folding, dead-code elimination, inlining, loop transformations belong to the middle-end / optimizer, not the front-end; safely excluded — *reason: the task specifies lowering to IR, not optimizing it; re-include only if the task adds "produce optimized IR"*

**H2. Linking out of scope** — resolving references across translation units, library symbol resolution, and relocation belong to the linker, not the front-end — *reason: front-end produces a single module's IR/object; re-include if multi-file compilation is added to the task*

**H3. Runtime library implementation out of scope** — the implementation of built-in functions (e.g., `print`, `malloc`) is out of scope; the front-end generates calls to them by name — *reason: implementation is a separate library; re-include if the task specifies "implement a complete runtime"*

**H4. Garbage collection implementation out of scope** — GC algorithm and collector implementation are out of scope; the front-end may need to annotate GC roots in the IR if the language is GC'd, but the collector itself is not — *reason: GC is a runtime concern; the annotation requirement stays in scope*

**H5. Target-specific ABI detail out of scope** — the full ABI specification (register assignment per type on specific ISAs) is out of scope; the front-end needs calling convention at an abstract level — *reason: ABI is backend / platform-specific; re-include if "targeting a specific ISA" is added*

**H6. Debug information format out of scope** — DWARF, PDB, or other debug-info wire formats are out of scope; source locations in the IR (in scope) are the prerequisite — *reason: format is tool-chain specific; source-location threading remains in scope*

**H7. Macro / metaprogramming system out of scope** — macro expansion, compile-time code generation, and template instantiation are out of scope unless the language spec includes them — *reason: the task says "small statically-typed language" without mentioning macros; re-include if the language spec adds them*

**H8. Separate compilation / module system out of scope** — importing symbols from other compiled units is out of scope; a single-file or single-module compilation model is assumed — *reason: the task does not specify multi-file; re-include if "module system" or "imports" are required*

# GFSO Agent Architecture: The Recursive Unit

**Status:** Technical Standard
**Version:** 2.1 (Recursive Error Handling)
**Context:** Defines the active runtime layer of GFSO.

---

## 1. The Core Abstraction: GFSO Unit

The Agent is composed of recursive instances of a single class: **GFSO Unit**.

**Definition:** A Unit is a tuple $(G, F, \eta)$ operating on a specific Node in the Topology $\mathcal{I}$.

### 1.1. The Duality of Artifacts ($F \to G$)
*   **Terminal Unit (Leaf):** Produces a final artifact (Code, Text).
    *   $F_{leaf}$ is the output.
*   **Structural Unit (Node):** Produces a Plan (DAG).
    *   Its output $F_{parent}$ **BECOMES** the Specification $G_{child}$ for its sub-units.
    *   *Crucial:* If children fail to execute $G_{child}$, it means $F_{parent}$ was flawed.

---

## 2. The Universal Control Loop

Every Unit (whether Architect or Worker) runs the same loop:

```python
def run_unit(self, input_context):
    attempts = 0
    while attempts < MAX_RETRIES:
        # 1. Implementation (F)
        # If Leaf: Generate Code.
        # If Node: Generate DAG and recursively run_unit() for children.
        try:
            artifact = self.implementation(input_context)
            
            # 2. Validation (η)
            # Checks strictly: ε (Quality) and λ (Context Usage)
            if self.validator.check(artifact) == PASS:
                return artifact
                
            # If Fail: Collect feedback
            input_context.add_feedback(self.validator.feedback)
            
        except ChildFailureException as e:
            # 3. Recursive Error Handling
            # A child failed max retries. 
            # This counts as a validation failure for ME (The Parent).
            # Why? Because my Plan (F) turned out to be unimplementable.
            input_context.add_feedback(f"Plan failed: {e}")
            
        attempts += 1
        
    # 4. Collapse
    raise UnitFailureException("Unable to converge")
```

---

## 3. The Metrics ($\epsilon, \lambda$)

The Critic MUST measure two distinct dimensions:

*   **$\\epsilon$ (Epsilon) - Object Error:**
    *   Internal correctness. "Is the code valid? Does the Plan have cycles?"
*   **$\\lambda$ (Laxity) - Morphism Error:**
    *   Contextual integrity. "Did you ignore the previous file? Did the Plan ignore the user prompt?"

---

## 4. Implementation Strategy

1.  **Single Class:** Use one `GFSOUnit` class.
2.  **Polymorphism:** The `implementation` function changes:
    *   For **Planner**: `impl = generate_dag_and_execute_children`
    *   For **Worker**: `impl = generate_code`
3.  **Error Bubbling:** Child failures are caught by Parent and treated as "Bad Attempt", triggering the Parent to Re-plan (Re-generate F).

This fractal architecture eliminates the need for a separate "Replanning Logic". Replanning is just a standard **Retry** of the Parent Unit.

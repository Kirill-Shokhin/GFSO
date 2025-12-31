# GFSO Agent Architecture: Fractal Symmetry

**Version:** 2.2 ("Pragmatic Symmetry")
**Last Updated:** Dec 31, 2025
**Role:** Primary context and handover document for the GFSO runtime.

---

## 1. Evolution & Philosophy

The GFSO Agent has evolved from a theoretical prototype into a self-regulating engineering system. 

### The Lesson of Version 2.1:
Initially, we attempted to force the LLM to "act like a mathematician" (using terms like Kleisli, Epsilon, Morphisms). This led to **"Bureaucratic Hallucination"**, where the Critic would reject perfectly functional code for lacking "categorical proof."

### The V2.2 Solution:
We separated the **Mathematical Structure** (which remains strict in the Python code) from the **Operational Language** (which is now pragmatic). 
- The engine still computes $\epsilon$ and $\lambda$.
- The LLM now simply "performs a code review" and "follows requirements."
This achieved the "Sweet Spot" where the system is mathematically sound but functionally efficient.

---

## 2. Core Architecture: The Recursive Unit

The system is built on a single, fractal abstraction: the **GFSO Unit**.

### 2.1. The Operational Flow
$$ \text{Intent} \xrightarrow{Architect} \text{Blueprint} \xrightarrow{Traversal} \text{Reality} $$

1.  **Architect (Functor G):** Decomposes tasks into a **Blueprint** (DAG + Contracts). 
    *   *Self-Correction:* The creation of the Blueprint is itself a Unit, validated by a Critic to prevent over-engineering.
2.  **Contracts:** Every node in the DAG has an **Object Spec** (what it is) and **Edge Specs** (how it integrates with parents).
3.  **Worker (Functor F):** Executes atomic tasks based on the Contract.
4.  **Validator (Natural Transformation $\eta$):** A mechanical judge comparing Output against Contract.

---

## 3. Codebase Map (Structural Integrity)

The implementation is strictly decoupled to ensure zero hardcode in the logic:

*   **`core.py`:** The Engine. Pure recursive traversal. Orchestrates `GFSOUnit` instances.
*   **`mechanisms.py`:** The Bridge. Implements `Architect`, `Worker`, and `LLMValidator` by inheriting from `gfso` Core classes.
*   **`config.py`:** The Soul. Centralized location for all Prompts, JSON Schemas, and Limits. **Modify here to change agent behavior.**
*   **`logger.py`:** The Eyes. A semantic logger that visualizes the flow of Category Theory without the noise.
*   **`types.py`:** The Constitution. Protocols and interfaces.

---

## 4. Operational Status (v2.2)

- **Multimodality:** Images are supported as global visual context across all units.
- **Reliability:** Structured Outputs (Tools) are used for all control data (Blueprints, Validation metrics).
- **Graceful Failure:** If a unit fails after `MAX_RETRIES`, the pipeline halts and returns a partial result instead of crashing.

---

## 5. Roadmap (Priorities for Next Session)

### 5.1. Priority 1: Contextual DRY (VFS Awareness)
**Current Issue:** The Worker re-implements dependencies (e.g., rewriting `factorial()` in `main.py`) instead of importing them because it sees previous steps as text blobs, not files.
**Solution:** Inject a **Virtual File System** view into the Worker context.
*   *Action:* Update `RuntimeContext` to track filenames/paths.
*   *Action:* Update Worker Prompt to "Import existing modules, do not rewrite."

### 5.2. Priority 2: The Supervisor (Meta-Agent)
**Current Issue:** If the chain fails, the process exits. There is no high-level recovery.
**Solution:** Implement a **Meta-Agent** wrapping `GFSOAgent`.
*   *Role:* "The Face" of the system.
*   *Tasks:* Handle catastrophic failures, summarize results, execute the final code.

---

## 6. Session Handover (Quick Start)

**Current Tuning:** `Pragmatic/Engineering`. The prompts in `config.py` are tuned to suppress "academic" hallucinations. Do not revert to "Math" prompts without testing.

**Verification:**
To verify the system state, run the complex smoke test:
```bash
python smoke_test.py
```
*Expected Result:* A 3-node Blueprint (db -> api -> ui) is generated and validated. Log output should show `BLUEPRINT` structure.

**Real Execution:**
To run a real task with full logging:
```bash
python run_agent.py "Your task here" --verbose --log-file gfso.log
```

**Artifacts:**
All generated code is saved to `output/`. This directory is git-ignored.
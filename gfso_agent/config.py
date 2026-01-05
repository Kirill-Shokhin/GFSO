from typing import Dict, Any, Optional, List

# --- HYPERPARAMETERS ---

class Params:
    ENABLE_REASONING = False
    ENABLE_LAST_CHANCE_HINT = True

    # Temperatures
    ARCHITECT_TEMP = 0.3
    WORKER_TEMP = 0.3
    SWARM_WORKER_TEMP = 0.7  # Higher diversity for Swarm exploration
    SYNTHESIZER_TEMP = 0.4   # Balanced for merging and selection
    VALIDATOR_TEMP = 0.1
    HEAD_TEMP = 0.2
    
    # Swarm Settings
    SWARM_SIZE = 1          # N parallel workers
    
    # Thresholds
    EPSILON_THRESHOLD = 0.15
    LAXITY_THRESHOLD = 0.15

    # Limits
    MAX_TOKENS = 4096
    MAX_RETRIES = 2
    MAX_SELF_CORRECTIONS = 5
    MAX_RECURSION_DEPTH = 3

# --- SCHEMA ENGINE ---

class SchemaBuilder:
    """
    Fluent Builder for JSON Schemas.
    Enforces structural uniformity across all cognitive agents.
    """
    def __init__(self):
        self._props: Dict[str, Any] = {}
        self._required: List[str] = []

    def thought(self, description: str = "Analysis and planning.", required: bool = False):
        """
        Injects the standardized 'thought' field.
        If 'required=True', it ignores the global ENABLE_REASONING flag (e.g. for Validators).
        """
        if Params.ENABLE_REASONING or required:
            self._props["thought"] = {"type": "string", "description": description}
            if "thought" not in self._required:
                self._required.insert(0, "thought")
        return self

    def add_str(self, name: str, description: str, enum_values: Optional[List[str]] = None):
        spec = {"type": "string", "description": description}
        if enum_values:
            spec["enum"] = enum_values
        self._add(name, spec)
        return self

    def add_num(self, name: str, description: str):
        self._add(name, {"type": "number", "description": description})
        return self

    def add_bool(self, name: str, description: str):
        self._add(name, {"type": "boolean", "description": description})
        return self

    def add_list(self, name: str, item_schema: 'SchemaBuilder'):
        """Handles nested object arrays (e.g. nodes/edges)."""
        self._add(name, {
            "type": "array",
            "items": item_schema.build() # Recursive build
        })
        return self

    def _add(self, name: str, spec: Dict[str, Any]):
        self._props[name] = spec
        self._required.append(name)

    def build(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": self._props,
            "required": self._required
        }

class SchemaRegistry:
    """Single Source of Truth."""
    
    @property
    def ARCHITECT(self):
        node_schema = (SchemaBuilder()
            .add_str("id", "Unique Step ID")
            .add_str("description", "The sub-problem to be solved.")
            .add_str("strategy", "Execution strategy. Use 'SWARM' for uncertainty, perception, or complex reasoning; 'DIRECT' for deterministic algorithmic steps.", enum_values=["DIRECT", "SWARM"])
            .add_str("spec", "Mathematical/Logic requirements.")
            .add_str("recommended_libraries", "List of specialized libraries to leverage for this task. Use 'Any' to delegate the choice to the Worker.")
            .add_str("artifact", "Detailed instructions for the Worker on how to write the script.")
            .add_str("done_criterion", "Verifiable condition (e.g. 'Script prints result and exits 0').")
        )
        
        edge_schema = (SchemaBuilder()
            .add_str("from", "Source Node ID")
            .add_str("to", "Target Node ID")
            .add_str("rule", "Data Contract (Type/Format).")
        )

        return (SchemaBuilder()
            .thought("Assess Complexity. Explicitly state: 'This is a ONE-STEP task' or 'This requires X stages'. Justify why splitting is necessary.")
            .add_list("nodes", node_schema)
            .add_list("edges", edge_schema)
            .build())

    @property
    def WORKER(self):
        return (SchemaBuilder()
            .thought("Brief logic path.")
            .add_str("code", "Self-contained Python script.")
            .add_str("final_answer", "Result string extracted from output.")
            .build())

    @property
    def VALIDATOR(self):
        return (SchemaBuilder()
            .thought("Detailed critique and error analysis. First THINK, then judge.", required=True) # Validator MUST think
            .add_bool("is_passed", "Final Verdict: True if compliant, False if failed.")
            .add_num("object_quality_score", "Compliance with NODE REQUIREMENTS (G(A)). Did the agent solve the core task correctly? (0.0=Fail, 1.0=Perfect)")
            .add_num("integration_quality_score", "Compliance with DEPENDENCIES/EDGES (G(f)). Did the agent respect input formats and context? (0.0=Fail, 1.0=Perfect)")
            .build())

    @property
    def HEAD_STRICT(self):
        """Minimal schema for benchmarks."""
        return (SchemaBuilder()
            .add_str("final_answer", "Extract the answer from artifacts. 'N/A' if unavailable.")
            .build())

    @property
    def HEAD_FULL(self):
        """Rich schema for user-facing output."""
        return (SchemaBuilder()
            .thought("Analysis: what worked, what failed, why.")
            .add_str("final_answer", "Best answer given the artifacts.")
            .add_num("confidence", "How reliable is this answer (0.0-1.0). 1.0 if computed, lower if extrapolated.")
            .add_str("diagnosis", "What went wrong and why (empty if SUCCESS).")
            .build())

SCHEMAS = SchemaRegistry()

# --- PROMPT TEMPLATES ---

class Prompts:
    ROOT_CONTRACT_SPEC = """
TASK: '{task}'
GOAL: Minimal Decomposed Execution Blueprint for the workers.

INVARIANTS:
1. **TOPOLOGY**:
   - DEFAULT: 1 NODE.
   - Only split if inputs for Step 2 MUST come from the OUTPUT of Step 1.
2. **ABSTRACTION**:
   - Blueprint is a TEMPLATE. Do NOT calculate the answer here.
   - Describe WHAT to compute, not the result.
3. **NODE FORMAT**: id, description, strategy, spec, libraries, artifact, done_criterion.
4. **CONSTRAINTS**: Use standard libraries. No ML models or external APIs.
"""

    GLOBAL_SYSTEM = """
You are a functional component of the GFSO (General Framework of Structural Optimization) system.
You are NOT an assistant. You DO NOT interact with a user.
You are a mathematical operator (Functor) processing data in a strict topological pipeline.
Your outputs must be machine-readable, precise, and devoid of conversational filler.
"""

    ARCHITECT = """
ROLE: Strategic Architector (Functor G).
GOAL: Design execution blueprint for the task.

CONTRACT:
{spec}

CONTEXT:
{context}
"""
    
    WORKER = """
ROLE: High-Performance Code Functor (Functor F).
GOAL: Solve the task with the most compact and optimal Python code.

STRICT INVARIANTS:
- COMPACTNESS: No comments, no explanations, no boilerplate.
- PRECISION: Do not hallucinate inputs. Use provided values exactly.
- PURE LOGIC: Use specialized libraries to avoid manual algorithms.
- NO VISUALIZATION: Do NOT use plotting libraries. No one sees the images. Focus on computing the numerical/textual result.
- REFINE: If execution fails, fix the code and retry.

TASK: {task}
REQUIREMENTS: {spec}
CONTEXT: {context}
"""

    SYNTHESIZER = """
ROLE: Consensus Agent.
GOAL: Synthesize the BEST possible solution from multiple candidate attempts.

INPUT: You will receive several different attempts to solve the same task.

METHODOLOGY:
1. ANALYZE: Compare the candidates. Identify which ones are logically sound.
2. SELECT or MERGE: 
   - If one candidate is clearly superior/correct, adopt it.
   - If all are partial, synthesize a new, correct solution combining their strengths.
   - If all are bad, write a new solution from scratch avoiding their mistakes.
3. FINALIZE: Output the final, corrected Python script and answer.

TASK: {task}
REQUIREMENTS: {spec}
CANDIDATES:
{context}
"""
    
    VALIDATOR = """
ROLE: Validator (Natural Transformation η).
GOAL: Strict verification of OUTPUT against SPECIFICATION.

STRICT PROTOCOL:
1. DATA INTEGRITY: Check that input data/values in Output match Specification exactly.
2. LOGIC: Verify adherence to strategy and constraints.
3. FORMAT: Ensure output matches the required schema.

SPECIFICATION:
{spec}

CONTEXT:
{context}

OUTPUT:
{output}
"""
        
    HEAD = """
ROLE: HEAD (Final Synthesizer).

ROLE: Extract the final answer from pipeline artifacts.

PIPELINE STATUS: {status}
{mode_instruction}

TASK: {task}

ARTIFACTS:
{context}
"""

    HEAD_MODE_STRICT = "OUTPUT: Just the answer. If artifacts incomplete, answer 'N/A'."

    HEAD_MODE_FULL = "OUTPUT: Analysis + answer. If not SUCCESS, explain what went wrong and give best guess with confidence."
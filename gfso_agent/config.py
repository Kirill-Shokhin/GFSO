from typing import Dict, Any, Optional, List

# --- HYPERPARAMETERS ---

class Params:
    ENABLE_REASONING = False
    ENABLE_LAST_CHANCE_HINT = True
    ENABLE_WEB_SEARCH = True
    ENABLE_HEAD_RETRY = True  # Re-run pipeline with hints from Head on FAILED/PARTIAL

    # Temperatures
    ARCHITECT_TEMP = 0.3
    WORKER_TEMP = 0.3
    SWARM_WORKER_TEMP = 0.7  # Higher diversity for Swarm exploration
    SYNTHESIZER_TEMP = 0.4   # Balanced for merging and selection
    VALIDATOR_TEMP = 0.1
    HEAD_TEMP = 0.2

    # Swarm Settings
    SWARM_SIZE = 3          # N parallel workers

    # Thresholds
    EPSILON_THRESHOLD = 0.15
    LAXITY_THRESHOLD = 0.15
    CONFIDENCE_THRESHOLD = 0.9  # Minimum confidence to accept answer (for benchmarks)

    # Limits
    MAX_TOKENS = 4096
    MAX_RETRIES = 2
    MAX_SELF_CORRECTIONS = 5
    MAX_HEAD_RETRIES = 1  # Global retries with Head feedback

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
            .add_str("strategy", "DIRECT: deterministic. SWARM: uncertainty/perception. SEARCH: web research for obscure facts.", enum_values=["DIRECT", "SWARM", "SEARCH"])
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
            .build())

    @property
    def VALIDATOR(self):
        return (SchemaBuilder()
            .thought("Detailed critique and error analysis. First THINK, then judge.", required=True) # Validator MUST think
            .add_num("object_quality_score", "Compliance with NODE REQUIREMENTS (G(A)). Did the agent solve the core task correctly? (0.0=Fail, 1.0=Perfect)")
            .add_num("integration_quality_score", "Compliance with DEPENDENCIES/EDGES (G(f)). Did the agent respect input formats and context? (0.0=Fail, 1.0=Perfect)")
            .build())

    @property
    def HEAD(self):
        """Schema for HEAD final synthesis."""
        return (SchemaBuilder()
            .thought("Analysis: what worked, what failed, why.")
            .add_str("final_answer", "The final answer. Provide best short answer based on artifacts.")
            .add_num("confidence", "1.0 if pipeline SUCCESS (answer extracted from artifacts). <1.0 only if FAILED/PARTIAL (guessing from incomplete data).")
            .add_str("refinement", "Conceptual insight derived from the execution artifacts to refine the initial problem statement. Isolates missing domain context or crucial constraints required for a successful re-run. Empty if SUCCESS.")
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
   - **NO META-PLANNING**: Nodes must be executable calculations, not planning steps.
   - **PERCEPTION FIRST**: If image is present, Step 1 MUST be 'Image Analysis' to extract data.
   - **SEARCH FIRST**: If task requires obscure theorems/facts, prepend a SEARCH node. Its output becomes context for analysis nodes.
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
- **OUTPUT**: The script MUST end with a `print()` statement to output the final result.
- **SILENCE**: Do NOT print debug messages. STDOUT must contain ONLY the final result.
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
2. CONTEXT CONSISTENCY: Verify that the Output matches the facts provided in the CONTEXT (Dependencies). Do not accept hallucinations that contradict the Context.
3. LOGIC: Verify adherence to strategy and constraints.
4. FORMAT: Ensure output matches the required schema.

SPECIFICATION:
{spec}

CONTEXT:
{context}

OUTPUT:
{output}
"""
        
    HEAD = """
ROLE: HEAD (Final Synthesizer).
GOAL: Extract the final answer from pipeline artifacts.

PIPELINE STATUS: {status}
TASK: {task}

ARTIFACTS:
{context}
"""
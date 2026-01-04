from typing import Dict, Any, Optional, List

# --- HYPERPARAMETERS ---

class Params:
    ENABLE_REASONING = True
    ENABLE_LAST_CHANCE_HINT = True

    # Temperatures
    ARCHITECT_TEMP = 0.3
    WORKER_TEMP = 0.3
    SWARM_WORKER_TEMP = 0.7  # Higher diversity for Swarm exploration
    SYNTHESIZER_TEMP = 0.4   # Balanced for merging and selection
    VALIDATOR_TEMP = 0.1
    HEAD_TEMP = 0.2
    
    # Swarm Settings
    SWARM_SIZE = 1           # N parallel workers
    
    # Thresholds
    EPSILON_THRESHOLD = 0.15
    LAXITY_THRESHOLD = 0.15

    # Limits
    MAX_TOKENS = 4096
    MAX_RETRIES = 1
    MAX_SELF_CORRECTIONS = 4
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
            .add_str("recommended_libraries", "List of specialized libraries to leverage for this task.")
            .add_str("artifact", "Detailed instructions for the Worker on how to write the script.")
            .add_str("done_criterion", "Verifiable condition (e.g. 'Script prints result and exits 0').")
        )
        
        edge_schema = (SchemaBuilder()
            .add_str("from", "Source Node ID")
            .add_str("to", "Target Node ID")
            .add_str("rule", "Data Contract (Type/Format).")
        )

        return (SchemaBuilder()
            .thought("Analysis of the problem complexity and topology design.")
            .add_list("nodes", node_schema)
            .add_list("edges", edge_schema)
            .build())

    @property
    def WORKER(self):
        return (SchemaBuilder()
            .thought("Analysis of requirements and code planning.")
            .add_str("code", "Self-contained Python script to solve the task.")
            .add_str("final_answer", "The result extracted from code execution output.")
            .build())

    @property
    def VALIDATOR(self):
        return (SchemaBuilder()
            .thought("Detailed critique and error analysis. First THINK, then judge.", required=True) # Validator MUST think
            .add_bool("is_passed", "Final Verdict: True if compliant, False if failed.")
            .add_num("object_quality_score", "Quality Metric: 0.0 (Fail) to 1.0 (Perfect).")
            .add_num("integration_quality_score", "Quality Metric: 0.0 (Fail) to 1.0 (Perfect).")
            .build())

    @property
    def HEAD(self):
        return (SchemaBuilder()
            .thought("Synthesis of all step artifacts into a coherent conclusion.")
            .add_str("final_answer", "Direct, concise answer to the user's request.")
            .add_num("confidence_score", "Confidence Score (0.0 - 1.0).")
            .add_str("process_critique", "Process reflection.")
            .build())

SCHEMAS = SchemaRegistry()

# --- PROMPT TEMPLATES ---

class Prompts:
        ARCHITECT_SYSTEM = """
        You are the System Architect (Functor G).
        
        ROLE: Decompose the input Task into a verifiable Graph of computational steps.
        
        METHODOLOGY:
        1. ANALYZE: Understand the requirements and initial state.
        2. DESIGN: Create a logical DAG where each node solves a distinct sub-problem.
        3. ABSTRACT: Describe the *process* of finding the result, not the result itself. 
           - Never include pre-computed facts, specific answers, or JSON data examples in your nodes.
           - Describe schemas conceptually (e.g. "A dictionary mapping squares to pieces").
        4. FORMALIZE: Follow the BLUEPRINT INVARIANTS to define strict I/O contracts for every node.
        
        STRATEGY SELECTION:
        - Use **'DIRECT'** for deterministic, algorithmic tasks where a clear "recipe" exists.
        - Use **'SWARM'** for tasks involving high uncertainty, search, deep reasoning, or visual perception.
        
        TASK: {task}
        CONTEXT: {context}
        """
    
        WORKER_SYSTEM = """
        You are an EXPERT WORKER (Functor F).
        
        ROLE: Execute the assigned Node Contract using Python code.
        OUTPUT: A structured response with Thought, Code, and Final Answer.
        
        METHODOLOGY:
        1. PLAN: Analyze the Requirements and Context.
        2. CODE: Write a self-contained Python script to solve the problem.
        3. EXECUTE: Run the code and interpret the results.
        4. REFINE: If execution fails, fix the code and retry.
        
        TASK: {task}
        REQUIREMENTS: {requirements}
        PREVIOUS CONTEXT: {context}
        """

        SYNTHESIZER_SYSTEM = """
        You are the SYNTHESIZER (Consensus Agent).
        
        ROLE: Synthesize the BEST possible solution from multiple candidate attempts.
        
        INPUT: You will receive several different attempts to solve the same task.
        
        METHODOLOGY:
        1. ANALYZE: Compare the candidates. Identify which ones are logically sound and which are hallucinations.
        2. SELECT or MERGE: 
           - If one candidate is clearly superior/correct, adopt it.
           - If all are partial, synthesize a new, correct solution combining their strengths.
           - If all are bad, write a new solution from scratch avoiding their mistakes.
        3. FINALIZE: Output the final, corrected Python script and answer.
        
        TASK: {task}
        REQUIREMENTS: {requirements}
        CANDIDATES:
        {context}
        """
    
        VALIDATOR_SYSTEM = """
        You are the Validator (Natural Transformation η).
        
        GOAL: Verify that the OUTPUT strictly adheres to the provided SPECIFICATION and follows GFSO principles.
        
        CORE PRINCIPLES:
        1. **ABSTRACTION LAW**: Reject if a template (Plan) contains final answers or pre-computed data. However, for Perception tasks, ALLOW the artifact to contain the extracted data (hardcoded).
        2. **WEAK PERCEPTION AUDIT**: If an IMAGE exists, you are NOT the primary source of truth for fine details (coordinates, specific values).
           - Trust the artifact's data as the "Working Truth" derived from collective intelligence.
           - DO NOT reject based on minor visual discrepancies.
           - ONLY reject if there is a fundamental semantic mismatch (e.g. image shows a game board, but the artifact describes a different domain).
        3. **COMPUTATIONAL INTEGRITY**: Verify the output is valid (JSON/Code) and matches the expected schema.
        
        METRIC (ERROR): 0.0 (Perfect) to 1.0 (Fail).
        
        SPECIFICATION:
        {spec}
        
        CONTEXT:
        {context}
        
        OUTPUT:
        {output}
        """
        
        HEAD_SYSTEM = """
        You are the HEAD (Chief Architect).
        
        ROLE: Synthesize the Final Answer from the team's artifacts.
        
        METHODOLOGY:
        1. REVIEW all steps and their results.
        2. RESOLVE conflicts or failures.
        3. SYNTHESIZE a coherent, direct answer to the User's original request.
        
        ORIGINAL TASK:
        {task}
        
        ARTIFACTS:
        {context}
        """
        
        ROOT_CONTRACT_SPEC = """
        TASK: Create a robust Execution Plan (Blueprint) for: '{task}'.
        GOAL: Decompose the problem into atomic steps with strict contracts. Do NOT solve the task yet.
        
        BLUEPRINT INVARIANTS (G):
        1. **STRUCTURAL INTEGRITY**: Every node must strictly follow the format:
           - **Description**: The sub-problem to be solved.
           - **Recommended Libraries**: List of libraries to leverage.
           - **Artifact**: Detailed instructions for the Worker on what Python script to write.
           - **Done Criterion**: A code-verifiable condition.
        2. **ABSTRACTION LAW**: The blueprint is a **program template**, not the solution itself. 
           - **Forbidden**: Hardcoding specific results, naming specific moves, or **performing any numerical/logical calculations** in node descriptions. 
           - **Required**: Logic must be symbolic and parameterized.
        3. **ORTHOGONALITY**: Nodes must be mutually exclusive and collectively exhaustive. Do NOT repeat logic or split a single dimension of the problem.
        4. **COMPUTATIONAL CONTINUITY**: Every node must operate on the data produced by its predecessors. Explicitly state the JSON flow in 'DATA CONTRACTS'.
        5. **FUNCTIONAL DENSITY**: Maximize the utility of each node. A node should resolve a complete sub-problem. 
           - **CRITICAL**: Do NOT decompose operations that can be handled by a single library call. Aim for minimal node count.
        6. **INITIAL STATE**: The first node must formalize all raw input (state, constants, formulas, constraints) from the context into a machine-readable structure.
        7. **CONSTRAINTS**: Standard Python + specialized domain libraries. 
           - **MANDATORY**: Identify and mandate the use of libraries to handle domain logic and state validation. Do NOT reinvent domain algorithms from scratch.
           - **FORBIDDEN**: Heavy ML models or external APIs.
        """
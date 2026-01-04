from typing import Dict, Any

# --- HYPERPARAMETERS & LIMITS ---

class Params:
    ARCHITECT_TEMP = 0.3
    WORKER_TEMP = 0.3
    VALIDATOR_TEMP = 0.1
    HEAD_TEMP = 0.2
    
    EPSILON_THRESHOLD = 0.15  # Object Error Limit (0.0 = Perfect)
    LAXITY_THRESHOLD = 0.15   # Morphism Error Limit (0.0 = Perfect)

    MAX_TOKENS = 4096
    MAX_RETRIES = 1 # External (Validator) Retries
    MAX_SELF_CORRECTIONS = 3 # Internal (Executor) Retries
    MAX_RECURSION_DEPTH = 3
    
    ENABLE_LAST_CHANCE_HINT = True

# --- JSON SCHEMAS ---

class Schemas:
    ARCHITECT_OUTPUT = {
        "type": "object",
        "properties": {
            "thought_trace": {"type": "string", "description": "Analysis of the problem complexity and topology design."},
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "strategy": {"type": "string", "enum": ["PYTHON"]},
                        "spec": {"type": "string", "description": "Mathematical/Logic requirements."},
                        "artifact": {"type": "string", "description": "Explicit instruction for the Python script to write (e.g. 'SymPy script to compute abelianization')."},
                        "done_criterion": {"type": "string", "description": "Verifiable condition (e.g. 'Script prints result and exits 0')."}
                    },
                    "required": ["id", "description", "spec", "artifact", "done_criterion"]
                }
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "rule": {"type": "string", "description": "Data Contract (Type/Format)."}
                    },
                    "required": ["from", "to", "rule"]
                }
            }
        },
        "required": ["thought_trace", "nodes", "edges"]
    }

    # Validator SGR: Critique -> Verdict -> Score
    VALIDATOR_OUTPUT = {
        "type": "object",
        "properties": {
            "critique": {"type": "string", "description": "Detailed analysis. First THINK, then judge."},
            "is_passed": {"type": "boolean", "description": "Final Verdict: True if compliant, False if failed."},
            "object_quality_score": {"type": "number", "description": "Quality Metric: 0.0 (Fail) to 1.0 (Perfect)."},
            "integration_quality_score": {"type": "number", "description": "Quality Metric: 0.0 (Fail) to 1.0 (Perfect)."}
        },
        "required": ["critique", "is_passed", "object_quality_score", "integration_quality_score"]
    }

    WORKER_OUTPUT = {
        "type": "object",
        "properties": {
            "thought": {"type": "string", "description": "Analysis of requirements and code planning."},
            "code": {"type": "string", "description": "Self-contained Python script to solve the task."},
            "final_answer": {"type": "string", "description": "The result extracted from code execution output."}
        },
        "required": ["thought", "code"]
    }

    HEAD_OUTPUT = {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string", "description": "Synthesis of all step artifacts into a coherent conclusion."},
            "final_answer": {"type": "string", "description": "Direct, concise answer to the user's request."},
            "confidence_score": {"type": "number"},
            "process_critique": {"type": "string"}
        },
        "required": ["reasoning", "final_answer", "confidence_score"]
    }

# --- PROMPT TEMPLATES ---

class Prompts:
        ARCHITECT_SYSTEM = """
        You are the System Architect (Functor G).
        
        ROLE: Decompose the input Task into a verifiable Graph of computational steps.
        
        METHODOLOGY:
        1. ANALYZE: Understand the requirements and initial state.
        2. DESIGN: Create a logical DAG where each node solves a distinct sub-problem.
        3. ABSTRACT: Describe the *process* of finding the result, not the result itself. Never include pre-computed facts or specific answers in your nodes.
        4. FORMALIZE: Follow the BLUEPRINT INVARIANTS to define strict I/O contracts for every node.
        
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
    
        VALIDATOR_SYSTEM = """
        You are the Validator (Natural Transformation η).
        
        GOAL: Verify that the OUTPUT strictly adheres to the BLUEPRINT INVARIANTS.
        
        CHECKS:
        1. **ABSTRACTION LAW**: Reject if the plan contains specific answers (moves, numbers, final results) that should be computed by the Worker. The plan must be a TEMPLATE.
        2. **COMPUTATIONAL INTEGRITY**: Does every node produce a verifiable computational artifact (JSON/Code)? Are pure text descriptions rejected?
        3. **DATA FLOW**: Is the transition between nodes clearly defined by data structures?
        4. **SPOT CHECK**: If an IMAGE exists, verify that the first node correctly captures its INITIAL STATE.
        
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
        Create an execution plan for: '{task}'.
        
        BLUEPRINT INVARIANTS (G):
        1. **STRUCTURAL INTEGRITY**: Every node must strictly follow the format:
           - **Description**: The sub-problem to be solved.
           - **Artifact**: A Python script (using allowed libraries) that implements the solution logic and outputs JSON.
           - **Done Criterion**: A code-verifiable condition (e.g., exit code 0 + specific JSON keys).
        2. **ABSTRACTION LAW**: The blueprint is a **program template**, not the solution itself. 
           - **Forbidden**: Hardcoding specific results, naming specific moves, or **performing any numerical/logical calculations** in node descriptions. 
           - **Required**: Logic must be symbolic and parameterized. Use variables (e.g. 'VAR_X', 'RANK_V') and general formulas (e.g. 'E - V + 1') instead of specific values.
        3. **ORTHOGONALITY**: Nodes must be mutually exclusive and collectively exhaustive. Do NOT repeat logic or split a single dimension of the problem (e.g., "Parse State" and "Parse Rules" should be merged into "Formalize Input").
        4. **COMPUTATIONAL CONTINUITY**: Every node must operate on the data produced by its predecessors. Explicitly state the JSON flow in 'DATA CONTRACTS'.
        5. **FUNCTIONAL DENSITY**: Maximize the utility of each node. A node should resolve a complete sub-problem. Do not split atomic algorithms or logical chains.
        6. **INITIAL STATE**: The first node must formalize all raw input (state, constants, formulas, constraints) from the context into a machine-readable structure.
        7. **CONSTRAINTS**: Standard Python + NumPy, Pandas, SymPy, SciPy, NetworkX, python-chess, Pillow. No heavy ML or external APIs.
        """
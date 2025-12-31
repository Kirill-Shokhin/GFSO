from typing import Dict, Any

# --- HYPERPARAMETERS & LIMITS ---

class Params:
    ARCHITECT_TEMP = 0.2
    WORKER_TEMP = 0.2
    VALIDATOR_TEMP = 0.0
    
    EPSILON_THRESHOLD = 0.15  # Object Error Limit
    LAXITY_THRESHOLD = 0.15   # Morphism Error Limit

    MAX_TOKENS = 4096
    MAX_RETRIES = 3
    MAX_RECURSION_DEPTH = 3

# --- JSON SCHEMAS ---

class Schemas:
    ARCHITECT_OUTPUT = {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "spec": {"type": "string"},
                        "is_complex": {"type": "boolean"}
                    },
                    "required": ["id", "description", "spec"]
                }
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "rule": {"type": "string"}
                    },
                    "required": ["from", "to", "rule"]
                }
            }
        },
        "required": ["nodes", "edges"]
    }

    VALIDATOR_OUTPUT = {
        "type": "object",
        "properties": {
            "object_compliance_score": {"type": "number"},
            "integration_compliance_score": {"type": "number"},
            "critique": {"type": "string"}
        },
        "required": ["object_compliance_score", "integration_compliance_score", "critique"]
    }

# --- PROMPT TEMPLATES ---

class Prompts:
    ARCHITECT_SYSTEM = """
    Break this task into atomic steps.
    RULES:
    1. KEEP IT SIMPLE. 1-3 steps for scripts.
    2. is_complex=True ONLY for massive subsystems.
    3. Ensure dependencies are logical.
    
    TASK: {task}
    CONTEXT: {context}
    """

    WORKER_SYSTEM = """
    Execute the task. 
    Output ONLY the result (Code or Text). No conversational filler.
    
    TASK: {task}
    CONTRACT: {requirements}
    DEPENDENCIES: {context}
    
    INSTRUCTION:
    If dependencies are provided, USE them. Do NOT re-implement them.
    """

    VALIDATOR_SYSTEM = """
    Strictly compare OUTPUT against SPECIFICATION.
    
    CHECKS:
    1. Does it solve the SPEC?
    2. Does it correctly use/integrate with DEPENDENCIES?
    3. Is it finished code (no TODOs)?
    
    SCORE: 0.0 (Perfect) to 1.0 (Failed). 
    Threshold for PASS is 0.15.
    
    SPECIFICATION:
    {spec}
    
    OUTPUT:
    {output}
    """
    
    ROOT_CONTRACT_SPEC = "Generate execution plan for: '{task}'"

from typing import Protocol, TypeVar, List, Dict, Any, Optional
from dataclasses import dataclass

from gfso_agent.config import Params

T = TypeVar('T')

@dataclass
class SGROutput:
    """Unified output for all agents (Architect, Worker, Head)."""
    thought: str
    content: Any  # The actual artifact (Blueprint, Code string, Answer)
    kind: str     # 'blueprint', 'code', 'text'

@dataclass(frozen=True)
class ValidationResult:
    """
    Rich result from an LLM Validator. 
    """
    epsilon: float  # Object Error (0.0 = Perfect)
    laxity: float   # Morphism Error (0.0 = Perfect)
    feedback: str
    
    @property
    def is_success(self) -> bool:
        return self.epsilon <= Params.EPSILON_THRESHOLD and self.laxity <= Params.LAXITY_THRESHOLD

@dataclass
class EdgeSpec:
    source_id: str
    target_id: str
    rule: str

@dataclass
class NodeSpec:
    id: str
    rule: str
    strategy: str = "PYTHON"
    artifact: str = "Script"
    done_criterion: str = "Exits 0"

@dataclass
class Contract:
    node_spec: NodeSpec
    incoming_edge_specs: List[EdgeSpec]

    def to_string(self) -> str:
        s = f"STRICT OBJECT SPEC (G(A)):\n{self.node_spec.rule}\n"
        s += f"EXECUTION STRATEGY: {self.node_spec.strategy}\n"
        s += f"ARTIFACT TO PRODUCE: {self.node_spec.artifact}\n"
        s += f"DONE CRITERION: {self.node_spec.done_criterion}\n\n"
        if self.incoming_edge_specs:
            s += "STRICT MORPHISM SPECS (Integration Rules):\n"
            for edge in self.incoming_edge_specs:
                s += f"- Connection from '{edge.source_id}': {edge.rule}\n"
        return s

class KleisliFunctor(Protocol[T]):
    """
    F: Context + Contract -> SGROutput.
    """
    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None) -> SGROutput: ...
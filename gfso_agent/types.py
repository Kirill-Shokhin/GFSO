from typing import Protocol, TypeVar, List, Dict, Any, Optional
from dataclasses import dataclass

T = TypeVar('T')

@dataclass(frozen=True)
class ValidationResult:
    """
    Rich result from an LLM Validator. 
    """
    epsilon: float  # Object Error 
    laxity: float   # Morphism Error
    feedback: str
    
    @property
    def is_success(self) -> bool:
        return self.epsilon < 0.15 and self.laxity < 0.15

@dataclass
class EdgeSpec:
    source_id: str
    target_id: str
    rule: str

@dataclass
class NodeSpec:
    id: str
    rule: str

@dataclass
class Contract:
    node_spec: NodeSpec
    incoming_edge_specs: List[EdgeSpec]

    def to_string(self) -> str:
        s = f"STRICT OBJECT SPEC (G(A)):\n{self.node_spec.rule}\n\n"
        if self.incoming_edge_specs:
            s += "STRICT MORPHISM SPECS (Integration Rules):\n"
            for edge in self.incoming_edge_specs:
                s += f"- Connection from '{edge.source_id}': {edge.rule}\n"
        return s

class KleisliFunctor(Protocol[T]):
    """
    F: Context + Contract -> Artifact.
    Enriched Kleisli Morphism with Context and Images.
    """
    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None) -> T: ...
from typing import Protocol, TypeVar, List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from gfso.core.graph import TaskDAG
from gfso_agent.config import Params


class HeadMode(Enum):
    """HEAD operation modes."""
    STRICT = "strict"  # Minimal output: answer + confidence (for benchmarks)
    FULL = "full"      # Rich output: analysis, speculation, retry feedback (for users)


@dataclass
class HeadResult:
    """Unified HEAD output."""
    answer: str
    status: str                            # "SUCCESS" | "PARTIAL" | "FAILED" - computed by core
    # FULL mode only
    confidence: Optional[float] = None     # How reliable (1.0 if computed, lower if guess)
    thought: Optional[str] = None          # Analysis
    diagnosis: Optional[str] = None        # What went wrong (empty if SUCCESS)

T = TypeVar('T')

class StepFailure(Exception):
    def __init__(self, step_id: str, feedback: str):
        self.step_id = step_id
        self.feedback = feedback
        super().__init__(f"Step '{step_id}' failed: {feedback}")

@dataclass
class StepMetrics:
    step_id: str
    role: str          # 'Architect', 'Worker'
    strategy: str = "DIRECT"
    validator_retries: int = 0
    self_corrections: int = 0
    status: str = "PENDING"

@dataclass
class RuntimeContext:
    original_task: str
    images: Optional[List[str]] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    feedback_log: Dict[str, List[str]] = field(default_factory=dict)
    metrics: Dict[str, StepMetrics] = field(default_factory=dict)

    def get_metric(self, step_id: str, role: str) -> StepMetrics:
        if step_id not in self.metrics:
            self.metrics[step_id] = StepMetrics(step_id, role)
        return self.metrics[step_id]

    def get_context_for_step(self, step_id: str, deps: List[str]) -> str:
        ctx = ""
        for d in deps:
            if d in self.artifacts:
                ctx += f"\n<dependency id='{d}'>\n{self.artifacts[d]}\n</dependency>"
        if step_id in self.feedback_log:
            ctx += f"\n<history>\n{str(self.feedback_log[step_id])}\n</history>"
        return ctx

    def record_feedback(self, step_id: str, fb: str):
        if step_id not in self.feedback_log:
            self.feedback_log[step_id] = []
        self.feedback_log[step_id].append(fb)

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
    # metadata holds ALL dynamic fields from the Schema (spec, strategy, artifact, etc.)
    metadata: Dict[str, Any]

@dataclass
class Contract:
    node_spec: NodeSpec
    incoming_edge_specs: List[EdgeSpec]

    def to_string(self) -> str:
        # Dynamic dump of the Schema fields
        # This makes types.py independent of config.py changes
        s = "REQUIREMENTS:\n"

        for key, value in self.node_spec.metadata.items():
            if key == 'id': continue # Skip ID as it's metadata
            # Format key: 'done_criterion' -> 'Done Criterion'
            pretty_key = key.replace('_', ' ').title()
            s += f"- {pretty_key}: {value}\n"
        
        s += "\nDEPENDENCIES (INPUTS):\n"
        if self.incoming_edge_specs:
            for edge in self.incoming_edge_specs:
                s += f"- From '{edge.source_id}': {edge.rule}\n"
        else:
            s += "(None)\n"
            
        return s.strip()

class Blueprint:
    """The Artifact produced by the Architect."""
    def __init__(self, dag: TaskDAG, edge_specs: List[EdgeSpec]):
        self.dag = dag
        self.edge_specs = edge_specs

    def get_contract_for_node(self, node_id: str) -> Contract:
        node = self.dag.get_task(node_id)
        incoming = [e for e in self.edge_specs if e.target_id == node_id]
        
        return Contract(
            node_spec=NodeSpec(
                id=node_id,
                metadata=node.metadata
            ),
            incoming_edge_specs=incoming
        )
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'Blueprint':
        """Constructs a Blueprint from a raw JSON dict."""
        dag = TaskDAG(state_metric=None)
        edge_specs = []

        raw_nodes = data.get('nodes', [])
        if not isinstance(raw_nodes, list):
            raise ValueError(f"Blueprint JSON Error: 'nodes' must be a list, got {type(raw_nodes)}")
            
        for node in raw_nodes:
            if not isinstance(node, dict): continue
            node_id = node.get('id', 'unknown')
            meta = node.copy()
            if 'id' in meta: del meta['id']
            
            dag.add_task(
                task_id=node_id,
                implementation=None, specification=None, validator=None,
                metadata=meta
            )

        raw_edges = data.get('edges', [])
        if not isinstance(raw_edges, list):
            raise ValueError(f"Blueprint JSON Error: 'edges' must be a list, got {type(raw_edges)}")

        for edge in raw_edges:
            if not isinstance(edge, dict): continue
            src = edge.get('from')
            dst = edge.get('to')
            if src and dst:
                dag.add_dependency(src, dst)
                edge_specs.append(EdgeSpec(source_id=src, target_id=dst, rule=edge.get('rule', '')))

        return cls(dag, edge_specs)

    def __str__(self) -> str:
        s = "BLUEPRINT:\n  [NODES]:\n"
        try:
            order = self.dag.get_topological_order()
        except:
            order = list(self.dag.tasks.keys())
            
        for t_id in order:
             task = self.dag.get_task(t_id)
             s += f"    • NODE ID: {t_id}\n"
             
             for key, val in task.metadata.items():
                 pretty_key = key.replace('_', ' ').title()
                 val_str = str(val).replace('\n', '\n        ')
                 s += f"      {pretty_key}: {val_str}\n"
             s += "\n"
                 
        s += "  [DEPENDENCIES]:\n"
        if not self.edge_specs: s += "    (None)\n"
        for edge in self.edge_specs:
             s += f"    • {edge.source_id} → {edge.target_id} ({edge.rule})\n"
        return s.strip()

class KleisliFunctor(Protocol[T]):
    """
    F: Context + Contract -> SGROutput.
    """
    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None, temperature: Optional[float] = None) -> SGROutput: ...
from typing import Protocol, TypeVar, List, Dict, Any, Optional
from dataclasses import dataclass, field

from gfso.core.graph import TaskDAG
from gfso_agent.config import Params

T = TypeVar('T')

class StepFailure(Exception):
    def __init__(self, step_id: str, feedback: str):
        self.step_id = step_id
        self.feedback = feedback
        super().__init__(f"Step '{step_id}' failed: {feedback}")

@dataclass
class RuntimeContext:
    original_task: str
    images: Optional[List[str]] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    feedback_log: Dict[str, List[str]] = field(default_factory=dict)

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
    rule: str
    strategy: str = "DIRECT"
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
                rule=node.metadata['spec'],
                strategy=node.metadata.get('strategy', 'DIRECT'),
                artifact=node.metadata.get('artifact', 'Script'),
                done_criterion=node.metadata.get('done_criterion', 'Exits 0')
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
            dag.add_task(
                task_id=node_id,
                implementation=None, specification=None, validator=None,
                metadata={
                    'spec': node.get('spec', 'No Spec'), 
                    'description': node.get('description', 'No Desc'),
                    'strategy': node.get('strategy', 'DIRECT'),
                    'artifact': node.get('artifact', 'Python script'),
                    'done_criterion': node.get('done_criterion', 'Script returns True')
                }
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
             strat = f"[{task.metadata.get('strategy', '???')}]"
             s += f"    • {t_id:<20} {strat:<12} : {task.metadata['description']}\n"
             s += f"      Artifact: {task.metadata.get('artifact', 'N/A')}\n"
             s += f"      Done:     {task.metadata.get('done_criterion', 'N/A')}\n"
        s += "\n  [DEPENDENCIES]:\n"
        if not self.edge_specs: s += "    (None)\n"
        for edge in self.edge_specs:
             s += f"    • {edge.source_id} → {edge.target_id} ({edge.rule})\n"
        return s

class KleisliFunctor(Protocol[T]):
    """
    F: Context + Contract -> SGROutput.
    """
    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None, temperature: Optional[float] = None) -> SGROutput: ...
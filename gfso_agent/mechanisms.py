import json
from typing import Any, Dict, List, Optional

from gfso.core.graph import TaskDAG
from gfso.contract.validator import Validator
from gfso.core.kleisli import Distribution

from gfso_agent.llm import LLMInterface
from gfso_agent.types import KleisliFunctor, Contract, NodeSpec, EdgeSpec, ValidationResult
from gfso_agent.config import Params, Schemas, Prompts

class Blueprint:
    """The Artifact produced by the Architect."""
    def __init__(self, dag: TaskDAG, edge_specs: List[EdgeSpec]):
        self.dag = dag
        self.edge_specs = edge_specs

    def get_contract_for_node(self, node_id: str) -> Contract:
        node = self.dag.get_task(node_id)
        incoming = [e for e in self.edge_specs if e.target_id == node_id]
        return Contract(
            node_spec=NodeSpec(id=node_id, rule=node.metadata['spec']),
            incoming_edge_specs=incoming
        )

    def __str__(self) -> str:
        s = "BLUEPRINT:\n  [NODES]:\n"
        try:
            order = self.dag.get_topological_order()
        except:
            order = list(self.dag.tasks.keys())
        for t_id in order:
             task = self.dag.get_task(t_id)
             cpx = "[Complex]" if task.metadata.get('is_complex') else "[Atomic]"
             s += f"    • {t_id:<20} {cpx} : {task.metadata['description']}\n"
        s += "\n  [DEPENDENCIES]:\n"
        if not self.edge_specs: s += "    (None)\n"
        for edge in self.edge_specs:
             s += f"    • {edge.source_id} → {edge.target_id} ({edge.rule})\n"
        return s

class Architect(KleisliFunctor[Blueprint]):
    def __init__(self, llm: LLMInterface):
        self.llm = llm

    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None) -> Blueprint:
        prompt = Prompts.ARCHITECT_SYSTEM.format(task=task_description, context=context_str)
        data = self.llm.generate_structured(
            prompt, 
            Schemas.ARCHITECT_OUTPUT, 
            images=images, 
            temperature=Params.ARCHITECT_TEMP,
            max_tokens=Params.MAX_TOKENS
        )
        return self._dict_to_blueprint(data)

    def _dict_to_blueprint(self, data: Dict[str, Any]) -> Blueprint:
        dag = TaskDAG(state_metric=None)
        edge_specs = []
        for node in data.get('nodes', []):
            dag.add_task(
                task_id=node['id'],
                implementation=None, specification=None, validator=None,
                metadata={
                    'spec': node['spec'], 
                    'description': node['description'],
                    'is_complex': node.get('is_complex', False)
                }
            )
        for edge in data.get('edges', []):
            src, dst = edge['from'], edge['to']
            dag.add_dependency(src, dst)
            edge_specs.append(EdgeSpec(source_id=src, target_id=dst, rule=edge['rule']))
        return Blueprint(dag, edge_specs)

class Worker(KleisliFunctor[str]):
    def __init__(self, llm: LLMInterface):
        self.llm = llm

    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None) -> str:
        prompt = Prompts.WORKER_SYSTEM.format(
            task=task_description,
            requirements=contract.to_string(),
            context=context_str
        )
        return self.llm.generate(
            prompt, 
            images=images, 
            temperature=Params.WORKER_TEMP,
            max_tokens=Params.MAX_TOKENS
        )

class LLMValidator(Validator):
    def __init__(self, llm: LLMInterface, contract: Contract, context_str: str, images: Optional[List[str]] = None):
        self.llm = llm
        self.contract = contract
        self.context_str = context_str
        self.images = images
        self._last_result: Optional[ValidationResult] = None

    def validate(self, real_state: Any) -> Distribution[Any]:
        # Convert artifact to string representation (using __str__ or str())
        artifact_str = str(real_state)
        
        prompt = Prompts.VALIDATOR_SYSTEM.format(
            spec=self.contract.to_string(),
            output=artifact_str[:20000] # Still good to truncate input context
        )

        try:
            res = self.llm.generate_structured(
                prompt, 
                Schemas.VALIDATOR_OUTPUT, 
                images=self.images, 
                temperature=Params.VALIDATOR_TEMP,
                max_tokens=Params.MAX_TOKENS
            )
            result = ValidationResult(
                epsilon=res.get('object_compliance_score', 1.0),
                laxity=res.get('integration_compliance_score', 1.0),
                feedback=res.get('critique', 'No feedback')
            )
            self._last_result = result
            return {real_state: 1.0} if result.is_success else {real_state: 0.0}
        except Exception as e:
            self._last_result = ValidationResult(1.0, 1.0, f"Validator error: {e}")
            return {real_state: 0.0}

    def get_epsilon(self) -> float: return Params.EPSILON_THRESHOLD
    def get_last_result(self) -> ValidationResult: return self._last_result or ValidationResult(1.0, 1.0, "N/A")
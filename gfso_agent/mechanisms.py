import json
from typing import Any, Dict, List, Optional

from gfso.core.graph import TaskDAG
from gfso.contract.validator import Validator
from gfso.core.kleisli import Distribution

from gfso_agent.llm import LLMInterface
from gfso_agent.types import KleisliFunctor, Contract, NodeSpec, EdgeSpec, ValidationResult, SGROutput
from gfso_agent.config import Params, Schemas, Prompts
from gfso_agent.logger import logger

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
                strategy=node.metadata.get('strategy', 'PYTHON'),
                artifact=node.metadata.get('artifact', 'Script'),
                done_criterion=node.metadata.get('done_criterion', 'Exits 0')
            ),
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
             strat = f"[{task.metadata.get('strategy', '???')}]"
             s += f"    • {t_id:<20} {strat:<12} : {task.metadata['description']}\n"
             s += f"      Artifact: {task.metadata.get('artifact', 'N/A')}\n"
             s += f"      Done:     {task.metadata.get('done_criterion', 'N/A')}\n"
        s += "\n  [DEPENDENCIES]:\n"
        if not self.edge_specs: s += "    (None)\n"
        for edge in self.edge_specs:
             s += f"    • {edge.source_id} → {edge.target_id} ({edge.rule})\n"
        return s

class LLMAgent(KleisliFunctor[Any]):
    """Generic Functor for ANY LLM-based agent (Architect, Worker, Validator)."""
    
    def __init__(self, llm: LLMInterface, prompt_tmpl: str, schema: dict, temp: float, kind: str):
        self.llm = llm
        self.prompt_tmpl = prompt_tmpl
        self.schema = schema
        self.temp = temp
        self.kind = kind # 'blueprint', 'code', 'validation'

    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None) -> SGROutput:
        # 1. Prepare Prompt Args
        fmt_args = {"task": task_description, "context": context_str}
        
        # Specific Logic for Validator Prompt
        if self.kind == 'validation':
            # CONVENTION: 
            # task_description = Context/Dependencies
            # context_str = Artifact to Validate
            fmt_args["spec"] = contract.to_string()
            fmt_args["context"] = task_description[:15000] 
            fmt_args["output"] = context_str[:25000]
        
        # Specific Logic for Worker Prompt
        elif "{requirements}" in self.prompt_tmpl:
            fmt_args["requirements"] = contract.to_string()
            
        prompt = self.prompt_tmpl.format(**fmt_args)
        
        # 2. Call LLM
        try:
            data = self.llm.generate_structured(
                prompt, 
                self.schema, 
                images=images, 
                temperature=self.temp,
                max_tokens=Params.MAX_TOKENS
            )
        except Exception as e:
            return SGROutput(thought=f"LLM Error: {e}", content=None, kind=self.kind)

        if not isinstance(data, dict):
             return SGROutput(thought=f"LLM Structure Error: Not a dict. Got {type(data)}", content=None, kind=self.kind)

        # 3. Parse Output based on Agent Kind
        thought = data.get('thought', data.get('thought_trace', data.get('critique', 'No thought provided.')))
        
        if self.kind == 'blueprint':
            content = self._dict_to_blueprint(data)
        elif self.kind == 'code':
            content = data.get('code', '')
        elif self.kind == 'validation':
            # Validator returns a Result Dict, NOT a string
            # MAPPING: Quality (High Good) -> Error (Low Good)
            q_obj = data.get('object_quality_score', 0.0)
            q_int = data.get('integration_quality_score', 0.0)
            
            content = {
                'is_passed': data.get('is_passed', False),
                'epsilon': 1.0 - q_obj,
                'laxity': 1.0 - q_int
            }
        else:
            content = str(data)

        return SGROutput(thought=thought, content=content, kind=self.kind)

    def _dict_to_blueprint(self, data: Dict[str, Any]) -> Blueprint:
        dag = TaskDAG(state_metric=None)
        edge_specs = []
        
        # Robust parsing of nodes
        raw_nodes = data.get('nodes', [])
        if not isinstance(raw_nodes, list):
            logger.error(f"Blueprint Error: 'nodes' is not a list, got {type(raw_nodes)}", 0)
            raw_nodes = []
            
        for node in raw_nodes:
            # Handle string nodes (fallback)
            if isinstance(node, str):
                node = {'id': node, 'description': node, 'spec': 'Verify integrity', 'strategy': 'PYTHON'}
            
            if not isinstance(node, dict):
                continue
                
            dag.add_task(
                task_id=node.get('id', 'unknown_node'),
                implementation=None, specification=None, validator=None,
                metadata={
                    'spec': node.get('spec', 'No Spec'), 
                    'description': node.get('description', 'No Desc'),
                    'strategy': node.get('strategy', 'PYTHON'),
                    'artifact': node.get('artifact', 'Python script'),
                    'done_criterion': node.get('done_criterion', 'Script returns True')
                }
            )
            
        # Robust parsing of edges
        raw_edges = data.get('edges', [])
        if not isinstance(raw_edges, list):
             raw_edges = []
             
        for edge in raw_edges:
            if not isinstance(edge, dict): continue
            src = edge.get('from')
            dst = edge.get('to')
            if src and dst:
                dag.add_dependency(src, dst)
                edge_specs.append(EdgeSpec(source_id=src, target_id=dst, rule=edge.get('rule', '')))
                
        return Blueprint(dag, edge_specs)
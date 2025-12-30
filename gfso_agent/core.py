from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from gfso_agent.types import KleisliFunctor, NaturalTransformation, Contract, NodeSpec, EdgeSpec
from gfso_agent.mechanisms import Architect, Worker, UniversalCritic, Blueprint
from gfso_agent.llm import LLMInterface
from gfso.core.graph import TaskDAG

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

class GFSOUnit:
    """Atomic Monad (F, η)."""
    def __init__(self, functor: KleisliFunctor, critic: NaturalTransformation, max_retries: int = 3):
        self.functor = functor
        self.critic = critic
        self.max_retries = max_retries

    def run(self, task: str, context: str, contract: Contract, step_id: str, runtime: RuntimeContext) -> Any:
        # Pass global images. Future: filter by relevance.
        images = runtime.images 
        
        for _ in range(self.max_retries + 1):
            artifact = self.functor.lift(task, context, contract, images)
            result = self.critic.transform(artifact, contract, context, images)
            
            if result.is_success:
                return artifact
            
            runtime.record_feedback(step_id, result.feedback)
            context += f"\n[CRITIC FEEDBACK]: {result.feedback}"
            
        raise RuntimeError(f"Unit '{step_id}' failed to converge.")

class GFSOAgent:
    """Recursive Runtime Engine."""
    def __init__(self, llm: LLMInterface, max_depth: int = 3):
        self.llm = llm
        self.max_depth = max_depth
        self.architect = Architect(llm)
        self.worker = Worker(llm)
        self.critic = UniversalCritic(llm)

    def run(self, user_task: str, images: Optional[List[str]] = None) -> Dict[str, str]:
        img_msg = f" [With {len(images)} images]" if images else ""
        print(f"--- GFSO Agent Started: {user_task[:50]}...{img_msg} ---")
        
        ctx = RuntimeContext(user_task, images=images)
        
        # 1. BLUEPRINTING PHASE (Intent -> Plan)
        # The Architect defines the structure (DAG) and the rules (Contracts).
        blueprint = self._synthesize_blueprint(user_task, ctx)
        
        # 2. EXECUTION PHASE (Traversal)
        # We simply walk the DAG. No separate Scheduler entity needed.
        self._execute_blueprint(blueprint, ctx, depth=0)
        
        print("--- GFSO Agent Finished ---")
        return ctx.artifacts

    def _synthesize_blueprint(self, task: str, ctx: RuntimeContext) -> Blueprint:
        # Meta-Contract for the Architect
        contract = Contract(
            node_spec=NodeSpec("root_plan", "Valid Blueprint with strict Object and Morphism specs."),
            incoming_edge_specs=[]
        )
        unit = GFSOUnit(self.architect, self.critic)
        return unit.run(task, "", contract, "root_architect", ctx)

    def _execute_blueprint(self, blueprint: Blueprint, ctx: RuntimeContext, depth: int):
        # Topological order IS the schedule.
        execution_order = blueprint.dag.get_topological_order()
        indent = "  " * depth
        print(f"{indent}Execution Order: {execution_order}")

        for step_id in execution_order:
            task = blueprint.dag.get_task(step_id)
            meta = task.metadata
            contract = blueprint.get_contract_for_node(step_id)
            deps = blueprint.dag.get_dependencies(step_id)
            step_ctx = ctx.get_context_for_step(step_id, deps)
            
            print(f"{indent}>> t({step_id})")

            # RECURSIVE FRACTAL LOGIC
            if meta.get('is_complex', False) and depth < self.max_depth:
                print(f"{indent}   [+] Recursion: Spawning Sub-Agent...")
                
                # The Sub-Agent creates its own Blueprint for the sub-task
                sub_dag_unit = GFSOUnit(self.architect, self.critic)
                sub_blueprint = sub_dag_unit.run(meta['description'], step_ctx, contract, f"{step_id}_arch", ctx)
                
                self._execute_blueprint(sub_blueprint, ctx, depth + 1)
                
                ctx.artifacts[step_id] = f"[Sub-Plan {step_id} Completed]"
            else:
                # ATOMIC WORK
                unit = GFSOUnit(self.worker, self.critic)
                result = unit.run(meta['description'], step_ctx, contract, step_id, ctx)
                ctx.artifacts[step_id] = result
                print(f"{indent}   [v] Converged.")
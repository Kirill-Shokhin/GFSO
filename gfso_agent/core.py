from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from gfso_agent.types import KleisliFunctor, Contract, NodeSpec, EdgeSpec
from gfso_agent.mechanisms import Architect, Worker, LLMValidator, Blueprint
from gfso_agent.llm import LLMInterface
from gfso_agent.logger import logger
from gfso_agent.config import Prompts, Params
from gfso.core.graph import TaskDAG

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

class GFSOUnit:
    """Atomic Monad (F, η)."""
    def __init__(self, functor: KleisliFunctor, llm: LLMInterface, max_retries: int = Params.MAX_RETRIES):
        self.functor = functor
        self.llm = llm
        self.max_retries = max_retries

    def run(self, task: str, context: str, contract: Contract, step_id: str, runtime: RuntimeContext, depth: int) -> Any:
        images = runtime.images 
        logger.log_contract(contract.to_string(), depth)

        validator = LLMValidator(self.llm, contract, context, images)
        last_feedback = "No feedback"

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                logger.step_start(f"{step_id} (Retry {attempt})", depth)

            artifact = self.functor.lift(task, context, contract, images)
            
            artifact_preview = str(artifact)
            if hasattr(artifact, 'to_dict'): artifact_preview = "Complex Object (Blueprint/DAG)"
            logger.log_artifact(step_id, artifact_preview, depth)
            
            # Validation
            dist = validator.validate(artifact)
            val_result = validator.get_last_result()
            last_feedback = val_result.feedback
            
            logger.log_validation(
                val_result.epsilon, 
                val_result.laxity, 
                val_result.feedback,
                val_result.is_success,
                depth
            )

            if val_result.is_success:
                return artifact
            
            runtime.record_feedback(step_id, val_result.feedback)
            context += f"\n[CRITIC FEEDBACK]: {val_result.feedback}"
            
        logger.error(f"Unit '{step_id}' failed to converge.", depth)
        raise StepFailure(step_id, last_feedback)

class GFSOAgent:
    """Recursive Runtime Engine."""
    def __init__(self, llm: LLMInterface, max_depth: int = Params.MAX_RECURSION_DEPTH):
        self.llm = llm
        self.max_depth = max_depth
        self.architect = Architect(llm)
        self.worker = Worker(llm)

    def run(self, user_task: str, images: Optional[List[str]] = None) -> Dict[str, str]:
        img_msg = f" [Images: {len(images)}]" if images else ""
        logger.section(f"GFSO Agent Init: {user_task[:40]}...{img_msg}", depth=0)
        
        ctx = RuntimeContext(user_task, images=images)
        
        try:
            # 1. BLUEPRINTING PHASE
            logger.section("Phase 1: Architecture (G)", depth=0)
            blueprint = self._synthesize_blueprint(user_task, ctx)
            logger.end_section("Phase 1", depth=0)
            
            # 2. EXECUTION PHASE
            logger.section("Phase 2: Execution (F)", depth=0)
            self._execute_blueprint(blueprint, ctx, depth=0)
            logger.end_section("Phase 2", depth=0)
            
            logger.section("Task Completed Successfully", depth=0)
            
        except StepFailure as e:
            logger.error(f"Pipeline Halted: {e}", depth=0)
            logger.section("Task Completed Partially (With Failures)", depth=0)
            
        except Exception as e:
            logger.error(f"Unexpected Crash: {e}", depth=0)
            import traceback
            logger._logger.debug(traceback.format_exc())

        return ctx.artifacts

    def _synthesize_blueprint(self, task: str, ctx: RuntimeContext) -> Blueprint:
        contract = Contract(
            node_spec=NodeSpec("root_plan", Prompts.ROOT_CONTRACT_SPEC.format(task=task)),
            incoming_edge_specs=[]
        )
        unit = GFSOUnit(self.architect, self.llm)
        return unit.run(task, "", contract, "root_architect", ctx, depth=1)

    def _execute_blueprint(self, blueprint: Blueprint, ctx: RuntimeContext, depth: int):
        execution_order = blueprint.dag.get_topological_order()
        
        if execution_order:
             logger._logger.info(f"{logger._indent(depth)}Plan: {execution_order}")

        for step_id in execution_order:
            task = blueprint.dag.get_task(step_id)
            meta = task.metadata
            contract = blueprint.get_contract_for_node(step_id)
            deps = blueprint.dag.get_dependencies(step_id)
            step_ctx = ctx.get_context_for_step(step_id, deps)
            
            logger.step_start(step_id, depth)

            if meta.get('is_complex', False) and depth < self.max_depth:
                logger.recursion_start(step_id, depth)
                
                sub_dag_unit = GFSOUnit(self.architect, self.llm)
                sub_blueprint = sub_dag_unit.run(meta['description'], step_ctx, contract, f"{step_id}_arch", ctx, depth + 1)
                
                self._execute_blueprint(sub_blueprint, ctx, depth + 1)
                
                ctx.artifacts[step_id] = f"[Sub-Plan {step_id} Completed]"
            else:
                unit = GFSOUnit(self.worker, self.llm)
                result = unit.run(meta['description'], step_ctx, contract, step_id, ctx, depth)
                ctx.artifacts[step_id] = result
                logger.step_success(step_id, depth)

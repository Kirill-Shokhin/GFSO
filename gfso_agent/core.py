from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field

from gfso_agent.types import KleisliFunctor, Contract, NodeSpec, EdgeSpec, SGROutput, ValidationResult
from gfso_agent.mechanisms import LLMAgent, Blueprint
from gfso_agent.llm import LLMInterface
from gfso_agent.logger import logger
from gfso_agent.config import Prompts, Params, Schemas
from gfso.core.graph import TaskDAG
from gfso_agent.tools.executor import PythonExecutor

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
    """Atomic Monad (F, η) with SGR Loop."""
    def __init__(self, functor: KleisliFunctor, validator_agent: KleisliFunctor, max_retries: int = Params.MAX_RETRIES):
        self.functor = functor
        self.validator_agent = validator_agent
        self.max_retries = max_retries
        self.executor = PythonExecutor(timeout=30)

    def _verify_local_artifact(self, sgr: SGROutput, depth: int) -> Tuple[bool, str, Any, Optional[str]]:
        """
        Unified verification strategy (Polymorphic F).
        Returns: (is_valid, feedback, formatted_artifact, raw_error_log)
        """
        # STRATEGY 1: PYTHON CODE (Worker)
        if sgr.kind == 'code':
            if not (isinstance(sgr.content, str) and sgr.content.strip()):
                return False, "Code content is empty or invalid.", None, "Empty Code"
            
            logger._logger.info(f"{logger._indent(depth)}[EXEC]: Running {len(sgr.content)} chars...")
            res = self.executor.run(sgr.content)
            logger._logger.info(f"{logger._indent(depth)}[EXEC]: Exit {res.exit_code}")

            if res.exit_code == 0:
                # GFSO INVARIANT: Every node MUST output valid JSON to stdout
                try:
                    import json
                    json.loads(res.stdout)
                except:
                    return False, "Code executed but STDOUT is not valid JSON. Ensure your script prints ONLY the JSON result.", None, res.stdout
                
                # Success
                view = f"## CODE\n```python\n{sgr.content}\n```\n\n## EXECUTION\nExit: {res.exit_code}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
                return True, "Execution Success", view, None
            else:
                # Failure
                error_msg = f"Code Execution Failed (Exit {res.exit_code}):\n{res.stderr[:1000]}"
                return False, error_msg, None, res.stderr

        # STRATEGY 2: BLUEPRINT (Architect)
        elif sgr.kind == 'blueprint':
            if sgr.content is not None:
                # GFSO INVARIANT: Blueprint must not be empty
                if not sgr.content.dag.tasks:
                    return False, "Blueprint parsed but contains NO nodes. Decompose the task into steps.", None, "Empty DAG"
                return True, "Blueprint Parsed", sgr.content, None
            else:
                # Failure
                error_msg = f"Blueprint Generation Failed (Structure Error): {sgr.thought}"
                logger._logger.info(f"{logger._indent(depth)}[BP FIX]: Structure invalid.")
                return False, error_msg, None, "Invalid JSON"

        # FALLBACK
        return True, "Passthrough", sgr.content, None

    def run(self, task: str, context: str, contract: Contract, step_id: str, runtime: RuntimeContext, depth: int) -> Any:
        images = runtime.images 
        logger.log_contract(contract.to_string(), depth)

        last_feedback = "No feedback"
        loop_context = context

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                logger.step_start(f"{step_id} (Retry {attempt})", depth)

            if Params.ENABLE_LAST_CHANCE_HINT and attempt == self.max_retries:
                 loop_context += "\n\n[SYSTEM WARNING]: This is your FINAL attempt. Ensure strict compliance with all constraints. Double-check your work.\n"

            # 1. THOUGHT & ACTION (Functor Lift)
            sgr = self.functor.lift(task, loop_context, contract, images)
            logger._logger.info(f"{logger._indent(depth)}[THOUGHT]: {sgr.thought[:2000]}...")
            
            # 2. UNIFIED LOCAL VERIFICATION (Self-Correction Loop)
            artifact_for_val = None
            exec_error_log = None
            
            # Internal SGR Loop (Self-Correction)
            for internal_try in range(Params.MAX_SELF_CORRECTIONS):
                is_valid, feedback, artifact, error_log = self._verify_local_artifact(sgr, depth)
                
                if is_valid:
                    artifact_for_val = artifact
                    break # Valid locally, proceed to external validation
                
                # Failed locally: Update context and retry internal loop
                exec_error_log = error_log
                loop_context += f"\n\n[SELF-CORRECTION REQUEST]:\n{feedback}\nINSTRUCTION: Fix the error and return the corrected artifact."
                
                if internal_try < Params.MAX_SELF_CORRECTIONS - 1:
                    logger._logger.info(f"{logger._indent(depth)}[FIXING]: Retrying internal generation...")
                    sgr = self.functor.lift(task, loop_context, contract, images)
            
            # If still invalid after self-corrections, use the last result (it will fail validation, but we proceed)
            if artifact_for_val is None:
                artifact_for_val = sgr.content # Fallback to raw content
            
            # LOGGING
            logger.log_artifact(step_id, str(artifact_for_val)[:5000] + ("..." if len(str(artifact_for_val))>5000 else ""), depth)
            
            # 3. VALIDATION (External Judge)
            val_deps_context = loop_context
            if Params.ENABLE_LAST_CHANCE_HINT and attempt == self.max_retries - 1:
                val_deps_context += "\n\n[SYSTEM NOTE]: The next attempt will be the FINAL one. Please provide specific, actionable feedback."

            val_sgr = self.validator_agent.lift(
                task_description=val_deps_context, 
                context_str=str(artifact_for_val), 
                contract=contract, 
                images=images
            )
            
            logger._logger.info(f"\n{logger._indent(depth)}[VALIDATOR REFLECTION]:\n{val_sgr.thought}\n")
            
            val_data = val_sgr.content 
            val_result = ValidationResult(
                epsilon=val_data['epsilon'],
                laxity=val_data['laxity'],
                feedback=val_sgr.thought
            )
            
            is_success = val_result.is_success
            logger.log_validation(val_result.epsilon, val_result.laxity, val_result.feedback, is_success, depth)

            # 4. CONVERGENCE CHECK
            if is_success:
                return artifact_for_val
            
            # 5. RETRY CONTEXT UPDATE
            runtime.record_feedback(step_id, val_result.feedback)
            last_feedback = val_result.feedback
            
            loop_context += f"\n\n=== ATTEMPT {attempt} FAILED ===\n"
            loop_context += f"THOUGHT: {sgr.thought}\n"
            loop_context += f"ACTION ({sgr.kind}): {str(sgr.content)}\n"
            if exec_error_log:
                loop_context += f"EXECUTION ERROR:\n{exec_error_log}\n"
            loop_context += f"CRITIC: {val_result.feedback}\n"
            loop_context += "================================\n"
            
        logger.error(f"Unit '{step_id}' failed to converge.", depth)
        raise StepFailure(step_id, last_feedback)

class GFSOAgent:
    """Recursive Runtime Engine."""
    def __init__(self, llm: LLMInterface, max_depth: int = Params.MAX_RECURSION_DEPTH):
        self.llm = llm
        self.max_depth = max_depth
        
        # Initialize generic agents
        self.architect = LLMAgent(
            llm, 
            Prompts.ARCHITECT_SYSTEM, 
            Schemas.ARCHITECT_OUTPUT, 
            Params.ARCHITECT_TEMP, 
            kind='blueprint'
        )
        
        self.worker = LLMAgent(
            llm, 
            Prompts.WORKER_SYSTEM, 
            Schemas.WORKER_OUTPUT, 
            Params.WORKER_TEMP, 
            kind='code'
        )
        
        self.validator = LLMAgent(
            llm,
            Prompts.VALIDATOR_SYSTEM,
            Schemas.VALIDATOR_OUTPUT,
            Params.VALIDATOR_TEMP,
            kind='validation'
        )

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
            
            # 3. SYNTHESIS PHASE (HEAD)
            logger.section("Phase 3: Synthesis (Head)", depth=0)
            final_answer = self._finalize(user_task, ctx)
            ctx.artifacts['FINAL_ANSWER'] = final_answer
            logger._logger.info(f"\n>>> FINAL ANSWER <<<{final_answer}\n")
            logger.end_section("Phase 3", depth=0)
            
            logger.section("Task Completed Successfully", depth=0)
            
        except StepFailure as e:
            logger.error(f"Pipeline Halted: {e}", depth=0)
            logger.section("Task Completed Partially (With Failures)", depth=0)
            
        except Exception as e:
            logger.error(f"Unexpected Crash: {e}", depth=0)
            import traceback
            logger._logger.debug(traceback.format_exc())

        return ctx.artifacts

    def _finalize(self, task: str, ctx: RuntimeContext) -> str:
        context_str = ""
        for k, v in ctx.artifacts.items():
            context_str += f"\n--- Artifact: {k} ---\n{str(v)[:10000]}\n"
            
        prompt = Prompts.HEAD_SYSTEM.format(task=task, context=context_str)
        
        try:
            from gfso_agent.config import Schemas
            res = self.llm.generate_structured(
                prompt,
                Schemas.HEAD_OUTPUT,
                temperature=Params.HEAD_TEMP
            )
            
            final_output = f"## PROCESS CRITIQUE\n{res.get('process_critique')}\n\n"
            final_output += f"## REASONING\n{res.get('reasoning')}\n\n"
            final_output += f"## FINAL ANSWER\n{res.get('final_answer')}\n\n"
            final_output += f"[Confidence: {res.get('confidence_score')}]"
            return final_output
            
        except Exception as e:
            logger.error(f"Head Synthesis Failed: {e}", 0)
            return f"Final Synthesis Error: {e}"

    def _synthesize_blueprint(self, task: str, ctx: RuntimeContext) -> Blueprint:
        contract = Contract(
            node_spec=NodeSpec("root_plan", Prompts.ROOT_CONTRACT_SPEC.format(task=task)),
            incoming_edge_specs=[]
        )
        unit = GFSOUnit(self.architect, self.validator)
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

            try:
                # Flat Execution: Always use Worker
                unit = GFSOUnit(self.worker, self.validator)
                result = unit.run(meta['description'], step_ctx, contract, step_id, ctx, depth)
                ctx.artifacts[step_id] = result
                logger.step_success(step_id, depth)
            
            except StepFailure as e:
                # FAIL FAST: Stop execution, go to Head
                logger.error(f"Step '{step_id}' failed validation. Aborting Graph Execution.", depth)
                ctx.artifacts[step_id] = f"[FAILED] {e.feedback}"
                break # Exit the loop, proceed to Phase 3 (Head)
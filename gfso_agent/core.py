from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from gfso_agent.types import KleisliFunctor, Contract, NodeSpec, SGROutput, ValidationResult, Blueprint, StepFailure, RuntimeContext
from gfso_agent.llm import LLMInterface, LLMAgent
from gfso_agent.logger import logger
from gfso_agent.config import Prompts, Params, SCHEMAS
from gfso_agent.tools.executor import PythonExecutor


class GFSOUnit:
    """Atomic Monad (F, η) with SGR Loop."""
    def __init__(self, functor: KleisliFunctor, validator_agent: KleisliFunctor, synthesizer_agent: Optional[KleisliFunctor] = None, max_retries: int = Params.MAX_RETRIES):
        self.functor = functor
        self.validator_agent = validator_agent
        self.synthesizer_agent = synthesizer_agent
        self.max_retries = max_retries
        self.executor = PythonExecutor(timeout=30)

    def _verify_local_artifact(self, sgr: SGROutput, depth: int) -> Tuple[bool, str, Any, Optional[str]]:
        """
        Unified verification strategy (Polymorphic F).
        Returns: (is_valid, feedback, formatted_artifact, raw_error_log)
        """
        # 0. HANDLE CRITICAL ERRORS (No content)
        if sgr.content is None:
            return False, f"Generation Failed. Agent error: {sgr.thought}", None, "Critical Error"

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
                    output_str = res.stdout.strip()
                    # HEURISTIC: Find first '{' and last '}' to extract valid JSON even if there is noise
                    start = output_str.find('{')
                    end = output_str.rfind('}')
                    if start != -1 and end != -1:
                         json_str = output_str[start:end+1]
                         json.loads(json_str)
                    else:
                         json.loads(output_str) # Fallback to strict full parse
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
            if not isinstance(sgr.content, dict):
                return False, f"Architect returned invalid content type: {type(sgr.content)}. Expected JSON object.", None, "Type Error"
            
            try:
                # Attempt to build the DAG using the static factory
                blueprint = Blueprint.from_json(sgr.content)
                if not blueprint.dag.tasks:
                     return False, "Blueprint contains NO nodes. Decompose the task into steps.", None, "Empty DAG"
                
                return True, "Blueprint Parsed Successfully", blueprint, None
            except Exception as e:
                # LOG RAW DATA FOR DEBUGGING
                logger._logger.info(f"\n{logger._indent(depth)}[BLUEPRINT ERROR]: {e}")
                import json
                raw_json = json.dumps(sgr.content, indent=2)
                error_feedback = f"Failed to construct Valid Blueprint Graph:\nERROR: {str(e)}\n\nRAW JSON PRODUCED:\n{raw_json}\n\nINSTRUCTION: Fix the JSON structure or Graph Topology (check IDs and dependencies) and try again."
                return False, error_feedback, None, str(e)

        # FALLBACK
        return True, "Passthrough", sgr.content, None

    def _execute_lane(self, task: str, context: str, contract: Contract, images: Optional[List[str]], depth: int, temp: float) -> Optional[Any]:
        """Runs a single SGR loop (Think->Act->Verify). Returns artifact or None if failed."""
        
        sgr = self.functor.lift(task, context, contract, images, temperature=temp)
        logger._logger.info(f"{logger._indent(depth)}\n[THOUGHT]: {sgr.thought}")

        for internal_try in range(Params.MAX_SELF_CORRECTIONS):
            is_valid, feedback, artifact, error_log = self._verify_local_artifact(sgr, depth)
            
            if is_valid:
                return artifact
            
            # Failed locally
            context += f"\n\n[SELF-CORRECTION REQUEST]:\n{feedback}\nINSTRUCTION: Fix the error and return the corrected artifact."
            if internal_try < Params.MAX_SELF_CORRECTIONS - 1:
                logger._logger.info(f"{logger._indent(depth)}[FIXING]: Retrying internal generation...")
                sgr = self.functor.lift(task, context, contract, images, temperature=temp)
        
        return None

    def _execute_swarm(self, task: str, context: str, contract: Contract, images: Optional[List[str]], depth: int) -> Any:
        """Executes N parallel lanes and synthesizes the result."""
        
        # OPTIMIZATION: If size is 1, bypass thread pool and synthesizer (degenerate swarm)
        if Params.SWARM_SIZE == 1:
            logger._logger.info(f"{logger._indent(depth)}[SWARM]: Optimized execution (Size=1)...")
            return self._execute_lane(task, context, contract, images, depth, temp=Params.SWARM_WORKER_TEMP)

        candidates = []
        valid_artifacts = []
        
        logger._logger.info(f"{logger._indent(depth)}[SWARM]: Spawning {Params.SWARM_SIZE} workers in parallel...")
        
        # Parallel Execution using ThreadPool
        with ThreadPoolExecutor(max_workers=Params.SWARM_SIZE) as executor:
            # key: future, value: lane_index (1-based)
            future_to_lane = {
                executor.submit(
                    self._execute_lane, 
                    task, 
                    context, 
                    contract, 
                    images, 
                    depth + 1, 
                    temp=Params.SWARM_WORKER_TEMP
                ): i + 1
                for i in range(Params.SWARM_SIZE)
            }

            # Collect results as they complete
            for future in as_completed(future_to_lane):
                lane_idx = future_to_lane[future]
                try:
                    lane_artifact = future.result()
                    if lane_artifact:
                        logger._logger.info(f"{logger._indent(depth)}  > Lane {lane_idx} FINISHED (Success)")
                        # Note: Order in candidates list doesn't strictly matter for synthesis, 
                        # but we might want to sort them later if needed. Thread pool completes out-of-order.
                        candidates.append(f"--- CANDIDATE {lane_idx} ---\n{str(lane_artifact)}\n")
                        valid_artifacts.append(lane_artifact)
                    else:
                        logger._logger.info(f"{logger._indent(depth)}  > Lane {lane_idx} FINISHED (Failed)")
                        candidates.append(f"--- CANDIDATE {lane_idx} ---\n[FAILED TO COMPILE/EXECUTE]\n")
                except Exception as e:
                    logger.error(f"Lane {lane_idx} crashed: {e}", depth)
                    candidates.append(f"--- CANDIDATE {lane_idx} ---\n[CRASHED: {e}]\n")

        # SYNTHESIS
        logger._logger.info(f"{logger._indent(depth)}[SWARM]: Synthesizing {len(valid_artifacts)} valid candidates...")
        
        if not valid_artifacts:
            # All lanes failed, we can't synthesize. We return a failure marker that Validator will reject.
            return "SWARM CRITICAL FAILURE: All parallel workers failed to produce executable code."
            
        syn_context = "\n".join(candidates)
        
        # Swap functor to Synthesizer for this call
        original_functor = self.functor
        self.functor = self.synthesizer_agent
        
        golden_artifact = self._execute_lane(task, syn_context, contract, images, depth, temp=Params.SYNTHESIZER_TEMP)
        
        self.functor = original_functor # Restore
        
        return golden_artifact if golden_artifact else valid_artifacts[0] # Fallback to first valid

    def run(self, task: str, context: str, contract: Contract, step_id: str, runtime: RuntimeContext, depth: int) -> Any:
        images = runtime.images 
        logger.log_contract(contract.to_string(), depth)

        last_feedback = "No feedback"
        loop_context = context

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                logger.step_start(f"{step_id} (Retry {attempt})", depth)
                # INJECT SHARED CONTEXT FROM PREVIOUS ATTEMPT (Evolution)
                if last_feedback != "No feedback":
                     loop_context += f"\n[SHARED SWARM MEMORY - PREVIOUS ATTEMPT FAILED]\nCRITIQUE: {last_feedback}\n"

            if Params.ENABLE_LAST_CHANCE_HINT and attempt == self.max_retries:
                 loop_context += "\n\n[SYSTEM WARNING]: This is your FINAL attempt. Ensure strict compliance with all constraints.\n"

            # 1. EXECUTION (F) - Polymorphic
            strategy = contract.node_spec.strategy
            artifact_for_val = None
            
            if strategy == 'SWARM' and self.synthesizer_agent:
                artifact_for_val = self._execute_swarm(task, loop_context, contract, images, depth)
            else:
                # DIRECT or Fallback
                artifact_for_val = self._execute_lane(task, loop_context, contract, images, depth, temp=Params.WORKER_TEMP)

            if artifact_for_val is None:
                raise StepFailure(step_id, "Failed to generate executable code (SGR Exhausted).")

            # LOGGING
            logger.log_artifact(step_id, str(artifact_for_val), depth)
            
            # 2. VALIDATION (External Judge)
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

            # 3. CONVERGENCE CHECK
            if is_success:
                return artifact_for_val
            
            # 4. RETRY CONTEXT UPDATE
            runtime.record_feedback(step_id, val_result.feedback)
            last_feedback = val_result.feedback
            
            # Local loop update (for next iteration of this Unit)
            loop_context += f"\n\n=== ATTEMPT {attempt} FAILED ===\n"
            loop_context += f"VALIDATOR CRITIQUE:\n{val_result.feedback}\n"
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
            SCHEMAS.ARCHITECT, 
            Params.ARCHITECT_TEMP, 
            kind='blueprint'
        )
        
        self.worker = LLMAgent(
            llm, 
            Prompts.WORKER_SYSTEM, 
            SCHEMAS.WORKER, 
            Params.WORKER_TEMP, 
            kind='code'
        )

        self.synthesizer = LLMAgent(
            llm,
            Prompts.SYNTHESIZER_SYSTEM,
            SCHEMAS.WORKER, # Synthesizer outputs code, same as Worker
            Params.SYNTHESIZER_TEMP,
            kind='code'
        )
        
        self.validator = LLMAgent(
            llm,
            Prompts.VALIDATOR_SYSTEM,
            SCHEMAS.VALIDATOR,
            Params.VALIDATOR_TEMP,
            kind='validation'
        )

    def run(self, user_task: str, images: Optional[List[str]] = None) -> Dict[str, str]:
        img_msg = f" [Images: {len(images)}]" if images else ""
        logger.section(f"GFSO Agent Init: {user_task}\n{img_msg}", depth=0)
        
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
            context_str += f"\n--- Artifact: {k} ---\n{str(v)}\n"
            
        prompt = Prompts.HEAD_SYSTEM.format(task=task, context=context_str)
        
        try:
            # from gfso_agent.config import Schemas (Removed local import)
            res = self.llm.generate_structured(
                prompt,
                SCHEMAS.HEAD,
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
            node_spec=NodeSpec("root_plan", Prompts.ROOT_CONTRACT_SPEC.format(task=task), strategy="SWARM"),
            incoming_edge_specs=[]
        )
        unit = GFSOUnit(self.architect, self.validator, self.synthesizer)
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
                # Flat Execution: Worker + Synthesizer
                unit = GFSOUnit(self.worker, self.validator, self.synthesizer)
                result = unit.run(meta['description'], step_ctx, contract, step_id, ctx, depth)
                ctx.artifacts[step_id] = result
                logger.step_success(step_id, depth)
            
            except StepFailure as e:
                # FAIL FAST: Stop execution, go to Head
                logger.error(f"Step '{step_id}' failed validation. Aborting Graph Execution.", depth)
                ctx.artifacts[step_id] = f"[FAILED] {e.feedback}"
                break # Exit the loop, proceed to Phase 3 (Head)

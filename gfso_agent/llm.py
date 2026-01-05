import os
import base64
import textwrap
from typing import Protocol, Optional, List, Dict, Any, Union
import anthropic

from gfso_agent.types import KleisliFunctor, Contract, SGROutput, Blueprint
from gfso_agent.config import Params, Prompts

class LLMInterface(Protocol):
    """Abstract interface for LLM interaction."""
    
    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        """Generate text response with optional images."""
        ...

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4096) -> dict:
        """Generate structured JSON response with optional images."""
        ...

class LLMAgent(KleisliFunctor[Any]):
    """Generic Functor for ANY LLM-based agent (Architect, Worker, Validator)."""
    
    def __init__(self, llm: LLMInterface, prompt_tmpl: str, schema: dict, temp: float, kind: str):
        self.llm = llm
        self.prompt_tmpl = textwrap.dedent(prompt_tmpl).strip()
        self.schema = schema
        self.temp = temp
        self.kind = kind # 'blueprint', 'code', 'validation'

    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None, temperature: Optional[float] = None) -> SGROutput:
        # 1. Prepare Prompt Args
        contract_str = contract.to_string()
        fmt_args = {
            "task": task_description, 
            "context": context_str,
            "spec": contract_str,
        }
        
        # Specific Logic for Validator Prompt
        if self.kind == 'validation':
            # CONVENTION: 
            # task_description = Context/Dependencies
            # context_str = Artifact to Validate
            fmt_args["context"] = task_description[:15000]
            fmt_args["output"] = context_str[:25000]
            
        # Centralized Dedent: Remove indentation from template before filling
        prompt = self.prompt_tmpl.format(**fmt_args)
        
        # 2. Call LLM
        final_temp = temperature if temperature is not None else self.temp
        try:
            data = self.llm.generate_structured(
                prompt, 
                self.schema, 
                images=images, 
                system_prompt=Prompts.GLOBAL_SYSTEM.strip(),
                temperature=final_temp,
                max_tokens=Params.MAX_TOKENS
            )
        except Exception as e:
            return SGROutput(thought=f"LLM Error: {e}", content=None, kind=self.kind)

        if not isinstance(data, dict):
             return SGROutput(thought=f"LLM Structure Error: Not a dict. Got {type(data)}", content=None, kind=self.kind)

        # 3. Parse Output based on Agent Kind
        # Unified 'thought' key for all agents (Polymorphism achieved)
        thought = data.get('thought', 'No thought provided.')
        
        if self.kind == 'blueprint':
            # ARCHITECT SYMMETRY: Return raw dict, let GFSOUnit handle parsing/verification
            content = data
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

_LOG_CLEARED = False

class BaseLLM:
    """Shared logic for all LLM implementations."""
    def _log_roundtrip(self, kind: str, system: str, user: str, schema: dict, response: Any, images: Optional[List[str]] = None):
        global _LOG_CLEARED
        mode = "a"
        if not _LOG_CLEARED:
            mode = "w"
            _LOG_CLEARED = True
            
        with open("prompts_debug.log", mode, encoding="utf-8") as f:
            f.write(f"\n\n{'='*30} [{kind} ROUNDTRIP] {'='*30}\n")
            f.write(f"--- SYSTEM ---\n{system}\n")
            
            img_info = f" [Images: {len(images)}]" if images else ""
            f.write(f"--- USER{img_info} ---\n{user}\n")
            
            f.write(f"--- SCHEMA ---\n{str(schema)}\n")
            
            import json
            res_str = json.dumps(response, indent=2, ensure_ascii=False) if isinstance(response, dict) else str(response)
            f.write(f"--- RESPONSE ---\n{res_str}\n")
            f.write(f"{'='*78}\n")

class MockLLM(BaseLLM):
    """Mock LLM for testing without API keys."""

    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        res = f"[MOCK] {prompt[:50]}..."
        self._log_roundtrip("MOCK_TEXT", system_prompt or "None", prompt, {}, res, images)
        return res

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4096) -> dict:
        props = schema.get("properties", {})

        # Default Mock Response
        res = {"thought": "Mock response", "final_answer": "42"}

        # ARCHITECT (has nodes/edges)
        if "nodes" in props:
            res = {
                "thought": "Mock plan: single compute step.",
                "nodes": [
                    {"id": "step_1", "description": "Compute result", "spec": "Return answer as JSON",
                     "strategy": "DIRECT", "artifact": "Script prints JSON", "done_criterion": "Exit 0"}
                ],
                "edges": []
            }

        # VALIDATOR (has is_passed)
        elif "is_passed" in props:
            res = {
                "thought": "Mock validation passed.",
                "is_passed": True,
                "object_quality_score": 1.0,
                "integration_quality_score": 1.0
            }

        # WORKER (has code)
        elif "code" in props:
            res = {
                "thought": "Mock worker executing.",
                "code": 'import json; print(json.dumps({"answer": "42"}))',
                "final_answer": "42"
            }

        # HEAD FULL (has diagnosis)
        elif "diagnosis" in props:
            res = {
                "thought": "Pipeline completed successfully.",
                "final_answer": "42",
                "confidence": 1.0,
                "diagnosis": ""
            }

        self._log_roundtrip("MOCK_STRUCT", system_prompt or "None", prompt, schema, res, images)
        return res

class AnthropicLLM(BaseLLM):
    """Production LLM using Anthropic API."""
    
    def __init__(self, model: str = "claude-haiku-4-5-20251001", api_key: Optional[str] = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        
        if not key:
            raise ValueError("No API key found. Please set ANTHROPIC_API_KEY or CLAUDE_API_KEY.")
            
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _get_media_type(self, image_path: str) -> str:
        ext = os.path.splitext(image_path)[1].lower()
        if ext in ['.jpg', '.jpeg']: return 'image/jpeg'
        if ext == '.png': return 'image/png'
        if ext == '.gif': return 'image/gif'
        if ext == '.webp': return 'image/webp'
        return 'image/jpeg'

    def _prepare_content(self, prompt: str, images: Optional[List[str]]) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        
        if images:
            for img_path in images:
                try:
                    b64_data = self._encode_image(img_path)
                    media_type = self._get_media_type(img_path)
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data
                        }
                    })
                except Exception as e:
                    print(f"[WARN] Failed to load image {img_path}: {e}")
                    content.append({"type": "text", "text": f"[Image load failed: {img_path}]"})
        return content

    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        try:
            content = self._prepare_content(prompt, images)
            
            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "user", "content": content}
                ]
            }
            
            if system_prompt:
                kwargs["system"] = system_prompt
                
            response = self.client.messages.create(**kwargs)
            res_text = response.content[0].text
            self._log_roundtrip(f"ANTHROPIC_TEXT({self.model})", system_prompt or "None", prompt, {}, res_text, images)
            return res_text
            
        except anthropic.APIError as e:
            err = f"Error calling Anthropic API: {str(e)}"
            self._log_roundtrip("ANTHROPIC_ERROR", system_prompt or "None", prompt, {}, err, images)
            return err

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4096) -> dict:
        tool_name = "output_formatter"
        tool_definition = {
            "name": tool_name,
            "description": "Output the result in the required format.",
            "input_schema": schema
        }

        try:
            content = self._prepare_content(prompt, images)

            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "tools": [tool_definition],
                "tool_choice": {"type": "tool", "name": tool_name},
                "messages": [
                    {"role": "user", "content": content}
                ]
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            final_res = None
            for block in response.content:
                if block.type == 'tool_use' and block.name == tool_name:
                    final_res = block.input
                    break

            if final_res is None:
                raise ValueError("Model did not use the required tool.")

            self._log_roundtrip(f"ANTHROPIC_STRUCT({self.model})", system_prompt or "None", prompt, schema, final_res,
                                images)
            return final_res

        except Exception as e:
            print(f"[LLM Error] Structured generation failed: {e}")
            self._log_roundtrip("ANTHROPIC_STRUCT_ERROR", system_prompt or "None", prompt, schema, str(e), images)
            raise e
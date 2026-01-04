import os
import base64
from typing import Protocol, Optional, List, Dict, Any, Union
import anthropic

from gfso_agent.types import KleisliFunctor, Contract, SGROutput, Blueprint
from gfso_agent.config import Params

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
        self.prompt_tmpl = prompt_tmpl
        self.schema = schema
        self.temp = temp
        self.kind = kind # 'blueprint', 'code', 'validation'

    def lift(self, task_description: str, context_str: str, contract: Contract, images: Optional[List[str]] = None, temperature: Optional[float] = None) -> SGROutput:
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
        final_temp = temperature if temperature is not None else self.temp
        try:
            data = self.llm.generate_structured(
                prompt, 
                self.schema, 
                images=images, 
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

class MockLLM:
    """Mock LLM for testing without API keys."""
    
    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        img_msg = f" [With {len(images)} images]" if images else ""
        return f"[MOCK OUTPUT] Response to: {prompt[:50]}...{img_msg}"

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4096) -> dict:
        if "nodes" in schema.get("properties", {}):
            if "root_architect" in prompt or "Web App" in prompt:
                return {
                    "thought": "Decomposing web app into steps.",
                    "nodes": [
                        {"id": "db", "description": "Setup SQLite", "spec": "Schema with Users table", "strategy": "DIRECT", "artifact": "db_setup.py", "done_criterion": "File exists"},
                        {"id": "api", "description": "Flask API", "spec": "CRUD endpoints for Users", "strategy": "SWARM", "artifact": "api.py", "done_criterion": "Endpoints return 200"},
                        {"id": "ui", "description": "React Frontend", "spec": "Dashboard with User list", "strategy": "DIRECT", "artifact": "ui.js", "done_criterion": "Renders without error"}
                    ],
                    "edges": [
                        {"from": "db", "to": "api", "rule": "API must use the connection string from DB setup"},
                        {"from": "api", "to": "ui", "rule": "UI must fetch data from /api/users endpoint"}
                    ]
                }
            return {
                "thought": "Decomposing sub-task.",
                "nodes": [
                    {"id": "logic", "description": "Core Logic", "spec": "Complex algorithm", "strategy": "SWARM", "artifact": "logic.py", "done_criterion": "Passes all tests"}
                ],
                "edges": []
            }
        
        # Worker/Synthesizer/Validator response
        if "SYNTHESIZER" in (system_prompt or ""):
             return {
                "thought": "Synthesizing best candidate.",
                "code": "print('{\"status\": \"synthesized\"}')",
                "final_answer": "Synthesized Result"
            }

        return {
            "object_quality_score": 1.0, 
            "integration_quality_score": 1.0, 
            "thought": "Mock Success",
            "is_passed": True,
            "code": "print('{\"status\": \"success\"}')",
            "final_answer": "Mock Answer"
        }

class AnthropicLLM:
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
            return response.content[0].text
            
        except anthropic.APIError as e:
            return f"Error calling Anthropic API: {str(e)}"

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
            
            for block in response.content:
                if block.type == 'tool_use' and block.name == tool_name:
                    return block.input
            
            raise ValueError("Model did not use the required tool.")

        except Exception as e:
            print(f"[LLM Error] Structured generation failed: {e}")
            raise e
import os
import base64
from typing import Protocol, Optional, List, Dict, Any, Union
import anthropic

class LLMInterface(Protocol):
    """Abstract interface for LLM interaction."""
    
    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7) -> str:
        """Generate text response with optional images."""
        ...

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0) -> dict:
        """Generate structured JSON response with optional images."""
        ...

class MockLLM:
    """Mock LLM for testing without API keys."""
    
    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7) -> str:
        img_msg = f" [With {len(images)} images]" if images else ""
        return f"[MOCK OUTPUT] Response to: {prompt[:50]}...{img_msg}"

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0) -> dict:
        # Mock implementation returning dummy data based on schema
        # If it looks like a Blueprint
        if "nodes" in schema.get("properties", {}) and "edges" in schema.get("properties", {}):
            return {
                "nodes": [
                    {"id": "foundation", "description": "Pour concrete", "spec": "Grade 500", "is_complex": False},
                    {"id": "walls", "description": "Build walls", "spec": "Brick layout", "is_complex": False}
                ],
                "edges": [
                    {
                        "from": "foundation", 
                        "to": "walls", 
                        "rule": "Walls must align with anchors within 5mm"
                    }
                ]
            }
        
        # Validation result
        return {
            "epsilon": 0.0, 
            "laxity": 0.0, 
            "feedback": "Mock Success",
            "is_passed": True
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
        return 'image/jpeg' # Default fallback

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

    def generate(self, prompt: str, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.7) -> str:
        """
        Generate response using Anthropic Messages API.
        """
        try:
            content = self._prepare_content(prompt, images)
            
            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
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

    def generate_structured(self, prompt: str, schema: dict, images: Optional[List[str]] = None, system_prompt: Optional[str] = None, temperature: float = 0.0) -> dict:
        """
        Generate structured response using Anthropic's tool use.
        """
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
                "max_tokens": 4096,
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
            
            # Extract tool use input
            for block in response.content:
                if block.type == 'tool_use' and block.name == tool_name:
                    return block.input
            
            raise ValueError("Model did not use the required tool.")

        except Exception as e:
            print(f"[LLM Error] Structured generation failed: {e}")
            raise e

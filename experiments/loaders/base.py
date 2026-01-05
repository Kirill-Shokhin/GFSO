"""Base classes for dataset loaders."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class Task:
    """Universal task representation across datasets."""
    id: str
    question: str
    answer: str  # Ground truth
    choices: List[str] = field(default_factory=list)  # For multiple choice
    domain: str = "unknown"
    difficulty: str = "unknown"
    images: List[Any] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DatasetLoader(ABC):
    """Abstract base for dataset loaders."""

    name: str = "base"

    @abstractmethod
    def load(self, split: str = "test", start: int = 0, count: int = None) -> List[Task]:
        """Load tasks from dataset.

        Args:
            split: Dataset split (test, train, etc.)
            start: Starting index
            count: Number of tasks to load (None = all)

        Returns:
            List of Task objects
        """
        pass

    def check_answer(self, prediction: str, ground_truth: str, llm: Any = None) -> bool:
        """Check if prediction matches ground truth (Normalize -> String Match -> LLM Judge)."""
        pred_norm = self._normalize(prediction)
        truth_norm = self._normalize(ground_truth)
        
        # 1. Fast path: Direct string match
        if pred_norm == truth_norm:
            return True
            
        # 2. Robust path: LLM Judge
        return self.judge(prediction, ground_truth, llm)

    def _normalize(self, s: str) -> str:
        """Default normalization: lower, strip."""
        if s is None: return ""
        return str(s).strip().lower()

    def judge(self, prediction: str, ground_truth: str, llm: Any) -> bool:
        """Universal LLM-based verification (Fallback)."""
        if not llm:
            return False
            
        try:
            prompt = f"""
            You are an impartial Judge.
            
            Compare these two answers. Are they semantically equivalent?
            
            Prediction: {prediction}
            Ground Truth: {ground_truth}
            """
            
            schema = {
                "type": "object",
                "properties": {"equivalent": {"type": "boolean"}},
                "required": ["equivalent"]
            }
            
            # Using generate_structured directly
            res = llm.generate_structured(prompt, schema, temperature=0.0)
            return res.get("equivalent", False)
            
        except Exception as e:
            print(f"[Judge Error] {e}")
            return False

    def total_count(self, split: str = "test") -> int:
        """Get total number of tasks in split."""
        return -1  # Unknown by default

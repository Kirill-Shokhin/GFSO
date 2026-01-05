"""MATH dataset loader (competition mathematics)."""

import re
from typing import List
from .base import DatasetLoader, Task


class MATHLoader(DatasetLoader):
    """Load MATH dataset (Hendrycks et al.)

    Levels 1-5, where 5 is hardest (AMC/AIME level).
    Categories: algebra, counting_and_probability, geometry,
                intermediate_algebra, number_theory, prealgebra, precalculus
    """

    name = "math"

    def __init__(self, levels: List[int] = None, categories: List[str] = None):
        """
        Args:
            levels: Filter by difficulty levels (1-5). Default: [4, 5]
            categories: Filter by category. Default: all
        """
        self.levels = levels or [4, 5]
        self.categories = categories

    def load(self, split: str = "test", start: int = 0, count: int = None) -> List[Task]:
        try:
            from datasets import load_dataset
        except ImportError:
            print("ERROR: 'datasets' library not installed")
            return []

        print(f"Loading MATH dataset (levels={self.levels}, split={split})...")

        try:
            # This dataset only has 'train' split, use it regardless of requested split
            dataset = load_dataset("qwedsacf/competition_math", split="train")
        except Exception as e:
            print(f"ERROR loading MATH: {e}")
            return []

        tasks = []
        idx = 0

        for item in dataset:
            try:
                level_str = item.get("level", "Level 1")
                # Handle '?' or other garbage
                if not level_str or "?" in level_str:
                    continue
                level = int(level_str.replace("Level ", ""))
            except ValueError:
                continue

            # Filter by level
            if level not in self.levels:
                continue

            # Filter by category
            category = item.get("type", "unknown")
            if self.categories and category not in self.categories:
                continue

            # Skip until start
            if idx < start:
                idx += 1
                continue

            # Extract answer from solution
            solution = item.get("solution", "")
            answer = self._extract_answer(solution)

            task = Task(
                id=f"math_{idx}",
                question=item.get("problem", ""),
                answer=answer,
                domain=category,
                difficulty=f"Level {level}",
                metadata={
                    "level": level,
                    "type": category,
                    "full_solution": solution
                }
            )
            tasks.append(task)
            idx += 1

            if count and len(tasks) >= count:
                break

        print(f"Loaded {len(tasks)} MATH tasks")
        return tasks

    def _extract_answer(self, solution: str) -> str:
        """Extract boxed answer from MATH solution, handling nested braces."""
        start_marker = "\\boxed{"
        idx = solution.rfind(start_marker)
        
        if idx == -1:
            # Fallback: Try to find last equation result
            match = re.search(r'=\s*([^\s]+)\s*$', solution)
            if match:
                return match.group(1)
            return "N/A"

        # Found \boxed{, now extract matching brace
        idx += len(start_marker)
        brace_count = 1
        start_idx = idx
        
        for i in range(idx, len(solution)):
            if solution[i] == '{':
                brace_count += 1
            elif solution[i] == '}':
                brace_count -= 1
            
            if brace_count == 0:
                return solution[start_idx:i]
        
        return "N/A (Unbalanced)"

    def _normalize(self, s: str) -> str:
        """Minimal normalization: strip whitespace."""
        if s is None: return ""
        return str(s).strip()

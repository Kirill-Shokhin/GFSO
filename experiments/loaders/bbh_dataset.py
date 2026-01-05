"""BIG-Bench Hard (BBH) dataset loader."""

from typing import List
from .base import DatasetLoader, Task


class BBHLoader(DatasetLoader):
    """Load BIG-Bench Hard dataset.

    Categories include:
    - logical_deduction_three_objects
    - logical_deduction_five_objects
    - logical_deduction_seven_objects
    - tracking_shuffled_objects_three_objects
    - tracking_shuffled_objects_five_objects
    - tracking_shuffled_objects_seven_objects
    - navigate
    - date_understanding
    - and more...
    """

    name = "bbh"

    # Good categories for GFSO (multi-step reasoning)
    RECOMMENDED = [
        "logical_deduction_three_objects",
        "logical_deduction_five_objects",
        "tracking_shuffled_objects_three_objects",
        "tracking_shuffled_objects_five_objects",
        "navigate",
        "date_understanding",
    ]

    def __init__(self, category: str = "logical_deduction_three_objects"):
        """
        Args:
            category: BBH task category
        """
        self.category = category

    def load(self, split: str = "test", start: int = 0, count: int = None) -> List[Task]:
        try:
            from datasets import load_dataset
        except ImportError:
            print("ERROR: 'datasets' library not installed")
            return []

        print(f"Loading BBH/{self.category}...")

        try:
            # BBH is structured as subsets
            dataset = load_dataset("lukaemon/bbh", self.category, split="test")
        except Exception as e:
            print(f"ERROR loading BBH: {e}")
            return []

        tasks = []

        for idx, item in enumerate(dataset):
            if idx < start:
                continue

            task = Task(
                id=f"bbh_{self.category}_{idx}",
                question=item.get("input", ""),
                answer=item.get("target", ""),
                domain=self.category,
                difficulty="hard",
                metadata={"category": self.category}
            )
            tasks.append(task)

            if count and len(tasks) >= count:
                break

        print(f"Loaded {len(tasks)} BBH/{self.category} tasks")
        return tasks

    def _normalize(self, s: str) -> str:
        """Normalize answer for comparison."""
        s = s.strip().lower()
        # Remove common prefixes
        for prefix in ["the answer is", "answer:", "answer is"]:
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
        # Remove parentheses around single letter answers
        if len(s) == 3 and s.startswith("(") and s.endswith(")"):
            s = s[1]
        return s

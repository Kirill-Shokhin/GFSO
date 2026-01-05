"""Humanity's Last Exam (HLE) dataset loader."""

import re
from typing import List, Any
from .base import DatasetLoader, Task


class HLELoader(DatasetLoader):
    """Load Humanity's Last Exam dataset.

    PhD-level questions across multiple domains.
    ~30% have images (vision tasks).
    """

    name = "hle"

    def load(self, split: str = "test", start: int = 0, count: int = None) -> List[Task]:
        from datasets import load_dataset
        from PIL import Image
        import io

        print(f"Loading HLE dataset (split={split})...")

        try:
            dataset = load_dataset("cais/hle", split=split, streaming=True)
        except Exception as e:
            print(f"ERROR loading HLE: {e}")
            return []

        tasks = []

        for idx, item in enumerate(dataset):
            if idx < start:
                continue

            # Parse choices from question
            q_text = item.get('question', '')
            choices = []
            answer_type = item.get('answer_type', '')

            if answer_type == 'multipleChoice':
                choice_pattern = r'^([A-F])\.\s*(.+?)$'
                for line in q_text.split('\n'):
                    match = re.match(choice_pattern, line.strip())
                    if match:
                        choices.append(match.group(2).strip())

            # Handle images
            images_list = []
            raw_img = item.get('image')
            if raw_img:
                import base64
                raw_items = raw_img if isinstance(raw_img, list) else [raw_img]
                for img_item in raw_items:
                    try:
                        if isinstance(img_item, str) and img_item.startswith('data:image'):
                            # Base64 data URI
                            header, encoded = img_item.split(",", 1)
                            data = base64.b64decode(encoded)
                            images_list.append(Image.open(io.BytesIO(data)))
                        elif isinstance(img_item, dict) and 'bytes' in img_item:
                            images_list.append(Image.open(io.BytesIO(img_item['bytes'])))
                        elif hasattr(img_item, 'save'):
                            images_list.append(img_item)
                    except Exception as e:
                        print(f"  [WARN] Image decode failed: {e}")

            task = Task(
                id=f"hle_{idx}",
                question=q_text,
                answer=item.get('answer', ''),
                choices=choices,
                domain=item.get('raw_subject', 'unknown'),
                difficulty='expert',
                images=images_list,
                metadata={
                    'original_id': item.get('id', ''),
                    'answer_type': answer_type,
                    'category': item.get('category', '')
                }
            )
            tasks.append(task)

            if count and len(tasks) >= count:
                break

        print(f"Loaded {len(tasks)} HLE tasks")
        return tasks

    def _normalize(self, s: str) -> str:
        """Normalize answer."""
        s = s.strip().lower()
        # Remove common wrappers
        s = re.sub(r'^\*+|\*+$', '', s)
        s = re.sub(r'^#+\s*', '', s)
        return s.strip()

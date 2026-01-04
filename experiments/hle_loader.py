"""Load Last Humanity Exam dataset from HuggingFace.

Dataset: cais/hle
Source: https://huggingface.co/datasets/cais/hle

Adapted for GFSO integration.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import re

@dataclass
class Question:
    """Single question from Last Humanity Exam."""
    id: str
    text: str
    choices: List[str]  # For multiple choice
    answer: str  # Ground truth
    domain: str  # Subject area (math, physics, etc.)
    difficulty: str  # If available
    metadata: Dict[str, Any]  # Additional info
    images: Optional[List] = field(default_factory=list)  # PIL Images for vision (30% of HLE)

def load_hle_dataset(split: str = "test", max_questions: int = None, specific_index: int = None) -> List[Question]:
    """Load Last Humanity Exam from HuggingFace.

    Args:
        split: Dataset split ('test', 'train', etc.)
        max_questions: Limit number of questions (for testing)
        specific_index: Load ONLY the question at this index (0-based)

    Returns:
        List of Question objects
    """
    try:
        from datasets import load_dataset

        print(f"Loading Humanity's Last Exam (split={split})...")
        # Load in streaming mode to avoid downloading huge files if we just need one index
        dataset = load_dataset("cais/hle", split=split, streaming=True)

        questions = []
        
        # If specific_index is set, we skip until we hit it
        target_indices = {specific_index} if specific_index is not None else None
        
        count = 0
        for idx, item in enumerate(dataset):
            if target_indices is not None:
                if idx != specific_index:
                    continue
            
            if max_questions and len(questions) >= max_questions:
                break

            # Parse choices from question text (usually labeled A, B, C, D)
            q_text = item.get('question', '')
            choices = []
            answer_type = item.get('answer_type', '')
            
            if answer_type == 'multipleChoice':
                choice_pattern = r'^([A-F])\.\s*(.+?)$'
                for line in q_text.split('\n'):
                    match = re.match(choice_pattern, line.strip())
                    if match:
                        choices.append(match.group(2).strip())

            # Estimate difficulty based on category
            category = item.get('category', 'unknown')
            difficulty = 'hard' if category == 'STEM' else 'medium'
            
            # Handle images (normalize to List[PIL.Image])
            raw_img = item.get('image')
            images_list = []
            if raw_img:
                from PIL import Image
                import io
                
                # Normalize raw_img to a list
                raw_items = raw_img if isinstance(raw_img, list) else [raw_img]
                
                for img_item in raw_items:
                    try:
                        if isinstance(img_item, dict) and 'bytes' in img_item:
                            images_list.append(Image.open(io.BytesIO(img_item['bytes'])))
                        elif isinstance(img_item, str):
                            if img_item.startswith('data:image'):
                                # Handle base64 Data URI
                                import base64
                                header, encoded = img_item.split(",", 1)
                                data = base64.b64decode(encoded)
                                images_list.append(Image.open(io.BytesIO(data)))
                            else:
                                # It might be a path or URL
                                images_list.append(Image.open(img_item))
                        else:
                            # Already a PIL Image or something else
                            images_list.append(img_item)
                    except Exception as e:
                        print(f"  [WARN] Failed to decode image: {e}")

            question = Question(
                id=item.get('id', f'q_{idx}'),
                text=q_text,
                choices=choices,
                answer=item.get('answer', ''),
                domain=item.get('raw_subject', 'unknown'),
                difficulty=difficulty,
                metadata=dict(item),
                images=images_list
            )
            questions.append(question)
            
            # If we found our specific index, we can stop immediately
            if target_indices is not None:
                break

        print(f"Loaded {len(questions)} questions")
        return questions

    except ImportError:
        print("ERROR: 'datasets' library not installed")
        print("Install with: pip install datasets")
        return []

    except Exception as e:
        print(f"ERROR loading dataset: {e}")
        import traceback
        traceback.print_exc()
        return []

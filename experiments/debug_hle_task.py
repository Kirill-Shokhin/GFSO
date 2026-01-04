"""Debug script to run GFSO Agent on a single HLE task."""

import sys
import os
import argparse
import json

# Add GFSO root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from experiments.hle_loader import load_hle_dataset
from gfso_agent.core import GFSOAgent
from gfso_agent.llm import AnthropicLLM, MockLLM

def run_debug_task(index: int, use_mock: bool = False):
    print(f"--- Debugging HLE Task #{index} ---")
    
    questions = load_hle_dataset(split="test", specific_index=index)
    
    if not questions:
        print(f"Error: Could not load question #{index}")
        return

    q = questions[0]
    print(f"\n[Domain]: {q.domain}")
    print(f"[Question]:\n{q.text}")
    print(f"[Ground Truth]: {q.answer}")
    
    # Handle images (if any)
    image_paths = []
    if q.images:
        print(f"[Images]: {len(q.images)} attached (vision task)")
        try:
            import tempfile
            for idx, img_obj in enumerate(q.images):
                # Check if it's really a PIL image or similar
                if not hasattr(img_obj, 'save'):
                    print(f"  [WARN] Image object {idx} has no save method (type: {type(img_obj)}). Skipping.")
                    continue

                # Determine format (default to PNG if unknown)
                fmt = getattr(img_obj, 'format', 'PNG') or 'PNG'
                suffix = f".{fmt.lower()}"
                
                # Create temp file. delete=False so Agent can read it.
                # User/OS handles cleanup of temp.
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode='wb') as tmp:
                    # We save to the file path, closing the handle first to allow re-opening
                    tmp.close()
                    img_obj.save(tmp.name, format=fmt)
                    image_paths.append(tmp.name)
                    print(f"  -> Saved temp image: {tmp.name}")
                    
        except Exception as e:
            print(f"  [ERROR] Image processing failed: {e}")

    print("\n--- Agent Execution (GFSO v2.2 Baseline) ---")
    
    try:
        if use_mock:
            print("Using MockLLM (Explicitly requested)")
            llm = MockLLM()
        else:
            print("Using AnthropicLLM (Real Inference)")
            # Check for API key
            key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
            if not key:
                print("\n[FATAL ERROR]: No API Key found in environment variables (ANTHROPIC_API_KEY or CLAUDE_API_KEY).")
                print("Aborting. To use Mock, pass --mock flag.")
                sys.exit(1)
            else:
                llm = AnthropicLLM(api_key=key)

        agent = GFSOAgent(llm)
        
        # Prepare task string
        task_str = f"Question: {q.text}\n"
        if q.choices:
            task_str += "Choices:\n" + "\n".join(f"- {c}" for c in q.choices)
        
        print(f"\n[Input Task]: {task_str[:200]}...")
        print(f"\n[GROUND TRUTH]: {q.answer}")
        print("=" * 60)
        
        # Run Agent
        if image_paths:
            print("\n--- Perception Check (Direct Vision Test) ---")
            check_prompt = "Look at this image. If it's a chess board, describe the position of key pieces and the current FEN. If it's something else, describe it briefly."
            try:
                perception = llm.generate(check_prompt, images=image_paths)
                print(f"[Model Perception]:\n{perception}")
            except Exception as e:
                print(f"[Perception Error]: {e}")
            print("-" * 40)

        artifacts = agent.run(task_str, images=image_paths)
        
        print("\n--- Execution Finished ---")
        print("[Artifacts Generated]:", list(artifacts.keys()))
        
        # Naive "Head" - just dumping the artifacts
        for k, v in artifacts.items():
            print(f"\n>>> Artifact [{k}]:\n{str(v)[:500]}...")
            
    except Exception as e:
        print(f"\n[CRITICAL FAILURE]: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int, help="Index of HLE question to test")
    parser.add_argument("--mock", action="store_true", help="Use MockLLM")
    args = parser.parse_args()
    
    run_debug_task(args.index, use_mock=args.mock)
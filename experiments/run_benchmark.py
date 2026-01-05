"""
Universal benchmark runner for GFSO experiments.

Usage:
    # MATH Level 5
    python experiments/run_benchmark.py --dataset math --start 0 --count 10

    # BBH logical_deduction
    python experiments/run_benchmark.py --dataset bbh --category logical_deduction_three_objects --count 10

    # HLE (legacy)
    python experiments/run_benchmark.py --dataset hle --start 0 --count 5
"""

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from experiments.loaders import get_loader, Task, DATASETS
from gfso_agent.core import GFSOAgent
from gfso_agent.llm import AnthropicLLM, MockLLM
from gfso_agent.logger import logger
from gfso_agent.types import HeadMode


def setup_output_dir(dataset: str, task_idx: int, output_root: str = "outputs") -> Path:
    """Create output directory for a task."""
    task_dir = Path(output_root) / dataset / f"task_{task_idx:04d}"
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def save_images(task: Task, task_dir: Path) -> list[str]:
    """Save task images if any."""
    if not task.images:
        return []

    images_dir = task_dir / "images"
    images_dir.mkdir(exist_ok=True)
    saved = []

    for idx, img in enumerate(task.images):
        if hasattr(img, 'save'):
            fmt = getattr(img, 'format', 'PNG') or 'PNG'
            path = images_dir / f"image_{idx}.{fmt.lower()}"
            img.save(str(path), format=fmt)
            saved.append(str(path))

    return saved


def run_task(task: Task, llm, dataset_name: str, loader, output_root: str = "outputs") -> dict:
    """Run single task with GFSO agent."""
    task_dir = setup_output_dir(dataset_name, int(task.id.split("_")[-1]), output_root)
    log_path = task_dir / "gfso_log.txt"

    # Configure logger for this task
    logger.setup(level="INFO", log_file=str(log_path))

    # Save images if any
    image_paths = save_images(task, task_dir)

    # Save task metadata
    meta = {
        "id": task.id,
        "domain": task.domain,
        "difficulty": task.difficulty,
        "question": task.question,
        "ground_truth": task.answer,
        "has_images": len(image_paths) > 0,
        "timestamp": datetime.now().isoformat()
    }
    with open(task_dir / "task_meta.json", 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # Run agent
    try:
        agent = GFSOAgent(llm)

        task_str = f"Question: {task.question}\n"
        if task.choices:
            task_str += "Choices:\n" + "\n".join(f"- {c}" for c in task.choices)

        # Use STRICT mode for benchmarks (minimal output)
        artifacts = agent.run(task_str, images=image_paths if image_paths else None, mode=HeadMode.STRICT)

        head = artifacts['HEAD_RESULT']
        answer, status = head.answer.strip(), head.status
        is_correct = loader.check_answer(answer, task.answer, llm=llm)

        result = {
            "task_id": task.id,
            "ground_truth": task.answer,
            "prediction": answer,
            "status": status,
            "correct": is_correct,
            "output_dir": str(task_dir)
        }

    except Exception as e:
        import traceback
        result = {
            "task_id": task.id,
            "ground_truth": task.answer,
            "status": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "output_dir": str(task_dir)
        }

    # Save results
    with open(task_dir / "results.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


def run_benchmark(
    dataset: str,
    start: int = 0,
    count: int = 10,
    use_mock: bool = False,
    output_root: str = "outputs",
    **loader_kwargs
):
    """Run benchmark on dataset."""
    print(f"\n{'#'*60}")
    print(f"  GFSO Benchmark Runner")
    print(f"  Dataset: {dataset}")
    print(f"  Tasks: {start} to {start + count - 1}")
    print(f"{'#'*60}\n")

    # Setup LLM
    if use_mock:
        print("[MODE] MockLLM")
        llm = MockLLM()
    else:
        print("[MODE] AnthropicLLM")
        key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not key:
            print("[FATAL] No API key. Set ANTHROPIC_API_KEY or use --mock")
            sys.exit(1)
        llm = AnthropicLLM(api_key=key)

    # Load dataset
    loader = get_loader(dataset, **loader_kwargs)
    tasks = loader.load(split="test", start=start, count=count)

    if not tasks:
        print("[ERROR] No tasks loaded")
        return

    # Run tasks
    results = []
    for task in tasks:
        print(f"\n{'='*60}")
        print(f"  Task: {task.id} | {task.domain}")
        print(f"{'='*60}")
        print(f"Q: {task.question[:100]}...")
        print(f"GT: {task.answer}")

        result = run_task(task, llm, dataset, loader, output_root)
        results.append(result)

        if result.get("status") != "ERROR":
            print(f"Pred: {result.get('prediction', '')[:50]}...")
            print(f"Result: {'CORRECT' if result.get('correct') else 'WRONG'} (pipeline: {result.get('status')})")
        else:
            print(f"Result: ERROR - {result.get('error', '')[:50]}")

        if not use_mock:
            import time
            time.sleep(1)

    # Summary
    print(f"\n{'#'*60}")
    print("  SUMMARY")
    print(f"{'#'*60}")

    total = len(results)
    success = sum(1 for r in results if r.get("status") != "ERROR")
    correct = sum(1 for r in results if r.get("correct"))
    no_answer = sum(1 for r in results if r.get("prediction") == "N/A")

    print(f"Total:      {total}")
    print(f"Completed:  {success}")
    print(f"Correct:    {correct} ({100*correct/total:.1f}%)")
    print(f"No Answer:  {no_answer}")
    print(f"Wrong:      {total - correct - no_answer}")

    # Save summary
    summary = {
        "dataset": dataset,
        "loader_kwargs": loader_kwargs,
        "start": start,
        "count": count,
        "total": total,
        "success": success,
        "correct": correct,
        "no_answer": no_answer,
        "accuracy": correct / total if total > 0 else 0,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }

    summary_path = Path(output_root) / dataset / f"summary_{start:04d}_{start+count-1:04d}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nSummary saved: {summary_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GFSO benchmark")
    parser.add_argument("--dataset", type=str, required=True, choices=list(DATASETS.keys()),
                        help="Dataset to run (math, bbh, hle)")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--count", type=int, default=10, help="Number of tasks")
    parser.add_argument("--mock", action="store_true", help="Use MockLLM")
    parser.add_argument("--output", type=str, default="outputs", help="Output directory")

    # MATH-specific
    parser.add_argument("--levels", type=int, nargs="+", default=[5],
                        help="MATH difficulty levels (1-5)")

    # BBH-specific
    parser.add_argument("--category", type=str, default="logical_deduction_three_objects",
                        help="BBH category")

    args = parser.parse_args()

    # Build loader kwargs
    loader_kwargs = {}
    if args.dataset == "math":
        loader_kwargs["levels"] = args.levels
    elif args.dataset == "bbh":
        loader_kwargs["category"] = args.category

    run_benchmark(
        dataset=args.dataset,
        start=args.start,
        count=args.count,
        use_mock=args.mock,
        output_root=args.output,
        **loader_kwargs
    )

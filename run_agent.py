import sys
import os
import argparse
from gfso_agent.core import GFSOAgent
from gfso_agent.llm import AnthropicLLM
from gfso_agent.logger import logger

def main():
    parser = argparse.ArgumentParser(description="GFSO Agent CLI")
    parser.add_argument("task", help="The task description")
    parser.add_argument("--images", nargs="*", help="List of image file paths", default=None)
    parser.add_argument("--model", help="Anthropic model ID", default="claude-haiku-4-5-20251001")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed mathematical logging")
    parser.add_argument("--log-file", help="Path to save execution log")
    
    args = parser.parse_args()

    # Configure Logger
    level = "DEBUG" if args.verbose else "INFO"
    logger.setup(level=level, log_file=args.log_file)

    try:
        llm = AnthropicLLM(model=args.model)
        agent = GFSOAgent(llm, max_depth=3)
        
        results = agent.run(args.task, images=args.images)
        
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        logger.section(f"Saving {len(results)} Artifacts to '{output_dir}/'")
        for step, content in results.items():
            ext = ".txt"
            if "def " in content or "class " in content or "import " in content:
                ext = ".py"
            elif "{" in content and "}" in content:
                ext = ".json"
                
            filename = f"{output_dir}/{step}{ext}"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            # Use raw logger for file saving info to avoid prefixing
            logger._logger.info(f"  Saved: {filename}")
            
    except Exception as e:
        logger.error(f"Critical System Failure: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
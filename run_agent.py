import sys
import os
import argparse
from gfso_agent.core import GFSOAgent
from gfso_agent.llm import AnthropicLLM

def main():
    parser = argparse.ArgumentParser(description="GFSO Agent CLI")
    parser.add_argument("task", help="The task description")
    parser.add_argument("--images", nargs="*", help="List of image file paths", default=None)
    parser.add_argument("--model", help="Anthropic model ID", default="claude-haiku-4-5-20251001")
    
    args = parser.parse_args()

    print(f"Initializing GFSO Agent with model: {args.model}")
    
    try:
        llm = AnthropicLLM(model=args.model)
        agent = GFSOAgent(llm, max_depth=3)
        
        results = agent.run(args.task, images=args.images)
        
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n\n=== Saving Artifacts to '{output_dir}/' ===")
        for step, content in results.items():
            ext = ".txt"
            if "def " in content or "class " in content or "import " in content:
                ext = ".py"
            elif "{" in content and "}" in content:
                ext = ".json"
                
            filename = f"{output_dir}/{step}{ext}"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Saved: {filename}")
            
    except Exception as e:
        print(f"Critical Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

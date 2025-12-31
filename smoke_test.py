from gfso_agent.core import GFSOAgent
from gfso_agent.llm import MockLLM
from gfso_agent.logger import logger

def test_complex_flow():
    # Force DEBUG level for full mathematical trace
    logger.setup(level="DEBUG")
    
    llm = MockLLM()
    agent = GFSOAgent(llm, max_depth=2)
    
    print("\n[STARTING COMPLEX SMOKE TEST]")
    try:
        # Complex task: Web App (triggers recursion in our mock)
        results = agent.run("Build a full-stack Web App with Dashboard", images=["ui_mockup.png"])
        
        print("\n[TEST COMPLETED]")
        print(f"Total artifacts generated: {len(results)}")
        for k in results.keys():
            print(f" - {k}")
            
    except Exception as e:
        print(f"\nFAILURE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_complex_flow()
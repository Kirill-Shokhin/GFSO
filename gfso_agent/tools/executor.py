import subprocess
import sys
import time
from dataclasses import dataclass

@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration: float
    timed_out: bool = False

    def __str__(self):
        s = f"[Exit: {self.exit_code}, Time: {self.duration:.2f}s"
        if self.timed_out: s += ", TIMEOUT"
        s += "\n"
        if self.stdout: s += f"STDOUT:\n{self.stdout}\n"
        if self.stderr: s += f"STDERR:\n{self.stderr}\n"
        return s

class PythonExecutor:
    """Executes Python code in a subprocess with timeout."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def run(self, code: str) -> ExecutionResult:
        start_time = time.time()
        print(f"    -> [EXECUTOR] Running {len(code)} bytes of Python code...")
        
        try:
            # We run python -c "code"
            # NOTE: Ideally we should write to a temp file to handle quotes/multiline better,
            # but for simplicity we start with subprocess piping.
            # ACTUALLY: Passing complex code via -c arg is risky on Windows due to quoting.
            # BETTER: Write to temp file.
            
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_path = f.name
            
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                
                process = subprocess.Popen(
                    [sys.executable, temp_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    cwd=os.getcwd(), # Run in current dir to access local files
                    env=env
                )
                
                try:
                    stdout, stderr = process.communicate(timeout=self.timeout)
                    return ExecutionResult(
                        stdout=stdout,
                        stderr=stderr,
                        exit_code=process.returncode,
                        duration=time.time() - start_time
                    )
                except subprocess.TimeoutExpired:
                    process.kill()
                    return ExecutionResult(
                        stdout="",
                        stderr=f"Execution timed out after {self.timeout}s.",
                        exit_code=-1,
                        duration=time.time() - start_time,
                        timed_out=True
                    )
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=f"System Error: {str(e)}",
                exit_code=-2,
                duration=time.time() - start_time
            )

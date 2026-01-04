import logging
import sys
from typing import Optional

class GFSOLogger:
    def __init__(self):
        self._logger = logging.getLogger("GFSO")
        self._logger.setLevel(logging.INFO)
        self._console_handler = logging.StreamHandler(sys.stdout)
        self._console_handler.setFormatter(logging.Formatter('%(message)s'))
        self._logger.addHandler(self._console_handler)
        self._file_handler = None

    def setup(self, level: str = "INFO", log_file: Optional[str] = None):
        log_level = getattr(logging, level.upper())
        self._logger.setLevel(log_level)
        
        if log_file:
            # Remove old file handler if exists to prevent duplicates and force overwrite
            if self._file_handler:
                self._logger.removeHandler(self._file_handler)
            
            # mode='w' forces overwrite
            self._file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
            # Format: relative seconds | msg. Simple.
            self._file_handler.setFormatter(logging.Formatter('%(relativeCreated)d s | %(message)s'))
            # We want seconds, relativeCreated is ms. 
            # Custom formatter needed or just accept ms. 
            # Let's keep it simple: Use asctime for absolute time or accept ms for now. 
            # Actually user asked for seconds.
            class SecFormatter(logging.Formatter):
                def format(self, record):
                    record.relativeSeconds = record.relativeCreated / 1000
                    return super().format(record)
            
            fmt = SecFormatter('%(relativeSeconds).3f s | %(message)s')
            self._file_handler.setFormatter(fmt)
            self._logger.addHandler(self._file_handler)

    def _indent(self, depth: int) -> str:
        return "  " * depth + "│ "

    def section(self, title: str, depth: int = 0):
        pre = "  " * depth
        self._logger.info(f"\n{pre}╔══ {title} ══")

    def end_section(self, title: str, depth: int = 0):
        pre = "  " * depth
        self._logger.info(f"{pre}╚══ {title} Done ══\n")

    def step_start(self, step_id: str, depth: int):
        self._logger.info(f"{self._indent(depth)}▶ t({step_id})")

    def step_success(self, step_id: str, depth: int):
        self._logger.info(f"{self._indent(depth)}✔ Converged: {step_id}")

    def recursion_start(self, step_id: str, depth: int):
        self._logger.info(f"{self._indent(depth)}⟳ RECURSION: Spawning Sub-Agent for '{step_id}'")

    def log_contract(self, contract_str: str, depth: int):
        # Changed to INFO so user can see what Architect passed to Worker
        ind = self._indent(depth)
        self._logger.info(f"{ind}┌── [CONTRACT G(x)] ──")
        for line in contract_str.split('\n'):
            if line.strip(): self._logger.info(f"{ind}│ {line}")
        self._logger.info(f"{ind}└─────────────────────")

    def log_artifact(self, name: str, content: str, depth: int):
        # Changed to INFO so user can see code/artifacts in the file
        ind = self._indent(depth)
        self._logger.info(f"{ind}┌── [ARTIFACT F(x): {name}] ──")
        
        # Limit preview length for console legibility, but file has full
        lines = content.split('\n')
        for i, line in enumerate(lines):
            self._logger.info(f"{ind}│ {line}")
            
        self._logger.info(f"{ind}└─────────────────────────────")

    def log_validation(self, epsilon: float, laxity: float, feedback: str, passed: bool, depth: int):
        ind = self._indent(depth)
        status = "PASSED" if passed else "REJECTED"
        icon = "✔" if passed else "✖"
        log_method = self._logger.info 
        
        log_method(f"{ind}{icon} [VALIDATION η] {status}")
        log_method(f"{ind}  Metric ε (Object Error):   {epsilon:.2f}")
        log_method(f"{ind}  Metric λ (Integr. Error): {laxity:.2f}")

    def error(self, msg: str, depth: int = 0):
        self._logger.error(f"{self._indent(depth)}!!! ERROR: {msg}")

logger = GFSOLogger()
logger.setup(level="INFO", log_file="gfso_agent.log")
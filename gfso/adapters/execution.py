"""Where a session or a command runs (`ExecutionPort`): `LocalExecution` — on this host, as every launch ran before
the port existed."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from gfso.core.types import ExecutionPort
from gfso.config import claude_config_dir
from gfso.adapters.children import adopt, kill_tree, release, spawn_kw


class LocalExecution(ExecutionPort):
    def which(self, program: str):
        return shutil.which(program)

    def popen(self, args, *, env, cwd, **pipes):
        # Windows: a console child ALLOCATES ITS OWN console when the parent has none (the shared server is spawned
        # detached) — every agent run popped an empty `claude` window on top of the user's screen, accidentally
        # closable (= killing the run). CREATE_NO_WINDOW suppresses the console; all real I/O rides the pipes.
        no_window = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        return adopt(subprocess.Popen(args, env=env, cwd=cwd, **pipes, **no_window, **spawn_kw()))

    def end(self, proc) -> None:
        kill_tree(proc)
        release(proc)

    def scratch(self, prefix: str):
        return tempfile.TemporaryDirectory(prefix=prefix)

    def state_dir(self):
        return claude_config_dir()

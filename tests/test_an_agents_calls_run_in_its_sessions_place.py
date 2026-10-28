"""An agent's own calls — its CLI session, its tool loop's commands — start in the execution of the place it works in
(`ExecutionPort.session`), never in the one the system's own commands run in: a call written past it would run with
every place of the project in reach again."""
from gfso.adapters.execution import LocalExecution
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.toolloop import Place


class _Proc:
    stdin = stdout = None
    pid, returncode = 4242, 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class _Session(LocalExecution):
    def __init__(self):
        self.started = []

    def popen(self, args, **kw):
        self.started.append(args)
        return _Proc()

    def end(self, proc):
        pass


class _Project(LocalExecution):
    """The system's execution: what it starts itself, and the session it hands each place."""

    def __init__(self):
        self.started, self.places = [], {}

    def popen(self, args, **kw):
        self.started.append(args)
        return _Proc()

    def session(self, cwd, agent=None):
        return self.places.setdefault(cwd, _Session())

    def end(self, proc):
        pass


def test_a_cli_session_starts_in_its_places_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(H.ClaudeCodeProvider, "_read_stream", lambda self, proc, t0, cap: ({"result": "R"}, [], 0))
    project = _Project()
    llm = H.ClaudeCodeProvider(execution=project)
    llm._cmd = "claude"
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path)) == "R"
    assert project.started == [] and project.places[str(tmp_path)].started, "started past the session's place"


def test_a_tool_loops_commands_run_in_its_places_execution(tmp_path):
    project = _Project()
    assert Place(project, str(tmp_path)).exec is project.session(str(tmp_path))


def test_a_conversation_keeps_its_state_where_its_session_runs(tmp_path, monkeypatch):
    """The handover hook's notes, the spend so far, the transcript a round resumes: kept in the state of the place
    the conversation runs in, which no other place's session holds."""
    monkeypatch.setattr(H.ClaudeCodeProvider, "_read_stream", lambda self, proc, t0, cap: ({"result": "R"}, [], 0))
    project = _Project()
    llm = H.ClaudeCodeProvider(execution=project)
    llm._cmd = "claude"
    llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path), session="s1")
    assert llm.hooks.where("s1") is project.places[str(tmp_path)]

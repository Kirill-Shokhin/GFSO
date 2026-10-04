"""The one owner of where state lives — the four paths every door has to agree about.

They were derived in seven places, and they did not agree: `serverctl` composed the roster as
`home()/"data"/"agents.json"` while the registry read `data_dir()/"agents.json"`, so setting
`GFSO_DATA_DIR` moved the graphs and left the roster behind; `connect` composed the database the
same hand-built way; `doctor` reported a path the engine did not use. One derivation each, here.

**Read at CALL time, never snapshotted at import.** `cli` writes six `GFSO_*` variables before
handing control to uvicorn, `driver` writes `GFSO_PROJECT`, `connect` fills the child's environment,
and the test suite sets and unsets these with `monkeypatch` from a session-scoped fixture — which
runs AFTER import. A snapshot makes all of that silently inert: not a red suite, a different
measurement.

What is deliberately NOT here: `GFSO_L2_GATE`. It is the switch of a MEASURED mechanism and lives at
its point of enforcement on purpose, where the code that obeys it is the code that reads it.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

# The installation root — the package's parent, used when the checkout itself is the home.
ROOT = Path(__file__).resolve().parent.parent


def home() -> Path:
    """The installation's home: `GFSO_HOME` wins; a source checkout (a `pyproject.toml` beside the
    package) is its own home; otherwise `~/.gfso` — ONE per user, for the same reason there is one
    server."""
    declared = os.environ.get("GFSO_HOME")
    if declared:
        return Path(declared).expanduser().resolve()
    return ROOT if (ROOT / "pyproject.toml").exists() else Path.home() / ".gfso"


def data_dir() -> Path:
    """THE state directory: `GFSO_DATA_DIR` if set, else `data/` under the home."""
    return Path(os.environ.get("GFSO_DATA_DIR") or (home() / "data"))


def db_path(project: str | None = None) -> Path:
    """The database file. `GFSO_DB_PATH` names the DEFAULT project's file explicitly; a named
    project is always `<data_dir>/<name>.db`, because a named graph is a file of its own and an
    explicit override of the default one says nothing about where the others go."""
    if project:
        return data_dir() / f"{project}.db"
    return Path(os.environ.get("GFSO_DB_PATH") or (data_dir() / "gfso.db"))


def agents_path() -> Path:
    """The roster of non-human participants — one file, shared by every session of the one server."""
    return Path(os.environ.get("GFSO_AGENTS_PATH") or (data_dir() / "agents.json"))


# ── The names two or more modules have to agree about ───────────────────────────────────────────

#: The loopback host. One server, one address (§ the product's own rule) — spelled in six modules
#: before this, which is five chances for the page and its API to disagree about who they are.
LOOPBACK = "127.0.0.1"

#: The DEFAULT model tier, per door rather than one global value — the doors are deliberately
#: different, and the MCP schema shows its default to the agent reading it. Collapsing them into one
#: number would be a decision about measurement wearing the clothes of a cleanup, so what is shared
#: here is the NAME, not a single value.
# A full id, not the `sonnet` alias: the alias resolves by the installed CLI's age — a container's 2.1.272 ran
# claude-sonnet-5 while the author meant the current one (2026-10-07) — and a row must say what ran
# `GFSO_SYSTEM_MODEL` moves every door at once — the plan's author, its reviewer, the issuer's function, and any
# executor or validator whose roster entry names no model: the user who chooses a cheaper model for the system
# chooses it for every role the system plays, or a stronger one holds the work through the doors left behind
MODEL_DEFAULT = os.environ.get("GFSO_SYSTEM_MODEL") or "claude-sonnet-5-5"

# HOW MANY READINGS OF THE GOAL the sufficiency check takes before it answers. Not a quality knob:
# measured on the MCP door 2026-08-21, the check discovered its objections SERIALLY — eight review
# rounds, ~20 minutes and ~$1.50, findings 7→5→2→2→1→1→1→0, each round surfacing a fresh obligation
# from a new reading of the SAME goal text. Every finding was true; the cost was the shape of the
# loop. Independent samples of one reading, unioned, is the same discovery paid for in parallel
# instead of in rounds. 1 = the old behaviour.
SUFFICIENCY_READINGS = 3

#: The id every door offers as the default root of a graph. Seven signatures spelled it, which is
#: six chances for one of them to drift and author a second root nobody is looking at.
ROOT_ID = "root"

#: The project that exists before anyone names one.
DEFAULT_PROJECT = "default"


# ── The settings the doors read, each with ONE reader ───────────────────────────────────────────
#
# Every one of these was `os.environ.get(...)` at its point of use, in ten modules, with the DEFAULT
# repeated at each site — so "what does GFSO do when this is unset" had as many answers as there were
# spellings. Read at CALL time (never snapshotted at import): a test that sets the variable after
# importing the module must be obeyed, which is how the gate's own probes work.

def _flag(name: str, default: str = "0") -> bool:
    """An on/off switch, read the way the product has always read them: anything but "" and "0"."""
    return os.environ.get(name, default) not in ("", "0")


def shared_url() -> str:
    """Where the ONE server lives — the single knob the whole product turns on (`GFSO_SHARED_URL`)."""
    return os.environ.get("GFSO_SHARED_URL", f"http://{LOOPBACK}:8000/mcp")


def agent_id() -> str:
    """The calling agent's standing identity. Identity is TRANSPORT-derived, not configured: this is
    the agent's own door, so an omitted assignee can only mean the agent itself. `GFSO_AGENT_ID`
    merely RENAMES it (the multi-agent future); it is never required."""
    return os.environ.get("GFSO_AGENT_ID") or "agent"


#: where the server remembers which project it was pointed at, so a RESTART does not silently
#: move everyone back to `default` (measured on the MCP door, wave 26, 2026-09-06: "use_project
#: falls back to default after a server restart" — the session map lives in memory and the session
#: object is new, so the fallback was the registry's active, and the registry started at default).
ACTIVE_PROJECT_FILE = "active_project"


def project_by_env() -> str:
    """The project the deployment names (`GFSO_PROJECT`), or ''."""
    return os.environ.get("GFSO_PROJECT", "")


def active_project() -> str:
    """The project a session starts in when it names none.

    `GFSO_PROJECT` wins — an explicit environment is a deployment saying where it points. Otherwise
    the last project this installation was SWITCHED to, which survives a restart; and `default` when
    nothing has been chosen yet.
    """
    if named := project_by_env():
        return named
    try:
        remembered = (data_dir() / ACTIVE_PROJECT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_PROJECT
    return remembered or DEFAULT_PROJECT


def remember_active_project(name: str) -> None:
    """Write down which project was switched to. Best-effort: a read-only data dir must not make
    `use_project` fail — what is lost then is only the memory of it across a restart."""
    try:
        d = data_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / ACTIVE_PROJECT_FILE).write_text(str(name), encoding="utf-8")
    except OSError as ex:
        # SAID, not swallowed: the switch still happened, and what was lost is only its memory
        # across a restart — which is exactly the thing whose absence was reported as silent.
        logging.getLogger(__name__).warning(
            "could not remember the active project %r (%s) — this session is switched, but a "
            "restart will start where it started before", name, ex)


def state_timeout() -> float:
    """Inv-5's state-age timeout, in seconds. DEFAULT 0 = OFF: a clock that fires on its own would
    move a graph nobody was driving."""
    try:
        return float(os.environ.get("GFSO_STATE_TIMEOUT", "0"))
    except ValueError:
        return 0.0


#: §12.2: which bound fires where. Work states (EXECUTING, REWORKING) run on the packet deadline;
#: ANSWER states — one party waiting on the other — run on the deadline AND their own bound,
#: whichever comes first; VALIDATING runs on T_validate ALONE, counted from DELIVER, so that a
#: last-moment delivery cannot be pushed to ESCALATED unvalidated through the deadline; the PROTOCOL
#: states carry their own bound only. The canon requires the bounds to exist and fire (Inv-5) and
#: fixes no numbers: these are defaults, each overridable by its own variable, and their adequacy is
#: a disclosed residue (§12.13) — a bound shorter than an answer takes satisfies the invariant and
#: puts every report into §16's issuer-response exception.
_STATE_BOUND_DEFAULTS = {
    # the answer states: generous, because what they wait for is a party's decision
    "OFFERED": 86_400.0, "CHALLENGED": 86_400.0, "BLOCKED": 86_400.0,
    # T_validate. A validation of a rich contract has been measured at 312 s at the top tier
    # (§9.9 / the batch note), so an hour is the wait before the issuer is asked again rather
    # than the time a verdict takes.
    "VALIDATING": 3_600.0,
    # the protocol states. CANCELLING waits for a handshake reply; ESCALATED waits for the issuer's
    # own decision.
    "CANCELLING": 120.0, "ESCALATED": 86_400.0,
}


def state_bound(state_name: str) -> float:
    """The per-state bound in seconds — `GFSO_BOUND_<STATE>`, 0 = none for that state."""
    try:
        return float(os.environ.get(f"GFSO_BOUND_{state_name}",
                                    _STATE_BOUND_DEFAULTS.get(state_name, 0.0)))
    except ValueError:
        return _STATE_BOUND_DEFAULTS.get(state_name, 0.0)


def agent_trace_dir() -> str:
    """Where each agent run's raw stream is kept — `GFSO_AGENT_TRACE_DIR`; empty = not kept."""
    return os.environ.get("GFSO_AGENT_TRACE_DIR", "")


def default_deadline_s() -> float:
    """How far ahead the engine writes a deadline the issuer did not type — `GFSO_DEFAULT_DEADLINE_S`.

    §2.5: every entry into OFFERED carries a deadline that lies ahead of it, and "the canon requires
    the packet to carry a deadline, not the issuer to type one": an implementation may write a
    default, logged as supplied. 0 = write none (the pre-v4.1 behaviour)."""
    try:
        return float(os.environ.get("GFSO_DEFAULT_DEADLINE_S", 86_400.0))
    except ValueError:
        return 86_400.0


def validation_batch() -> int:
    """How many PROBES one validator run owes at most — `GFSO_VALIDATION_BATCH`, default 16, `0` = one run over
    the whole validation. A run owes its criteria's pinned probes, the parts' pinned probes they rest on (each once)
    and their regression lines; a criterion owing none counts one (`tools_llm._scope_batches`).

    A dial rather than a constant because it is the knob of a MEASURED trade: batching unblocked
    acceptance on rich contracts (a report must speak to every criterion, §2.3, and on long ones it
    stopped doing so), and the batches run concurrently, so the size decides how much of a
    validation happens in parallel. It counted CRITERIA until 2026-10-11, and a criterion is not a unit
    of work: the c_compiler root (GB_c_compiler_tmqn88552, every role on claude-haiku-5-5) had 4 criteria,
    one batch, and owed 75 probes (4 pinned, 33 distinct part probes, 38 regression lines) — 17 reports in
    55 minutes were not a verdict, 15 of them for probes left out. In the same run the same model's reports
    over lists of at most 16 owed probes (the ten parts; root.vec's reached 16) were verdicts 16 times of 18,
    and the root's, over 37 and more, 2 times of 19. The default is the largest list it was seen to cover."""
    try:
        return max(0, int(os.environ.get("GFSO_VALIDATION_BATCH", VALIDATION_BATCH)))
    except ValueError:
        return VALIDATION_BATCH


#: Model sessions one server runs at once (`max_sessions`).
MAX_SESSIONS = 8


def max_sessions() -> int:
    """How many model sessions the dispatcher runs at once — executors, validators and the issuer's answers alike —
    `GFSO_MAX_SESSIONS`, default 8. It bounds the user's machine and the account, nothing in the protocol: every
    independent part may run at once (§10.4, the frontier). Four, fixed, made a plan of eight independent parts run
    in two waves, and a delivered part waited for its validator behind them (AUTO haiku coreutils, 2026-10-10)."""
    try:
        return max(1, int(os.environ.get("GFSO_MAX_SESSIONS", MAX_SESSIONS)))
    except ValueError:
        return MAX_SESSIONS


def validator_retry_model() -> str | None:
    """Which tier validates the RETRY after a validator returns no verdict — `GFSO_VALIDATOR_RETRY_MODEL`,
    default none: the retry runs on the node's own tier.

    It used to escalate to opus by default, on the reading that a ⊥ report is a coverage gap a bigger
    model closes. It is a patch over the gap, not its repair, and a costly one: once a node refused
    once, every later delivery of it validated on opus — on the automatic `json_parser` run
    (2026-09-27) 13 of 19 validations, $7.76 of $17.83, on a task one sonnet agent finishes in five
    minutes. The ⊥ is fixed where it arises; an installation that wants the escalation names a tier."""
    _m = os.environ.get("GFSO_VALIDATOR_RETRY_MODEL", "").strip()
    return None if _m.lower() in ("off", "none", "") else _m


#: How much of the two append-only ledgers one read returns by default. The numbers were written
#: five times each — the port, both storage adapters, the engine and the HTTP door — and a default
#: that disagrees between the door and the store is a page that silently ends early.
PIPELINE_PAGE = 500       # the signal ledger: a graph's whole history is usually well under this
USAGE_PAGE = 5000         # the spend ledger: one run makes hundreds of records, a project thousands

#: How much prose ONE criterion's entry may carry back through a tool door before it is trimmed.
#: A verdict read is not a page — every criterion must come back, because an entry that is missing
#: reads exactly like a criterion nobody validated (⊥, §2.3), which is the one thing this surface
#: exists to make visible. So the read never drops an entry; it shortens the two fields that carry
#: the bulk (the narrated evidence, a probe's captured output) and says so in place.
#: Measured on the delegated `json_parser` cell (2026-09-22): three validations returned no verdict,
#: the driving agent called `get_verdict` to find out why, the response came back ~85 KB — past the
#: client's own cap — and it escalated BLIND. The refused reports were the evidence and nobody ever
#: read them. A surface that answers "why was this refused" is worth nothing if the answer does not
#: fit through the door it answers at.
VERDICT_FIELD_CHARS = 2000

#: …and the WHOLE response's budget, as a multiple of the field bound. A per-field limit is not a
#: limit on the read: nothing bounds how many criteria a contract has, and one node can carry a
#: current verdict, an overruled one, the record it closed on AND a refused report, each with an
#: entry per criterion. Every field can sit inside its own bound while the sum sails past the
#: door's cap — the same blindness reached by addition. Past this, the per-criterion DETAIL folds
#: to the criterion NAMES (never to nothing: the names are what tell a reader which one to ask for)
#: and `criterion=<name>` still returns any single entry whole.
VERDICT_RESPONSE_MULTIPLE = 12

#: How much of a node's description stands in for its name in a one-line listing.
LABEL_CHARS = 40


def provider() -> str:
    """Which transport the LLM ports run on — `GFSO_PROVIDER`, `anthropic` (default) or `generic`."""
    return os.environ.get("GFSO_PROVIDER", "anthropic")


def generic_provider() -> dict:
    """Where the OpenAI-compatible transport points (`GFSO_GENERIC_BASE_URL` / `_MODEL` / `_API_KEY`).

    `base_url` is REQUIRED when `provider() == "generic"` — reading it here rather than at the
    adapter keeps the whole provider switch in one place, which is what "flip the system to another
    vendor and seamlessly back" means operationally."""
    return {"base_url": os.environ.get("GFSO_GENERIC_BASE_URL"),
            "model": os.environ.get("GFSO_GENERIC_MODEL"),
            "api_key": os.environ.get("GFSO_GENERIC_API_KEY")}


def api_billing() -> bool:
    """`GFSO_BILLING=api` keeps ANTHROPIC_API_KEY in the child env (per-token billing); the default
    `subscription` strips it (claude.ai login)."""
    return os.environ.get("GFSO_BILLING", "subscription") == "api"


def storage_kind(default: str = "sqlite") -> str:
    """`GFSO_STORAGE` — sqlite (a file) or memory (this process only)."""
    return os.environ.get("GFSO_STORAGE", default)


def llm_kind(default: str = "none") -> str:
    """`GFSO_LLM` — `llm`/`claude` (the real provider), `stub`, or none."""
    return os.environ.get("GFSO_LLM", default)


def engine_model(default: str = "haiku") -> str:
    """`GFSO_MODEL` — the tier the engine's own LLM runs on when one is built from the environment."""
    return os.environ.get("GFSO_MODEL", default)


def child_env(**overrides: str) -> dict:
    """This process's environment for a CHILD, with `overrides` applied — the one place a spawn's
    environment is composed, so a switch a child must see is set where the switches are owned."""
    return {**os.environ, **overrides}


def reconcile_allowed() -> bool:
    """May THIS process bring the one server to the declared state (`GFSO_NO_RECONCILE` turns it off)?

    A HEALTH CHECK MAY NOT RESTART A SERVER. `doctor` asks the Claude CLI whether the agent door is
    registered, and `claude mcp list` STARTS each configured server to answer — so the probe ran
    `gfso connect`, which reconciled: with the probing process's own environment, which for the test
    suite is a temporary home. Measured 2026-08-22: every full suite run took down the live server
    and left one homed in a tempdir behind it, twice killing a paid measurement run mid-flight. The
    flag rides the environment because the reconciler is reached through a spawned CLI, where an
    argument cannot go."""
    return not _flag("GFSO_NO_RECONCILE")


def seed_demo() -> bool:
    """Seed the demo graph into a fresh engine (`GFSO_SEED`) — opt-in, always."""
    return _flag("GFSO_SEED")


def serving() -> bool:
    """Is this process the gfso server (`GFSO_SERVING`)? Set by the server itself and inherited by a
    `--reload` worker, which uvicorn starts in a fresh interpreter."""
    return _flag("GFSO_SERVING")


def mark_serving() -> None:
    """Declare this process — and the processes it starts — the server (`serving`)."""
    os.environ["GFSO_SERVING"] = "1"


def validate_internal() -> bool:
    """Observe EVERY delivery with the independent instrument, internal nodes inside a scope included —
    off by default, on for measurement (`GFSO_VALIDATE_INTERNAL=1`).

    Where a validation stands is decided by κ, not by this dial (`validation.observed_here`): at every seam
    and at the top of every scope one executor session carries, which in SOLO means below the root too
    wherever the plan is larger than one session. It was on by default from 2026-09-27, read as "SOLO must
    not bypass the system"; what SOLO lacked was a validation at each κ-scope, not one per piece, and a
    validation per piece is what turned a 2.6-minute task into 39 and 70 (§10.2 permits a check on every
    delivery; it does not require one)."""
    return _flag("GFSO_VALIDATE_INTERNAL", "0")


def with_mcp() -> bool:
    """Mount the MCP transport inside the HTTP server."""
    return _flag("GFSO_WITH_MCP")


def autoexit() -> bool:
    """Let the server exit when the last session's lease lapses."""
    return _flag("GFSO_AUTOEXIT")


def ui_enabled() -> bool:
    """Serve the page from the standalone MCP process (default ON)."""
    return _flag("GFSO_MCP_UI", "1")


def ui_address() -> tuple[str, int]:
    """Host and port the standalone MCP process serves the page on."""
    return (os.environ.get("GFSO_UI_HOST", LOOPBACK), int(os.environ.get("GFSO_UI_PORT", "8000")))


# HOW MANY PROBES ONE VALIDATION RUN OWES. V(t) = ⋀ cᵢ (§2), so validating a contract in disjoint
# batches and taking the conjunction is the same verdict — provided every owed probe is carried exactly
# once and a criterion split between runs is read as their conjunction, which the merge enforces. It exists
# because the coverage discipline the engine demands (a probe per behaviour of every criterion) is what a
# report fails on a rich contract: measured 2026-08-21, 44 refused reports against 57 recorded verdicts,
# and two E3 runs stalled at 25 and 42 root criteria. 0 = one run for the whole validation, whatever its size.
VALIDATION_BATCH = 16          # …the DEFAULT; `validation_batch()` decides (a measured dial)


def narrate() -> bool:
    """Should a long verb mirror the project's observation lines while it runs? (`GFSO_QUIET=1` = no.)

    The lines go to stderr, where they cannot corrupt the JSON on stdout — but a caller whose harness
    merges the two streams gets prose in front of the payload and a JSONDecodeError at column 3
    (measured on the human door 2026-08-22, one burnt review round). Silence is one variable away.
    """
    return not _flag("GFSO_QUIET")


# HOW MANY READINGS THE LEVEL-2 CHECKER TAKES on the FIRST check of a node. Same rationale as
# SUFFICIENCY_READINGS and the same evidence: with the contract no longer inflating, the checker
# still returned exactly one NEW finding per round for three rounds and the run died in the gate
# (E3, 2026-08-22). A doubt raised by any reading is a doubt to answer; later rounds read once,
# because by then the plan has changed and what they validate is the change. 1 = the old behaviour.
CHECKER_READINGS = 3


def fill_env_gaps(declared: dict) -> dict:
    """The declared server configuration, with anything the operator EXPORTED left standing.

    A declaration (`data/serve.json`) says what this installation's server should be; an export says
    what THIS run means. `gfso serve` has always let the export win — the measurement arm sets
    `GFSO_L2_GATE=0` deliberately, and the gate is the mechanism it measures — while the reconciler's
    spawn path applied the same declaration with `update`, so a session that had exported the switch
    could still be handed a server with it back on. One rule, two spellings, and the louder one
    overruled the operator; this is the one place it is spelled.
    """
    return {k: os.environ.get(k, v) for k, v in declared.items()}


# HOW OFTEN A LONG VERB SAYS IT IS STILL THERE, over a transport with a per-message timeout. A
# decomposition is several model calls and one of them can outlast any ceiling a client sets; an MCP
# session aborted `auto_decompose` at 1800 s after thirty minutes of silence, and the graph had been
# changed by then. Not progress about the work — evidence that the work is still running.
HEARTBEAT_SECONDS = 30


# HOW LONG A VALIDATION CLAIM IS HONOURED WITH NOBODY BEHIND IT. The claim that stops two validators
# validating one delivery is released in a `finally`, so an orderly end always frees it — and a run that
# dies without unwinding cannot. The node then reads as "being validated" everywhere while nothing runs,
# and `validate_result` refuses the re-run its own refusal advises (agent door, 2026-09-02: fifteen
# minutes of dead polling on each of two nodes). Longer than any single validation run this product
# waits for, so a live run is never reclaimed out from under itself.
VALIDATION_CLAIM_TTL = 1800.0


def sufficiency_at_authoring() -> bool:
    """Does the decomposer close its own goal's undecided obligations before handing the plan over?

    ON by default. The check is the same one the Level-2 review runs; asking it at authoring costs
    one call and saves the caller the review rounds that repair what the previous call just wrote.
    `GFSO_SUFFICIENCY_AT_AUTHORING=0` turns it off — the measurement arm needs to be able to author a
    plan the gate has NOT already pre-repaired, or the two halves of the experiment collapse.
    """
    return os.environ.get("GFSO_SUFFICIENCY_AT_AUTHORING", "1") not in ("0", "false", "no")


# THE BLOCKING WAIT on the frontier verb. Every tester of waves 18-19 wrote the same poll loop by
# hand and spent 8-15 minutes of their run inside it: a graph that is working looks exactly like one
# that is stuck from a single call away. The ceiling exists because a call that never returns is a
# worse surface than one that says "nothing yet", and because every transport has a ceiling of its
# own that would cut it less politely.
WAIT_MAX_SECONDS = 600.0
WAIT_POLL_SECONDS = 2.0


def select_project(name: str) -> None:
    """Point this PROCESS at one project's graph — the door's choice, written where env lives.

    `GFSO_PROJECT` is read here like every other setting; two doors were setting it by hand, which is
    how a setting acquires a second owner and then a second meaning.
    """
    os.environ["GFSO_PROJECT"] = str(name)

def install_serve_env(declared: dict, *, storage: str, db_path: str | None, llm: str, model: str,
                      seed: bool, with_mcp: bool, on_declaration_error=None) -> None:
    """Put the environment a `serve` process runs under in place — the ONE owner of that act.

    `gfso serve` turns its arguments into the variables the app reads, and it was doing so by hand:
    eight `os.environ[...]` writes in the command, beside a ninth in the bridge and two more in the
    headless runner. That is a setting acquiring a second owner and then a second meaning — the
    class this module exists to close, and the reason `select_project` moved here before it.

    The DECLARATION fills gaps only: an explicitly exported value still wins, because the
    measurement arm sets `GFSO_L2_GATE=0` deliberately and the gate is the mechanism it measures.
    A declaration that cannot be read must never stop the server, so the caller is handed the error
    rather than raised at.
    """
    try:
        os.environ.update(fill_env_gaps(declared))
    except Exception as ex:                       # never let the declaration stop the server
        if on_declaration_error is not None:
            on_declaration_error(ex)
    os.environ["GFSO_STORAGE"] = storage
    os.environ["GFSO_DB_PATH"] = db_path or str(data_dir() / "gfso.db")
    os.environ["GFSO_LLM"] = llm
    os.environ["GFSO_MODEL"] = model
    os.environ["GFSO_SEED"] = "1" if seed else ""   # the name the app actually reads
    os.environ["GFSO_WITH_MCP"] = "" if with_mcp is False else "1"


def install_spawned_server_env(declared: dict) -> None:
    """The environment THE shared server is spawned under, when a bridge has to raise one.

    Same act as `install_serve_env` from a different door, and it was spelled separately there.
    `GFSO_AUTOEXIT=0` is the one difference and it is deliberate: a server raised to serve somebody
    else's session outlives the session that happened to raise it.
    """
    os.environ.update(fill_env_gaps(declared))     # the spawn inherits THIS process's environment
    os.environ["GFSO_AUTOEXIT"] = "0"              # up until it is stale or stopped, not until we go


def subprocess_env(*, keep_key: bool, extra: dict | None = None) -> dict:
    """The environment a MODEL subprocess inherits — a fresh dict, nothing installed here.

    The API key is stripped unless the caller asks to keep it, because with it present the runner
    bills the paid API while the operator believes they are on the subscription. That is a money
    fact, not a style one, and it is the reason the measurement layer patches the same thing at its
    own boundary (P1) — one question, and until now two places answering it.
    """
    env = (dict(os.environ) if keep_key else
           {k: v for k, v in os.environ.items()
            if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")})
    # …and the server's mark: a model child is not the server, and a gfso it runs (a probe running
    # this product's own suite) must not treat itself as one and end its own children.
    env.pop("GFSO_SERVING", None)
    # …and room to answer: the CLI's default 32k output cap cut a plan of 14 parts, and the model's re-emission after
    # the cut is what was kept (AUTO haiku 4.5 sql_database, GB_sql_database_tmu9cb784)
    env.setdefault("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "64000")
    if extra:
        env.update({k: str(v) for k, v in extra.items() if v is not None})
    return env


def install_mcp_env(*, db_path: str | None, llm: str, model: str) -> None:
    """The environment the stdio MCP door runs under — the same act as `install_serve_env`.

    A third door turning its arguments into the variables the app reads, spelled a third time.
    """
    os.environ["GFSO_DB_PATH"] = db_path or str(data_dir() / "gfso.db")
    os.environ["GFSO_LLM"] = llm
    os.environ["GFSO_MODEL"] = model


def spawned_server_popen_env() -> dict:
    """The env dict handed to the SPAWN of the shared server — a fresh dict, nothing installed.

    `GFSO_AUTOEXIT` defaults to off for the same reason as `install_spawned_server_env`: a server
    raised for somebody's session is a background service, not that session's property.
    """
    return dict(os.environ, GFSO_AUTOEXIT=os.environ.get("GFSO_AUTOEXIT", "0"))

"""The suite's construction kit — one owner for the objects the tests keep building by hand.

Fifty-four test bodies built an `Engine` themselves, in five drifting spellings of the same three
decisions (which storage, whether signals are validated, how often the monitor wakes). That is the
off-diagonal element the FORM ratchet counts as `T1_engine_built_by_hand`: a constructor argument
that gains a meaning — as `state_timeout` and `runner` both did — has to be found in fifty-four
places, and the ones that are only *nearly* the same are exactly where a test stops testing what its
name says. The same happened to the Spec builder: `_spec` existed six times with four signatures.

The defaults here are the ENGINE's own defaults, deliberately: this module owns the *spelling* of
construction, not the policy of any test. A test that wants a non-default engine still says so, and
now says so in one vocabulary.
"""
from __future__ import annotations

from typing import Optional

from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.types.ports import ClockPort, RunnerPort, StoragePort
from gfso.core.types import AcceptedRiskItem, Criteria, Predictability, Spec
from gfso.engine import Engine

#: What a decomposition declares it knowingly does not cover. Every graph the engine admits needs a
#: non-empty register (STD-1 / CHECK-4), so the suite carries one rather than inventing it per file.
UNMODELLED_FAULT = AcceptedRiskItem("an unmodelled environment fault", Predictability.EXTRAORDINARY)


def make_engine(
    storage: Optional[StoragePort] = None,
    *,
    agents=None,
    llm=None,
    check_interval: float = 10.0,
    validate_signals: bool = True,
    critique_log_path: Optional[str] = None,
    state_timeout: Optional[float] = None,
    clock: Optional[ClockPort] = None,
    runner: Optional[RunnerPort] = None,
) -> Engine:
    """An engine over in-memory storage and a human agent port, unless told otherwise.

    `storage=None` means MemoryStorage and `agents=None` means HumanAgent: each is what a test
    overrides when the test is ABOUT that port — persistence, or an agent that answers by itself —
    and passing them everywhere else only hid which tests those were.
    """
    return Engine(
        storage if storage is not None else MemoryStorage(),
        agents if agents is not None else HumanAgent(),
        llm=llm,
        check_interval=check_interval,
        validate_signals=validate_signals,
        critique_log_path=critique_log_path,
        state_timeout=state_timeout,
        clock=clock,
        runner=runner,
    )


def spec(description: str = "goal", *criteria: str, risks: bool = True) -> Spec:
    """A contract with one decidable criterion per name given, and the standard risk register.

    `risks=False` builds the register-less spec the CHECK-4 tests need — the one shape that must
    stay expressible, since a missing register is a defect the suite has to be able to construct.
    """
    return Spec(
        description=description,
        criteria=tuple(Criteria(c, f"{c} description") for c in (criteria or ("c1",))),
        accepted_risks=(UNMODELLED_FAULT,) if risks else (),
    )

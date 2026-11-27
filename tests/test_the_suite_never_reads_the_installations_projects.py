"""A module that reads a path as it is imported reads it at collection, ahead of every fixture: the server module's own
registry took the checkout's `data/` — the live server's projects — and `past.OPEN` handed them to a test reading the
past (tests/conftest.py says where the suite's home is laid). Imported here at the top, as collection imports it.
CONTROL: the home set in the session fixture, as it was — the registry's directory is the checkout's `data/`."""
from pathlib import Path

import gfso.api.server as S
import gfso.past as P
from gfso import config


def test_the_server_modules_registry_reads_the_suites_home():
    home = Path(config.home()).resolve()
    assert Path(S._registry._dir).resolve().is_relative_to(home), S._registry._dir
    assert all(Path(x).resolve().is_relative_to(home) for x in P.OPEN() if isinstance(x, str)), list(P.OPEN())

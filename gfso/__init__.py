"""GFSO — the protocol engine.

`__version__` is the SOFTWARE's version and the only place it is written down: `pyproject.toml`
reads it from here, the CLI prints it, and the HTTP surface reports it. It is a SemVer line of its
own and says nothing about the canon (`docs/applied_gfso_v4_en.md`, closed at v4.0), which is
versioned separately — the two numbers are unrelated by construction and must never be synchronised.

Not to be confused with the server's `code_version` (`gfso.serverctl.source_fingerprint`), which is
a hash of the sources on disk and answers "is the running process the current code", not "which
release is this".
"""
__version__ = "0.1.0"

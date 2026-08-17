"""Build the gfso-core wheel from the manifest (publication uses exactly this).

Usage: python packaging/build_core.py [outdir]   (needs `pip install build`)

Stages the manifest files into a temp tree next to the gfso-core pyproject and runs
`python -m build`. The artifact this produces is the one tests/test_core_dist.py proves
closed and zero-dependency on every run — publishing later is uploading it, not making it.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from core_manifest import core_paths  # noqa: E402 — sibling module, run as a script

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _main_version() -> str:
    """The ONE version source is `gfso.__version__` — the core template carries a placeholder, so
    there is no second version string to keep in sync.

    Read out of the source file rather than imported: this script stages a subset of the package and
    must run without the package's dependencies installed. (It read `[project] version` from the
    pyproject until that key became `dynamic`, at which point this raised KeyError and the core
    wheel could not be built at all — unnoticed, because the closure test re-implements the staging
    loop instead of calling into here.)"""
    import re
    src = (ROOT / "gfso" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__ = "([^"]+)"', src, re.M)
    if not m:
        raise RuntimeError(f"no __version__ in {ROOT / 'gfso' / '__init__.py'}")
    return m.group(1)


def stage(build_root: pathlib.Path) -> None:
    for src in core_paths(ROOT):
        dst = build_root / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    template = (ROOT / "packaging" / "gfso-core.pyproject.toml").read_text(encoding="utf-8")
    version_line = f'version = "{_main_version()}"'
    out = "\n".join(version_line if line.startswith('version = "0.0.0"') else line
                    for line in template.split("\n"))
    (build_root / "pyproject.toml").write_text(out, encoding="utf-8")


def main() -> int:
    outdir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    with tempfile.TemporaryDirectory() as td:
        build_root = pathlib.Path(td) / "gfso-core"
        stage(build_root)
        return subprocess.call([sys.executable, "-m", "build", "--wheel",
                                "--outdir", str(outdir), str(build_root)])


if __name__ == "__main__":
    raise SystemExit(main())

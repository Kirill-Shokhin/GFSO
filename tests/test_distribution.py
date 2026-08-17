"""The DISTRIBUTION is checked, not the declaration that describes it.

`tests/test_packaging.py` compares the package-data globs against the files on disk. That is a check
of a `pyproject.toml` field, and the failure it is written to prevent — a wheel that carries the
Python and none of the assets, so the UI comes up unstyled and the MCP server hands an agent an
EMPTY protocol — survives it: the globs can be right while the artifact is wrong (a build backend
change, an exclusion, a package without an `__init__.py` so its data has no owner). The declaration
was never the thing that ships.

So here the wheel and the sdist are BUILT and opened, and the wheel is installed into a fresh
environment and driven from a directory that is not the repository — the machine that has never
seen this tree, which the packaging comment correctly named as the only one that finds out.

Both directions are asserted: everything the product reads at runtime is inside, and the internal
documents and research directories are outside. A distribution that quietly ships a 115 KB status
file or an experiment's transcripts is the same defect wearing the other sign.
"""
import pathlib
import subprocess
import sys
import sysconfig
import tarfile
import venv
import zipfile

import pytest

ROOT = pathlib.Path(__file__).parent.parent

# What the product reads at runtime. Named here as well as in test_packaging.py on purpose: there
# the question is "is it declared", here "did it arrive".
REQUIRED = (
    "gfso/web/index.html", "gfso/web/gfso.css", "gfso/web/tokens.css", "gfso/web/icon.svg",
    "gfso/mcp/ORCHESTRATOR.md", "gfso/mcp/prompts/executor.md", "gfso/mcp/prompts/validator.md",
    "gfso/decompose/prompts/search.md", "gfso/decompose/prompts/audit.md",
    "gfso/critic/prompts/atomicity.md", "gfso/critic/prompts/checker.md",
    "gfso/examples/human_only.py", "gfso/examples/async_precompute.py",
)

# What must never leave this repository. The E3 documents and ROADMAP_INTERNAL are gitignored, so
# they are absent from a clean checkout — but a build runs against the WORKING TREE, where they sit
# beside pyproject.toml, and one added MANIFEST.in glob would sweep them into an sdist.
FORBIDDEN_SUBSTRINGS = ("experiments/", "runs/", "E3_", "ROADMAP_INTERNAL", "docs/notes",
                        "data/gfso.db", ".claude")


# Build caches that make a working tree lie about what it would produce. `gfso.egg-info/SOURCES.txt`
# is the dangerous one: setuptools reuses it, so a file that has DROPPED out of the package-data
# globs keeps shipping. Measured — deleting `*.css` from the globs left the stylesheet in the wheel
# built here and removed it from the wheel built from a clean export. A test that builds in place
# therefore cannot see a package-data regression; CI, building from a fresh checkout, would.
BUILD_CACHES = ("*.egg-info", "build", "dist", ".git", "__pycache__", ".pytest_cache",
                "data", "runs", "experiments", "docs", "formal", "scripts", ".idea", ".github")


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> tuple[pathlib.Path, pathlib.Path]:
    """(wheel, sdist) built from a CLEAN COPY of this tree. Skipped, never faked, without `build`."""
    pytest.importorskip("build", reason="python -m build is the tool under test here")
    import shutil
    src = tmp_path_factory.mktemp("src") / "tree"
    # The copy is for BUILDING a distribution, so it takes what the build reads and nothing else:
    # the full tree drags in `data/` (hundreds of live databases) and `experiments/*/results` (a
    # running run's workspace), which makes the test slow and, worse, races with files being written
    # while it copies.
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns(
        *BUILD_CACHES, "data", "results", "runs", "*.db", "*.db-wal", "*.db-shm", ".git"))
    out = tmp_path_factory.mktemp("dist")
    proc = subprocess.run([sys.executable, "-m", "build", "--outdir", str(out), str(src)],
                          capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    wheel = next(out.glob("*.whl"))
    sdist = next(out.glob("*.tar.gz"))
    return wheel, sdist


@pytest.fixture(scope="session")
def built_with_internal_material_planted(tmp_path_factory) -> tuple[pathlib.Path, pathlib.Path]:
    """A build of a tree that DOES carry the internal material — the state a release build is cut
    from, where `E3_STATUS.md` and `experiments/` sit beside `pyproject.toml`, gitignored and very
    much present on disk."""
    pytest.importorskip("build", reason="python -m build is the tool under test here")
    import shutil
    src = tmp_path_factory.mktemp("src-planted") / "tree"
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns(*BUILD_CACHES))
    (src / "E3_STATUS.md").write_text("internal", encoding="utf-8")
    (src / "ROADMAP_INTERNAL.md").write_text("internal", encoding="utf-8")
    for d in ("experiments/e9_probe", "runs/probe", "docs/notes"):
        (src / d).mkdir(parents=True, exist_ok=True)
        (src / d / "note.md").write_text("internal", encoding="utf-8")
    out = tmp_path_factory.mktemp("dist-planted")
    proc = subprocess.run([sys.executable, "-m", "build", "--outdir", str(out), str(src)],
                          capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    return next(out.glob("*.whl")), next(out.glob("*.tar.gz"))


def test_the_wheel_carries_every_runtime_asset(built):
    wheel, _ = built
    names = set(zipfile.ZipFile(wheel).namelist())
    missing = [r for r in REQUIRED if r not in names]
    assert not missing, (f"the built wheel does not carry {missing} — an installed product would "
                         f"come up without them and say nothing")


def test_the_wheel_states_the_version_the_package_states(built):
    wheel, _ = built
    from gfso import __version__
    assert f"-{__version__}-" in wheel.name or wheel.name.startswith(f"gfso-{__version__}"), wheel.name


def test_neither_artifact_ships_anything_internal(built_with_internal_material_planted):
    """Planted, not assumed absent.

    The build copy prunes the research directories for speed, which made an earlier version of this
    check ask whether files deleted before the build had reached it — a question with only one
    answer. The fixture puts them back, as the files a real release build would find sitting beside
    `pyproject.toml`, so the exclusion machinery is what is being tested.
    """
    wheel, sdist = built_with_internal_material_planted
    names = list(zipfile.ZipFile(wheel).namelist())
    names += [n.split("/", 1)[-1] for n in tarfile.open(sdist).getnames()]
    leaked = [n for n in names if any(bad in n for bad in FORBIDDEN_SUBSTRINGS)]
    assert not leaked, f"internal material reached a distribution: {sorted(set(leaked))[:20]}"


def test_the_sdist_carries_what_a_rebuild_needs(built):
    _, sdist = built
    names = {n.split("/", 1)[-1] for n in tarfile.open(sdist).getnames()}
    for needed in ("pyproject.toml", "README.md", "LICENSE", "gfso/__init__.py"):
        assert needed in names, f"the sdist cannot be rebuilt without {needed}"


def test_the_installed_wheel_runs_from_a_directory_that_is_not_the_repository(built, tmp_path):
    """The end of the packaging claim: install the artifact and use it as a stranger would.

    `--system-site-packages` lends the third-party dependencies from the running environment: the
    subject here is THIS wheel — its assets, its entry point, its imports — not pip's ability to
    fetch fastapi. `--no-deps` keeps the install to the artifact itself.
    """
    env_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env_dir)
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    py = env_dir / scripts / ("python.exe" if sys.platform == "win32" else "python")
    exe = env_dir / scripts / ("gfso.exe" if sys.platform == "win32" else "gfso")

    wheel, _ = built
    # --ignore-installed: the lent system site-packages usually already carry a `gfso` (the
    # development install), and pip would call the requirement satisfied and install NOTHING — the
    # test would then pass while exercising the source tree it was written to stop trusting.
    install = subprocess.run([str(py), "-m", "pip", "install", "--no-deps", "--ignore-installed",
                              "-q", str(wheel)], capture_output=True, text=True, timeout=900)
    assert install.returncode == 0, install.stdout + install.stderr

    workdir = tmp_path / "elsewhere"           # deliberately not the repository
    workdir.mkdir()

    from gfso import __version__
    version = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                             cwd=workdir, timeout=120)
    assert version.returncode == 0 and __version__ in version.stdout, version.stdout + version.stderr

    # The assets are read through the INSTALLED package, and the protocol an agent receives at
    # initialize is non-empty — the one failure that reported 32 healthy tools while handing the
    # session a blank string.
    probe = ("import pathlib, gfso, gfso.decompose;"
             "p = pathlib.Path(gfso.__file__).parent;"
             "print('ORCH', len((p / 'mcp' / 'ORCHESTRATOR.md').read_text(encoding='utf-8')));"
             "print('CSS', (p / 'web' / 'gfso.css').exists())")
    out = subprocess.run([str(py), "-c", probe], capture_output=True, text=True,
                         cwd=workdir, timeout=300)
    assert out.returncode == 0, out.stderr
    assert "CSS True" in out.stdout
    assert int(out.stdout.split("ORCH ")[1].split()[0]) > 1000, "the MCP instructions arrived empty"

    # And the mechanism the front page opens with runs, with no model and no server.
    demo = subprocess.run([str(exe), "demo", "human_only"], capture_output=True, text=True,
                          cwd=workdir, timeout=300)
    assert demo.returncode == 0, demo.stdout + demo.stderr
    assert "accepted? False" in demo.stdout and "final: DONE" in demo.stdout


def test_the_console_script_is_the_interpreter_it_was_installed_into():
    """`claude mcp add --scope user gfso -- gfso connect` names a console script for this reason: a client
    started outside the virtualenv resolves its own `python`, which is usually not this one."""
    scripts = pathlib.Path(sysconfig.get_path("scripts"))
    assert (scripts / ("gfso.exe" if sys.platform == "win32" else "gfso")).exists() or \
        (scripts / "gfso").exists(), "the gfso entry point is not installed in this environment"

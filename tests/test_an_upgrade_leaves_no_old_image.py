"""An upgrade builds the agent image anew; what the older versions built and the build cache do not stay on the disk."""
import json
import subprocess

from gfso import config as _config
from gfso import doctor


def _docker(tags, refused=(), prune_err="", freed="0B"):
    calls = []

    def run(argv, **_):
        calls.append(argv)
        if argv[1:3] == ["image", "ls"]:
            return subprocess.CompletedProcess(argv, 0, "\n".join(tags), "")
        if argv[1:3] == ["image", "rm"]:
            return subprocess.CompletedProcess(argv, 1 if argv[3] in refused else 0, b"", b"")
        if argv[1:3] == ["builder", "prune"]:
            bad = prune_err and argv[4] == "--reserved-space"
            return subprocess.CompletedProcess(argv, 1 if bad else 0, f"Total:\t{freed}", prune_err if bad else "")
        raise AssertionError(argv)
    return run, calls


def test_the_images_older_versions_built_are_removed_and_the_declared_stay(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "executions_path", lambda: tmp_path / "executions.json")
    (tmp_path / "executions.json").write_text(json.dumps({"mine": {"image": "gfso-agent:aaaa"}}))
    run, calls = _docker(["gfso-agent:new", "gfso-agent:aaaa", "gfso-agent:old1", "gfso-agent:busy"], refused={"gfso-agent:busy"})
    said = doctor.drop_replaced_images("gfso-agent:new", run=run)
    removed = [c[3] for c in calls if c[1:3] == ["image", "rm"]]
    assert removed == ["gfso-agent:old1", "gfso-agent:busy"]   # never the new one, never one an execution names
    assert said == "removed the replaced gfso-agent:old1"      # one a container still uses stays, and is not claimed


def test_nothing_replaced_says_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "executions_path", lambda: tmp_path / "none.json")
    run, _ = _docker(["gfso-agent:new"])
    assert doctor.drop_replaced_images("gfso-agent:new", run=run) == ""


def test_the_build_cache_is_bounded_on_an_older_engine_too():
    run, calls = _docker([], freed="1.2GB")
    assert doctor.bound_build_cache(run=run) == "build cache: 1.2GB freed"
    run, calls = _docker([], prune_err="unknown flag: --reserved-space", freed="300MB")
    assert doctor.bound_build_cache(run=run) == "build cache: 300MB freed"
    assert [c[4] for c in calls] == ["--reserved-space", "--keep-storage"]


def test_a_cache_an_image_still_holds_is_no_claim():
    run, _ = _docker([])                     # every layer shared with an image: the prune frees 0B
    assert doctor.bound_build_cache(run=run) == ""


def test_the_image_an_upgrade_replaced_goes_once_the_default_moved_off_it(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "executions_path", lambda: tmp_path / "executions.json")
    (tmp_path / "executions.json").write_text(json.dumps({"default": {"image": "gfso-agent:old"}}))
    run, calls = _docker(["gfso-agent:new", "gfso-agent:old"])
    monkeypatch.setattr(doctor.children, "run", run)
    monkeypatch.setattr(doctor, "docker_state", lambda: (True, "engine"))
    monkeypatch.setattr(doctor, "agent_image", lambda: "gfso-agent:new")
    monkeypatch.setattr(doctor, "image_present", lambda tag: True)
    said = doctor.install_execution()
    assert [c[3] for c in calls if c[1:3] == ["image", "rm"]] == ["gfso-agent:old"]
    assert "removed the replaced gfso-agent:old" in said

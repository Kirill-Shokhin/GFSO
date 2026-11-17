"""An agent's shell call ends at about two minutes; `gfso setup` building the agent image took longer, and a setup cut
by its caller looked failed while the build ran on (a tester's install note, 2026-11-13). The build runs in a process of
its own, setup waits a bounded time, and the next setup waits on that build rather than starting another."""
import os
import time

from gfso import doctor as D


def test_a_long_build_is_left_running_and_the_next_setup_waits_on_it(monkeypatch, tmp_path):
    monkeypatch.setattr(D._config, "data_dir", lambda: tmp_path)
    started = []
    spawn = lambda tag, log: (started.append(tag), log.write_text("step 1/9\n"))
    said = D.image_built_detached("img:1", wait_s=0.1, spawn=spawn, present=lambda t: False)
    assert started == ["img:1"] and "still building img:1" in said and "Run `gfso setup` again" in said
    assert D.image_built_detached("img:1", wait_s=0.1, spawn=spawn, present=lambda t: False) and started == ["img:1"]
    assert D.image_built_detached("img:1", wait_s=5, spawn=spawn, present=lambda t: True) == ""


def test_a_build_that_ended_without_the_image_is_said_and_started_again(monkeypatch, tmp_path):
    monkeypatch.setattr(D._config, "data_dir", lambda: tmp_path)
    log = tmp_path / "image-build.log"
    log.write_text("build failed: no space left on device\n")
    old = time.time() - 600
    os.utime(log, (old, old))
    started = []
    said = D.image_built_detached("img:1", wait_s=0.1, spawn=lambda t, l: started.append(t), present=lambda t: False)
    assert started == ["img:1"] and "no space left on device" in said
    assert D.STEP_WAIT_S < 120

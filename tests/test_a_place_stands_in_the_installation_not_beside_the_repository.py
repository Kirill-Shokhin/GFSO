"""A node's place and its validations' rounds stand under the installation's own state, never beside the user's
repository: places laid out as `<repo's parent>/.gfso-nodes-<repo>` grew directories next to the user's work (6.5 GB
once, 2026-11-14; a fresh-client tester found them there), and the author: «чинить до пуша». The path still reads back
to its base by itself — the transition bus asks it with no subprocess — and what a project recorded or left standing in
the old layout goes on being read."""
import os
from pathlib import Path

import pytest

from gfso import config
from gfso.adapters.execution import scratch_of
from gfso.adapters.worktrees import base_of, relative_alternates
from gfso.core.types import NODES, PLACES, base_of_nodes, nodes_root
from gfso.workspaces import _laid_out_before


def test_a_base_s_places_stand_in_the_installation_and_read_back_to_it(tmp_path):
    base = tmp_path / "work" / "my repo"
    base.mkdir(parents=True)
    nodes = nodes_root(base)
    assert nodes.is_relative_to(config.data_dir() / PLACES), nodes
    assert not nodes.is_relative_to(base.parent), "nothing of the system's beside the user's repository"
    place = nodes / "p" / "root.a"
    assert base_of(str(place)) == str(base)
    assert base_of_nodes(nodes) == base
    assert list(base.parent.iterdir()) == [base], "naming a place makes nothing beside the base"


def test_a_base_s_rounds_stand_with_its_places(tmp_path):
    base = tmp_path / "ws"
    base.mkdir()
    assert scratch_of(base, "p") == nodes_root(base) / "p" / ".gfso-scratch-.ws"
    place = nodes_root(base) / "p" / "root.a"
    assert scratch_of(place, "p") == nodes_root(base) / "p" / ".gfso-scratch-root.a"


def test_two_bases_of_one_name_under_two_parents_keep_their_places_apart(tmp_path):
    a, b = tmp_path / "x" / "app", tmp_path / "y" / "app"
    assert nodes_root(a) != nodes_root(b)
    assert base_of_nodes(nodes_root(a)) == a and base_of_nodes(nodes_root(b)) == b


def test_what_the_old_layout_laid_down_is_still_read(tmp_path):
    base = tmp_path / "ws"
    old = tmp_path / f"{NODES}ws" / "p" / "root.a"
    assert base_of(str(old)) == str(base), "a place made beside its base before reads back as it did"
    assert _laid_out_before(nodes_root(base) / "p" / "root.a") == old, "a record keyed by the old name is found"
    assert _laid_out_before(base / "src") == base / "src", "any other path as it is"


@pytest.mark.skipif(os.name != "nt", reason="drives are Windows'")
def test_a_host_clone_borrows_a_base_on_another_drive_by_its_absolute_path(tmp_path):
    """The places stand in the installation, the base where the person keeps it — on Windows often another drive, where
    no relative path exists (`relpath` raised and no host place could be made — critic, 2026-11-15)."""
    (tmp_path / "o" / "info").mkdir(parents=True)
    other = "D:/repo/.git/objects" if str(tmp_path).upper()[:1] != "D" else "E:/repo/.git/objects"
    relative_alternates(tmp_path / "o", Path(other))
    assert (tmp_path / "o" / "info" / "alternates").read_text().strip() == other
    relative_alternates(tmp_path / "o", tmp_path / "base" / ".git" / "objects")
    assert (tmp_path / "o" / "info" / "alternates").read_text().strip() == "../base/.git/objects", "same drive: relative"

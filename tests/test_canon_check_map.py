"""The CHECK → failure-mode routing, parsed OUT OF THE CANON and compared with the product's table.

Same doctrine as `test_canon_fsm_table.py`: a mapping that is typed twice is a mapping that drifts,
and the drift is silent because nothing computes on it — it is display. It drifted exactly that way:
the UI carried its own JavaScript copy that routed CHECK-6 to FM-1, and the copy predated CHECK-1b/7/8
entirely. A row may route to NO mode — `→ no FM`, CHECK-6's since v4.1 (an unowned leaf is an unissued
one; what it guards is Del's definition, not a failure mode) — and that is a row too, parsed as ().

Both directions are asserted — a canon row missing from the product AND a product row the canon does
not state — because a one-way test passes happily while the table quietly grows.
"""
import re

import pytest
from pathlib import Path

from gfso.core.handlers.structural import CHECK_TO_FM, FM_LABEL

CANON = Path(__file__).resolve().parents[1] / "docs" / "applied_gfso_v4_en.md"

# `CHECK-1 (coverage):  <the condition>   → FM-1.a` — the battery of §9.5–9.6, both levels.
_ROW = re.compile(r"^CHECK-(\S+)\s*\([^)]*\):.*?→\s*((?:FM-[0-9a-z.]+)(?:,\s*FM-[0-9a-z.]+)*|no FM)\b.*$",
                  re.MULTILINE)


def _canon_rows() -> dict[str, tuple[str, ...]]:
    """One row routes to a LIST of modes, which may be empty — CHECK-6 guards none, CHECK-2 FM-5 by its Dep
    clause alone (§9.5)."""
    rows = {n: () if fm == "no FM" else tuple(x.strip() for x in fm.split(","))
            for n, fm in _ROW.findall(CANON.read_text(encoding="utf-8"))}
    assert len(rows) == 9, f"the canon states NINE CHECKs (§9.5); parsed {sorted(rows)}"
    return rows


def test_every_canon_check_is_routed_by_the_product():
    canon = _canon_rows()
    product = {name.split(":")[0].removeprefix("CHECK-"): fm for name, fm in CHECK_TO_FM.items()}
    assert product == canon, (
        f"the product's CHECK→FM routing disagrees with §9.5–9.6:\n"
        f"  canon-only:   {sorted(set(canon.items()) - set(product.items()))}\n"
        f"  product-only: {sorted(set(product.items()) - set(canon.items()))}")


def test_the_ui_reads_that_table_instead_of_carrying_its_own():
    """Enforcement, not narration: if the UI re-hardcodes the map, this goes red. The page may hold
    the FETCH and a rendering fallback; what it may not hold is a second source of truth."""
    ui = (Path(__file__).resolve().parents[1] / "gfso" / "web" / "index.html").read_text(encoding="utf-8")
    hardcoded = re.findall(r"'CHECK-\d\w*:\w+'\s*:\s*'FM-", ui)
    assert not hardcoded, f"the UI carries its own CHECK→FM table again: {hardcoded}"
    assert "/api/check_map" in ui, "the UI must read the routing from the product"


def test_failure_mode_labels_match_the_canon_names():
    """Each mode is named once, at its definition in Ch. 8 (`**FM-3 (Veracity).**`); a label that lags a
    rename (FM-3 was Verifiability, FM-5 was Currency in v3.9) is exactly what shipped to the UI once."""
    canon = CANON.read_text(encoding="utf-8")
    for fm, label in FM_LABEL.items():
        assert re.search(rf"^\*\*{re.escape(fm)} \({label}\)\.\*\*", canon, re.MULTILINE), \
            f"{fm} is not named {label!r} at its definition in Ch. 8"

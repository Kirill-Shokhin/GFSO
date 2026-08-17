"""The CHECK → failure-mode routing, parsed OUT OF THE CANON and compared with the product's table.

Same doctrine as `test_canon_fsm_table.py`: a mapping that is typed twice is a mapping that drifts,
and the drift is silent because nothing computes on it — it is display. It drifted exactly that way:
the UI carried its own JavaScript copy that routed CHECK-6 to FM-1 where §13.4 routes leaf delegation
to FM-7 (a delegation hole is a FEEDBACK defect: a leaf with no executor has nobody to report), and
the copy predated CHECK-1b/7/8 entirely.

Both directions are asserted — a canon row missing from the product AND a product row the canon does
not state — because a one-way test passes happily while the table quietly grows.
"""
import re
from pathlib import Path

from gfso.core.handlers.structural import CHECK_TO_FM, FM_LABEL

CANON = Path(__file__).resolve().parents[1] / "docs" / "applied_gfso_v4_en.md"

# `CHECK-1 (coverage):  <the condition>   → FM-1.a` — the battery of §13.4, both levels.
_ROW = re.compile(r"^CHECK-(\S+)\s*\([^)]*\):.*?→\s*(FM-[0-9a-z.]+)\s*$", re.MULTILINE)


def _canon_rows() -> dict[str, str]:
    rows = {n: fm for n, fm in _ROW.findall(CANON.read_text(encoding="utf-8"))}
    assert len(rows) == 9, f"the canon states NINE CHECKs (§13.4); parsed {sorted(rows)}"
    return rows


def test_every_canon_check_is_routed_by_the_product():
    canon = _canon_rows()
    product = {name.split(":")[0].removeprefix("CHECK-"): fm for name, fm in CHECK_TO_FM.items()}
    assert product == canon, (
        f"the product's CHECK→FM routing disagrees with §13.4:\n"
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
    """§12.6's summary table names the seven modes; a label that lags a rename (FM-3 was
    Verifiability, FM-5 was Currency in v3.9) is exactly what shipped to the UI once."""
    canon = CANON.read_text(encoding="utf-8")
    for fm, label in FM_LABEL.items():
        n = fm.removeprefix("FM-")
        assert re.search(rf"\|\s*{n}\s*\|\s*{label}\s*\|", canon), \
            f"{fm} is not named {label!r} in §12.6's table"

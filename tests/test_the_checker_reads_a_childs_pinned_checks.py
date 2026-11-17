"""The Level-2 checker judges a parent criterion by what the children's PINNED CHECKS decide, not by their prose: shown
the parent's probes and only the children's `name: description`, a haiku checker named one more GCC-rejected instance of
a universal root criterion each review and the issuer answered add_child ~28 times, though a child carried the root's
exact probe (own-plan row 3, GB_c_compiler_tnmsd1088; docs/notes/OWN_PLAN_UNIVERSAL_CRITERION.md)."""
from gfso.core.types import Task, TaskId, AgentId, Spec, Criteria, CriterionMapping, Probe
from gfso.core.graph.projection import build, render

_PROBE = Probe("a compile error exits non-zero", "./cc {inputs}/bad.c; test $? -ne 0", "exit non-zero",
               (("bad.c", "int main(){ return &5; }"),))


def test_the_checker_is_shown_the_childs_pinned_check_with_its_input():
    parent = Task(id=TaskId("root"), spec=Spec("a C compiler", (
        Criteria("errors_nonzero", "every compile error exits non-zero", check=(_PROBE,)),)),
        assignee=AgentId("pm"), criterion_mappings=(CriterionMapping("errors_nonzero", TaskId("root.err")),))
    child = Task(id=TaskId("root.err"), spec=Spec("error exits", (
        Criteria("rejects_bad", "rejects invalid programs", check=(_PROBE,)),)), assignee=AgentId("x"))
    md = render(build(parent, [child], [], []))
    split = md.split("## Subtasks (D)", 1)[1]
    assert "./cc {inputs}/bad.c; test $? -ne 0" in split          # the child's procedure, not only its name
    assert "bad.c@" in split                                      # its input named by content, not by file name

"""A severed validation is severed, whichever of its batches came back last.

A contract with more criteria than the batch size is judged in CONCURRENT batches, and every batch
pushes its stats onto one list in completion order. Asked of the last entry, "was this call cut?"
therefore depended on a race: the same torn transport was recognised as cut when its batch finished
last and read as "answered badly" when it did not. That reading is expensive — a cut call gets a
free redial, an answer-that-did-not-parse spends the node's ONE retry and the second one parks the
node in VALIDATING with no verdict ever coming. The run then stops on a coin toss.
"""
from gfso.adapters.llm.stats import the_call_was_cut


class _Fake:
    def __init__(self, *torn):
        self.calls = [{"duration_ms": 900, "transport_torn": t} for t in torn]


def test_a_torn_batch_is_seen_wherever_it_lands():
    assert the_call_was_cut(_Fake(True, False), "")
    assert the_call_was_cut(_Fake(False, True), "")
    assert the_call_was_cut(_Fake(False, True, False), "")


def test_a_judgement_that_answered_is_not_cut():
    assert not the_call_was_cut(_Fake(False, False, False), "{}")


def test_one_batch_behaves_as_before():
    assert the_call_was_cut(_Fake(True), "")
    assert not the_call_was_cut(_Fake(False), "{}")


def test_a_provider_that_cannot_say_still_falls_back_to_the_shape():
    """Positive control: the inference for providers with no typed field must survive."""
    class _Untyped:
        calls = [{"duration_ms": 5}]
    assert the_call_was_cut(_Untyped(), "short")
    assert not the_call_was_cut(_Untyped(), "{" + "x" * 500 + "}")


def test_untyped_entries_beside_typed_ones_do_not_hide_a_tear():
    class _Mixed:
        calls = [{"duration_ms": 5}, {"duration_ms": 9, "transport_torn": True}]
    assert the_call_was_cut(_Mixed(), "")

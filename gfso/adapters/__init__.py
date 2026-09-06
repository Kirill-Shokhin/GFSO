"""The implementations of the ports the core declares — storage, agent, LLM, verifier.

Everything here is REPLACEABLE and nothing in `core/` may import it: that direction is the layer
gate, enforced as a red CI test rather than as a convention. An embedder swaps a module here and
the protocol above does not notice.
"""

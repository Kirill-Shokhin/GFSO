"""The protocol itself, free of any substrate: types, the FSM, the graph, the CHECK battery.

Nothing here may import an adapter, a transport or a model — that is what makes the guarantees
checkable and the core embeddable in a foreign host. The layer gate is a test, not a promise.
"""

"""AgentPort implementations — how a participant is REACHED, not who they are.

`HumanAgent` is the honest default: a person is an id the engine knows and nothing it can call,
so the port answers "not mine to dispatch" and the graph waits for their signal.
"""

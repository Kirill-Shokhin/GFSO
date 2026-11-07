"""The model transports and the bookkeeping around them.

A provider is chosen by the model spec (`registry.provider_for`): the Claude Code CLI (`headless`), or any chat API over
its wire (`chat`) with the system's own agent loop (`toolloop`). Every provider records its calls in one neutral shape
(`base`); `conformance` measures which roles a provider can hold.
"""

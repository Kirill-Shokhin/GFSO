"""StoragePort implementations — where the graph and its append-only log live.

The log is MANDATORY core, not an extension: Thm 11 / Inv-7 give `state = fold(log)` only if the
log is complete, so an adapter that silently drops entries voids the guarantee rather than
degrading a feature.
"""

"""The model transports and the bookkeeping around them.

Two ports, deliberately apart: zero-tool one-shots (`complete`) and TOOL-USING agent runs
(`run_agent`, the headless CLI). A provider that covers only the first is usable for the checker
and useless for a validator, and the verbs say so rather than failing halfway.
"""

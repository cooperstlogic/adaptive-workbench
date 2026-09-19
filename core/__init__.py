"""Pure-numpy optimization core. No network I/O, no printing.

Every surface -- the skill scripts, the MCP servers, and the browser app under
Pyodide -- is a thin wrapper over this package. Nothing here may import from
``data`` (the simulated lab) or reach the network.
"""

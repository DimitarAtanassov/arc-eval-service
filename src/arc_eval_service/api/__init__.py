"""HTTP boundary: routes, the wire contract, and dependency wiring.

This package is the only place that knows about FastAPI. Routes translate HTTP to
service calls, ``schemas`` is the public request/response contract that
arc-platform depends on, and ``dependencies`` is the composition root.
"""

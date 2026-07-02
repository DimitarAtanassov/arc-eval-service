"""Domain core: framework-free evaluation types and errors.

Everything here is pure data and pure logic with no dependency on FastAPI, the
database, or any provider SDK. Higher layers (``api``, ``services``, ``judging``,
``prompts``) depend on this package; it depends on nothing internal, so it is the
root of the dependency graph and the seam that keeps those layers decoupled.
"""

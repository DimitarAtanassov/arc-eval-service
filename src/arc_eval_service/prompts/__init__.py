"""The prompt library: metric and judge definitions loaded from YAML.

Each metric is one file under ``metrics/`` and each judge one file under
``judges/``, keyed by filename. ``schema`` defines the validated shapes,
``loader`` reads and validates them once at startup, and ``render`` fills a
metric's case template. The judge engine composes a judge's optional system prompt
with a metric's rubric at score time; the verdict/JSON contract stays in code,
next to the parser.
"""

"""The evaluator catalog: the metrics (what to grade) and judges (who grades).

Two concepts, two subpackages: :mod:`~arc_eval_service.catalog.metric` and
:mod:`~arc_eval_service.catalog.judge`, each owning its definition schema and its
YAML instances. :class:`Catalog` aggregates both; the judge engine composes a
metric with a judge at score time. Adding or editing a metric or judge is a YAML
edit under the matching subpackage, not a code change.
"""

from arc_eval_service.catalog.judge import JudgeDefinition
from arc_eval_service.catalog.loader import Catalog, load_catalog
from arc_eval_service.catalog.metric import MetricDefinition, render_case

__all__ = [
    "Catalog",
    "JudgeDefinition",
    "MetricDefinition",
    "load_catalog",
    "render_case",
]

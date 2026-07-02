"""The evaluator catalog: metric and judge definitions loaded from YAML.

The catalog reads one YAML file per metric (``metric/*.yaml``) and per judge
(``judge/*.yaml``), validates each with Pydantic once at startup, and exposes them
for the judge engine to compose. A malformed or missing file fails boot, not a
request. :class:`Catalog` is the aggregate; the two concepts it holds live in the
:mod:`~arc_eval_service.catalog.metric` and :mod:`~arc_eval_service.catalog.judge`
subpackages.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from arc_eval_service.catalog.judge.definition import JudgeDefinition
from arc_eval_service.catalog.metric.definition import MetricDefinition
from arc_eval_service.domain.errors import UnknownJudgeError, UnknownMetricError

_BUNDLED_ROOT = Path(__file__).parent


class Catalog(BaseModel):
    """The metric and judge definitions, keyed by name."""

    metrics: dict[str, MetricDefinition]
    judges: dict[str, JudgeDefinition]

    def metric(self, name: str) -> MetricDefinition:
        """Return the metric definition, or raise :class:`UnknownMetricError`."""
        try:
            return self.metrics[name]
        except KeyError as exc:
            raise UnknownMetricError(name) from exc

    def judge(self, name: str) -> JudgeDefinition:
        """Return the judge definition, or raise :class:`UnknownJudgeError`."""
        try:
            return self.judges[name]
        except KeyError as exc:
            raise UnknownJudgeError(name) from exc


def load_catalog(path: str | None = None) -> Catalog:
    """Load and validate the catalog from ``path`` or the bundled directory.

    ``path`` is a directory containing ``metric/`` and ``judge/`` subdirectories.
    """
    root = Path(path) if path is not None else _BUNDLED_ROOT
    return Catalog(
        metrics=_load_definitions(root / "metric", MetricDefinition),
        judges=_load_definitions(root / "judge", JudgeDefinition),
    )


def _load_definitions[T: BaseModel](directory: Path, model: type[T]) -> dict[str, T]:
    """Load and validate every ``*.yaml`` in ``directory``, keyed by filename stem."""
    definitions: dict[str, T] = {}
    for file in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        definitions[file.stem] = model.model_validate(data)
    return definitions

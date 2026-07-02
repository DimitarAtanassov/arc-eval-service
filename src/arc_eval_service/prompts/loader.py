"""Load and validate the prompt library from per-file YAML definitions.

The library reads one YAML file per metric (``metrics/*.yaml``) and per judge
(``judges/*.yaml``), keyed by filename stem, from the bundled directory next to
this module or from an override directory. Each file is validated with Pydantic,
so a malformed file fails fast at startup rather than degrading a request.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from arc_eval_service.prompts.schema import (
    JudgeDefinition,
    MetricDefinition,
    PromptLibrary,
)

_BUNDLED_ROOT = Path(__file__).parent

_T = TypeVar("_T", bound=BaseModel)


def load_library(path: str | None = None) -> PromptLibrary:
    """Load and validate the prompt library from ``path`` or the bundled directory.

    ``path`` is a directory containing ``metrics/`` and ``judges/`` subdirectories.
    """
    root = Path(path) if path is not None else _BUNDLED_ROOT
    return PromptLibrary(
        metrics=_load_definitions(root / "metrics", MetricDefinition),
        judges=_load_definitions(root / "judges", JudgeDefinition),
    )


def _load_definitions(directory: Path, model: type[_T]) -> dict[str, _T]:
    """Load and validate every ``*.yaml`` in ``directory``, keyed by filename stem."""
    definitions: dict[str, _T] = {}
    for file in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        definitions[file.stem] = model.model_validate(data)
    return definitions


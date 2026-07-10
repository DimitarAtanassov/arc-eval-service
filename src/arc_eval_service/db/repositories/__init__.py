"""Repositories: the only code that reads and writes the database.

One repository per table, one module each, over a shared session base
(:mod:`base`). The ``record <-> row`` mappers are co-located with their repository
and stay pure for unit testing. Adding a table means adding a module here, not
editing the others.
"""

from __future__ import annotations

from arc_eval_service.db.repositories.eval_requests import EvalRequestRepository
from arc_eval_service.db.repositories.evaluation_results import (
    EvaluationResultRepository,
)
from arc_eval_service.db.repositories.experiments import (
    ExperimentRepository,
    ExperimentRunRepository,
)

__all__ = [
    "EvalRequestRepository",
    "EvaluationResultRepository",
    "ExperimentRepository",
    "ExperimentRunRepository",
]

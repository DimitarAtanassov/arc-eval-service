"""Repositories: the only code that reads and writes the database.

One repository per aggregate, one module each, over a shared session base
(:mod:`base`). The row <-> domain mappers are co-located with their repository
and stay pure for unit testing. Adding an aggregate means adding a module here,
not editing the others.
"""

from __future__ import annotations

from arc_eval_service.db.repositories.eval_inputs import EvalInputRepository

__all__ = ["EvalInputRepository"]

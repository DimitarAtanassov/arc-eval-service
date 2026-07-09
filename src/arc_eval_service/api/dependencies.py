from __future__ import annotations

from functools import lru_cache

from arc_eval_service.catalog import Catalog, load_catalog
from arc_eval_service.clients.lab_inference_client import (
    LabInferenceClient,
    LabInferenceSettings,
    build_lab_inference_client,
)
from arc_eval_service.core.config import get_settings
from arc_eval_service.db.engine import Database
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
    ExperimentRepository,
    ExperimentRunRepository,
)
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.services.evaluation_service import EvaluationService
from arc_eval_service.services.experiment_service import ExperimentService
from arc_eval_service.services.read_service import ReadService


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Return the process-wide database (engine + session factory)."""
    url = get_settings().database_url
    if url is None:
        msg = "ARC_EVAL_DATABASE_URL must be set"
        raise RuntimeError(msg)
    return Database(url)


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Return the process-wide prompt library (loaded and validated once)."""
    return load_catalog(get_settings().prompts_path)


def get_model_registry() -> ModelRegistry:
    """Return the judge-model registry built from configured profiles."""
    settings = get_settings()
    return ModelRegistry(settings.model_profiles, default=settings.default_model)


def get_judge_engine() -> JudgeEngine:
    """Return a JudgeEngine over the prompt library and model registry."""
    return JudgeEngine(
        library=get_catalog(),
        models=get_model_registry(),
        default_judge=get_settings().default_judge,
    )


def get_evaluation_service() -> EvaluationService:
    """Return an EvaluationService wired to the engine and repositories."""
    database = get_database()
    return EvaluationService(
        engine=get_judge_engine(),
        library=get_catalog(),
        requests=EvalRequestRepository(database.sessionmaker),
        results=EvaluationResultRepository(database.sessionmaker),
    )


def get_read_service() -> ReadService:
    """Return a ReadService for the browse endpoints (reads only)."""
    database = get_database()
    return ReadService(
        requests=EvalRequestRepository(database.sessionmaker),
        results=EvaluationResultRepository(database.sessionmaker),
        catalog=get_catalog(),
    )


@lru_cache(maxsize=1)
def get_lab_inference_client() -> LabInferenceClient | None:
    """Return the process-wide lab inference client, or None when unconfigured."""
    return build_lab_inference_client(LabInferenceSettings())


def get_experiment_service() -> ExperimentService:
    """Return an ExperimentService wired to experiment repos, the lab client, and the eval service."""
    database = get_database()
    return ExperimentService(
        experiments=ExperimentRepository(database.sessionmaker),
        runs=ExperimentRunRepository(database.sessionmaker),
        lab_client=get_lab_inference_client(),
        evaluation=get_evaluation_service(),
    )

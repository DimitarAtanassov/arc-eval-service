# Service: arc-eval-service

Audience: backend engineers. Reading time: 4 minutes.

## Role

Score one completed AI interaction and return a quality score per metric. Scoring
is synchronous on the request, best effort, and LLM-as-a-judge. The service owns
the metrics, their rubrics, the judges, and the judge-model calls. Metric and
judge prompts live in a YAML library, not in code. It does not run inference,
route requests, or decide a caller's response.

The wire contract is in the [README](../README.md). This document is the internal
design.

## Scoring flow

```mermaid
flowchart LR
    API["POST /v1/evaluate"] --> SVC["EvaluationService"]
    SVC -->|"metrics"| ENG["JudgeEngine"]
    ENG --> LIB["Catalog (metric + judge, YAML)"]
    ENG --> PORT["JudgeModel (port)"]
    PORT --> OAI["OpenAI-compatible adapter"]
    SVC --> REQ["EvalRequestRepository"]
    SVC --> RES["EvaluationResultRepository"]
    REQ --> DB[("Postgres")]
    RES --> DB
```

1. `EvaluationService` validates the metrics the request names against the
   catalog. An unknown metric name is rejected with `404` before any scoring.
2. It scores them concurrently through `JudgeEngine`, one metric at a time,
   each run on the resolved model requesting a structured `Verdict` response.
3. It persists the request and every result, then returns the metrics that scored.

A **metric** is a criterion (a rubric, the case fields it needs, a case-layout
template, and a threshold). A **judge** is prompt scaffolding (an optional system
prompt plus sampling settings) bound to a model profile. Both are data, loaded
from per-file YAML. The engine composes them; the model call and verdict parsing
are its only logic. Add or edit a metric or judge by editing YAML, not code.

## Metric selection

The caller names the metrics to score on every request. There is no server-side
task classification: the service scores exactly the metrics it is given, and an
unknown metric name is rejected with `404` before any scoring or persistence.

## Metrics and judges

Metric and judge definitions live in per-file YAML under
[catalog/metric/](../src/arc_eval_service/catalog/metric) and
[catalog/judge/](../src/arc_eval_service/catalog/judge), one file per metric or
judge, loaded and validated once at startup (a malformed file fails boot, not a
request). The engine
composes the system prompt as an ordered pipeline of optional layers:

```text
system = [judge.system_prompt?] + metric.rubric
user   = render(metric.template, case)
```

A judge with no system prompt of its own runs the metric rubric only; a judge with
one has it prepended. The output contract is not a prompt: the engine requests a
structured [Verdict](../src/arc_eval_service/judging/verdict.py) through the model's
JSON-schema mode, so the JSON shape cannot drift from the parser. Adding a metric
or a judge, or tuning a rubric, is a YAML edit; the code does not change.

## Judge models

A judge in the library names a `model_profile`; the profile is the transport and
credentials (provider, model id, optional `base_url`, and the env var holding the
API key). Secrets resolve at call time, never stored in a profile, a judge, a
request, or a log. Models are pluggable through the `JudgeModel` port: one
OpenAI-compatible adapter covers OpenAI, Azure OpenAI, and self-hosted servers
(vLLM, Ollama) by changing `base_url`. Adding a vendor is a new adapter under
[judging/providers](../src/arc_eval_service/judging/providers); nothing else
changes.

## Failure handling

| Condition | Behavior |
| --- | --- |
| One metric fails to score (bad verdict, model error) | That metric is persisted with its error and omitted from the response. Other metrics are unaffected. |
| No judge model configured | Every metric errors. The response is `{"results": []}`; the errored rows are still persisted. |
| The observability write fails | Logged and swallowed. The caller still receives its scores. |
| Required request field missing | `422`, before any scoring. |
| A named metric is not in the catalog | `404`, before any scoring or persistence. |

Scoring never fails the request: the judge engine degrades a failed metric to an
errored result rather than raising. Persistence is the caller's bookkeeping, not
their availability, so it never fails the response.

## What it does not own

Inference, routing, guardrails, dataset curation, or the roll-up of many metrics
into a single verdict. It reports and stores per-metric scores; the caller decides
what they mean.

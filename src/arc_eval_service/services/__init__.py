"""Application services: scoring orchestration, task policy, and DTO mappers.

``evaluation_service`` orchestrates one ``POST /v1/evaluate`` call; ``policy``
decides which metrics run for a task type; ``mapping`` holds the pure translations
between the wire contract, the domain, and persistence records.
"""

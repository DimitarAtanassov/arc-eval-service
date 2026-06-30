"""Ingestion slice: store one LLM interaction to be evaluated later.

A single endpoint records the prompt template, the inputs that rendered it, the
LLM response and the model config. It runs no evaluation logic.
"""

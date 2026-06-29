"""Built-in LLM-as-a-judge strategies."""

from __future__ import annotations

from arc_eval_service.judges.builtins.answer_relevance import AnswerRelevanceJudge
from arc_eval_service.judges.builtins.custom import CustomJudge
from arc_eval_service.judges.builtins.faithfulness import FaithfulnessJudge
from arc_eval_service.judges.builtins.safety import SafetyJudge

__all__ = [
    "AnswerRelevanceJudge",
    "CustomJudge",
    "FaithfulnessJudge",
    "SafetyJudge",
]

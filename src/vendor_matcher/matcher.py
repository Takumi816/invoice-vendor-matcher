"""Vendor name reconciliation with a human-in-the-loop escalation queue.

Design principle: an LLM's fuzzy-match judgement is never trusted blindly.
Exact matches bypass the LLM entirely (cost control). Anything below the
confidence threshold — or that the LLM itself calls uncertain, or that fails
to call at all — is routed to a review queue instead of being auto-committed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .llm_client import LlmJudgement

LlmJudge = Callable[[str, list[str]], LlmJudgement]


def normalize(name: str) -> str:
    """Normalize a name for matching purposes only.

    Whitespace is stripped and case is folded, but legal-entity notation
    (株式会社 / (株) / 有限会社 etc.) is intentionally left untouched — collapsing
    that away is exactly the kind of silent, hard-to-audit rewrite that this
    project is designed to avoid. Matching and display are kept as separate
    concerns: this function is for matching only, never for what gets shown
    to a human.
    """
    return re.sub(r"\s+", "", name).casefold()


@dataclass(frozen=True)
class MatchResult:
    raw_name: str
    matched_canonical: Optional[str]
    confidence: int  # 0-100
    needs_review: bool
    reason: str


class VendorMatcher:
    def __init__(
        self,
        master_names: list[str],
        llm_judge: LlmJudge,
        confidence_threshold: int = 90,
    ) -> None:
        if not 0 <= confidence_threshold <= 100:
            raise ValueError("confidence_threshold must be between 0 and 100")
        self.master_names = list(master_names)
        self._normalized_master = {normalize(n): n for n in master_names}
        self.llm_judge = llm_judge
        self.confidence_threshold = confidence_threshold

    def match(self, raw_name: str) -> MatchResult:
        exact = self._normalized_master.get(normalize(raw_name))
        if exact is not None:
            return MatchResult(raw_name, exact, 100, False, "完全一致（正規化後）")

        try:
            judgement = self.llm_judge(raw_name, self.master_names)
        except Exception as exc:  # noqa: BLE001 - fail-safe by design, not a bug
            return MatchResult(
                raw_name, None, 0, True, f"LLM呼び出しに失敗したため要確認: {exc}"
            )

        if judgement.candidate is None:
            return MatchResult(
                raw_name, None, judgement.confidence, True, "候補なし（LLM判定）"
            )

        if judgement.confidence < self.confidence_threshold:
            return MatchResult(
                raw_name,
                judgement.candidate,
                judgement.confidence,
                True,
                f"確信度{judgement.confidence}が閾値{self.confidence_threshold}未満のため要確認",
            )

        return MatchResult(
            raw_name,
            judgement.candidate,
            judgement.confidence,
            False,
            "LLM判定（高確信度のため自動確定）",
        )

    def match_all(self, raw_names: list[str]) -> list[MatchResult]:
        return [self.match(name) for name in raw_names]

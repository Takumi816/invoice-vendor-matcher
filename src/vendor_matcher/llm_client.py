"""Thin, replaceable LLM client for vendor-name judgement.

This module is deliberately small: it exists only to turn a raw name + a
candidate list into a structured judgement. Everything about *how* that
judgement is used (thresholds, escalation, fail-safety) lives in matcher.py
and does not know or care which LLM produced it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LlmJudgement:
    candidate: Optional[str]
    confidence: int
    rationale: str


_PROMPT_TEMPLATE = """以下は請求書に記載された業者名の表記です。業者マスターの候補リストの中から、
最も一致する可能性が高いものを1つ選んでください。表記ゆれ（法人格の有無・全角半角・旧字体・スペース等）
を考慮してください。どれにも該当しないと判断した場合はcandidateをnullにしてください。

業者名: {raw_name}
候補リスト: {candidates}

以下のJSON形式のみで回答してください（説明文・コードブロックは不要）:
{{"candidate": "選んだ候補文字列 or null", "confidence": 0から100の整数, "rationale": "判断理由を一文で"}}
"""


def claude_vendor_judge(
    raw_name: str,
    candidates: list[str],
    *,
    model: Optional[str] = None,
) -> LlmJudgement:
    """Ask a Claude model to judge which candidate a raw vendor name refers to.

    Requires the ``anthropic`` package and an ``ANTHROPIC_API_KEY`` environment
    variable. Raises on any failure — the caller (VendorMatcher) is responsible
    for treating that as "needs human review", not this function.
    """
    import anthropic  # imported lazily so tests never need the dependency

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = _PROMPT_TEMPLATE.format(raw_name=raw_name, candidates=candidates)

    response = client.messages.create(
        model=model or os.environ.get("VENDOR_MATCHER_MODEL", "claude-sonnet-5"),
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    data = json.loads(text)
    return LlmJudgement(
        candidate=data.get("candidate"),
        confidence=int(data.get("confidence", 0)),
        rationale=str(data.get("rationale", "")),
    )

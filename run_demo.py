"""End-to-end demo: reconcile a list of raw invoice vendor names against a
master list, using Claude for the fuzzy cases and a human-review queue for
anything the model isn't confident about.

Usage:
    ANTHROPIC_API_KEY=sk-... python run_demo.py

All names in data/ are fictional. This mirrors, on dummy data, the design of
a production vendor-name reconciliation system built for a real client.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from vendor_matcher.llm_client import claude_vendor_judge  # noqa: E402
from vendor_matcher.matcher import VendorMatcher  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"


def load_column(csv_path: Path, column: str) -> list[str]:
    with csv_path.open(encoding="utf-8") as f:
        return [row[column] for row in csv.DictReader(f)]


def main() -> None:
    if "ANTHROPIC_API_KEY" not in os.environ:
        print(
            "ANTHROPIC_API_KEY が未設定です。実際のLLM判定は行えません。\n"
            "テストスイート（tests/test_matcher.py）は疑似LLMで全ロジックを検証済みです。\n"
            "実際にAPIを叩いて試す場合は環境変数を設定してから再実行してください。"
        )
        return

    master_names = load_column(DATA_DIR / "master_vendors.csv", "canonical_name")
    raw_names = load_column(DATA_DIR / "raw_invoice_names.csv", "raw_name")

    matcher = VendorMatcher(master_names, claude_vendor_judge, confidence_threshold=90)
    results = matcher.match_all(raw_names)

    auto_confirmed = [r for r in results if not r.needs_review]
    needs_review = [r for r in results if r.needs_review]

    print(f"=== 自動確定（{len(auto_confirmed)}件） ===")
    for r in auto_confirmed:
        print(f"  {r.raw_name!r} -> {r.matched_canonical} (確信度{r.confidence}) [{r.reason}]")

    print(f"\n=== 要確認（{len(needs_review)}件） ===")
    for r in needs_review:
        print(f"  {r.raw_name!r} -> 候補: {r.matched_canonical} (確信度{r.confidence}) [{r.reason}]")


if __name__ == "__main__":
    main()

# invoice-vendor-matcher

![Tests](https://github.com/Takumi816/invoice-vendor-matcher/actions/workflows/test.yml/badge.svg)

請求書に記載された業者名の表記ゆれ（法人格の有無・全角半角・旧字体など）を、LLMを使って業者マスターと突合するツールです。実務で担当した請求業務改善で採用した「最後は人が確認・承認する」という設計思想を、LLM照合というテーマに移植し、機密データを一切含まないダミーデータで再構成しています。

## なぜ全自動化しなかったか

表記ゆれの吸収は、文字列の類似度だけで機械的に「えいや」と自動確定することもできます。ここではあえてそうしていません。

請求金額の照合という業務では、誤った1件の自動確定が「間違った金額で請求書を出す」という実害に直結します。速度より正確さが優先される場面で、AIの判断をそのまま信用して自動化するのは筋が悪いという判断です。

そこで、このツールは3段階の確信度に応じて挙動を変えます。

1. **完全一致**（正規化後）は無条件で自動確定します。この場合LLMは呼びません。表記が完全に一致している業者名にまでAPIコストと待ち時間をかける理由がないからです。
2. **LLMが高い確信度で候補を示した場合**のみ自動確定します。
3. **確信度が閾値未満・候補なし・API呼び出し自体の失敗**——このいずれかに該当する場合は、自動確定させず「要確認」キューに積みます。人が最後に見て承認する前提です。

「AIが間違えないこと」を目指すのではなく、「AIが間違えても実害が出ない構造にする」ことを目指した設計です。

## 使い方

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,llm]"

# テスト実行（LLM APIキー不要。疑似LLMで全ロジックを検証済み）
pytest -v

# 実際にLLMを使ったデモ（要 ANTHROPIC_API_KEY）
ANTHROPIC_API_KEY=sk-... python run_demo.py
```

### 実行例（`pytest -v`）

CI（GitHub Actions・Python 3.10〜3.13のマトリクス）とローカル（Python 3.14）の両方で以下が再現します。実データではなく `tests/test_matcher.py` 内の疑似LLM（`fake_llm` 関数を都度差し替え）だけで、高確信度・低確信度・候補なし・API障害・境界値の全分岐を検証しています。

```
============================= test session starts ==============================
collected 12 items

tests/test_matcher.py::TestNormalize::test_strips_whitespace_and_folds_case PASSED [  8%]
tests/test_matcher.py::TestNormalize::test_preserves_legal_entity_notation PASSED [ 16%]
tests/test_matcher.py::TestExactMatch::test_exact_match_bypasses_llm_entirely PASSED [ 25%]
tests/test_matcher.py::TestExactMatch::test_whitespace_only_difference_is_still_exact_match PASSED [ 33%]
tests/test_matcher.py::TestLlmAssistedMatch::test_high_confidence_match_is_auto_confirmed PASSED [ 41%]
tests/test_matcher.py::TestLlmAssistedMatch::test_low_confidence_match_is_escalated_not_auto_committed PASSED [ 50%]
tests/test_matcher.py::TestLlmAssistedMatch::test_no_candidate_is_escalated PASSED [ 58%]
tests/test_matcher.py::TestLlmAssistedMatch::test_llm_failure_fails_safe_to_review_queue PASSED [ 66%]
tests/test_matcher.py::TestLlmAssistedMatch::test_confidence_exactly_at_threshold_is_auto_confirmed PASSED [ 75%]
tests/test_matcher.py::TestMatchAll::test_processes_each_name_independently PASSED [ 83%]
tests/test_matcher.py::TestConstructorValidation::test_rejects_out_of_range_threshold[-1] PASSED [ 91%]
tests/test_matcher.py::TestConstructorValidation::test_rejects_out_of_range_threshold[101] PASSED [100%]

============================== 12 passed in 0.01s ==============================
```

## 構成

```
src/vendor_matcher/
  matcher.py      # 照合ロジック本体。閾値判定・要確認キューへの振り分け（LLM非依存）
  llm_client.py   # Claude APIへの薄いラッパー（差し替え可能）
tests/
  test_matcher.py # 疑似LLM（関数の差し替え）で全分岐を検証。実APIへの依存なし
data/
  *.csv           # 架空の業者名のみ。実データは一切含まない
```

`matcher.py` は `llm_judge` を関数として受け取る設計にしており、テストでは本物のAPIを呼ぶ代わりに好きな返り値を返す疑似関数を渡しています。これにより、API課金や通信なしで「確信度が閾値ちょうどのときの挙動」「API障害時の挙動」まで含めて全パターンを検証できます。

## 実務での実績（参考）

実務で担当した請求業務改善では、表記ゆれの解消を業者マスター＋承認制のルールベースで解決しており、LLMは実行時の判定には使っていません（開発時のコーディング支援としてのみ利用）。このツールは、その「最後は人が確認・承認する」という設計思想を、LLM照合というテーマに移植・再構成した独立の実装です。

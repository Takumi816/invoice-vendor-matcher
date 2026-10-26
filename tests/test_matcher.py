import pytest

from vendor_matcher.llm_client import LlmJudgement
from vendor_matcher.matcher import VendorMatcher, normalize

MASTER = ["株式会社山田商事", "田中興業株式会社", "鈴木運輸有限会社"]


def _never_call(raw_name, candidates):
    raise AssertionError(f"LLM should not be called for {raw_name!r}, but was")


class TestNormalize:
    def test_strips_whitespace_and_folds_case(self):
        assert normalize(" ABC 商事 ") == normalize("abc商事")

    def test_preserves_legal_entity_notation(self):
        # 法人格表記は正規化で消さない設計（表示との一致・監査可能性のため）
        assert normalize("株式会社山田商事") != normalize("山田商事")


class TestExactMatch:
    def test_exact_match_bypasses_llm_entirely(self):
        matcher = VendorMatcher(MASTER, _never_call)
        result = matcher.match("株式会社山田商事")
        assert result.matched_canonical == "株式会社山田商事"
        assert result.confidence == 100
        assert result.needs_review is False
        assert "完全一致" in result.reason

    def test_whitespace_only_difference_is_still_exact_match(self):
        matcher = VendorMatcher(MASTER, _never_call)
        result = matcher.match(" 株式会社山田商事 ")
        assert result.matched_canonical == "株式会社山田商事"
        assert result.needs_review is False


class TestLlmAssistedMatch:
    def test_high_confidence_match_is_auto_confirmed(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement("田中興業株式会社", 95, "法人格表記のみの違い")

        matcher = VendorMatcher(MASTER, fake_llm, confidence_threshold=90)
        result = matcher.match("(株)田中興業")

        assert result.matched_canonical == "田中興業株式会社"
        assert result.confidence == 95
        assert result.needs_review is False

    def test_low_confidence_match_is_escalated_not_auto_committed(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement("鈴木運輸有限会社", 60, "部分一致のみで確信が持てない")

        matcher = VendorMatcher(MASTER, fake_llm, confidence_threshold=90)
        result = matcher.match("すずき")

        # 候補は提示するが、確定はさせない
        assert result.matched_canonical == "鈴木運輸有限会社"
        assert result.confidence == 60
        assert result.needs_review is True

    def test_no_candidate_is_escalated(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement(None, 0, "候補リストのどれにも該当しない")

        matcher = VendorMatcher(MASTER, fake_llm)
        result = matcher.match("未知の業者名")

        assert result.matched_canonical is None
        assert result.needs_review is True

    def test_high_confidence_candidate_not_in_master_is_escalated(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement("架空商事株式会社", 99, "存在しない業者を自信満々に返す")

        matcher = VendorMatcher(MASTER, fake_llm, confidence_threshold=90)
        result = matcher.match("かくう商事")

        # 実在しない候補は、確信度が高くても確定させない
        assert result.matched_canonical is None
        assert result.needs_review is True
        assert "架空商事株式会社" in result.reason

    def test_candidate_differing_in_legal_entity_notation_is_escalated(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement("山田商事", 95, "法人格を省いた表記")

        matcher = VendorMatcher(MASTER, fake_llm, confidence_threshold=90)
        result = matcher.match("山田商事")

        # 法人格を除いた文字列はマスターに無いため、人が確認する
        assert result.matched_canonical is None
        assert result.needs_review is True

    def test_candidate_with_stray_whitespace_resolves_to_master_name(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement(" 田中興業株式会社 ", 95, "空白が混じった候補")

        matcher = VendorMatcher(MASTER, fake_llm, confidence_threshold=90)
        result = matcher.match("(株)田中興業")

        # 空白差は正規化で吸収し、確定値はマスター側の表記で返す
        assert result.matched_canonical == "田中興業株式会社"
        assert result.needs_review is False

    def test_llm_failure_fails_safe_to_review_queue(self):
        def broken_llm(raw_name, candidates):
            raise RuntimeError("API timeout")

        matcher = VendorMatcher(MASTER, broken_llm)
        result = matcher.match("なにか")

        assert result.needs_review is True
        assert result.matched_canonical is None
        assert "失敗" in result.reason

    def test_confidence_exactly_at_threshold_is_auto_confirmed(self):
        def fake_llm(raw_name, candidates):
            return LlmJudgement("田中興業株式会社", 90, "境界値")

        matcher = VendorMatcher(MASTER, fake_llm, confidence_threshold=90)
        result = matcher.match("たなか興業")

        assert result.needs_review is False


class TestMatchAll:
    def test_processes_each_name_independently(self):
        calls = []

        def fake_llm(raw_name, candidates):
            calls.append(raw_name)
            return LlmJudgement(None, 0, "")

        matcher = VendorMatcher(MASTER, fake_llm)
        results = matcher.match_all(["株式会社山田商事", "謎の業者"])

        assert results[0].needs_review is False  # 完全一致、LLM未呼び出し
        assert results[1].needs_review is True
        assert calls == ["謎の業者"]


class TestConstructorValidation:
    @pytest.mark.parametrize("bad_threshold", [-1, 101])
    def test_rejects_out_of_range_threshold(self, bad_threshold):
        with pytest.raises(ValueError):
            VendorMatcher(MASTER, _never_call, confidence_threshold=bad_threshold)

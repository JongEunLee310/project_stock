import json
from dataclasses import FrozenInstanceError
from typing import ClassVar, cast

import pytest

from app.adapters.llm.cache import CachedCompletion, LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy, EscalationSignal
from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.masking import MaskCategory, mask_sensitive_text
from app.adapters.llm.privacy import (
    CloudSafePayload,
    DecisionAssistSnapshot,
    NewsSummarySnapshot,
    PrivacyGate,
    ResearchQAEvidenceProjection,
    ResearchQASnapshot,
)
from app.adapters.llm.router import LLMRouter, TaskRoute
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from tests.test_llm_gateway import ExampleResponse, SpyLLMClient, SpyResponseCache


@pytest.mark.parametrize(
    "text,expected,categories",
    [
        ("연락 me@example.com", "연락 [이메일]", {MaskCategory.EMAIL}),
        ("010-1234-5678", "[전화번호]", {MaskCategory.PHONE}),
        ("+82 10 1234 5678", "[전화번호]", {MaskCategory.PHONE}),
        ("02-123-4567", "[전화번호]", {MaskCategory.PHONE}),
        ("+1 212 555 1234", "[전화번호]", {MaskCategory.PHONE}),
        ("900101-1234567", "[주민등록번호]", {MaskCategory.RESIDENT_ID}),
        ("1234-5678-9012-3456", "[카드번호]", {MaskCategory.CARD}),
        ("1234 5678 9012 3456", "[카드번호]", {MaskCategory.CARD}),
        ("1234567890123456", "[카드번호]", {MaskCategory.CARD}),
        ("계좌 123-456789-01-012", "계좌 [계좌번호]", {MaskCategory.ACCOUNT}),
        ("account 123-456789-01", "account [계좌번호]", {MaskCategory.ACCOUNT}),
        ("123456789012", "[계좌번호]", {MaskCategory.ACCOUNT}),
        (
            "삼성전자 300주를 평단 7만 원에 샀는데 지금 리스크는?",
            "삼성전자 [수량]를 평단 [금액]에 샀는데 지금 리스크는?",
            {MaskCategory.QUANTITY, MaskCategory.AMOUNT},
        ),
        (
            "I bought 100 shares at $180, should I worry?",
            "I bought [수량] at [금액], should I worry?",
            {MaskCategory.QUANTITY, MaskCategory.AMOUNT},
        ),
        (
            "내 보유 1,000주 평단 5천만원, 원금 1.2억, $20,000",
            "내 보유 [수량] 평단 [금액], 원금 [금액], [금액]",
            {MaskCategory.QUANTITY, MaskCategory.AMOUNT},
        ),
        (
            "내 원금 1.2억이다. 애플 300억 달러 계약! 보유 10주\n100주 7만 원",
            "내 원금 [금액]이다. 애플 300억 달러 계약! 보유 [수량]\n100주 7만 원",
            {MaskCategory.QUANTITY, MaskCategory.AMOUNT},
        ),
    ],
)
def test_sensitive_text(
    text: str, expected: str, categories: set[MaskCategory]
) -> None:
    result = mask_sensitive_text(text)
    assert result.text == expected
    assert result.categories == categories
    assert mask_sensitive_text(result.text).text == result.text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "애플-브로드컴 300억 달러 계약 내용은?",
        "PER 30배 이하 종목의 3분기 실적은?",
        "자사주 1,000만 주 소각 계획은?",
        "내 수익률 20%, -15.3%, 3%p, PER 30배, PBR 1.2배, 2배 레버리지",
        "내 종목 005930, NVDA, 2026년 3분기, 52주 신고가, 5년",
        "코스피 2,600. 엔비디아 시총 4조 달러",
        "제조업 300억 달러 계약",
        "123-456789-01",
        "123456789",
        "12345678901234567",
    ],
)
def test_public_text(text: str) -> None:
    assert mask_sensitive_text(text).text == text
    assert not mask_sensitive_text(text).categories


@pytest.mark.parametrize(
    "marker",
    [
        "내",
        "제",
        "저의",
        "나의",
        "우리",
        "보유",
        "들고 있",
        "매수",
        "매입",
        "매도",
        "샀",
        "팔았",
        "사 둔",
        "평단",
        "평균단가",
        "투자했",
        "넣었",
        "물려",
        "손절",
        "익절",
        "계좌",
        "예수금",
        "원금",
        "my",
        "mine",
        "I have",
        "I hold",
        "I bought",
        "I sold",
        "I own",
        "my position",
        "cost basis",
        "average cost",
    ],
)
def test_personal_markers(marker: str) -> None:
    assert mask_sensitive_text(f"{marker} 300주 7만 원").categories == {
        MaskCategory.QUANTITY,
        MaskCategory.AMOUNT,
    }


def snapshot(question: str) -> ResearchQASnapshot:
    return ResearchQASnapshot(
        symbol="NVDA",
        asset_name="NVIDIA",
        question=question,
        evidence=[
            ResearchQAEvidenceProjection(
                id=1,
                title="공개 300억 달러",
                source_name="news",
                published_at=None,
                excerpt="보유 300주 7만 원 me@example.com",
            )
        ],
    )


def test_gate_only_masks_declared_fields_and_logs_categories(
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = snapshot("내 300주 7만 원 me@example.com")
    with caplog.at_level("INFO"):
        masked, categories = PrivacyGate().mask(original)
    assert masked is not original
    assert masked.as_payload()["question"] == "내 [수량] [금액] [이메일]"
    assert masked.as_payload()["evidence"] == original.as_payload()["evidence"]
    assert original.question == "내 300주 7만 원 me@example.com"
    assert categories == {
        MaskCategory.EMAIL,
        MaskCategory.QUANTITY,
        MaskCategory.AMOUNT,
    }
    assert "EMAIL" in caplog.text
    for raw in ["300주", "7만 원", "me@example.com"]:
        assert raw not in caplog.text
    public = NewsSummarySnapshot(title="news", body="me@example.com")
    assert PrivacyGate().mask(public) == (public, frozenset())
    decision = DecisionAssistSnapshot(
        target_type="SYMBOL",
        symbol=None,
        decision_type=None,
        thesis=None,
        rationale="",
        memo="010-1234-5678",
    )
    masked, categories = PrivacyGate().mask(decision)
    assert masked.as_payload()["thesis"] is None
    assert masked.as_payload()["rationale"] == ""
    assert categories == {MaskCategory.PHONE}
    with pytest.raises(FrozenInstanceError):
        mask_sensitive_text("").text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ["missing", "count", "mixed"])
def test_invalid_declaration(field_name: str) -> None:
    class InvalidPayload(CloudSafePayload):
        sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.PUBLIC
        free_text_fields: ClassVar[tuple[str, ...]] = (field_name,)
        count: int = 1
        mixed: str | int = "text"

    with pytest.raises(CloudBoundaryViolationError):
        PrivacyGate().mask(InvalidPayload())


@pytest.mark.parametrize("cached", [False, True])
def test_cloud_masks_before_transport_and_cache(cached: bool) -> None:
    client = SpyLLMClient()
    cache = SpyResponseCache(
        CachedCompletion({"summary": "ok"}, "spy", "spy-model") if cached else None
    )
    gateway = LLMGateway({CLOUD: client}, response_cache=cast(LLMResponseCache, cache))
    payload = snapshot("내 300주 평단 7만 원 010-1234-5678")
    payload = payload.model_copy(update={"evidence": []})
    result = gateway.complete_json(
        LLMTaskType.RESEARCH_QA, payload, ExampleResponse, "qa"
    )
    assert result.cached == cached
    assert result.masked_categories == {
        MaskCategory.PHONE,
        MaskCategory.QUANTITY,
        MaskCategory.AMOUNT,
    }
    serialized = json.dumps(cache.build_calls[0][1].as_payload(), ensure_ascii=False)
    if not cached:
        serialized += client.calls[0][1].content
    else:
        assert not client.calls
    for raw in ["300주", "7만 원", "010-1234-5678"]:
        assert raw not in serialized


@pytest.mark.parametrize("mode", ["local", "verify", "verify_invalid", "before"])
def test_local_and_escalation_masking(mode: str) -> None:
    local = SpyLLMClient({"summary": "local"} if mode != "verify" else {})
    if mode == "verify_invalid":
        local.response = {}
    cloud = SpyLLMClient({} if mode == "verify_invalid" else {"summary": "cloud"})
    router = LLMRouter({LLMTaskType.RESEARCH_QA: TaskRoute(LOCAL, CLOUD)})
    gateway = LLMGateway(
        {LOCAL: local, CLOUD: cloud},
        router=router,
        escalation_policy=EscalationPolicy(),
    )
    payload = snapshot("내 300주 평단 7만 원 010-1234-5678").model_copy(
        update={"evidence": []}
    )
    result = gateway.complete_json(
        LLMTaskType.RESEARCH_QA,
        payload,
        ExampleResponse,
        "qa",
        escalation_signal=EscalationSignal(trade_question=mode == "before"),
    )
    if mode != "before":
        assert json.loads(local.calls[0][1].content)["question"] == payload.question
    if mode == "local":
        assert not cloud.calls and not result.masked_categories
    else:
        assert result.escalated
        assert result.masked_categories == {
            MaskCategory.PHONE,
            MaskCategory.QUANTITY,
            MaskCategory.AMOUNT,
        }
        for raw in ["300주", "7만 원", "010-1234-5678"]:
            assert raw not in cloud.calls[0][1].content


def test_identifier_precedence_in_one_sentence() -> None:
    result = mask_sensitive_text(
        "900101-1234567 1234-5678-9012-3456 010-1234-5678 "
        "me@example.com 계좌 123-456789-01-012 내 300주 7만 원"
    )
    assert result.text == (
        "[주민등록번호] [카드번호] [전화번호] [이메일] 계좌 [계좌번호] 내 [수량] [금액]"
    )
    assert result.categories == frozenset(MaskCategory)


def test_real_cache_reuses_masked_payload_and_recomputes_categories() -> None:
    from tests.test_llm_cache import FakeRedisCache

    redis = FakeRedisCache()
    cache = LLMResponseCache(redis, ttl_seconds=300)
    client = SpyLLMClient()
    gateway = LLMGateway({CLOUD: client}, response_cache=cache)
    results = [
        gateway.complete_json(
            LLMTaskType.RESEARCH_QA, snapshot(question), ExampleResponse, "qa"
        )
        for question in ["내 300주 평단 7만 원", "내 500주 평단 9만 원"]
    ]
    assert not results[0].cached and results[1].cached
    assert (
        results[0].masked_categories
        == results[1].masked_categories
        == {MaskCategory.QUANTITY, MaskCategory.AMOUNT}
    )
    assert len(client.calls) == len(redis.set_calls) == 1
    assert list(redis.values) == [
        cache.build_key(
            LLMTaskType.RESEARCH_QA,
            PrivacyGate().mask(snapshot("내 300주 평단 7만 원"))[0],
            "qa",
            client.model_name,
            ExampleResponse,
        )
    ]


@pytest.mark.parametrize("field", ["thesis", "rationale", "memo"])
def test_each_decision_free_text_field_is_masked(field: str) -> None:
    original = DecisionAssistSnapshot(
        target_type="SYMBOL",
        symbol="NVDA",
        decision_type=None,
        thesis=None,
        rationale=None,
        memo=None,
    ).model_copy(update={field: "my 100 shares at $180 me@example.com"})
    masked, categories = PrivacyGate().mask(original)
    assert getattr(masked, field) == "my [수량] at [금액] [이메일]"
    assert categories == {
        MaskCategory.EMAIL,
        MaskCategory.QUANTITY,
        MaskCategory.AMOUNT,
    }
    assert original.as_payload()[field] == "my 100 shares at $180 me@example.com"

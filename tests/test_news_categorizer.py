import pytest

from app.domains.news.categorizer import categorize
from app.domains.news.schema import NewsCategory


@pytest.mark.parametrize(
    ("title", "summary", "expected"),
    [
        ("삼성전자 2분기 영업이익 증가", None, "EARNINGS"),
        ("Company raises annual revenue guidance", None, "EARNINGS"),
        ("신제품 스마트폰 출시", None, "PRODUCT"),
        ("Company unveils new product", None, "PRODUCT"),
        ("전략적 제휴 계약 체결", None, "PARTNERSHIP"),
        ("Companies announce global partnership", None, "PARTNERSHIP"),
        ("공정위, 독점 규제 제재", None, "REGULATION"),
        ("FTC files antitrust lawsuit", None, "REGULATION"),
        ("신임 대표이사 선임", None, "PERSONNEL"),
        ("Company appoints new CEO", None, "PERSONNEL"),
        ("자사주 매입과 배당 결정", None, "CAPITAL"),
        ("Board approves share buyback", None, "CAPITAL"),
        ("주가 상승으로 증시 관심 집중", None, "MARKET"),
        ("Stock market rally continues", None, "MARKET"),
    ],
)
def test_categorize_matches_korean_and_english_keywords(
    title: str,
    summary: str | None,
    expected: NewsCategory,
) -> None:
    assert categorize(title, summary) == expected


def test_categorize_uses_summary_and_is_case_insensitive() -> None:
    assert categorize("Company update", "DIVIDEND policy approved") == "CAPITAL"


def test_categorize_falls_back_to_other() -> None:
    assert categorize("지역 사회 봉사 활동", None) == "OTHER"


def test_categorize_returns_first_category_by_priority() -> None:
    assert categorize("분기 실적 발표 후 주가 상승", None) == "EARNINGS"

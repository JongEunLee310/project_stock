from app.domains.news.schema import NewsCategory


CATEGORY_KEYWORDS: tuple[tuple[NewsCategory, tuple[str, ...]], ...] = (
    (
        "EARNINGS",
        (
            "실적",
            "영업이익",
            "순이익",
            "매출",
            "분기",
            "earnings",
            "operating profit",
            "net income",
            "revenue",
            "guidance",
        ),
    ),
    (
        "PRODUCT",
        (
            "신제품",
            "출시",
            "제품",
            "서비스",
            "launch",
            "product",
            "service",
            "unveil",
        ),
    ),
    (
        "PARTNERSHIP",
        (
            "협력",
            "제휴",
            "파트너십",
            "계약 체결",
            "partnership",
            "collaboration",
            "joint venture",
            "agreement",
        ),
    ),
    (
        "REGULATION",
        (
            "규제",
            "소송",
            "제재",
            "공정위",
            "금융위",
            "ftc",
            "lawsuit",
            "antitrust",
            "regulator",
            "sanction",
        ),
    ),
    (
        "PERSONNEL",
        (
            "인사",
            "대표이사",
            "임원",
            "선임",
            "사임",
            "ceo",
            "executive",
            "appoint",
            "resign",
        ),
    ),
    (
        "CAPITAL",
        (
            "유상증자",
            "무상증자",
            "자사주",
            "배당",
            "buyback",
            "dividend",
            "share offering",
            "capital raise",
        ),
    ),
    (
        "MARKET",
        (
            "주가",
            "증시",
            "시장",
            "상승",
            "하락",
            "stock",
            "shares",
            "market",
            "rally",
        ),
    ),
)


def categorize(title: str, summary: str | None) -> NewsCategory:
    content = " ".join(part for part in (title, summary) if part).casefold()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword.casefold() in content for keyword in keywords):
            return category
    return "OTHER"

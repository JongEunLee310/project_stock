import hashlib
from unittest.mock import patch

import pytest
from lxml import etree  # type: ignore[import-untyped]

from app.domains.rag.indexing import (
    chunk_text,
    clean_body_text,
    compose_embedding_text,
    embedding_input_hash,
)
from app.domains.rag.types import ChunkContentQuality


# raw_news_events 실데이터 형태, 2026-10-12 확인: id=60007 원문.
SINGLE_HEADLINE_BODY = (
    '<a href="https://news.google.com/rss/articles/'
    'CBMiX0FVX3lxTE9ScWVYNngzeTJqV2s3eWRTbVI1Z2Q4aTQ5anBFc1dEZ0Z3RURZelNZWlNWaVdu'
    'RGE0VnlacFhGOXJvY1NlNEVBMlRfejJrU3lHOVBpVnpCZE9RY3lyMks4?oc=5" target="_blank">'
    'US has nothing to worry about Chinese AI models, Jensen Huang says</a>'
    '&nbsp;&nbsp;<font color="#6f6f6f">Cybernews</font>'
)
SINGLE_HEADLINE_TITLE = (
    "US has nothing to worry about Chinese AI models, Jensen Huang says - Cybernews"
)

# raw_news_events 실데이터 형태, 2026-10-12 확인: id=88 제목·구조 예시로 재구성.
RELATED_HEADLINES_BODY = (
    '<ol><li><a href="https://example.com/1" target="_blank">'
    'Apple says it will spend $30 billion to design US-made Broadcom chips</a>'
    '&nbsp;&nbsp;<font color="#6f6f6f">CNN</font></li>'
    '<li><a href="https://example.com/2" target="_blank">'
    'Apple’s Chip Deal With Broadcom Expected to Exceed $30 Billion</a>'
    '&nbsp;&nbsp;<font color="#6f6f6f">Bloomberg.com</font></li></ol>'
)


def test_single_headline_rss_contract() -> None:
    cleaned = clean_body_text(SINGLE_HEADLINE_BODY)
    assert cleaned == SINGLE_HEADLINE_TITLE.replace(" - ", " ")
    assert all(token not in cleaned for token in ("https://", "href", "&nbsp;", "<"))
    text, quality = compose_embedding_text(
        SINGLE_HEADLINE_TITLE, SINGLE_HEADLINE_BODY, None
    )
    assert quality == ChunkContentQuality.TITLE_ONLY
    assert text == SINGLE_HEADLINE_TITLE
    assert text.count(SINGLE_HEADLINE_TITLE.split(" - ")[0]) == 1


def test_related_headlines_rss_shape() -> None:
    assert clean_body_text(RELATED_HEADLINES_BODY).splitlines() == [
        "Apple says it will spend $30 billion to design US-made Broadcom chips CNN",
        "Apple’s Chip Deal With Broadcom Expected to Exceed $30 Billion Bloomberg.com",
    ]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (None, ""),
        ("", ""),
        (" \t \n ", ""),
        (" 일반  텍스트\t본문 \n\n 다음  줄 ", "일반 텍스트 본문\n다음 줄"),
        ("가격 < 30 및 > 20", "가격 < 30 및 > 20"),
        (" 일반 &amp; 텍스트 ", "일반 &amp; 텍스트"),
        ('<a href="https://example.com">닫히지 않은 태그', "닫히지 않은 태그"),
        ("<p>A&amp;B&nbsp; C</p>", "A&B C"),
        ("<ol><li>첫 항목<li>둘째 항목</ol>", "첫 항목\n둘째 항목"),
    ],
)
def test_clean_body_text(body: str | None, expected: str) -> None:
    assert clean_body_text(body) == expected


def test_clean_body_parser_failure() -> None:
    with patch(
        "app.domains.rag.indexing.html.fromstring",
        side_effect=etree.ParserError("invalid RSS fragment"),
    ):
        assert clean_body_text(RELATED_HEADLINES_BODY).splitlines() == [
            "Apple says it will spend $30 billion to design US-made Broadcom chips CNN",
            "Apple’s Chip Deal With Broadcom Expected to Exceed $30 Billion Bloomberg.com",
        ]
        assert clean_body_text("<p>A&amp;B&nbsp; C</p>") == "A&B C"


@pytest.mark.parametrize("remaining", [29, 30])
def test_duplicate_headline_boundary(remaining: int) -> None:
    body = "헤드라인 " + "x" * remaining
    expected = "헤드라인 - 매체"
    if remaining == 30:
        expected += "\n\n" + body
    assert compose_embedding_text("헤드라인 - 매체", body, None) == (
        expected,
        ChunkContentQuality.TITLE_ONLY,
    )


def test_duplicate_headline_uses_summary() -> None:
    assert compose_embedding_text(SINGLE_HEADLINE_TITLE, SINGLE_HEADLINE_BODY, "요약") == (
        SINGLE_HEADLINE_TITLE + "\n\n요약",
        ChunkContentQuality.SUMMARY,
    )


@pytest.mark.parametrize("length", [199, 200])
def test_full_quality_uses_cleaned_length(length: int) -> None:
    body = '<a href="https://example.com/' + "u" * 300 + '">' + "x" * length + "</a>"
    quality = ChunkContentQuality.FULL if length == 200 else ChunkContentQuality.TITLE_ONLY
    assert compose_embedding_text("제목", body, None) == (
        "제목\n\n" + "x" * length,
        quality,
    )


@pytest.mark.parametrize(
    ("body", "summary", "expected", "quality"),
    [
        ("x" * 199, None, "제목\n\n" + "x" * 199, ChunkContentQuality.TITLE_ONLY),
        ("x" * 200, "요약", "제목\n\n" + "x" * 200, ChunkContentQuality.FULL),
        (
            " 짧은 본문 ",
            " 요약 ",
            "제목\n\n짧은 본문\n\n요약",
            ChunkContentQuality.SUMMARY,
        ),
        (None, "요약", "제목\n\n요약", ChunkContentQuality.SUMMARY),
        (None, None, "제목", ChunkContentQuality.TITLE_ONLY),
        (" \n ", " \t ", "제목", ChunkContentQuality.TITLE_ONLY),
        (
            " " + "x" * 199 + " ",
            None,
            "제목\n\n" + "x" * 199,
            ChunkContentQuality.TITLE_ONLY,
        ),
    ],
)
def test_compose_embedding_text(
    body: str | None, summary: str | None, expected: str, quality: ChunkContentQuality
) -> None:
    assert compose_embedding_text(" 제목 ", body, summary) == (expected, quality)


@pytest.mark.parametrize(
    ("length", "lengths"),
    [
        (0, []),
        (10, [10]),
        (1500, [1500]),
        (1501, [1500, 151]),
        (2850, [1500, 1500]),
        (2851, [1500, 1500, 151]),
    ],
)
def test_chunk_boundaries(length: int, lengths: list[int]) -> None:
    text = "가" * length
    assert [len(chunk) for chunk in chunk_text(text)] == lengths


def test_chunk_overlap_preserves_text() -> None:
    text = "".join(chr(0xAC00 + index) for index in range(3000))
    chunks = chunk_text(text)
    assert chunks[0][-150:] == chunks[1][:150]
    assert chunks[1][-150:] == chunks[2][:150]
    assert chunks[0] + "".join(chunk[150:] for chunk in chunks[1:]) == text
    assert chunk_text("abcdef", size=3, overlap=0) == ["abc", "def"]


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (3, -1), (3, 3), (3, 4)])
def test_invalid_chunk_parameters(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size=size, overlap=overlap)


def test_embedding_hash() -> None:
    assert embedding_input_hash("뉴스") == hashlib.sha256("뉴스".encode()).hexdigest()
    assert embedding_input_hash("뉴스") != embedding_input_hash("뉴스 변경")

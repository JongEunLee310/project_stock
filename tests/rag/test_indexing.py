import hashlib

import pytest

from app.domains.rag.indexing import (
    chunk_text,
    compose_embedding_text,
    embedding_input_hash,
)
from app.domains.rag.types import ChunkContentQuality


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

import hashlib
import re
from html import unescape

from lxml import etree, html  # type: ignore[import-untyped]

from app.domains.rag.types import ChunkContentQuality

MIN_FULL_BODY_CHARS = 200
MIN_DISTINCT_BODY_CHARS = 30
CHUNK_SIZE_CHARS = 1500
CHUNK_OVERLAP_CHARS = 150


def clean_body_text(body: str | None) -> str:
    text = body or ""
    if re.search(r"</?[a-zA-Z][^>]*>", text):
        try:
            root = html.fromstring(text)
            for element in root.iter("li", "br"):
                element.text = "\n" + (element.text or "")
                if element.tag == "li":
                    element.tail = "\n" + (element.tail or "")
            text = root.text_content()
        except (etree.ParserError, ValueError):
            text = re.sub(r"</?li\b[^>]*>|<br\b[^>]*>", "\n", text, flags=re.I)
            text = re.sub(r"<[^>]*>", "", text)
            text = unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def compose_embedding_text(
    title: str, body: str | None, summary: str | None
) -> tuple[str, ChunkContentQuality]:
    title = title.strip()
    body = clean_body_text(body)
    headline = title.rsplit(" - ", 1)[0].strip()
    if headline and headline in body:
        remainder = body.replace(headline, "").strip()
        if len(remainder) < MIN_DISTINCT_BODY_CHARS:
            body = ""
    summary = (summary or "").strip()
    parts = [title, body]
    if len(body) >= MIN_FULL_BODY_CHARS:
        quality = ChunkContentQuality.FULL
    elif summary:
        parts.append(summary)
        quality = ChunkContentQuality.SUMMARY
    else:
        quality = ChunkContentQuality.TITLE_ONLY
    return "\n\n".join(part for part in parts if part), quality


def chunk_text(
    text: str, size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS
) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def embedding_input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

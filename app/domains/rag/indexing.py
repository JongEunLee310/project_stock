import hashlib

from app.domains.rag.types import ChunkContentQuality

MIN_FULL_BODY_CHARS = 200
CHUNK_SIZE_CHARS = 1500
CHUNK_OVERLAP_CHARS = 150


def compose_embedding_text(
    title: str, body: str | None, summary: str | None
) -> tuple[str, ChunkContentQuality]:
    body = (body or "").strip()
    summary = (summary or "").strip()
    parts = [title.strip(), body]
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

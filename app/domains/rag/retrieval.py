from dataclasses import replace

from app.adapters.vector.types import ChunkHit
from app.domains.rag.types import ChunkContentQuality

CANDIDATE_K = 20
MIN_SCORE = 0.3
MAX_CHUNKS_PER_SOURCE = 2
TITLE_ONLY_WEIGHT = 0.8
FINAL_EVIDENCE_K = 8


def postprocess_hits(hits: list[ChunkHit]) -> list[ChunkHit]:
    weighted = [
        replace(hit, score=hit.score * TITLE_ONLY_WEIGHT)
        if hit.content_quality == ChunkContentQuality.TITLE_ONLY
        else hit
        for hit in hits
        if hit.score >= MIN_SCORE
    ]
    weighted.sort(key=lambda hit: (-hit.score, hit.chunk_id))
    counts: dict[tuple[str, int], int] = {}
    selected: list[ChunkHit] = []
    for hit in weighted:
        key = (hit.source_type, hit.source_id)
        if counts.get(key, 0) >= MAX_CHUNKS_PER_SOURCE:
            continue
        counts[key] = counts.get(key, 0) + 1
        selected.append(hit)
        if len(selected) == FINAL_EVIDENCE_K:
            break
    return selected


def extract_source_name(title: str, source: str) -> str:
    headline, separator, tail = title.rpartition(" - ")
    return tail.strip() if separator and headline.strip() and tail.strip() else source

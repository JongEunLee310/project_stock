from enum import Enum

EMBEDDING_DIMENSIONS = 1024


class ChunkSourceType(str, Enum):
    NEWS = "NEWS"


class ChunkContentQuality(str, Enum):
    FULL = "FULL"
    SUMMARY = "SUMMARY"
    TITLE_ONLY = "TITLE_ONLY"

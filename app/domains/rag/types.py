from enum import Enum


class ChunkSourceType(str, Enum):
    NEWS = "NEWS"


class ChunkContentQuality(str, Enum):
    FULL = "FULL"
    SUMMARY = "SUMMARY"
    TITLE_ONLY = "TITLE_ONLY"

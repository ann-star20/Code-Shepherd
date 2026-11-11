"""M5-owned learning resources, separate from M6 ontology entities."""

import hashlib
import json
from dataclasses import dataclass
from typing import TypedDict

RETENTION_SECONDS = 28 * 86400


class VideoCandidate(TypedDict):
    video_id: str
    title: str
    url: str
    thumbnail: str | None
    channel_title: str | None


@dataclass(frozen=True)
class SearchTarget:
    concept_name: str
    query: str

    @property
    def key(self) -> str:
        value = json.dumps(
            [self.concept_name.casefold(), self.query], ensure_ascii=False
        )
        return hashlib.sha256(value.encode()).hexdigest()

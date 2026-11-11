"""Explicit offline demo data. Never writes fixtures into the live graph."""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

from app.graph_query import (
    CodeExampleMeta,
    ConceptGraphResponse,
    ConceptOverview,
    GraphOverviewResponse,
    MechanismGraphResponse,
    MechanismMeta,
)


def enabled() -> bool:
    return os.getenv("M5_MOCK_MODE", "false").lower() == "true"


def concepts() -> list[ConceptGraphResponse]:
    raw = json.loads(
        (Path(__file__).parent / "fixtures/concepts.json").read_text(encoding="utf-8")
    )
    return [
        ConceptGraphResponse(
            concept_name=c["concept_name"],
            concept_desc=c["description_ko"],
            cwe_id=c.get("cwe_id"),
            owasp_id=c.get("owasp_id"),
            severity=c.get("severity"),
            affected_components=c.get("affected_components", []),
            parent_domains=c["domains"],
            mechanisms=[
                MechanismMeta(
                    mechanism_name=m["mechanism_name"],
                    code_examples=[
                        CodeExampleMeta(
                            unq_id=m["mechanism_name"]
                            + "_"
                            + hashlib.md5(
                                " ".join(ce.get("code", "").split()).encode()
                            ).hexdigest()[:8],
                            lang=ce.get("lang"),
                            framework=ce.get("framework"),
                        )
                        for ce in m.get("code_examples", [])
                    ],
                )
                for m in c["mechanism"]
            ],
        )
        for c in raw
    ]


def overview() -> GraphOverviewResponse:
    return GraphOverviewResponse(
        concepts=[
            ConceptOverview(
                concept_name=c.concept_name,
                severity=c.severity,
                domain_names=c.parent_domains,
                mechanism_names=[m.mechanism_name for m in c.mechanisms],
            )
            for c in concepts()
        ]
    )


def concept(keyword: str) -> ConceptGraphResponse | None:
    return next(
        (c for c in concepts() if c.concept_name.casefold() == keyword.casefold()), None
    )


def mechanism(keyword: str) -> MechanismGraphResponse | None:
    for c in concepts():
        for m in c.mechanisms:
            if m.mechanism_name.casefold() == keyword.casefold():
                return MechanismGraphResponse(
                    concept_name=c.concept_name, **m.model_dump()
                )
    return None


def candidates(concept_name: str, query: str) -> list[dict]:
    # A real YouTube search page URI, not a fabricated playable video ID.
    return [
        {
            "video_id": "mock-" + hashlib.sha256(query.encode()).hexdigest()[:16],
            "title": f"[MOCK] {concept_name} — {query}",
            "url": "https://www.youtube.com/results?search_query="
            + quote(query, safe=""),
            "thumbnail": None,
            "channel_title": "Mock sample (not collected)",
            "is_mock": True,
        }
    ]

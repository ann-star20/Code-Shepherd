"""도메인 레지스트리 API (task1_multi_domain §4.3)."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.interfaces.api._deps import get_conn
from app.infrastructure.database.domain_repo import (
    get_registered_domains, classify_domains, suggest_similar_domains,
)

router = APIRouter(prefix="/api/domains", tags=["domains"])
staging_router = APIRouter(prefix="/api/staging", tags=["staging-domain"])


# ── 스키마 ─────────────────────────────────────────────────────────────────

class DomainEntry(BaseModel):
    name: str
    label_ko: str
    description: str | None
    color_hex: str
    is_active: bool


class NewDomainPayload(BaseModel):
    name: str
    label_ko: str
    description: str = ""
    color_hex: str = "#888780"

    @field_validator("name")
    @classmethod
    def name_lowercase(cls, v: str) -> str:
        v = v.lower().strip()
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("도메인 이름은 영문 소문자/숫자/하이픈만 허용")
        return v


class ResolveDomainRequest(BaseModel):
    action: Literal["map", "register", "reject"]
    target_domain: str | None = None    # action="map"
    new_domain: NewDomainPayload | None = None  # action="register"


# ── GET /api/domains ───────────────────────────────────────────────────────

@router.get("", response_model=list[DomainEntry])
async def list_domains(conn=Depends(get_conn)):
    rows = await conn.fetch(
        "SELECT name, label_ko, description, color_hex, is_active "
        "FROM domain_registry ORDER BY name"
    )
    return [dict(r) for r in rows]


# ── POST /api/domains ──────────────────────────────────────────────────────

@router.post("", status_code=201, response_model=DomainEntry)
async def register_domain(body: NewDomainPayload, conn=Depends(get_conn)):
    existing = await conn.fetchrow(
        "SELECT name FROM domain_registry WHERE name = $1", body.name
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"domain '{body.name}' already exists")

    row = await conn.fetchrow(
        """INSERT INTO domain_registry (name, label_ko, description, color_hex, created_by)
           VALUES ($1, $2, $3, $4, 'admin') RETURNING *""",
        body.name, body.label_ko, body.description, body.color_hex,
    )
    return dict(row)


# ── GET /api/staging/domain-pending ───────────────────────────────────────

@staging_router.get("/domain-pending")
async def list_domain_pending(conn=Depends(get_conn)):
    rows = await conn.fetch(
        "SELECT id, session_id, doc_id, concept_json, known_domains, unknown_domains, created_at "
        "FROM staging_concepts WHERE state = 'DOMAIN_PENDING' ORDER BY created_at DESC"
    )
    registered = await get_registered_domains(conn)
    result = []
    for r in rows:
        suggestions = {}
        for u in (r["unknown_domains"] or []):
            suggestions[u] = suggest_similar_domains(u, registered)
        result.append({**dict(r), "suggestions": suggestions})
    return result


# ── POST /api/staging/{id}/resolve-domain ─────────────────────────────────

@staging_router.post("/{staging_id}/resolve-domain")
async def resolve_domain(staging_id: str, body: ResolveDomainRequest, conn=Depends(get_conn)):
    row = await conn.fetchrow(
        "SELECT id, concept_json, unknown_domains, known_domains FROM staging_concepts "
        "WHERE id = $1 AND state = 'DOMAIN_PENDING'",
        staging_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="DOMAIN_PENDING staging record not found")

    if body.action == "reject":
        await conn.execute("DELETE FROM staging_concepts WHERE id = $1", staging_id)
        return {"result": "rejected", "id": staging_id}

    if body.action == "map":
        if not body.target_domain:
            raise HTTPException(status_code=422, detail="target_domain required for action=map")
        registered = await get_registered_domains(conn)
        if body.target_domain not in registered:
            raise HTTPException(status_code=400, detail=f"'{body.target_domain}' is not a registered domain")
        # unknown_domains를 target_domain으로 치환 후 APPROVED로 전이
        new_domains = (row["known_domains"] or []) + [body.target_domain]
        concept = dict(row["concept_json"])
        concept["domains"] = new_domains
        await conn.execute(
            "UPDATE staging_concepts SET state='APPROVED', concept_json=$1, "
            "known_domains=$2, unknown_domains='{}' WHERE id=$3",
            concept, new_domains, staging_id,
        )
        return {"result": "mapped", "domains": new_domains}

    if body.action == "register":
        if not body.new_domain:
            raise HTTPException(status_code=422, detail="new_domain required for action=register")
        nd = body.new_domain
        await conn.execute(
            "INSERT INTO domain_registry (name, label_ko, description, color_hex, created_by) "
            "VALUES ($1, $2, $3, $4, 'admin') ON CONFLICT (name) DO NOTHING",
            nd.name, nd.label_ko, nd.description, nd.color_hex,
        )
        new_domains = (row["known_domains"] or []) + [nd.name]
        concept = dict(row["concept_json"])
        concept["domains"] = new_domains
        await conn.execute(
            "UPDATE staging_concepts SET state='APPROVED', concept_json=$1, "
            "known_domains=$2, unknown_domains='{}' WHERE id=$3",
            concept, new_domains, staging_id,
        )
        return {"result": "registered", "domain": nd.name, "domains": new_domains}

"""ingestion — corpus/*.md → §단위 청크 → 임베딩(src/embeddings) → Chroma

원커맨드 재인덱싱 (핫스왑 시연의 핵심): make reindex → 컬렉션 드롭 후 전체 재구축.
청크 메타데이터는 contracts.Chunk 필드와 1:1 (rule_id, section, severity, source_path).
임베딩: src/embeddings.embed_texts — provider(.env)·캐시·차원검증 단일 관리.
컬렉션 metadata 에 임베딩 provider/model/dims 기록 → retrieve 가 불일치 검출.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import chromadb
from dotenv import load_dotenv

from src import config
from src.config import CHROMA_COLLECTION, CHROMA_DIR, CORPUS_DIR
from src.embeddings import _active_model, embed_texts

load_dotenv()


class _Chunk(NamedTuple):
    rule_id: str
    section: str
    text: str
    severity: str
    source_path: str


def _parse_corpus_file(path: Path) -> list[_Chunk]:
    """마크다운 파일 → §단위 청크 목록."""
    raw = path.read_text(encoding="utf-8")

    # rule_id: 첫 줄 # [CONV-API-001] 형태에서 추출
    first_line = raw.split("\n")[0]
    id_match = re.search(r"\[([A-Z]+-[A-Z]+-\d+)\]", first_line)
    if not id_match:
        return []
    rule_id = id_match.group(1)

    # severity: "- severity: Major|Minor|Info"
    sev_match = re.search(r"-\s*severity:\s*(Major|Minor|Info)", raw)
    severity = sev_match.group(1) if sev_match else "Info"

    source_path = f"corpus/{path.name}"

    # §단위 분할: "## §N" 헤딩 앞에서 split
    parts = re.split(r"(?=^## §)", raw, flags=re.MULTILINE)

    chunks: list[_Chunk] = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        sec_match = re.match(r"## (§\d+)", part)
        section = sec_match.group(1) if sec_match else "§0"

        chunks.append(_Chunk(
            rule_id=rule_id,
            section=section,
            text=part,
            severity=severity,
            source_path=source_path,
        ))

    return chunks


def reindex() -> None:
    """corpus/*.md → Chroma 전체 재인덱싱 (핫스왑 원커맨드)."""
    corpus_dir = Path(CORPUS_DIR)
    md_files = sorted(f for f in corpus_dir.glob("*.md") if f.name != "README.md")

    if not md_files:
        print(f"[ingestion] corpus 파일 없음: {corpus_dir.resolve()}")
        return

    # 1. 파싱
    all_chunks: list[_Chunk] = []
    for f in md_files:
        parsed = _parse_corpus_file(f)
        print(f"[ingestion] {f.name} → {len(parsed)}청크")
        all_chunks.extend(parsed)
    print(f"[ingestion] 총 {len(all_chunks)}개 청크 파싱 완료")

    # 2. 임베딩 (캐시 우선 — provider 는 .env EMBEDDING_PROVIDER)
    texts = [c.text for c in all_chunks]
    embeddings = embed_texts(texts)
    print(f"[ingestion] 임베딩 {len(embeddings)}개 완료 "
          f"(provider={config.EMBEDDING_PROVIDER}, dims={len(embeddings[0])})")

    # 3. Chroma 재구축: 기존 컬렉션 드롭 → 재생성
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        chroma.delete_collection(CHROMA_COLLECTION)
        print(f"[ingestion] 기존 컬렉션 '{CHROMA_COLLECTION}' 삭제")
    except Exception:
        pass

    # metadata 에 임베딩 출처 기록 — retrieve 가 질의 모델과 대조해 오염 차단
    collection = chroma.create_collection(
        name=CHROMA_COLLECTION,
        metadata={
            "embedding_provider": config.EMBEDDING_PROVIDER,
            "embedding_model": _active_model(),
            "dims": len(embeddings[0]),
        },
    )

    ids = [f"{c.rule_id}_{c.section}_{i}" for i, c in enumerate(all_chunks)]
    metadatas = [
        {
            "rule_id": c.rule_id,
            "section": c.section,
            "severity": c.severity,
            "source_path": c.source_path,
        }
        for c in all_chunks
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    print(
        f"[ingestion] Chroma '{CHROMA_COLLECTION}' "
        f"인덱싱 완료: {len(all_chunks)}개 청크 ({CHROMA_DIR})"
    )


if __name__ == "__main__":
    reindex()

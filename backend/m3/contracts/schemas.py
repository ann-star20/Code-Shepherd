"""계약 스키마 — Dev3 코드리뷰 에이전트 (게이트 2: 승인 후 수정 금지).

이 파일이 파이프라인 전체의 단일 진실 공급원(single source of truth)이다.
- 외부 입출력(ReviewInput/ReviewOutput)은 팀 합의 인터페이스(브리프 §1.2)와 1:1.
- ReviewState 는 LangGraph State. 노드별 입출력 필드는 브리프 §3 표와 1:1.
- 검증 가능성 원칙: Finding.rule_quote 는 코퍼스 청크에, evidence_lines 는 diff 에
  string-match 되어야 한다 (eval 하네스가 자동 검증 — 환각률 지표).

변경 절차: [결정요청] 제출 → 정현 명시 승인 → SCHEMA_VERSION 올리고 수정.
"""
from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"  # 동결 — 게이트 2 승인 (정현, D1 2026-06-12). 변경은 결정요청+명시 승인 필수.

Severity = Literal["Major", "Minor", "Info"]
Verdict = Literal["violation", "no_violation"]
Route = Literal["proceed", "requery", "gap_report"]


# ── 외부 입출력 (팀 공유 인터페이스 계약, 브리프 §1.2 — MVP 중 변경 없음) ──

class ReviewInput(BaseModel):
    """파이프라인 입력. 어댑터(webhook/streamlit/harness)가 이 형태로 만들어 넣는다."""
    diff: str                                  # unified diff 전문
    file_paths: list[str]                      # 변경 파일 상대경로 목록
    repo_meta: dict = Field(default_factory=dict)
    # repo_meta 권장 키(강제 아님): repo, pr_number, head_sha, title, author


class ReviewOutput(BaseModel):
    """파이프라인 최종 출력. 어댑터가 이걸 받아 코멘트 POST / 화면 표시한다."""
    findings: list["Finding"]
    comment_md: str                            # 출처(rule_id·§·파일링크) 인용 포함 마크다운
    gap_report: "GapReport | None" = None      # 지침공백일 때만 채움


# ── 내부 데이터 단위 ─────────────────────────────────────────────────────

class Concept(BaseModel):
    """① extract_concepts 산출 단위."""
    name: str                                  # 예: "외부 API 호출"
    synonyms: list[str]                        # 기본 3개 (src/config.py SYNONYMS_PER_CONCEPT)


class Chunk(BaseModel):
    """② retrieve 산출 단위 — 코퍼스 §단위 청크."""
    rule_id: str                               # 예: "CONV-API-001"
    section: str                               # 예: "§2"
    text: str                                  # 청크 원문 (rule_quote 검증 기준)
    severity: Severity
    score: float                               # 유사도 (높을수록 관련)
    source_path: str                           # 예: "corpus/external_api.md" — 코멘트 출처 링크용


class Finding(BaseModel):
    """④ judge 산출 단위 — 규칙 1건에 대한 판정."""
    rule_id: str
    verdict: Verdict
    severity: Severity                         # 인용 규칙의 severity 를 그대로
    rule_quote: str                            # 코퍼스 원문 인용 — 해당 Chunk.text 에 부분일치 필수
    file: str                                  # 위반 파일 상대경로 ("" 허용: 파일 특정 불가 시)
    evidence_lines: list[str]                  # diff 에서 그대로 옮긴 코드 줄 — diff 에 부분일치 필수
    reasoning: str                             # 조항-코드 대조 요약 (1~3문장)
    fp_note: str | None = None                 # 오탐 점검 메모 (예외조항 검토 결과 등)


class GapReport(BaseModel):
    """⑤ compose_comment(gap 경로) 산출 — 지침공백 정직 보고."""
    pattern_summary: str                       # 지침이 없는 PR 패턴 요약
    queries_tried: list[str]                   # 시도한 검색 질의 (재질의 포함)
    nearest_rule_ids: list[str] = Field(default_factory=list)  # 근접했지만 미달한 규칙
    proposed_rule_md: str                      # 신규 지침 제안 초안 (마크다운)


# ── LangGraph State (노드 I/O — 브리프 §3 표와 1:1) ──────────────────────

class ReviewState(TypedDict, total=False):
    # 입력 (ReviewInput 과 동일 키)
    diff: str
    file_paths: list[str]
    repo_meta: dict
    # ⓪ assemble_input
    pr_context: str            # diff + 변경 파일 전문(또는 함수 주변 컨텍스트)
    # ① extract_concepts
    concepts: list[Concept]
    queries: list[str]
    # ② retrieve (top-k 5/query, dedup)
    chunks: list[Chunk]
    # ③ check_sufficiency
    route: Route               # proceed / requery / gap_report
    requery_count: int         # 전 파이프라인 합산 최대 1 (브리프 §3)
    # ④ judge
    findings: list[Finding]
    # ⑤ compose_comment
    comment_md: str
    gap_report: GapReport | None


# ── 골든셋 라벨 (golden/pr_NNN/label.yaml — 게이트 1) ────────────────────

class ExpectedFinding(BaseModel):
    rule_id: str
    verdict: Verdict


class GoldenLabel(BaseModel):
    """label.yaml 스키마.

    yaml 표기:
      expected: [{rule_id: CONV-API-001, verdict: violation}]   # 위반
      expected: []                                              # 정상 (지적 없음)
      expected: gap                                             # 지침공백 보고 기대
    """
    expected: list[ExpectedFinding] | Literal["gap"]

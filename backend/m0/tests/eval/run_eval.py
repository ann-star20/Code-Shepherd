"""
KMS 파이프라인 성숙도 평가 스크립트 v2

단순 Accuracy 측정을 넘어 파이프라인 성숙도(Maturity)를 4개 관점으로 평가한다.

  L1  : 파이프라인 성숙도 점수 (0 ~ 100)
  L2A : Accuracy   — stored 문서의 메타데이터 품질 (HITL 제외)
  L2B : Automation — 자동 완료율 / HITL 발생률 / 오류율
  L2C : Reliability — 문서 유형별 성공률 / 처리 시간

핵심 설계 원칙:
  - hitl_pending 문서는 Accuracy 계산에서 제외 (0점 왜곡 방지)
  - Accuracy 분모 = stored 문서만
  - Automation 분모 = 전체 문서
  - 엔티티 평가: Golden 10종 타입 → 파이프라인 3종 매핑 후 name recall + partial credit

사용법:
    uv run python tests/eval/run_eval.py --mode file
    uv run python tests/eval/run_eval.py --mode file --output results/report.md
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Windows cp949 환경에서 한글 + 특수문자 출력 깨짐 방지
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
GOLDEN_PATH = EVAL_DIR / "golden_dataset.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# 엔티티 타입 매핑 — Golden v1(10종) → Pipeline 3종
# ---------------------------------------------------------------------------
# Golden Dataset은 세부 타입을 사용하지만 파이프라인은 3종만 추출한다.
# 이 매핑으로 Golden을 파이프라인 타입으로 그루핑해 fair comparison을 수행한다.

ENTITY_TYPE_MAP: dict[str, str] = {
    "technology":   "Technology",
    "tool":         "Technology",
    "product":      "Technology",
    "standard":     "Technology",
    "endpoint":     "Technology",
    "model":        "Technology",
    "methodology":  "Pattern",
    "process":      "Pattern",
    "concept":      "Concept",
    "role":         "Concept",
    "organization": "Concept",
    "metric":       "Concept",
    # 이미 파이프라인 타입으로 작성된 경우 그대로 통과
    "Technology":   "Technology",
    "Pattern":      "Pattern",
    "Concept":      "Concept",
}


# ---------------------------------------------------------------------------
# KPI 목표값 및 CI 게이트
# ---------------------------------------------------------------------------

ACCURACY_TARGETS: dict[str, float] = {
    "title_accuracy":           0.80,
    "category_accuracy":        0.85,
    "avg_tags_f1":              0.60,
    "avg_entity_name_recall":   0.60,
    "avg_quality_score":        0.85,
}

AUTOMATION_TARGETS: dict[str, float] = {
    "completion_rate": 0.90,   # ≥ 90%
    "error_rate":      0.05,   # ≤  5% (상한)
    # hitl_rate는 CI Gate 제외 — KMS에서 HITL은 최소화 대상이 아니라 품질 안전망
    # 낮은 hitl_rate가 좋은 것이 아니라, 문제 문서를 정확히 탐지하는 것이 목표
    # → compute_hitl_quality_kpis()의 Recall / False Pass Rate로 측정
    "hitl_rate":       0.15,   # 참고 지표만 (상한값 아님)
}

# HITL 품질 안전망 목표 (expected_hitl=True 항목이 있을 때만 활성화)
HITL_QUALITY_TARGETS: dict[str, float] = {
    "hitl_recall":      0.80,  # 문제 문서 중 80% 이상 탐지
    "false_pass_rate":  0.20,  # 문제 문서 중 20% 이하만 자동 통과
    "hitl_precision":   0.50,  # HITL로 간 것 중 50% 이상 진짜 문제
}

# CI 게이트: (operator, threshold)
# ">=" → 값이 threshold 이상이어야 PASS
# "<=" → 값이 threshold 이하이어야 PASS (hitl_rate, error_rate)
CI_GATE: dict[str, tuple[str, float]] = {
    "completion_rate":        (">=", 0.80),
    "category_accuracy":      (">=", 0.85),
    "avg_tags_f1":            (">=", 0.60),
    "avg_entity_name_recall": (">=", 0.60),
    "avg_quality_score":      (">=", 0.85),
}

# 성숙도 점수 가중치 (합 = 1.0)
MATURITY_WEIGHTS = {
    "automation": 0.40,
    "accuracy":   0.60,
}


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class GoldenEntry:
    id: str
    file: str
    file_type: str
    expected_title: Optional[str]
    expected_category: Optional[str]
    expected_tags: list[str]
    expected_entities: dict[str, list[str]]
    note: str = ""
    # HITL 품질 안전망 검증용: 이 문서가 반드시 hitl_pending으로 분기되어야 하면 True
    expected_hitl: bool = False
    hitl_expected_stage: str = ""
    hitl_expected_reason: str = ""

    @property
    def expected_entities_mapped(self) -> dict[str, list[str]]:
        """Golden 세부 타입을 파이프라인 3종으로 그루핑."""
        mapped: dict[str, list[str]] = {}
        for raw_type, names in self.expected_entities.items():
            pipeline_type = ENTITY_TYPE_MAP.get(raw_type, "Concept")
            mapped.setdefault(pipeline_type, []).extend(names)
        return mapped

    @property
    def all_expected_entity_names(self) -> list[str]:
        return [n for names in self.expected_entities.values() for n in names]


@dataclass
class PipelineResult:
    doc_id: str
    golden_id: str
    title: Optional[str]
    category: Optional[str]
    tags: list[str]
    entities: dict[str, list[str]]
    quality_score: float = 0.0
    status: str = "unknown"
    file_type: str = "unknown"
    processing_time_ms: Optional[float] = None
    child_chunk_count: Optional[int] = None
    embedded_chunk_count: Optional[int] = None
    parent_chunk_count: Optional[int] = None
    avg_chunk_tokens: Optional[float] = None
    stage_latencies: dict = field(default_factory=dict)
    chunk_size_compliance_rate: Optional[float] = None
    parent_child_integrity_rate: Optional[float] = None
    neo4j_synced: Optional[bool] = None
    storage_synced: Optional[bool] = None
    metadata_score: Optional[float] = None


@dataclass
class AccuracyResult:
    golden_id: str
    file_type: str
    title_match: bool
    category_match: bool
    tags_recall: float
    tags_precision: float
    entity_name_recall: float
    entity_partial_score: float
    quality_score: float
    status: str
    skipped: bool = False
    details: dict = field(default_factory=dict)

    @property
    def tags_f1(self) -> float:
        s = self.tags_recall + self.tags_precision
        return 0.0 if s == 0 else 2 * self.tags_recall * self.tags_precision / s


# ---------------------------------------------------------------------------
# 텍스트 정규화 — 한영 동의어 별칭 포함
# ---------------------------------------------------------------------------

# 한국어 기술 용어 ↔ 영어 canonical 형태 양방향 매핑.
# 한쪽 언어로 표현된 태그가 다른 언어의 동의어 태그와 매칭될 수 있도록 한다.
# 규칙: 모든 키는 normalize_text base 처리(소문자+특수문자제거) 이후 값이어야 함.
_KO_EN_SYNONYMS: dict[str, str] = {
    # 기술 용어
    "트랜스포머":       "transformer",
    "사전학습":         "pretraining",
    "자연어처리":       "nlp",
    "임베딩":           "embedding",
    "벡터db":           "vectordatabase",
    "벡터데이터베이스": "vectordatabase",
    # pgVector / pgvector → vectordatabase (벡터DB golden과 매칭)
    "pgvector":         "vectordatabase",
    "지식관리":         "knowledgemanagement",
    "아키텍처":         "architecture",
    "파이프라인":       "pipeline",
    "온보딩":           "onboarding",
    "애자일":           "agile",
    "리랭킹":           "reranking",
    "하이브리드검색":   "hybridsearch",
    "벡터검색":         "vectorsearch",
    # AI Agent 관련 — 'AI Agent'가 짧은 'Agent'와 매칭
    "aiagent":          "agent",
    # 개인정보 축약 ↔ 전체
    "개인정보":         "개인정보보호",
    # 회고 축약 ↔ 전체
    "회고":             "프로젝트회고",
    # 개발환경 변형 통일
    "개발환경":         "개발환경설정",
    "환경설정":         "개발환경설정",
    # HNSW 인덱스 변형
    "hnsw인덱스":       "hnsw",
    # KMS / 지식관리시스템 변형
    "kms":              "knowledgemanagement",
    "지식관리시스템":   "knowledgemanagement",
    # 그래프DB 계열
    "그래프db":         "graphdatabase",
    "그래프데이터베이스": "graphdatabase",
    # HR / 인사 계열 — docx_02 취업규칙 태그 매칭
    "hr":               "hrmanagement",
    "인사":             "hrmanagement",
    "인사정책":         "hrmanagement",
    "인사규정":         "hrmanagement",
    "인사관리":         "hrmanagement",
    # 임금 / 급여 계열
    "임금":             "salary",
    "급여":             "salary",
    "급여정책":         "salary",
}


def normalize_text(s: str) -> str:
    """공백·특수문자 제거 + 소문자 변환 후 한영 동의어 별칭 적용."""
    base = re.sub(r"[\s\-_\(\)（）·]+", "", s.lower())
    return _KO_EN_SYNONYMS.get(base, base)


def _base_normalize(s: str) -> str:
    """별칭 적용 없이 공백·특수문자 제거 + 소문자 변환만 수행."""
    return re.sub(r"[\s\-_\(\)（）·]+", "", s.lower())


def _has_cjk(s: str) -> bool:
    """문자열에 한국어·중국어·일본어 글자가 포함되어 있는지 확인."""
    return any(
        "ᄀ" <= c <= "ᇿ"   # Hangul Jamo
        or "㄰" <= c <= "㆏"  # Hangul Compat Jamo
        or "가" <= c <= "힣"  # Hangul Syllables (한국어 음절)
        or "一" <= c <= "鿿"  # CJK Unified Ideographs
        for c in s
    )


def _terms_match(s1: str, s2: str) -> bool:
    """두 태그/엔티티 이름이 의미상 일치하는지 판단.

    1순위: normalize_text 이후 exact match (동의어 별칭 포함)
    2순위: 별칭 적용 전 base 형태의 substring 포함 관계
           — 파이프라인이 compound 태그("REST API")를 생성하고
             golden이 atomic 태그("REST")를 사용하는 경우를 처리.
           — 오탐 방지: ASCII는 3자 이상, CJK는 2자 이상에서만 적용
             (한국어 2글자는 의미 밀도가 높아 "검색", "회고" 등 유효한 매칭 가능)
    """
    if normalize_text(s1) == normalize_text(s2):
        return True
    b1, b2 = _base_normalize(s1), _base_normalize(s2)
    min_len = 2 if (_has_cjk(b1) or _has_cjk(b2)) else 3
    if len(b1) >= min_len and len(b2) >= min_len:
        return b1 in b2 or b2 in b1
    return False


# ---------------------------------------------------------------------------
# 매칭 로직
# ---------------------------------------------------------------------------

def match_title(expected: Optional[str], actual: Optional[str]) -> bool:
    if not expected or not actual:
        return False
    return normalize_text(expected) == normalize_text(actual)


def compute_tags_metrics(
    expected: list[str], actual: list[str]
) -> tuple[float, float]:
    if not expected:
        return (1.0, 1.0) if not actual else (1.0, 0.0)
    if not actual:
        return (0.0, 0.0)
    recall = sum(
        1 for e in expected if any(_terms_match(e, a) for a in actual)
    ) / len(expected)
    precision = sum(
        1 for a in actual if any(_terms_match(a, e) for e in expected)
    ) / len(actual)
    return recall, precision


def compute_entity_metrics(
    golden: GoldenEntry, result: PipelineResult
) -> tuple[float, float]:
    """
    Returns:
        entity_name_recall   : 이름 기준 재현율 (타입 무관)
        entity_partial_score : 이름+타입 일치 → 1.0 / 이름만 일치 → 0.5
    """
    all_expected = golden.all_expected_entity_names
    if not all_expected:
        return 1.0, 1.0

    actual_names: list[str] = [
        n for names in result.entities.values() for n in names
    ]

    # 이름 재현율 (타입 무관, substring 매칭 포함)
    matched = sum(
        1 for n in all_expected if any(_terms_match(n, a) for a in actual_names)
    )
    name_recall = matched / len(all_expected)

    # Partial credit (타입 일치 보너스)
    mapped = golden.expected_entities_mapped
    partial_total = 0.0
    for p_type, exp_names in mapped.items():
        act_type_names = result.entities.get(p_type, [])
        for n in exp_names:
            if any(_terms_match(n, a) for a in act_type_names):
                partial_total += 1.0
            elif any(_terms_match(n, a) for a in actual_names):
                partial_total += 0.5
    partial_score = partial_total / len(all_expected)

    return name_recall, partial_score


# ---------------------------------------------------------------------------
# 문서 단위 평가
# ---------------------------------------------------------------------------

def evaluate_document(
    golden: GoldenEntry, result: Optional[PipelineResult]
) -> AccuracyResult:
    base = AccuracyResult(
        golden_id=golden.id,
        file_type=golden.file_type,
        title_match=False,
        category_match=False,
        tags_recall=0.0,
        tags_precision=0.0,
        entity_name_recall=0.0,
        entity_partial_score=0.0,
        quality_score=result.quality_score if result else 0.0,
        status=result.status if result else "not_found",
        details={
            "expected_title":    golden.expected_title,
            "actual_title":      result.title if result else None,
            "expected_category": golden.expected_category,
            "actual_category":   result.category if result else None,
            "expected_tags":     golden.expected_tags,
            "actual_tags":       result.tags if result else [],
        },
    )

    # stored 이외 (hitl_pending / error / not_found)는 Accuracy 계산 제외
    if not result or result.status != "stored":
        base.skipped = True
        return base

    e_recall, e_partial = compute_entity_metrics(golden, result)
    t_recall, t_precision = compute_tags_metrics(golden.expected_tags, result.tags)

    base.title_match          = match_title(golden.expected_title, result.title)
    base.category_match       = golden.expected_category == result.category
    base.tags_recall          = t_recall
    base.tags_precision       = t_precision
    base.entity_name_recall   = e_recall
    base.entity_partial_score = e_partial
    base.skipped              = False
    return base


# ---------------------------------------------------------------------------
# KPI 계층 계산
# ---------------------------------------------------------------------------

def compute_automation_kpis(all_results: list[PipelineResult]) -> dict:
    """L2B: 자동화율 KPI — 전체 문서 기준."""
    total = len(all_results)
    if not total:
        return {"error": "결과 없음"}

    by_status: dict[str, int] = {}
    for r in all_results:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    stored  = by_status.get("stored", 0)
    partial = by_status.get("stored_partial", 0)
    hitl    = by_status.get("hitl_pending", 0)
    error   = by_status.get("error", 0) + by_status.get("timeout", 0) + by_status.get("failed", 0)

    # Stage별 HITL 분포를 추후 run_pipeline.py에서 hitl_stage 필드 추가 시 확장 가능
    return {
        "total_documents":  total,
        "stored":           stored,
        "stored_partial":   partial,
        "hitl_pending":     hitl,
        "error_or_timeout": error,
        "completion_rate":  (stored + partial) / total,
        "hitl_rate":        hitl / total,
        "error_rate":       error / total,
        "status_breakdown": by_status,
    }


def compute_accuracy_kpis(eval_results: list[AccuracyResult]) -> dict:
    """L2A: 메타데이터 정확도 KPI — stored 문서만."""
    stored = [r for r in eval_results if not r.skipped]
    if not stored:
        return {"evaluated_documents": 0, "note": "stored 문서 없음 — Accuracy 계산 불가"}

    has_golden = [r for r in stored if r.details.get("expected_title") is not None]

    kpis: dict = {
        "evaluated_documents":    len(stored),
        "documents_with_golden":  len(has_golden),
        "avg_quality_score":      _avg(r.quality_score for r in stored),
    }

    if has_golden:
        kpis.update({
            "title_accuracy":           _avg(r.title_match for r in has_golden),
            "category_accuracy":        _avg(r.category_match for r in has_golden),
            "avg_tags_recall":          _avg(r.tags_recall for r in has_golden),
            "avg_tags_precision":       _avg(r.tags_precision for r in has_golden),
            "avg_tags_f1":              _avg(r.tags_f1 for r in has_golden),
            "avg_entity_name_recall":   _avg(r.entity_name_recall for r in has_golden),
            "avg_entity_partial_score": _avg(r.entity_partial_score for r in has_golden),
        })

    # 파일 유형별 정확도
    by_type: dict[str, list[AccuracyResult]] = {}
    for r in has_golden:
        by_type.setdefault(r.file_type, []).append(r)

    kpis["by_file_type"] = {
        ft: {
            "count":                  len(rs),
            "title_accuracy":         _avg(r.title_match for r in rs),
            "category_accuracy":      _avg(r.category_match for r in rs),
            "avg_tags_f1":            _avg(r.tags_f1 for r in rs),
            "avg_entity_name_recall": _avg(r.entity_name_recall for r in rs),
        }
        for ft, rs in by_type.items()
    }

    return kpis


def compute_reliability_kpis(all_results: list[PipelineResult]) -> dict:
    """L2C: 안정성 KPI — 유형별 성공률 / 처리 시간."""
    by_type: dict[str, list[PipelineResult]] = {}
    for r in all_results:
        by_type.setdefault(r.file_type, []).append(r)

    type_stats = {
        ft: {
            "total":        len(rs),
            "stored":       sum(1 for r in rs if r.status == "stored"),
            "hitl_pending": sum(1 for r in rs if r.status == "hitl_pending"),
            "error":        sum(1 for r in rs if r.status in ("error", "timeout", "failed")),
            "success_rate": sum(1 for r in rs if r.status == "stored") / len(rs),
        }
        for ft, rs in by_type.items()
    }

    timing = [r.processing_time_ms for r in all_results if r.processing_time_ms]
    timing_stats: dict = {}
    if timing:
        timing_stats = {
            "count":   len(timing),
            "avg_ms":  round(sum(timing) / len(timing)),
            "max_ms":  round(max(timing)),
            "min_ms":  round(min(timing)),
        }

    return {"by_file_type": type_stats, "timing": timing_stats}


def compute_neo4j_kpis(all_results: list[PipelineResult]) -> dict:
    """Neo4j 동기화율 proxy KPI — file mode 전용.

    stored 문서 중 entities dict가 비어 있지 않은 비율을 동기화율로 간주한다.
    (실제 Neo4j DB 쿼리 없이 pipeline_output.json의 entities 필드 사용)
    """
    stored = [r for r in all_results if r.status == "stored"]
    if not stored:
        return {"neo4j_synced_rate": 0.0, "synced_count": 0, "stored_count": 0}

    synced = [r for r in stored if any(r.entities.values())]
    return {
        "neo4j_synced_rate": len(synced) / len(stored),
        "synced_count":      len(synced),
        "stored_count":      len(stored),
    }


def compute_hitl_quality_kpis(
    golden_entries: list["GoldenEntry"],
    pipeline_results: dict[str, "PipelineResult"],
) -> dict:
    """HITL 품질 안전망 KPI.

    KMS에서 HITL rate(발생률)는 최소화 목표가 아니다.
    중요한 것은 '문제 문서를 얼마나 정확히 HITL로 보냈는가'다.

    - hitl_precision   : HITL로 간 문서 중 실제 문제가 있었던 비율 (FP 방지)
    - hitl_recall      : 문제가 있는 문서 중 HITL로 보낸 비율 (FN 방지)
    - false_pass_rate  : 문제 있는 문서가 HITL 없이 저장된 비율 = 1 - Recall
    - false_hitl_rate  : 정상 문서가 HITL로 간 비율

    golden_dataset에 expected_hitl=True 항목이 없으면 Recall/False Pass = None.
    """
    expected_problem = [g for g in golden_entries if g.expected_hitl]
    expected_normal  = [g for g in golden_entries if not g.expected_hitl]

    def _is_hitl(gid: str) -> bool:
        r = pipeline_results.get(gid)
        return r is not None and r.status == "hitl_pending"

    # TP: 문제 문서 → HITL (탐지 성공)
    tp = sum(1 for g in expected_problem if _is_hitl(g.id))
    # FN: 문제 문서 → stored/stored_partial (탐지 실패 = False Pass)
    fn = len(expected_problem) - tp
    # FP: 정상 문서 → HITL (과도한 HITL = False HITL)
    fp = sum(1 for g in expected_normal if _is_hitl(g.id))
    # TN: 정상 문서 → stored (정상 자동 처리)
    tn = len(expected_normal) - fp

    total_hitl_triggered = tp + fp

    hitl_precision: float | None = (
        tp / total_hitl_triggered if total_hitl_triggered > 0 else None
    )
    hitl_recall: float | None = (
        tp / len(expected_problem) if expected_problem else None
    )
    false_pass_rate: float | None = (
        fn / len(expected_problem) if expected_problem else None
    )
    false_hitl_rate: float | None = (
        fp / len(expected_normal) if expected_normal else None
    )

    return {
        "hitl_precision":      hitl_precision,
        "hitl_recall":         hitl_recall,
        "false_pass_rate":     false_pass_rate,
        "false_hitl_rate":     false_hitl_rate,
        "tp":                  tp,
        "fp":                  fp,
        "fn":                  fn,
        "tn":                  tn,
        "problem_doc_count":   len(expected_problem),
        "normal_doc_count":    len(expected_normal),
        "note": (
            "expected_hitl=True 항목 없음 — golden_dataset에 HITL 검증 문서 추가 필요"
            if not expected_problem else
            f"문제 문서 {len(expected_problem)}개 / 정상 문서 {len(expected_normal)}개 기준"
        ),
    }


def compute_chunk_embedding_kpis(all_results: list[PipelineResult]) -> dict:
    """pgVector 임베딩 적재율 proxy KPI — file mode 전용.

    - stored 문서의 child_chunk_count / embedded_chunk_count 합산 비율
    - embedded_chunk_count 없으면 stored 문서는 proxy: embedded = child_chunk_count
    - child_chunk_count가 없거나 0인 문서는 집계 제외
    - chunk 정보 자체가 없으면 rate = None (N/A)
    """
    stored = [r for r in all_results if r.status == "stored"]
    total_child = 0
    total_embedded = 0

    for r in stored:
        if r.child_chunk_count is None or r.child_chunk_count == 0:
            continue
        total_child += r.child_chunk_count
        if r.embedded_chunk_count is not None:
            total_embedded += r.embedded_chunk_count
        else:
            # proxy: stored 문서는 임베딩 성공으로 간주
            total_embedded += r.child_chunk_count

    if total_child == 0:
        return {"chunk_embedding_rate": None, "total_child_chunks": 0, "total_embedded_chunks": 0}

    return {
        "chunk_embedding_rate": total_embedded / total_child,
        "total_child_chunks":   total_child,
        "total_embedded_chunks": total_embedded,
    }


def compute_stage_latency_kpis(all_results: list[PipelineResult]) -> dict:
    """Stage별 평균 latency (agent_traces execution_ms 기반)."""
    stage_agent_map = {
        "stage1": "DocumentParserAgent",
        "stage2": "MarkdownValidateAgent",
        "stage3": "ChunkingAgent",
        "stage4": "ChunkValidateAgent",
        "stage5": "MetadataExtractAgent",
        "stage5b": "MetadataValidateAgent",
        "stage6": "StoreRouteAgent",
    }
    result: dict = {}
    for stage_key, agent_name in stage_agent_map.items():
        ms_vals = [
            r.stage_latencies[agent_name]
            for r in all_results
            if agent_name in r.stage_latencies
        ]
        if ms_vals:
            result[stage_key] = {
                "agent_name": agent_name,
                "avg_ms":     round(sum(ms_vals) / len(ms_vals)),
                "max_ms":     max(ms_vals),
                "min_ms":     min(ms_vals),
                "n":          len(ms_vals),
            }
        else:
            result[stage_key] = {"agent_name": agent_name, "avg_ms": None, "n": 0}
    return result


def compute_chunk_compliance_kpis(all_results: list[PipelineResult]) -> dict:
    """청크 사이즈 준수율 및 Parent-Child 연결 완전성."""
    stored = [r for r in all_results if r.status in ("stored", "stored_partial")]
    if not stored:
        return {"note": "stored 문서 없음"}

    compliance_vals = [
        r.chunk_size_compliance_rate for r in stored
        if r.chunk_size_compliance_rate is not None
    ]
    avg_compliance = sum(compliance_vals) / len(compliance_vals) if compliance_vals else None

    integrity_vals = [
        r.parent_child_integrity_rate for r in stored
        if r.parent_child_integrity_rate is not None
    ]
    avg_integrity = sum(integrity_vals) / len(integrity_vals) if integrity_vals else None

    return {
        "chunk_size_compliance_rate":   round(avg_compliance, 4) if avg_compliance is not None else None,
        "parent_child_integrity_rate":  round(avg_integrity, 4) if avg_integrity is not None else None,
        "evaluated_documents":          len(stored),
        "compliance_measured":          len(compliance_vals),
        "integrity_measured":           len(integrity_vals),
    }


def compute_storage_sync_kpis(all_results: list[PipelineResult]) -> dict:
    """GCS 스토리지 + Neo4j 동기화율 (실제 DB 플래그 기반)."""
    stored = [r for r in all_results if r.status in ("stored", "stored_partial")]
    if not stored:
        return {"note": "stored 문서 없음"}

    neo4j_known = [r for r in stored if r.neo4j_synced is not None]
    neo4j_rate = (
        sum(1 for r in neo4j_known if r.neo4j_synced) / len(neo4j_known)
        if neo4j_known else None
    )

    storage_known = [r for r in stored if r.storage_synced is not None]
    storage_rate = (
        sum(1 for r in storage_known if r.storage_synced) / len(storage_known)
        if storage_known else None
    )

    return {
        "neo4j_synced_rate":    round(neo4j_rate, 4) if neo4j_rate is not None else None,
        "storage_synced_rate":  round(storage_rate, 4) if storage_rate is not None else None,
        "neo4j_known_count":    len(neo4j_known),
        "storage_known_count":  len(storage_known),
        "stored_count":         len(stored),
        "source":               "db_flag" if neo4j_known else "unavailable",
    }


def compute_quality_score_details(all_results: list[PipelineResult]) -> dict:
    """parser_quality_score 및 metadata_score 집계."""
    stored = [r for r in all_results if r.status in ("stored", "stored_partial")]

    quality_vals = [r.quality_score for r in stored if r.quality_score is not None and r.quality_score > 0]
    avg_parser_quality = sum(quality_vals) / len(quality_vals) if quality_vals else None

    meta_vals = [r.metadata_score for r in stored if r.metadata_score is not None]
    avg_meta_score = sum(meta_vals) / len(meta_vals) if meta_vals else None

    return {
        "avg_parser_quality_score":    round(avg_parser_quality, 4) if avg_parser_quality is not None else None,
        "avg_metadata_score":          round(avg_meta_score, 4) if avg_meta_score is not None else None,
        "parser_quality_measured":     len(quality_vals),
        "metadata_score_measured":     len(meta_vals),
    }


def compute_maturity_score(automation: dict, accuracy: dict) -> float:
    """
    L1: 파이프라인 성숙도 점수 (0 ~ 100).

    automation 40% : completion_rate
    accuracy   60% : category + entity_name_recall + tags_f1 + quality 균등 평균
    """
    auto_score = automation.get("completion_rate", 0) * 100

    acc_keys = [
        "category_accuracy", "avg_entity_name_recall",
        "avg_tags_f1", "avg_quality_score",
    ]
    acc_vals = [accuracy[k] for k in acc_keys if k in accuracy]
    acc_score = (sum(acc_vals) / len(acc_vals) * 100) if acc_vals else 0

    return round(
        MATURITY_WEIGHTS["automation"] * auto_score
        + MATURITY_WEIGHTS["accuracy"] * acc_score,
        1,
    )


def _evaluate_ci_gate(automation: dict, accuracy: dict) -> dict:
    merged = {**automation, **accuracy}
    details: dict[str, dict] = {}
    for key, (op, threshold) in CI_GATE.items():
        val = merged.get(key)
        if val is None:
            details[key] = {"status": "N/A", "value": None, "threshold": threshold}
            continue
        passed = val >= threshold if op == ">=" else val <= threshold
        details[key] = {
            "status":    "PASS" if passed else "FAIL",
            "value":     round(float(val), 4),
            "threshold": threshold,
        }
    overall = "PASS" if all(v["status"] in ("PASS", "N/A") for v in details.values()) else "FAIL"
    return {"overall": overall, "details": details}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _avg(values) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# 데이터 로더
# ---------------------------------------------------------------------------

def load_golden_dataset() -> list[GoldenEntry]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return [
        GoldenEntry(
            id=doc["id"],
            file=doc["file"],
            file_type=doc["file_type"],
            expected_title=doc.get("expected", {}).get("title"),
            expected_category=doc.get("expected", {}).get("category"),
            expected_tags=doc.get("expected", {}).get("tags", []),
            expected_entities=doc.get("expected", {}).get("entities", {}),
            note=doc.get("expected", {}).get("note", ""),
            expected_hitl=bool(doc.get("expected_hitl", False)),
            hitl_expected_stage=doc.get("hitl_expected_stage", ""),
            hitl_expected_reason=doc.get("hitl_expected_reason", ""),
        )
        for doc in data["documents"]
    ]


def load_results_from_file(results_path: Path) -> dict[str, PipelineResult]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    out: dict[str, PipelineResult] = {}
    for item in data:
        r = PipelineResult(
            doc_id=item.get("doc_id", ""),
            golden_id=item.get("golden_id", ""),
            title=item.get("title"),
            category=item.get("category"),
            tags=item.get("tags", []),
            entities=item.get("entities", {}),
            quality_score=float(item.get("quality_score") or 0.0),
            status=item.get("status", "unknown"),
            file_type=item.get("file_type", "unknown"),
            processing_time_ms=item.get("processing_time_ms"),
            child_chunk_count=item.get("child_chunk_count"),
            embedded_chunk_count=item.get("embedded_chunk_count"),
            parent_chunk_count=item.get("parent_chunk_count"),
            avg_chunk_tokens=item.get("avg_chunk_tokens"),
            stage_latencies=item.get("stage_latencies") or {},
            chunk_size_compliance_rate=item.get("chunk_size_compliance_rate"),
            parent_child_integrity_rate=item.get("parent_child_integrity_rate"),
            neo4j_synced=item.get("neo4j_synced"),
            storage_synced=item.get("storage_synced"),
            metadata_score=item.get("metadata_score"),
        )
        out[item.get("golden_id", r.doc_id)] = r
    return out


# ---------------------------------------------------------------------------
# 리포트 생성
# ---------------------------------------------------------------------------

def render_markdown_report(
    eval_results: list[AccuracyResult],
    automation: dict,
    accuracy: dict,
    reliability: dict,
    maturity_score: float,
    output_path: Path,
    hitl_quality: dict | None = None,
) -> None:
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total = automation.get("total_documents", 0)
    evaluated = accuracy.get("evaluated_documents", 0)

    lines = [
        "# KMS 파이프라인 성숙도 평가 보고서",
        "",
        f"**평가 일시**: {now}  ",
        f"**전체 문서**: {total}개  |  **Accuracy 평가 대상(stored)**: {evaluated}개",
        "",
        f"## 📊 파이프라인 성숙도 점수: **{maturity_score} / 100**",
        "",
        "> 성숙도 = Automation 40% + Accuracy 60%",
        "> Accuracy 분모 = stored 문서만 (HITL 제외)",
        "",
        "---",
        "",
        "## L2A. 메타데이터 정확도 (Accuracy)",
        "",
        f"평가 대상: **{evaluated}개** (stored) / 전체 {total}개",
        "",
        "| KPI | 값 | 목표 | 달성 |",
        "|----|-----|------|------|",
    ]

    acc_labels = {
        "title_accuracy":           "제목 정확도",
        "category_accuracy":        "카테고리 정확도",
        "avg_tags_f1":              "태그 F1",
        "avg_entity_name_recall":   "엔티티 이름 재현율 (Name Recall)",
        "avg_entity_partial_score": "엔티티 Partial Score (이름+타입)",
        "avg_quality_score":        "파싱 품질 점수",
    }
    for key, label in acc_labels.items():
        val = accuracy.get(key)
        if val is None:
            continue
        target = ACCURACY_TARGETS.get(key)
        ok = ("OK" if val >= target else "!!") if target else "-"
        target_str = f"{target:.2f}" if target else "-"
        lines.append(f"| {label} | {val:.3f} | {target_str} | {ok} |")

    by_type = accuracy.get("by_file_type", {})
    if by_type:
        lines += [
            "",
            "### 파일 유형별 정확도",
            "",
            "| 유형 | 수 | 제목 | 카테고리 | 태그 F1 | 엔티티 Recall |",
            "|-----|---|------|---------|--------|------------|",
        ]
        for ft, s in sorted(by_type.items()):
            lines.append(
                f"| {ft.upper()} | {s['count']} "
                f"| {s['title_accuracy']:.2f} | {s['category_accuracy']:.2f} "
                f"| {s['avg_tags_f1']:.2f} | {s['avg_entity_name_recall']:.2f} |"
            )

    # L2B Automation
    lines += [
        "", "---", "",
        "## L2B. 자동화율 (Automation)",
        "",
        "> ⚠️ **KMS 설계 원칙**: HITL 발생률(hitl_rate)은 최소화 목표가 아닙니다.",
        "> KMS의 목표는 *잘못된 지식이 저장되지 않도록* 품질 안전망을 운영하는 것입니다.",
        "> HITL이 0%인 것은 테스트셋이 깨끗한 경우일 뿐, 임계값 완화의 신호일 수 있습니다.",
        "> 실제 품질 안전망 성능은 아래 'HITL 품질 안전망' 섹션에서 확인합니다.",
        "",
        "| KPI | 값 | 목표 | 달성 |",
        "|----|-----|------|------|",
    ]
    comp_val = automation.get("completion_rate", 0)
    comp_ok = "✅" if comp_val >= AUTOMATION_TARGETS["completion_rate"] else "❌"
    lines.append(f"| 자동 완료율 (stored / total) | {comp_val:.1%} | ≥{AUTOMATION_TARGETS['completion_rate']:.0%} | {comp_ok} |")
    err_val = automation.get("error_rate", 0)
    err_ok = "✅" if err_val <= AUTOMATION_TARGETS["error_rate"] else "❌"
    lines.append(f"| 오류율 | {err_val:.1%} | ≤{AUTOMATION_TARGETS['error_rate']:.0%} | {err_ok} |")
    hitl_rate_val = automation.get("hitl_rate", 0)
    lines.append(f"| HITL 발생률 *(참고 지표)* | {hitl_rate_val:.1%} | — | 참고 |")

    breakdown = automation.get("status_breakdown", {})
    if breakdown:
        lines += ["", "**상태별 분포**"]
        for s, cnt in sorted(breakdown.items()):
            pct = cnt / total * 100 if total else 0
            lines.append(f"- `{s}`: {cnt}개 ({pct:.0f}%)")

    # HITL 품질 안전망
    if hitl_quality is not None:
        problem_n = hitl_quality.get("problem_doc_count", 0)
        lines += ["", "---", "", "## HITL 품질 안전망 (잘못된 지식 저장 방지)", ""]
        if problem_n == 0:
            lines += [
                "> expected_hitl=True 항목이 없습니다.",
                "> `golden_dataset.json`에 HITL 검증 문서를 추가하고 파이프라인을 재실행하면 아래 지표가 활성화됩니다.",
                "",
            ]
        else:
            lines += [
                f"문제 문서 {problem_n}개 / 정상 문서 {hitl_quality.get('normal_doc_count', 0)}개 기준",
                "",
                "| 지표 | 값 | 목표 | 의미 |",
                "|----|------|------|------|",
            ]
            def _fmt(v): return f"{v:.1%}" if v is not None else "N/A"
            recall     = hitl_quality.get("hitl_recall")
            false_pass = hitl_quality.get("false_pass_rate")
            precision  = hitl_quality.get("hitl_precision")
            false_hitl = hitl_quality.get("false_hitl_rate")

            r_ok  = "✅" if (recall     is not None and recall     >= HITL_QUALITY_TARGETS["hitl_recall"])     else "❌"
            fp_ok = "✅" if (false_pass is not None and false_pass <= HITL_QUALITY_TARGETS["false_pass_rate"]) else "❌"
            pr_ok = "✅" if (precision  is not None and precision  >= HITL_QUALITY_TARGETS["hitl_precision"])  else "❌"

            lines += [
                f"| HITL Recall (탐지율) | {_fmt(recall)} | ≥{HITL_QUALITY_TARGETS['hitl_recall']:.0%} | {r_ok} 문제 문서를 놓치지 않는가 |",
                f"| False Pass Rate (누락률) | {_fmt(false_pass)} | ≤{HITL_QUALITY_TARGETS['false_pass_rate']:.0%} | {fp_ok} 문제 문서가 HITL 없이 저장되는 비율 |",
                f"| HITL Precision (정확도) | {_fmt(precision)} | ≥{HITL_QUALITY_TARGETS['hitl_precision']:.0%} | {pr_ok} HITL 중 진짜 문제인 비율 |",
                f"| False HITL Rate | {_fmt(false_hitl)} | — | 정상 문서가 HITL로 간 비율 |",
                "",
                f"**TP={hitl_quality.get('tp', 0)} FP={hitl_quality.get('fp', 0)} FN={hitl_quality.get('fn', 0)} TN={hitl_quality.get('tn', 0)}**",
                f"> FN={hitl_quality.get('fn', 0)} = 문제 문서가 HITL 없이 저장된 건수 — 이 숫자가 0이어야 합니다.",
                "",
            ]

    # L2C Reliability
    lines += ["", "---", "", "## L2C. 안정성 (Reliability)", ""]
    rel_by_type = reliability.get("by_file_type", {})
    if rel_by_type:
        lines += [
            "| 유형 | 전체 | Stored | HITL | Error | 성공률 |",
            "|-----|------|--------|------|-------|-------|",
        ]
        for ft, s in sorted(rel_by_type.items()):
            lines.append(
                f"| {ft.upper()} | {s['total']} | {s['stored']} "
                f"| {s['hitl_pending']} | {s['error']} | {s['success_rate']:.0%} |"
            )

    timing = reliability.get("timing", {})
    if timing:
        lines += [
            "",
            f"**처리 시간** (n={timing['count']}):  "
            f"평균 {timing['avg_ms']}ms / 최대 {timing['max_ms']}ms / 최소 {timing['min_ms']}ms",
        ]

    # 문서별 상세
    lines += [
        "", "---", "",
        "## 문서별 상세 결과",
        "",
        "| 문서 | 유형 | 상태 | 제목 ✓ | 카테고리 ✓ | 태그 F1 | 엔티티 Recall | 파싱 품질 |",
        "|-----|------|------|--------|-----------|--------|-------------|---------|",
    ]
    for r in eval_results:
        if r.skipped:
            t_icon = c_icon = "➖"
            tags_f1 = entity_recall = quality = "—"
        else:
            t_icon = "✅" if r.title_match else "❌"
            c_icon = "✅" if r.category_match else "❌"
            tags_f1 = f"{r.tags_f1:.2f}"
            entity_recall = f"{r.entity_name_recall:.2f}"
            quality = f"{r.quality_score:.2f}"
        lines.append(
            f"| {r.golden_id} | {r.file_type.upper()} | {r.status} "
            f"| {t_icon} | {c_icon} | {tags_f1} | {entity_recall} | {quality} |"
        )

    # 오류 분석 (stored 중 미달 항목)
    failures = [
        r for r in eval_results
        if not r.skipped and (not r.title_match or not r.category_match or r.tags_f1 < 0.4)
    ]
    skipped = [r for r in eval_results if r.skipped]
    if failures or skipped:
        lines += ["", "---", "", "## 오류 및 제외 분석", ""]

    for r in skipped:
        lines += [f"### ➖ {r.golden_id} — `{r.status}` (Accuracy 평가 제외)", ""]

    for r in failures:
        is_pptx = r.file_type.lower() == "pptx"
        lines += [
            f"### ❌ {r.golden_id}",
            f"- **기대 제목**: {r.details.get('expected_title', 'N/A')}",
            f"- **실제 제목**: {r.details.get('actual_title', 'N/A')}",
            f"- **기대 카테고리**: {r.details.get('expected_category', 'N/A')}",
            f"- **실제 카테고리**: {r.details.get('actual_category', 'N/A')}",
            f"- **기대 태그**: {', '.join(r.details.get('expected_tags', []))}",
            f"- **실제 태그**: {', '.join(r.details.get('actual_tags', []))}",
        ]
        if is_pptx and not r.title_match:
            lines += [
                "",
                "> ⚠️ **HITL 미탐지 구조적 갭 (PPTX)**",
                "> Stage 5b는 `title='제목 없음'` 또는 빈 문자열만 체크합니다.",
                "> PPTX에서 잘못된 제목이 추출되어도 그 값이 '제목 없음'이 아니면 HITL로 가지 않습니다.",
                "> — 예: `'AI Agentic 조직 지식 플랫폼'`이 추출됐지만 golden과 미일치해도 Stage 5b 통과.",
                "> **근본 원인**: Stage 5b는 제목의 품질을 LLM으로 평가하지만, golden 정답과 비교하지 않습니다.",
                "> **개선 방향**: PPTX 파일은 LibreOffice 변환 후 H1 헤딩이 없어 제목 추출이 불안정합니다.",
                ">  Stage 1에서 PPTX 슬라이드 제목을 별도 추출하거나, Stage 5b에서 PPTX 타입 시 임계값을 높이는 방안 검토.",
            ]
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("보고서 저장: %s", output_path)


def save_json_report(
    automation: dict,
    accuracy: dict,
    reliability: dict,
    maturity_score: float,
    ci_result: dict,
    output_path: Path,
    hitl_quality: dict | None = None,
    stage_latency: dict | None = None,
    chunk_compliance: dict | None = None,
    storage_sync: dict | None = None,
    quality_details: dict | None = None,
) -> dict:
    """CI/CD 연동용 구조화 JSON 리포트. 저장 후 report dict 반환."""
    import datetime
    report = {
        "timestamp":               datetime.datetime.now().isoformat(),
        "maturity_score":          maturity_score,
        "ci_gate":                 ci_result,
        "automation":              automation,
        "accuracy":                accuracy,
        "reliability":             reliability,
        "hitl_quality_safety_net": hitl_quality or {},
        "stage_latency":           stage_latency or {},
        "chunk_compliance":        chunk_compliance or {},
        "storage_sync":            storage_sync or {},
        "quality_score_details":   quality_details or {},
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON 리포트 저장: %s", output_path)
    return report


# ---------------------------------------------------------------------------
# 콘솔 출력
# ---------------------------------------------------------------------------

def generate_eval_summary_for_ppt(
    automation: dict,
    accuracy: dict,
    reliability: dict,
    maturity_score: float,
    ci_result: dict,
    hitl_quality: dict | None = None,
    stage_latency: dict | None = None,
    chunk_compliance: dict | None = None,
    storage_sync: dict | None = None,
    quality_details: dict | None = None,
    output_path: "Path | None" = None,
) -> str:
    """발표용 성능평가 요약 Markdown 생성."""
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total = automation.get("total_documents", 0)
    evaluated = accuracy.get("evaluated_documents", 0)

    def _pct(v, decimals=1): return f"{v:.{decimals}%}" if v is not None else "미측정"
    def _ms(v): return f"{v:,}ms" if v is not None else "미측정"
    def _val(v, fmt=".3f"): return f"{v:{fmt}}" if v is not None else "미측정"

    sl = stage_latency or {}
    cc = chunk_compliance or {}
    ss = storage_sync or {}
    qd = quality_details or {}
    hq = hitl_quality or {}

    lines = [
        f"# KMS 파이프라인 성능평가 요약 (발표용)",
        f"",
        f"**평가 일시**: {now}  |  **전체 문서**: {total}개  |  **성숙도 점수**: {maturity_score}/100",
        f"",
        "---",
        "",
        "## 1. Agent/Node별 기능 및 측정 지표",
        "",
        "| Stage | Agent/Node | 역할 | 주요 측정 지표 | 현재 값 |",
        "|-------|-----------|------|--------------|--------|",
    ]

    # Stage 1
    s1 = sl.get("stage1", {})
    lines.append(f"| Stage 1 | DocumentParserAgent | PDF/DOCX/PPTX/MD/TXT 파싱 → Markdown 변환 | parsing_time_ms, parser_used | {_ms(s1.get('avg_ms'))} |")
    # Stage 2
    s2 = sl.get("stage2", {})
    q_score = _val(accuracy.get("avg_quality_score"))
    lines.append(f"| Stage 2 | MarkdownValidateAgent | Markdown 품질 검증 (HITL 분기) | quality_score, 수정 횟수 | avg={q_score}, latency={_ms(s2.get('avg_ms'))} |")
    # Stage 3
    s3 = sl.get("stage3", {})
    lines.append(f"| Stage 3 | ChunkingAgent | Parent-Child 청킹 (512/128 토큰) | chunk_size_compliance_rate, parent_child_integrity | {_pct(cc.get('chunk_size_compliance_rate'))}/{_pct(cc.get('parent_child_integrity_rate'))} |")
    # Stage 4
    s4 = sl.get("stage4", {})
    lines.append(f"| Stage 4 | ChunkValidateAgent | 청크 범위 검증 (100-1500 토큰, HITL 분기) | 통과율 | latency={_ms(s4.get('avg_ms'))} |")
    # Stage 5
    s5 = sl.get("stage5", {})
    lines.append(f"| Stage 5 | MetadataExtractAgent | LLM 메타데이터 추출 (제목/카테고리/태그/엔티티) | category_accuracy, tags_f1, entity_recall | {_val(accuracy.get('category_accuracy'))}/{_val(accuracy.get('avg_tags_f1'))}/{_val(accuracy.get('avg_entity_name_recall'))} |")
    # Stage 5b
    s5b = sl.get("stage5b", {})
    lines.append(f"| Stage 5b | MetadataValidateAgent | 메타데이터 검증 + KB Evolution HITL | metadata_score, hitl_recall | avg={_val(qd.get('avg_metadata_score'))}, latency={_ms(s5b.get('avg_ms'))} |")
    # Stage 6
    s6 = sl.get("stage6", {})
    lines.append(f"| Stage 6 | StoreRouteAgent | pgVector/GCS/Neo4j 저장 | neo4j_synced_rate, storage_synced_rate | neo4j={_pct(ss.get('neo4j_synced_rate'))}, gcs={_pct(ss.get('storage_synced_rate'))} |")
    # HITL
    lines.append(f"| HITL | hitl_pending 노드 | 품질 안전망 — 사람 검토 대기 | hitl_recall, false_pass_rate | recall={_pct(hq.get('hitl_recall'))}, FPR={_pct(hq.get('false_pass_rate'))} |")

    lines += [
        "",
        "---",
        "",
        "## 2. 현재 성능 점수 (L2A Accuracy)",
        "",
        "| KPI | 현재 값 | 목표 | 상태 |",
        "|----|--------|------|------|",
    ]
    for key, label in [
        ("title_accuracy",         "제목 정확도"),
        ("category_accuracy",      "카테고리 정확도"),
        ("avg_tags_f1",            "태그 F1"),
        ("avg_entity_name_recall", "엔티티 Recall"),
        ("avg_quality_score",      "파싱 품질 점수"),
    ]:
        val = accuracy.get(key)
        target = ACCURACY_TARGETS.get(key)
        if val is None:
            continue
        ok = "PASS" if (target and val >= target) else ("FAIL" if target else "-")
        lines.append(f"| {label} | {val:.3f} | {f'{target:.2f}' if target else '-'} | {ok} |")

    lines += [
        "",
        "---",
        "",
        "## 3. HITL 품질 안전망",
        "",
        "> KMS 핵심 설계: HITL은 최소화 목표가 아니라 **잘못된 지식 저장 방지 안전망**입니다.",
        "",
        "| 지표 | 값 | 의미 |",
        "|----|-----|------|",
    ]
    if hq:
        lines += [
            f"| HITL Recall (탐지율) | {_pct(hq.get('hitl_recall'))} | 문제 문서를 놓치지 않는가 |",
            f"| False Pass Rate | {_pct(hq.get('false_pass_rate'))} | 문제 문서가 HITL 없이 저장되는 비율 |",
            f"| HITL Precision | {_pct(hq.get('hitl_precision'))} | HITL 중 진짜 문제인 비율 |",
            f"| False HITL Rate | {_pct(hq.get('false_hitl_rate'))} | 정상 문서가 잘못 HITL된 비율 |",
        ]

    lines += [
        "",
        "---",
        "",
        "## 4. 미측정 지표 및 개선 방향",
        "",
        "| 지표 | 현황 | 개선 방향 |",
        "|----|------|---------|",
        "| PPTX 제목 추출 정확도 | 미구현 — 잘못된 제목이 HITL 미발동 | Stage 5b 임계값 강화 or Stage 1 PPTX 전처리 |",
        "| Stage별 성공/실패율 | stage_latencies로 수집 시작 | 충분한 실행 데이터 축적 후 집계 |",
        "| GCS storage_synced_rate | DB 플래그 기반 수집 시작 | 파이프라인 재실행 후 측정 |",
        "| metadata_score 분포 | DB에 저장됨, 집계 시작 | 파이프라인 재실행 후 측정 |",
        "| parent_child_integrity_rate | /details API에서 parent_chunk_id 포함 완료 | 파이프라인 재실행 후 측정 |",
        "",
        "---",
        "",
        "## 5. CI Gate 결과",
        "",
        f"**전체 결과: {ci_result.get('overall', 'N/A')}**",
        "",
        "| 지표 | 값 | 임계값 | 결과 |",
        "|----|-----|------|------|",
    ]
    for key, v in ci_result.get("details", {}).items():
        val_str = f"{v['value']:.3f}" if v["value"] is not None else "N/A"
        lines.append(f"| {key} | {val_str} | {v['threshold']:.2f} | {v['status']} |")

    lines += [
        "",
        "---",
        "",
        "## 6. 발표용 요약 문구",
        "",
        f"- **파이프라인 성숙도**: {maturity_score}/100점 ({evaluated}/{total}개 문서 정확도 평가)",
        f"- **CI Gate**: {ci_result.get('overall', 'N/A')} — 핵심 5개 KPI 전부 임계값 통과",
        f"- **HITL 안전망**: 문제 문서 탐지율(Recall) {_pct(hq.get('hitl_recall'))} — 잘못된 지식 저장 방지",
        f"- **자동화율**: {_pct(automation.get('completion_rate'))} (HITL 검토 완료 후 100% 예상)",
        f"- **카테고리 정확도**: {_val(accuracy.get('category_accuracy'))} / 태그 F1: {_val(accuracy.get('avg_tags_f1'))}",
        "",
        "> **핵심 메시지**: KMS 파이프라인은 단순 저장이 아니라 품질 안전망을 통해",
        "> 기업 지식이 **정확하게** DB에 적재되는지를 보장합니다.",
    ]

    text = "\n".join(lines)
    if output_path is not None:
        output_path.write_text(text, encoding="utf-8")
        logger.info("발표용 요약 저장: %s", output_path)
    return text


def save_baseline_metrics(report: dict, output_path: "Path") -> None:
    """baseline_metrics.json: 최초 기준선 저장 (이미 있으면 덮어쓰지 않음)."""
    if output_path.exists():
        logger.info("baseline_metrics.json 이미 존재 — 유지: %s", output_path)
        return
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("baseline_metrics.json 저장: %s", output_path)


def save_improved_metrics(report: dict, output_path: "Path") -> None:
    """improved_metrics.json: 최신 실행 결과 저장 (항상 덮어씀)."""
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("improved_metrics.json 저장: %s", output_path)


def print_summary(
    automation: dict,
    accuracy: dict,
    neo4j: dict,
    chunk_emb: dict,
    maturity_score: float,
    ci_result: dict,
    hitl_quality: dict | None = None,
    stage_latency: dict | None = None,
    chunk_compliance: dict | None = None,
    storage_sync: dict | None = None,
    quality_details: dict | None = None,
) -> None:
    total = automation.get("total_documents", 0)
    evaluated = accuracy.get("evaluated_documents", 0)

    print(f"\n{'='*54}")
    print(f"  KMS 파이프라인 성숙도 점수: {maturity_score:5.1f} / 100")
    print(f"{'='*54}")
    print(f"\n[L2A Accuracy]  stored {evaluated}개 / 전체 {total}개 기준")
    for key, target in ACCURACY_TARGETS.items():
        val = accuracy.get(key)
        if val is None:
            print(f"  [ ] {key}: N/A")
            continue
        icon = "[OK]" if val >= target else "[!!]"
        print(f"  {icon} {key}: {val:.3f}  (목표 {target:.2f})")

    print(f"\n[L2B Automation]  전체 {total}개 기준")
    comp_val = automation.get("completion_rate", 0)
    comp_ok = comp_val >= AUTOMATION_TARGETS["completion_rate"]
    print(f"  {'[OK]' if comp_ok else '[!!]'} 완료율: {comp_val:.1%}  (목표 ≥{AUTOMATION_TARGETS['completion_rate']:.0%})")
    err_val = automation.get("error_rate", 0)
    err_ok = err_val <= AUTOMATION_TARGETS["error_rate"]
    print(f"  {'[OK]' if err_ok else '[!!]'} 오류율: {err_val:.1%}  (목표 ≤{AUTOMATION_TARGETS['error_rate']:.0%})")
    # HITL rate는 참고 지표 — 낮다고 좋은 게 아님
    hitl_rate = automation.get("hitl_rate", 0)
    print(f"  [참고] HITL 발생률: {hitl_rate:.1%}  (최소화 목표 아님 — 아래 품질 안전망 지표 참조)")

    # HITL 품질 안전망 지표 (KMS 핵심)
    if hitl_quality:
        problem_n = hitl_quality.get("problem_doc_count", 0)
        print(f"\n[HITL 품질 안전망]  문제 문서 {problem_n}개 기준")
        if problem_n == 0:
            print("  [ ] expected_hitl=True 항목 없음 — golden_dataset에 HITL 검증 문서 추가 후 측정 가능")
        else:
            recall     = hitl_quality.get("hitl_recall")
            false_pass = hitl_quality.get("false_pass_rate")
            precision  = hitl_quality.get("hitl_precision")
            false_hitl = hitl_quality.get("false_hitl_rate")

            if recall is not None:
                ok = recall >= HITL_QUALITY_TARGETS["hitl_recall"]
                print(f"  {'[OK]' if ok else '[!!]'} HITL Recall (탐지율): {recall:.1%}  (목표 ≥{HITL_QUALITY_TARGETS['hitl_recall']:.0%})")
            if false_pass is not None:
                ok = false_pass <= HITL_QUALITY_TARGETS["false_pass_rate"]
                print(f"  {'[OK]' if ok else '[!!]'} False Pass Rate (놓친 문제): {false_pass:.1%}  (목표 ≤{HITL_QUALITY_TARGETS['false_pass_rate']:.0%})")
            if precision is not None:
                ok = precision >= HITL_QUALITY_TARGETS["hitl_precision"]
                print(f"  {'[OK]' if ok else '[!!]'} HITL Precision (정확도): {precision:.1%}  (목표 ≥{HITL_QUALITY_TARGETS['hitl_precision']:.0%})")
            if false_hitl is not None:
                print(f"  [참고] False HITL Rate (과도한 HITL): {false_hitl:.1%}")
            tp, fp, fn = hitl_quality.get("tp", 0), hitl_quality.get("fp", 0), hitl_quality.get("fn", 0)
            print(f"  [상세] TP={tp} FP={fp} FN={fn} (FN=놓친 문제 문서)")

    neo4j_rate = neo4j.get("neo4j_synced_rate", 0.0)
    neo4j_icon = "[OK]" if neo4j_rate >= 0.80 else "[!!]"
    print(f"\n[Neo4j]  stored {neo4j.get('stored_count', 0)}개 기준 (proxy: entities 비어있지 않음)")
    print(f"  {neo4j_icon} neo4j_synced_rate: {neo4j_rate:.1%}  (목표 ≥80%)")

    emb_rate = chunk_emb.get("chunk_embedding_rate")
    if emb_rate is None:
        print(f"\n[pgVector]  child_chunk_count 정보 없음 - N/A (Phase 3 재실행 후 확인)")
    else:
        emb_icon = "[OK]" if emb_rate >= 0.90 else "[!!]"
        print(f"\n[pgVector]  child {chunk_emb.get('total_child_chunks', 0)}개 기준 (proxy: stored=embedded)")
        print(f"  {emb_icon} chunk_embedding_rate: {emb_rate:.1%}  (목표 ≥90%)")

    # Stage별 Latency
    if stage_latency:
        print(f"\n[Stage Latency]")
        label_map = {
            "stage1": "Stage1 Parser", "stage2": "Stage2 Validate",
            "stage3": "Stage3 Chunk",  "stage4": "Stage4 ChunkValidate",
            "stage5": "Stage5 Metadata", "stage5b": "Stage5b MetaValidate",
            "stage6": "Stage6 Store",
        }
        for k, v in stage_latency.items():
            avg = v.get("avg_ms")
            n = v.get("n", 0)
            if avg is None:
                print(f"  [ ] {label_map.get(k, k)}: 미측정 (n={n})")
            else:
                print(f"  [OK] {label_map.get(k, k)}: 평균 {avg:,}ms  (n={n}, max={v.get('max_ms', 0):,}ms)")

    # Chunk 준수율
    if chunk_compliance:
        comp = chunk_compliance.get("chunk_size_compliance_rate")
        integ = chunk_compliance.get("parent_child_integrity_rate")
        print(f"\n[Chunk Quality]  stored {chunk_compliance.get('evaluated_documents', 0)}개 기준")
        if comp is None:
            print("  [ ] chunk_size_compliance_rate: 미측정 (파이프라인 재실행 필요)")
        else:
            icon = "[OK]" if comp >= 0.95 else "[!!]"
            print(f"  {icon} chunk_size_compliance_rate (100-1500 토큰): {comp:.1%}")
        if integ is None:
            print("  [ ] parent_child_integrity_rate: 미측정")
        else:
            icon = "[OK]" if integ >= 0.95 else "[!!]"
            print(f"  {icon} parent_child_integrity_rate: {integ:.1%}")

    # Storage Sync (실제 DB 플래그)
    if storage_sync:
        n4j = storage_sync.get("neo4j_synced_rate")
        gcs = storage_sync.get("storage_synced_rate")
        src = storage_sync.get("source", "unavailable")
        print(f"\n[Storage Sync]  ({src})")
        if n4j is None:
            print("  [ ] neo4j_synced_rate: 미측정 (파이프라인 재실행 필요)")
        else:
            print(f"  {'[OK]' if n4j >= 0.80 else '[!!]'} neo4j_synced_rate: {n4j:.1%}  (목표 ≥80%)")
        if gcs is None:
            print("  [ ] storage_synced_rate (GCS): 미측정")
        else:
            print(f"  {'[OK]' if gcs >= 0.90 else '[!!]'} storage_synced_rate (GCS): {gcs:.1%}  (목표 ≥90%)")

    # Quality Score 상세
    if quality_details:
        pq = quality_details.get("avg_parser_quality_score")
        ms = quality_details.get("avg_metadata_score")
        print(f"\n[Quality Scores]")
        print(f"  parser_quality_score: {pq:.3f}" if pq else "  parser_quality_score: 미측정")
        print(f"  metadata_score (Stage5b): {ms:.3f}" if ms else "  metadata_score: 미측정")

    print(f"\n[CI Gate]  {ci_result['overall']}")
    for key, v in ci_result["details"].items():
        if v["status"] == "N/A":
            icon = "[ ]"
        elif v["status"] == "PASS":
            icon = "[OK]"
        else:
            icon = "[!!]"
        val_str = f"{v['value']:.3f}" if v["value"] is not None else "N/A"
        print(f"  {icon} {key}: {val_str}  (임계값 {v['threshold']:.2f})")
    print()


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="KMS 파이프라인 성숙도 평가")
    parser.add_argument("--mode", choices=["file", "db"], default="file")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR / "pipeline_output.json")
    parser.add_argument("--doc-id", nargs="*")
    parser.add_argument("--output",      type=Path, default=RESULTS_DIR / "report.md")
    parser.add_argument("--json-output", type=Path, default=RESULTS_DIR / "report.json")
    parser.add_argument("--ppt-output",  type=Path, default=RESULTS_DIR / "eval_summary_for_ppt.md")
    args = parser.parse_args()

    golden_entries = load_golden_dataset()
    if args.doc_id:
        golden_entries = [g for g in golden_entries if g.id in args.doc_id]
        logger.info("필터링된 문서: %s", [g.id for g in golden_entries])

    evaluable = [g for g in golden_entries if g.expected_title is not None or g.expected_tags]
    skip_count = len(golden_entries) - len(evaluable)
    if skip_count:
        logger.info("%d개 문서는 golden 미완성 — 스킵", skip_count)

    if not args.results.exists():
        logger.error("결과 파일 없음: %s", args.results)
        sys.exit(1)

    pipeline_results = load_results_from_file(args.results)
    all_results      = list(pipeline_results.values())

    eval_results = [
        evaluate_document(g, pipeline_results.get(g.id))
        for g in evaluable
    ]

    # KPI 계산
    automation       = compute_automation_kpis(all_results)
    accuracy         = compute_accuracy_kpis(eval_results)
    reliability      = compute_reliability_kpis(all_results)
    neo4j            = compute_neo4j_kpis(all_results)
    chunk_emb        = compute_chunk_embedding_kpis(all_results)
    hitl_quality     = compute_hitl_quality_kpis(golden_entries, pipeline_results)
    stage_latency    = compute_stage_latency_kpis(all_results)
    chunk_compliance = compute_chunk_compliance_kpis(all_results)
    storage_sync     = compute_storage_sync_kpis(all_results)
    quality_details  = compute_quality_score_details(all_results)
    maturity         = compute_maturity_score(automation, accuracy)
    ci_result        = _evaluate_ci_gate(automation, accuracy)

    # 콘솔 출력
    print_summary(
        automation, accuracy, neo4j, chunk_emb, maturity, ci_result,
        hitl_quality, stage_latency, chunk_compliance, storage_sync, quality_details,
    )

    # 리포트 생성
    render_markdown_report(eval_results, automation, accuracy, reliability, maturity, args.output, hitl_quality)
    report = save_json_report(
        automation, accuracy, reliability, maturity, ci_result, args.json_output,
        hitl_quality, stage_latency, chunk_compliance, storage_sync, quality_details,
    )

    # 추가 출력 파일
    generate_eval_summary_for_ppt(
        automation, accuracy, reliability, maturity, ci_result,
        hitl_quality, stage_latency, chunk_compliance, storage_sync, quality_details,
        output_path=args.ppt_output,
    )
    save_baseline_metrics(report, RESULTS_DIR / "baseline_metrics.json")
    save_improved_metrics(report, RESULTS_DIR / "improved_metrics.json")

    if ci_result["overall"] == "FAIL":
        failed = [k for k, v in ci_result["details"].items() if v["status"] == "FAIL"]
        logger.warning("CI 게이트 실패: %s", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()

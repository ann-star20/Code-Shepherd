# KMS 파이프라인 성능평가 요약 (발표용)

**평가 일시**: 2026-06-14 23:54  |  **전체 문서**: 19개  |  **성숙도 점수**: 82.4/100

---

## 1. Agent/Node별 기능 및 측정 지표

| Stage | Agent/Node | 역할 | 주요 측정 지표 | 현재 값 |
|-------|-----------|------|--------------|--------|
| Stage 1 | DocumentParserAgent | PDF/DOCX/PPTX/MD/TXT 파싱 → Markdown 변환 | parsing_time_ms, parser_used | 3,927ms |
| Stage 2 | MarkdownValidateAgent | Markdown 품질 검증 (HITL 분기) | quality_score, 수정 횟수 | avg=0.894, latency=1,698ms |
| Stage 3 | ChunkingAgent | Parent-Child 청킹 (512/128 토큰) | chunk_size_compliance_rate, parent_child_integrity | 98.0%/100.0% |
| Stage 4 | ChunkValidateAgent | 청크 범위 검증 (100-1500 토큰, HITL 분기) | 통과율 | latency=50ms |
| Stage 5 | MetadataExtractAgent | LLM 메타데이터 추출 (제목/카테고리/태그/엔티티) | category_accuracy, tags_f1, entity_recall | 0.938/0.641/0.773 |
| Stage 5b | MetadataValidateAgent | 메타데이터 검증 + KB Evolution HITL | metadata_score, hitl_recall | avg=0.950, latency=1,171ms |
| Stage 6 | StoreRouteAgent | pgVector/GCS/Neo4j 저장 | neo4j_synced_rate, storage_synced_rate | neo4j=100.0%, gcs=100.0% |
| HITL | hitl_pending 노드 | 품질 안전망 — 사람 검토 대기 | hitl_recall, false_pass_rate | recall=100.0%, FPR=0.0% |

---

## 2. 현재 성능 점수 (L2A Accuracy)

| KPI | 현재 값 | 목표 | 상태 |
|----|--------|------|------|
| 제목 정확도 | 0.875 | 0.80 | PASS |
| 카테고리 정확도 | 0.938 | 0.85 | PASS |
| 태그 F1 | 0.641 | 0.60 | PASS |
| 엔티티 Recall | 0.773 | 0.60 | PASS |
| 파싱 품질 점수 | 0.894 | 0.85 | PASS |

---

## 3. HITL 품질 안전망

> KMS 핵심 설계: HITL은 최소화 목표가 아니라 **잘못된 지식 저장 방지 안전망**입니다.

| 지표 | 값 | 의미 |
|----|-----|------|
| HITL Recall (탐지율) | 100.0% | 문제 문서를 놓치지 않는가 |
| False Pass Rate | 0.0% | 문제 문서가 HITL 없이 저장되는 비율 |
| HITL Precision | 100.0% | HITL 중 진짜 문제인 비율 |
| False HITL Rate | 0.0% | 정상 문서가 잘못 HITL된 비율 |

---

## 4. 미측정 지표 및 개선 방향

| 지표 | 현황 | 개선 방향 |
|----|------|---------|
| PPTX 제목 추출 정확도 | 미구현 — 잘못된 제목이 HITL 미발동 | Stage 5b 임계값 강화 or Stage 1 PPTX 전처리 |
| Stage별 성공/실패율 | stage_latencies로 수집 시작 | 충분한 실행 데이터 축적 후 집계 |
| GCS storage_synced_rate | DB 플래그 기반 수집 시작 | 파이프라인 재실행 후 측정 |
| metadata_score 분포 | DB에 저장됨, 집계 시작 | 파이프라인 재실행 후 측정 |
| parent_child_integrity_rate | /details API에서 parent_chunk_id 포함 완료 | 파이프라인 재실행 후 측정 |

---

## 5. CI Gate 결과

**전체 결과: PASS**

| 지표 | 값 | 임계값 | 결과 |
|----|-----|------|------|
| completion_rate | 0.842 | 0.80 | PASS |
| category_accuracy | 0.938 | 0.85 | PASS |
| avg_tags_f1 | 0.641 | 0.60 | PASS |
| avg_entity_name_recall | 0.773 | 0.60 | PASS |
| avg_quality_score | 0.894 | 0.85 | PASS |

---

## 6. 발표용 요약 문구

- **파이프라인 성숙도**: 82.4/100점 (16/19개 문서 정확도 평가)
- **CI Gate**: PASS — 핵심 5개 KPI 전부 임계값 통과
- **HITL 안전망**: 문제 문서 탐지율(Recall) 100.0% — 잘못된 지식 저장 방지
- **자동화율**: 84.2% (HITL 검토 완료 후 100% 예상)
- **카테고리 정확도**: 0.938 / 태그 F1: 0.641

> **핵심 메시지**: KMS 파이프라인은 단순 저장이 아니라 품질 안전망을 통해
> 기업 지식이 **정확하게** DB에 적재되는지를 보장합니다.
# SESSION 8D — RAG 품질: RAGAS 신규 도입 (VS Code 복붙용)

> 목적: 사내규칙 인용(RAG)의 품질을 **RAGAS**로 정량화한다 — 인용이 **관련 있는지·충실한지**.
> 범위: `test-performance-agent/rag/`(retriever·augment) 평가만. retriever 로직은 안 바꾼다(필요 시 8B/8D 분석 후 별도). 평가 코드는 `validation/`(또는 `rag/eval/`).
> 선행: **8-0c(RAG 상시 ON) 완료 후**. RAG 기본 ON·HF 캐시 볼륨은 **8-0c에서 이미 설정됨** → 이 세션은 GCP `chunks`/`chunk_embeddings` 접속 + BGE-M3 임베더가 실제로 도는지 확인하고 **RAGAS 측정만** 한다.

> ### ✅ 현재 상태 (2026-06-09 — 착수 전 실측 확인됨)
> - **8-0c(RAG 기본 ON + HF 캐시 볼륨) 완료** — docker-compose `RAG_ENABLED=1` + `hf_cache` 볼륨. → 아래 [선행 점검]의 "RAG 켜기"는 이미 됨, **접속·임베더 동작 검증만** 하면 됨.
> - **RAG 실동작 실측 확인** — 8A 벤치에서 `rag` 단계가 실 GCP pgvector 를 때려 warm p50 ≈7.7초(네트워크 변동 큼, cold 첫 모델로드 ~수십초)로 측정됨 → retriever 가 라이브로 돈다는 증거.
> - **8-0a·8-0b·8A·8B 완료** — 테스트 306 green.
> - **⚠️ 쿼터/설치 주의** — ① RAGAS judge 가 Gemini 면 기본 `gemini-2.5-flash`(1일 ~20회) 말고 **`gemini-2.5-flash-lite`** (실측 쿼터 함정). ② `ragas` 는 새 패키지 → `pyproject.toml` 수정 + `uv add` 필요(**컨테이너 변경이라 착수 전 사용자 동의**).

## 배경 (왜)
- RAG는 제일 마지막에 붙여 **품질 평가가 사실상 없다**. "인용이 진짜 그 이슈에 맞는지", "지어내지 않았는지"를 수치로 못 댄다.
- RAGAS는 검색증강 품질의 사실상 표준: **context precision/recall**(검색이 맞는 문서를 가져왔나) + **faithfulness**(인용이 근거에 충실한가) + answer relevancy.

---

```
너는 우리 팀 LLM/검색 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3\test-performance-agent
실행: docker compose m3 컨테이너(uv). RAG_ENABLED=1 로 켜고 chunks/임베더 접속 확인 후 진행.
새 의존성: ragas (uv add). LLM/임베딩 judge는 Gemini + bge-m3(또는 사용 가능한 것)로 설정.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 사용. RAGAS 호출부는 seam 으로 분리해 mock.
- search-first 스킬로 ragas 사용법(현재 API)·Gemini judge 연동을 먼저 확인(추측 금지).

[선행 점검 — RAGAS 전 "검색이 멀쩡한가" 먼저 ★]
RAG 품질을 재기 전에 retriever 가 실제로 동작해야 한다:
- RAG_ENABLED=1 로 켜고 BGE-M3 임베더 로드·GCP chunks/chunk_embeddings 접속 성공 확인.
- 알려진 이슈 문장(예: 커버리지/N+1) 1~2개로 search_convention 스모크 — 빈 결과가 아니라
  '관련 있어 보이는' 청크가 점수와 함께 오는지 눈으로 확인.
- 빈 결과·엉뚱한 결과·접속 실패면 그게 선결 문제 → 멈추고 보고(RAGAS 점수 내기 전).
  rag/retriever 테스트가 있으면 green 확인.

[배경/문제]
rag/retriever.py 는 이슈 message → BGE-M3 임베딩 → pgvector 코사인 → small-to-big 부모 인용을 반환한다.
이게 "관련 있는 규칙을 가져오는지", "인용이 충실한지"를 측정한 적이 없다.

[목표]
1. RAG 평가셋: (이슈 message=query, 정답 사내규칙 chunk/doc) 쌍을 최소 10건 사람이 라벨링.
   - TEST/PERF 이슈 문장 → 그에 맞아야 할 사내규칙 문서 대목을 정답으로 고정.
   - 정답이 애매하면 제외(가짜 정답 금지).
2. RAGAS 측정: 평가셋에 retriever 를 돌려
   - context_precision / context_recall (검색 품질),
   - faithfulness / answer_relevancy (인용이 근거에 충실·관련).
   judge 모델은 설정으로 주입(재현 가능하게 명시).
3. 결과 표 + 약점: 낮은 지표의 케이스(엉뚱한 인용·놓친 규칙)를 원인과 함께.
4. (선택) RAG off 와 비교: 인용을 붙였을 때 코멘트가 실제로 더 근거 있는지 정성 1~2 사례.

[반드시 지킬 것 — 합격 기준]
- 정답(관련 규칙)은 사람이 확정. retriever 출력으로 정답을 만들지 말 것(순환 금지).
- DB/모델/RAGAS 미가용 시 "skip(사유)" — 가짜 점수 금지.
- 평가셋 수·judge 모델·RAGAS 버전을 리포트에 명시. 1커맨드 재실행.

[TDD]
- 평가 파이프라인 단위테스트: 가짜 retriever 결과 + 가짜 RAGAS 점수 → 집계·표 검증.
- 빈 검색결과(인용 없음) 케이스 → 해당 지표 skip/0 처리가 정직한지.

[끝나면]
- [RAGAS 지표 표 / 평가셋 수 / judge·버전 / 약점 사례 / 한계] 정리.
- 막히면 멈추고 물어봐라(특히 RAG_ENABLED·chunks 접속이 안 되면 거기서 멈추고 보고).
```

---

## 참고 (사용자용 메모)
- 이건 **새 라이브러리(ragas) 추가** 작업이라 8개 중 제일 무거움. 8A·8B 는 이미 끝났으니 이제 해도 됨.
- 발표에선 "RAG 인용을 그냥 붙인 게 아니라 **RAGAS로 관련성·충실도를 수치화**했다"가 차별점입니다.
- (해결됨) RAG 기본 ON·HF 캐시 볼륨은 8-0c 에서 설정 완료 → 더는 매번 수 GB 재다운로드 안 함(cold 첫 로드만 수십초).
- 실측 함정: RAGAS judge 가 Gemini 면 `gemini-2.5-flash-lite` 로 (기본 flash 1일 20회 쿼터).

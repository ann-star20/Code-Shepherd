# SESSION 8-0c — RAG 상시 ON (제품 기본값) + HF 캐시 볼륨 (VS Code 복붙용)

> **시스템 완성 3단계 중 3번째.** 선행: 없음(독립 — 8-0a·8-0b와 순서 무관, 단 8A·8B·8D 평가 전엔 끝). 후행: 8D(RAGAS)가 이걸 전제.
> 목적: RAG를 "기본 ON"으로 바꿔, **PR 리뷰마다 사내규칙 인용이 항상 들어가게** 한다. 제품 목표가 "RAG가 항상 리뷰에 포함"인데 지금은 기본 OFF 토글이라 어긋난다.
> 범위: RAG 기본값(`RAG_ENABLED`)·docker-compose·.env·HF 캐시 볼륨. retriever/augment **로직은 안 바꾼다**(품질 평가는 8D).
> 선행: 없음. (8-0a·8-0b와 독립이라 아무 때나, 단 평가 전에)

## 배경 (왜)
- RAG가 `RAG_ENABLED` 기본 OFF 토글이다. 제품 목표 = **항상 사내규칙을 찾아 근거 인용** → 기본 OFF는 목표와 어긋남. 평가(8D RAGAS)도 RAG가 켜져 있어야 의미 있다.
- ★ 주의: **토글 자체를 없애면 안 된다.** 단위테스트가 BGE-M3(수GB)·GCP 접속 없이 돌아야 하기 때문. 올바른 그림: **실제 실행 기본 ON + 테스트는 가짜 retriever 주입(seam 유지) + 모델/DB 없으면 정직하게 빈 인용.** "기본을 켜는" 것이지 "토글 제거"가 아님.
- 함정(메모리): RAG 켜면 임베딩 모델 캐시가 없을 때 매 recreate 마다 수GB 재다운로드 → HF 캐시 볼륨 필수.

---

```
너는 우리 팀 백엔드/인프라 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
실행 환경: docker compose 의 m3 컨테이너(uv). 테스트는 컨테이너 안에서 uv run --extra test pytest.

[작업 방식]
- TDD로(테스트 먼저). superpowers:test-driven-development 스킬 사용.
- 변경은 설정/기본값 중심(surgical). retriever/augment 로직은 손대지 않는다(품질은 8D).

[선행 점검]
- 현재 RAG 게이트 위치 확인: main.py(run)·app/main.py(_review) 의 `if os.getenv("RAG_ENABLED")`.
- 기존 RAG wiring 테스트 green 확인(test_main_rag_wiring, test_review_endpoint 의 RAG 케이스).
- (가능하면) RAG_ENABLED=1 로 켜고 BGE-M3 로드·GCP chunks/chunk_embeddings 접속, 알려진 이슈 문장
  1~2개로 search 스모크 — 인용이 점수와 함께 오는지. 안 되면 그 사실을 보고(8D 선행과도 직결).

[목표 — RAG 기본 ON]
1. 기본값 전환: docker-compose 와 .env(.env.example 포함)에 RAG_ENABLED=1 설정.
   - main.py/app.main.py 의 RAG 게이트는 "기본 ON" 의미가 되도록 정리하되,
     테스트에서 끌 수 있게 seam 유지(monkeypatch.delenv 로 off 되는 현재 테스트 패턴 보존).
2. HF 임베딩 캐시 볼륨: docker-compose 의 m3 서비스에 HuggingFace 캐시 볼륨(예: ~/.cache/huggingface)
   마운트 추가 — recreate 마다 모델 재다운로드 방지.
3. 정직성: 모델/DB 미가용 시 RAG 는 빈 인용으로 안전 통과(가짜 인용 금지). 기존 폴백 유지.

[반드시 지킬 것 — 합격 기준]
- 실제 실행 시 RAG 기본 ON(이슈에 rag_context 인용 시도)·테스트는 seam 으로 off 가능, 둘 다 동작.
- 기존 테스트 전부 여전히 green(회귀 0). 단위테스트가 BGE-M3·GCP 를 실제로 때리지 않는지 확인(느려지면 잘못된 것).
- 캐시 볼륨으로 재다운로드가 사라지는지 확인(2회 recreate 비교).

[TDD]
- RAG on(가짜 retriever) → rag_context 채워짐 / 테스트 off → 빈 채 안전, 둘 다 검증.

[끝나면 — 8D 로 인수인계]
- [RAG 기본 ON 상태 / 캐시 볼륨 설정 / 스모크(인용 오는지) / 회귀 테스트] 정리.
- 다음(8D): RAG 가 이미 ON 이므로 선행 생략 → RAGAS 측정만.
- 막히면 멈추고 물어봐라(특히 chunks 접속·모델 로드가 안 되면 거기서 멈추고 보고).
```

---

## 참고 (사용자용 메모)
- 3단계 중 **3번째·제일 가벼움**. 8-0a·8-0b와 순서 상관없어요(독립). 평가(특히 8D) 전에만 끝나면 됨.
- 핵심: "토글을 없애는 게 아니라 **기본을 켜는** 것" — 테스트는 여전히 RAG 없이 빨리 돌아야 하니까요.
- 캐시 볼륨을 같이 넣어야 매번 수GB 재다운로드를 안 합니다(전에 겪은 함정).

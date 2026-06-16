# Dev3 코드리뷰 에이전트 (5일 MVP)

PR diff를 받아 **사내 KMS 컨벤션에 근거해서만** 리뷰 코멘트를 다는 에이전트.
일반 코드리뷰 AI는 세상 기준으로 보고, 이 에이전트는 **우리 회사 기준**으로 본다. 그리고 모르면 모른다고 한다.

- 마스터 브리프: [DEV3_MVP_KICKOFF.md](DEV3_MVP_KICKOFF.md) · PRD/아키텍처: [docs/PRD.md](docs/PRD.md) · 계약: [contracts/](contracts/README.md)

## 차별점 3가지 (시연으로 증명)

1. **근거 인용** — 모든 지적에 rule_id·§·출처. 인용 문구는 코퍼스 원문과 자동 대조(환각 검증).
2. **지침공백 정직 보고** — 지침이 없으면 지어내지 않고 gap 리포트 + 신규 지침 제안.
3. **핫스왑** — 지침 문서 수정 + `make reindex` 만으로 코드 변경 없이 판정이 바뀜.

## 빠른 시작

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# repo 루트 .env 에 키 배치 (.env_example 참고 — 값은 절대 커밋 금지):
#   ANTHROPIC_API_KEY / OPENAI_API_KEY / GITHUB_TOKEN / GITHUB_WEBHOOK_SECRET
# 임베딩 기본은 bge-m3 — ollama 기동 + `ollama pull bge-m3` 필요 (폴백: EMBEDDING_PROVIDER=openai)

make reindex     # corpus → Chroma 인덱싱 (핫스왑도 이 명령)
make eval        # 골든셋 12 PR 평가 → 탐지율/오탐/환각률/지침공백 리포트
make demo        # Streamlit 데모 (시연 절차: docs/DEMO_SCRIPT.md)
make webhook     # Flask 웹훅 서버 — ngrok http 5000 으로 공개

# 팀 스택 m3 drop-in (port 8004, M3ReviewRequest/Response 계약):
.venv\Scripts\uvicorn src.adapters.http_adapter:app --port 8004
docker build -t dev3-m3:latest .   # 도커 절차: docs/INTEGRATION_GUIDE.md
```

Windows에 make가 없으면 동일 타깃의 `.\make.bat eval` 형태로 실행.

## 팀 통합 (D5)

- 통합 준비 상태: [docs/INTEGRATION_READINESS.md](docs/INTEGRATION_READINESS.md) — 게이트 G1~G4 집계
- compose 교체 절차(팀 파일 무수정): [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)
- m1→m3 계약 정본 분석: [docs/FRONTEND_INTEGRATION.md](docs/FRONTEND_INTEGRATION.md)
- 최종 수치: **골든셋 12/12 PASS** (탐지 6/6 · 오탐 0 · 환각 0% · 지침공백 2/2, bge-m3 1024d)

## 구조

```
contracts/   계약 스키마 (수정 금지 · 게이트 2)     src/nodes/   노드 6개 (⓪~⑤)
corpus/      사내 컨벤션 마크다운 5~8개            src/graph.py LangGraph 조립
golden/      골든셋 12 PR (수정 금지 · 게이트 1)    src/adapters webhook / streamlit
eval/        평가 하네스 (make eval)              src/ingestion.py  corpus→Chroma
app/         Streamlit UI                        examples/    LangGraph 버전 기준 예제
```

모델: 전 노드 `claude-sonnet-4-6` · temperature 0 · 임베딩 기본 `bge-m3`(ollama, 1024d)·폴백 `text-embedding-3-small` · 설정은 [src/config.py](src/config.py) 한 곳.

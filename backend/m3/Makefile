# Dev3 코드리뷰 에이전트 — make eval / make reindex / make demo (브리프 §5.1)
# Windows에 make 없으면 동일 타깃의 .\make.bat 사용 (CLAUDE.md 참고)

PY ?= .venv/Scripts/python.exe

.PHONY: eval eval-one eval-failed reindex demo webhook test

eval:
	$(PY) -m eval.harness

eval-one:           # make eval-one PR=pr_003
	$(PY) -m eval.harness --only $(PR)

eval-failed:        # 직전 실패 케이스만 (브리프 §9.2)
	$(PY) -m eval.harness --failed

reindex:            # corpus → Chroma 핫스왑 (원커맨드)
	$(PY) -m src.ingestion

demo:
	$(PY) -m streamlit run app/streamlit_app.py

webhook:
	$(PY) -m src.adapters.webhook_adapter

test:
	$(PY) -m pytest tests/ -q

"""T2 파이프라인 수동 실행 스크립트 — Cloud SQL의 review_issue 1건을 실제로 가져와
RAG 검색 + 카드 생성을 거쳐 curriculum_plan에 저장까지 end-to-end로 확인한다.

단위 테스트(tests/test_pipeline.py)는 mock 기반이라 실제 Cloud SQL/Ollama/Gemini를 타지 않는다.
이 스크립트는 그 파이프라인이 실제 환경에서도 동작하는지 손으로 한 번 돌려보기 위한 것이다.

사용 전 준비물:
  - Ollama 로컬 실행 + bge-m3 모델 (embed_query가 호출)
  - .env에 GEMINI_API_KEY 설정 (build_card가 Gemini 호출)
  - Cloud SQL 접속 정보(.env의 DB_HOST/DB_NAME/DB_USER/DB_PASSWORD 등)

사용법:
  python scripts/run_pipeline_for_issue.py                     # 가장 최근 review_issue로 실행
  python scripts/run_pipeline_for_issue.py <review_issue_id>   # 특정 이슈 UUID로 실행
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path  # m4 스크립트에서 루트 .env 경로를 계산하기 위해 필요

# m4 스크립트 전용 처리: Windows 콘솔(cp1252)이 한글/특수문자를 못 찍어서 나는 UnicodeEncodeError 방지 (embed_kms_docs.py와 동일 패턴)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # m4 스크립트가 공통 .env를 직접 로드하기 위해 필요 (embed_kms_docs.py와 동일 패턴)
from sqlalchemy import select

# m4 스크립트 전용 처리: cwd가 backend/m4일 때도 루트 .env(DB_HOST 등 공통 설정)를 찾도록 경로를 명시
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from app.kms.search_adapter import PgvectorAdapter
from app.models.review_issue import ReviewIssue
from app.pipeline.learn_pipeline import generate_card
from shared.config import get_settings
from shared.db import create_engine_from_url, create_session_factory


async def _load_issue(session, issue_id: uuid.UUID | None) -> ReviewIssue | None:
    if issue_id is not None:
        return await session.get(ReviewIssue, issue_id)
    result = await session.execute(
        select(ReviewIssue).order_by(ReviewIssue.created_at.desc()).limit(1)
    )
    return result.scalars().first()


async def main(issue_id: uuid.UUID | None) -> None:
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        issue = await _load_issue(session, issue_id)
        if issue is None:
            print("review_issue를 찾지 못했습니다 — Cloud SQL에 mock 데이터가 있는지 확인하세요.")
            await engine.dispose()
            return

        print(f"[1/3] review_issue 로드 — id={issue.id} keyword={issue.keyword} severity={issue.severity}")

        adapter = PgvectorAdapter(session)
        plan = await generate_card(issue, adapter)
        print(f"[2/3] generate_card 완료 — status={plan.status} llm_fallback={plan.llm_fallback}")

        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        print(f"[3/3] curriculum_plan 저장 완료 — plan_id={plan.id}")

        print("\n--- 결과 ---")
        print(f"status:        {plan.status}")
        print(f"llm_fallback:  {plan.llm_fallback}")
        print(f"error_message: {plan.error_message}")
        if plan.card_content:
            print("card_content:")
            print(json.dumps(plan.card_content, ensure_ascii=False, indent=2))

    await engine.dispose()


if __name__ == "__main__":
    raw_id = sys.argv[1] if len(sys.argv) > 1 else None
    parsed_id = uuid.UUID(raw_id) if raw_id else None
    asyncio.run(main(parsed_id))

"""[삭제 가능 — mock 데이터 전용] 1회성 데이터 보정 스크립트.

review_issue.code_snippet에 수동 SQL INSERT 시 잘못 들어간 리터럴 백슬래시+n(\\n)을
실제 줄바꿈 문자로 치환한다 (T3 E2E 검증 중 발견, D34: "코딩 에이전트 미연동 → 직접 INSERT").

코딩 에이전트가 연동되어 POST /api/ingest로 JSON 데이터가 정상 유입되기 시작하면
(JSON 파싱 과정에서 \\n이 자동으로 실제 줄바꿈으로 디코딩되므로) 이 문제 자체가
재발하지 않는다 — 더 이상 review_issue를 수동 SQL INSERT로 채울 일이 없어지면
이 스크립트는 통째로 삭제해도 된다.

주의: 아래 raw SQL UPDATE 우회(또는 비슷한 패턴)는 이 스크립트만의 문제가 아니라
review_issue 테이블 자체의 구조적 이슈이므로, 이 파일을 지워도 별도로 챙겨야 한다
(자세한 내용은 본문 주석 참조).
"""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from sqlalchemy import select, text

from app.models.review_issue import ReviewIssue
from shared.config import get_settings
from shared.db import create_engine_from_url, create_session_factory

# [삭제 가능 — mock 데이터 전용] 수동 SQL INSERT 특유의 손상 패턴. 정상 JSON ingest에서는 발생하지 않음
LITERAL_BACKSLASH_N = chr(92) + "n"


async def main():
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    sf = create_session_factory(engine)
    async with sf() as session:
        result = await session.execute(select(ReviewIssue).where(ReviewIssue.code_snippet.is_not(None)))
        issues = result.scalars().all()
        fixed = 0
        for issue in issues:
            if LITERAL_BACKSLASH_N in issue.code_snippet:
                # [삭제 불가 — 구조적 이슈, mock 데이터와 무관] review_issue.pull_request_id/user_id가
                # m4가 소유하지 않은 테이블(pull_requests/users, m4 Base.metadata에 미등록)을 FK로
                # 참조해서, ORM session.add()/flush 시 NoReferencedTableError(table sort 실패)가 난다.
                # POST /api/ingest 구현 시에도 ORM으로 review_issue를 INSERT하면 동일하게 실패하므로
                # 그쪽도 raw SQL(파라미터 바인딩) 또는 FK 매핑 보완이 필요할 것 — 이 스크립트를 지워도
                # 이 이슈 자체는 별도로 트래킹해야 한다.
                await session.execute(
                    text("UPDATE review_issue SET code_snippet = :snippet WHERE id = :id"),
                    {"snippet": issue.code_snippet.replace(LITERAL_BACKSLASH_N, "\n"), "id": issue.id},
                )
                fixed += 1
                print(f"[fix] {issue.id} ({issue.keyword})")
        await session.commit()
        print(f"\n총 {len(issues)}건 중 {fixed}건 치환 완료")
    await engine.dispose()


asyncio.run(main())

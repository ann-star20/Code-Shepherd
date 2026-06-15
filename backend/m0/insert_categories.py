"""평가용 카테고리 DB 삽입 스크립트 (컨테이너 내부에서 실행)"""
import asyncio
import sys
sys.path.insert(0, '/app/_shared')

CATEGORIES = {
    'AI_ML': 'LLM, RAG, 임베딩, 벡터검색, MLOps, 생성형 AI, 머신러닝, 딥러닝',
    'HR_EDUCATION': '온보딩, 신입교육, 취업규칙, 인사정책, 근로조건, 커리어 성장',
    'DEVELOPMENT': 'API 설계, REST, 코드리뷰, 코딩컨벤션, SW 설계, 아키텍처',
    'SECURITY_COMPLIANCE': '보안정책, 암호화, 컴플라이언스, 개인정보보호, 데이터 거버넌스',
    'PROJECT_MANAGEMENT': '프로젝트관리, 스프린트, 회고, KPT, 애자일, 스크럼',
    'OPERATION': '운영, 장애보고, 인시던트, 모니터링, CI/CD, 포스트모텀, SLA',
    '기타': '위 카테고리에 해당하지 않는 경우',
}

async def insert():
    from shared.db import get_session_factory
    from sqlalchemy import text
    session_factory = get_session_factory()
    async with session_factory() as session:
        async with session.begin():
            for name, desc in CATEGORIES.items():
                await session.execute(
                    text('INSERT INTO categories (name, description) VALUES (:n, :d) ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description'),
                    {'n': name, 'd': desc}
                )
                print(f'registered: {name}')

asyncio.run(insert())
print('완료')

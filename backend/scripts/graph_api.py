import uvicorn
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Security Knowledge Graph API")
router = APIRouter()


# 스키마 선언
class ConceptRequest(BaseModel):
    concepts: List[str]


# API 엔드포인트
@router.post("/api/v1/concepts/subgraph")
async def get_concepts_subgraph(payload: ConceptRequest):
    # (원래는 여기에 Neo4j 드라이버 로직이 들어갑니다)
    # mock_data를 리턴한다고 가정합니다.
    mock_data = {
        "concepts": [{"id": "11", "name": "SQLi", "cwe_id": "CWE-89"}],
        "mechanisms": [
            {"id": "10", "source": "11", "target": "1", "type": "BELONGS_TO"}
        ],
        # 명시적으로 properties를 안 넣으면 FastAPI가 알아서 제외하고 출력합니다.
    }
    return mock_data


# 라우터 등록
app.include_router(router)

if __name__ == "__main__":
    # 백엔드 로컬 서버 기동 (8005번 포트)
    # 실제 실행 명령어: python main.py
    uvicorn.run("main:app", host="127.0.0.1", port=8005, reload=True)

"""Dev3 설정 상수 — 모든 임계값·타임아웃·모델명은 여기서 관리 (하드코딩 금지)."""
import os

# --- 테스트 커버리지 ---
COVERAGE_THRESHOLD: float = float(os.getenv("COVERAGE_THRESHOLD", "0.80"))

# --- N+1 탐지: DB 호출 메서드명 (좁은 집합으로 시작 — PRD §5.4, §18)
# .get/.all/.first/.count는 일반 메서드 이름과 충돌 → 제외
DB_CALL_NAMES: frozenset[str] = frozenset(
    os.getenv("DB_CALL_NAMES", "query,execute,filter,fetchone,fetchall,scalar").split(",")
)

# --- 복잡도 탐지: 중첩 루프 깊이 ---
COMPLEXITY_MINOR_DEPTH: int = int(os.getenv("COMPLEXITY_MINOR_DEPTH", "2"))
COMPLEXITY_MAJOR_DEPTH: int = int(os.getenv("COMPLEXITY_MAJOR_DEPTH", "3"))

# --- 타임아웃 (초) ---
AGENT_TIMEOUT_S: int = int(os.getenv("AGENT_TIMEOUT_S", "30"))
DOCKER_TIMEOUT_S: int = int(os.getenv("DOCKER_TIMEOUT_S", "120"))
COV_TIMEOUT_S: int = int(os.getenv("COV_TIMEOUT_S", "15"))
LLM_TIMEOUT_S: int = int(os.getenv("LLM_TIMEOUT_S", "8"))

# --- LLM (Gemini 2.5 Flash로 통일) ---
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
LLM_MAX_RETRY: int = int(os.getenv("LLM_MAX_RETRY", "2"))
LLM_CONFIDENCE_MIN: float = float(os.getenv("LLM_CONFIDENCE_MIN", "0.7"))

# --- 관찰(LangSmith) ---
LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "dev3-test-performance")

# --- 검증 ---
FALSE_ALARM_THRESHOLD: float = float(os.getenv("FALSE_ALARM_THRESHOLD", "0.10"))
SANDBOX_IMAGE: str = os.getenv("SANDBOX_IMAGE", "dev3-sandbox")

# --- RAG (사내 컨벤션 검색 — B안: Dev3 직접 임베딩·pgvector 검색) ---
# 절대규칙(위험 1): 저장=검색 임베딩 모델 동일 → rag/embedder.py 한 곳에서만 사용.
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "BAAI/bge-m3")  # 저장·검색 공유 모델
EMBED_DIM: int = int(os.getenv("EMBED_DIM", "1024"))        # BGE-M3 벡터 차원
RAG_SCORE_MIN: float = float(os.getenv("RAG_SCORE_MIN", "0.5"))  # 환각 방지 임계 (위험·정직)
KMS_SEARCH_URL: str = os.getenv("KMS_SEARCH_URL", "")  # (A안 잔재·미사용, 하위호환 위해 유지)

"""pr-comment-agent 설정 상수 및 환경변수."""
import os

# ── verdict 판정 임계값 ──
CRITICAL_ESCALATE_THRESHOLD: int = 1
MAJOR_REWORK_THRESHOLD: int = 3

# ── 개발자 스킬 레벨 ──
SKILL_LEVELS: frozenset[str] = frozenset({"junior", "mid", "senior"})

# ── LLM (Gemini 2.5 Flash로 통일) ──
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# ── 외부 서비스 ──
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.getenv("GITHUB_REPO", "")  # "owner/repo"

# ── 관찰(LangSmith) ──
LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "dev3-pr-comment")

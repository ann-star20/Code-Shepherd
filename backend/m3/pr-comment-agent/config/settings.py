"""pr-comment-agent 설정 상수 및 환경변수."""
import os

# ── verdict 판정 임계값 ──
# F3: m3 탐지기는 Critical 을 만들지 않아(전부 Major/Minor) Major 2건 실결함 PR이
# 임계 3에서 lgtm 으로 샜다(8C 실측 80%, 불일치 2건 모두 이 패턴) → 2로 보정.
CRITICAL_ESCALATE_THRESHOLD: int = 1
MAJOR_REWORK_THRESHOLD: int = 2

# ── 개발자 스킬 레벨 ──
SKILL_LEVELS: frozenset[str] = frozenset({"junior", "mid", "senior"})

# ── LLM (Gemini 2.5 Flash로 통일) ──
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# ── 외부 서비스 ──
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.getenv("GITHUB_REPO", "")  # "owner/repo"

# ── 리뷰 대시보드 링크 (코멘트 footer) — 데모=localhost, 배포 시 env 로 주입 ──
# 실제 사용 시점 값은 llm_refiner._dashboard_url() 이 env 에서 직접 읽는다.
REVIEW_DASHBOARD_URL: str = os.getenv("REVIEW_DASHBOARD_URL", "http://localhost:5173/review")

# ── 관찰(LangSmith) ──
LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "dev3-pr-comment")

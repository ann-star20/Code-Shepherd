"""
Task 4-a/b/c/d 테스트 — LangGraph 노드 단위 테스트

모든 테스트는 Mock 기반으로 실제 DB/LLM/CLI 도구 없이 통과해야 한다. (CLAUDE.md §13)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# ── Task 4-a: run_tools 노드 ────────────────────────────────────────────────

# TypedDict는 일반 dict처럼 생성해야 함
SAMPLE_STATE = {
    "task_id": "uuid-001",
    "pr_id": "1",
    "pr_diff": "+++ b/src/auth.py\n+query = sql + user_input",
    "developer_id": "dev-001",
    "skill_level": "junior",
    "tech_stack": ["python"],
    "static_raw": [],
    "security_raw": [],
    "enriched": [],
    "final_output": [],
}


@pytest.mark.asyncio
async def test_run_tools_node_populates_raw():
    """run_tools_node가 static_raw, security_raw를 채우는지 확인"""
    from dev2.nodes.run_tools import run_tools_node

    mock_result = {
        "static": [
            {
                "severity": "Major", "line": 1, "file": "src/auth.py",
                "message": "복잡도 높음", "rule_id": "SA-001",
                "suggestion": "분리하세요", "similar_issues": [],
            }
        ],
        "security": [
            {
                "severity": "Critical", "line": 2, "file": "src/auth.py",
                "message": "SQL 인젝션", "rule_id": "SEC-B608",
                "suggestion": "파라미터 바인딩 사용", "similar_issues": [],
            }
        ],
    }

    with patch(
        "dev2.nodes.run_tools._run_for_language",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await run_tools_node(SAMPLE_STATE)

    assert len(result["static_raw"]) > 0
    assert len(result["security_raw"]) > 0
    assert result["static_raw"][0]["severity"] == "Major"
    assert result["security_raw"][0]["rule_id"] == "SEC-B608"


@pytest.mark.asyncio
async def test_run_tools_handles_exception():
    """_run_for_language 예외 시 해당 언어 결과 제외 (빈 리스트 반환)"""
    from dev2.nodes.run_tools import run_tools_node

    with patch(
        "dev2.nodes.run_tools._run_for_language",
        new_callable=AsyncMock,
        side_effect=Exception("tool crash"),
    ):
        result = await run_tools_node(SAMPLE_STATE)

    # 예외 발생 시 빈 리스트로 안전하게 처리 (CLAUDE.md §12)
    assert result["static_raw"] == []
    assert result["security_raw"] == []


@pytest.mark.asyncio
async def test_run_tools_extracts_files_from_diff():
    """pr_diff에서 변경 파일 목록을 올바르게 추출하는지 확인"""
    from dev2.nodes.run_tools import _extract_changed_files

    diff = (
        "+++ b/src/auth.py\n"
        "+++ b/src/app.js\n"
        "+++ b/README.md\n"        # .md는 지원 안 됨 → 제외
        "+++ b/styles/main.css\n"
        "--- a/old_file.py\n"       # ---로 시작하는 줄 → 제외
    )
    files = _extract_changed_files(diff)
    assert "src/auth.py" in files
    assert "src/app.js" in files
    assert "styles/main.css" in files
    # .md 제외, --- 줄 제외 확인
    assert "README.md" not in files
    assert len([f for f in files if "old_file" in f]) == 0


@pytest.mark.asyncio
async def test_run_tools_empty_diff():
    """빈 diff → 빈 결과 (예외 없음)"""
    from dev2.nodes.run_tools import run_tools_node

    empty_state = {**SAMPLE_STATE, "pr_diff": ""}
    result = await run_tools_node(empty_state)
    assert result["static_raw"] == []
    assert result["security_raw"] == []


# ── Task 4-c: llm_judge 노드 ────────────────────────────────────────────────

# llm_judge 테스트용 enriched 이슈 샘플
SAMPLE_ENRICHED = [
    {
        "severity": "Critical",
        "line": 10,
        "file": "src/auth.py",
        "message": "SQL 파라미터 미처리",
        "rule_id": "SEC-B608",
        "suggestion": "파라미터 바인딩 사용",
        "similar_issues": [
            {"pr_id": "98", "similarity": 0.94, "message": "SQL 인젝션 패턴"},
        ],
    },
    {
        "severity": "Major",
        "line": 42,
        "file": "src/service.py",
        "message": "순환복잡도 15",
        "rule_id": "CC-001",
        "suggestion": "함수 분리 필요",
        "similar_issues": [],
    },
    {
        "severity": "Minor",
        "line": 5,
        "file": "src/utils.py",
        "message": "변수명 snake_case 위반",
        "rule_id": "STYLE-001",
        "suggestion": "snake_case 사용",
        "similar_issues": [],
    },
]


@pytest.mark.asyncio
async def test_llm_judge_mock_mode():
    """USE_MOCK_LLM=true → 실제 LLM 호출 없이 Mock 응답 반환"""
    from dev2.nodes.llm_judge import llm_judge_node

    state = {
        **SAMPLE_STATE,
        "enriched": SAMPLE_ENRICHED,
        "skill_level": "junior",
    }

    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}):
        result = await llm_judge_node(state)

    enriched = result["enriched"]
    assert len(enriched) == 3

    # Critical/Major: llm_judged=True (Mock이라도 처리됨)
    critical_issue = next(i for i in enriched if i["severity"] == "Critical")
    assert critical_issue["llm_judged"] is True
    assert critical_issue["llm_model"] == "claude-sonnet-4-6"

    major_issue = next(i for i in enriched if i["severity"] == "Major")
    assert major_issue["llm_judged"] is True
    assert "haiku" in major_issue["llm_model"]

    # Minor: LLM 생략 (llm_judged=False, llm_model=None)
    minor_issue = next(i for i in enriched if i["severity"] == "Minor")
    assert minor_issue["llm_judged"] is False
    assert minor_issue["llm_model"] is None


@pytest.mark.asyncio
async def test_llm_judge_minor_skipped():
    """Minor severity → LLM 호출 없이 그대로 통과"""
    from dev2.nodes.llm_judge import llm_judge_node

    minor_only = [
        {
            "severity": "Minor",
            "line": 1,
            "file": "app.py",
            "message": "코드 스멜",
            "rule_id": "STYLE-001",
            "suggestion": "개선 권장",
            "similar_issues": [],
        }
    ]
    state = {**SAMPLE_STATE, "enriched": minor_only, "skill_level": "senior"}

    # Minor만 있으면 LLM 호출이 일어나지 않아야 함
    with patch("dev2.nodes.llm_judge._call_llm_with_retry") as mock_llm:
        with patch.dict("os.environ", {"USE_MOCK_LLM": "false"}):
            result = await llm_judge_node(state)

    # LLM 호출 없음 확인
    mock_llm.assert_not_called()
    assert result["enriched"][0]["llm_judged"] is False
    assert result["enriched"][0]["llm_model"] is None
    # 원래 severity 유지
    assert result["enriched"][0]["severity"] == "Minor"


@pytest.mark.asyncio
async def test_llm_judge_empty_enriched():
    """enriched가 비어 있으면 빈 리스트 반환 (예외 없음)"""
    from dev2.nodes.llm_judge import llm_judge_node

    state = {**SAMPLE_STATE, "enriched": [], "skill_level": "junior"}
    result = await llm_judge_node(state)
    assert result["enriched"] == []


@pytest.mark.asyncio
async def test_llm_judge_fallback_on_parse_failure():
    """LLM 응답 파싱 2회 실패 → 원래 severity 유지 (CLAUDE.md §12 fallback)"""
    from dev2.nodes.llm_judge import llm_judge_node

    critical_only = [
        {
            "severity": "Critical",
            "line": 10,
            "file": "src/auth.py",
            "message": "SQL 인젝션",
            "rule_id": "SEC-B608",
            "suggestion": "파라미터 바인딩",
            "similar_issues": [],
        }
    ]
    state = {**SAMPLE_STATE, "enriched": critical_only, "skill_level": "junior"}

    # _call_llm_with_retry가 {} 반환 (파싱 실패 시뮬레이션)
    with patch(
        "dev2.nodes.llm_judge._call_llm_with_retry",
        new_callable=AsyncMock,
        return_value={},   # 빈 dict = 파싱 실패
    ):
        with patch.dict("os.environ", {"USE_MOCK_LLM": "false"}):
            result = await llm_judge_node(state)

    issue = result["enriched"][0]
    # fallback: 원래 severity "Critical" 유지
    assert issue["severity"] == "Critical"
    assert issue["llm_judged"] is False
    # 원래 메시지도 유지
    assert issue["message"] == "SQL 인젝션"


@pytest.mark.asyncio
async def test_llm_judge_individual_exception_continues():
    """개별 이슈 예외 시 해당 이슈만 fallback, 나머지 정상 처리"""
    from dev2.nodes.llm_judge import llm_judge_node

    two_issues = [
        {
            "severity": "Critical", "line": 1, "file": "a.py",
            "message": "이슈A", "rule_id": "A-001",
            "suggestion": "수정A", "similar_issues": [],
        },
        {
            "severity": "Critical", "line": 2, "file": "b.py",
            "message": "이슈B", "rule_id": "B-001",
            "suggestion": "수정B", "similar_issues": [],
        },
    ]
    state = {**SAMPLE_STATE, "enriched": two_issues, "skill_level": "mid"}

    call_count = 0

    async def flaky_judge(issue, developer_level, use_mock, tech_stack=None):
        """첫 번째 이슈만 예외, 두 번째는 정상"""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("첫 번째 이슈 처리 실패")
        return {**issue, "llm_judged": True, "llm_model": "claude-sonnet-4-6", "llm_rationale": "정상"}

    with patch("dev2.nodes.llm_judge._judge_single_issue", side_effect=flaky_judge):
        with patch.dict("os.environ", {"USE_MOCK_LLM": "false"}):
            result = await llm_judge_node(state)

    assert len(result["enriched"]) == 2
    # 첫 번째: fallback (예외)
    assert result["enriched"][0]["llm_judged"] is False
    # 두 번째: 정상 처리
    assert result["enriched"][1]["llm_judged"] is True


# ── Task 4-d: vector_search 노드 ────────────────────────────────────────────

# vector_search 테스트용 raw 이슈 샘플
RAW_ISSUES_SAMPLE = [
    {
        "severity": "Critical",
        "line": 10,
        "file": "src/auth.py",
        "message": "SQL 파라미터 미처리 — 인젝션 위험",
        "rule_id": "SEC-B608",
        "suggestion": "파라미터 바인딩 사용",
    },
    {
        "severity": "Major",
        "line": 42,
        "file": "src/service.py",
        "message": "순환복잡도 15 감지",
        "rule_id": "CC-001",
        "suggestion": "함수 분리 필요",
    },
]


@pytest.mark.asyncio
async def test_vector_search_mock_mode_enriches_issues():
    """USE_MOCK_LLM=true → Mock 검색으로 similar_issues 주입 확인"""
    from dev2.nodes.vector_search import vector_search_node

    state = {
        **SAMPLE_STATE,
        "static_raw": [RAW_ISSUES_SAMPLE[1]],  # 복잡도 이슈
        "security_raw": [RAW_ISSUES_SAMPLE[0]],  # SQL 이슈
    }

    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}):
        result = await vector_search_node(state)

    enriched = result["enriched"]
    assert len(enriched) == 2  # static_raw 1 + security_raw 1

    # 모든 이슈에 similar_issues 필드가 추가되어야 함
    for issue in enriched:
        assert "similar_issues" in issue

    # SQL 관련 이슈 → Mock에서 SQL 유사 사례 반환
    sql_issue = next(i for i in enriched if "SQL" in i["message"] or "sql" in i["message"].lower())
    assert len(sql_issue["similar_issues"]) > 0
    # similar_issues 각 항목 형식 확인 (severity_judge.py가 기대하는 형식)
    for case in sql_issue["similar_issues"]:
        assert "pr_id" in case
        assert "similarity" in case
        assert "message" in case


@pytest.mark.asyncio
async def test_vector_search_empty_raw():
    """static_raw, security_raw 모두 비어 있으면 빈 enriched 반환 (예외 없음)"""
    from dev2.nodes.vector_search import vector_search_node

    state = {**SAMPLE_STATE, "static_raw": [], "security_raw": []}
    result = await vector_search_node(state)
    assert result["enriched"] == []


@pytest.mark.asyncio
async def test_vector_search_unknown_pattern_returns_empty_similar():
    """알 수 없는 이슈 패턴 → similar_issues=[] (CLAUDE.md §12 — 예외 없음)"""
    from dev2.nodes.vector_search import vector_search_node

    unknown_issue = {
        "severity": "Minor",
        "line": 1,
        "file": "app.py",
        "message": "완전히 알 수 없는 패턴 xyzzy",
        "rule_id": "UNKNOWN",
        "suggestion": "확인 필요",
    }
    state = {**SAMPLE_STATE, "static_raw": [unknown_issue], "security_raw": []}

    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}):
        result = await vector_search_node(state)

    assert len(result["enriched"]) == 1
    assert result["enriched"][0]["similar_issues"] == []  # 빈 리스트 (예외 없음)


@pytest.mark.asyncio
async def test_vector_search_db_failure_fallback():
    """DB 연결 실패 → Mock 검색으로 fallback (파이프라인 중단 없음)"""
    from dev2.nodes.vector_search import vector_search_node

    state = {
        **SAMPLE_STATE,
        "static_raw": [RAW_ISSUES_SAMPLE[0]],
        "security_raw": [],
    }

    # USE_MOCK_LLM=false지만 DB 연결 실패 → fallback
    with patch("dev2.nodes.vector_search._get_pool", return_value=None):
        with patch.dict("os.environ", {"USE_MOCK_LLM": "false"}):
            result = await vector_search_node(state)

    # DB 없어도 예외 없이 결과 반환 (similar_issues가 있거나 빈 리스트)
    assert len(result["enriched"]) == 1
    assert "similar_issues" in result["enriched"][0]


@pytest.mark.asyncio
async def test_vector_search_mock_embedding_deterministic():
    """동일 텍스트 → 동일 Mock 임베딩 (결정적, 테스트 재현성)"""
    from dev2.nodes.vector_search import _mock_embedding
    import os

    dim = int(os.getenv("PGVECTOR_DIMENSION", "768"))
    vec1 = _mock_embedding("SQL 파라미터 미처리")
    vec2 = _mock_embedding("SQL 파라미터 미처리")

    assert vec1 == vec2          # 결정적 — 동일 입력 → 동일 출력
    assert len(vec1) == dim       # EMBEDDING_DIM 길이 (CLAUDE.md §8)
    assert all(isinstance(x, float) for x in vec1)  # float 타입


@pytest.mark.asyncio
async def test_vector_search_pg_string_format():
    """pgVector 파라미터 문자열 형식 확인 ('[x.xx,y.yy,...]')"""
    from dev2.nodes.vector_search import _vec_to_pg_str

    vec = [0.1, 0.2, 0.3]
    pg_str = _vec_to_pg_str(vec)

    assert pg_str.startswith("[")
    assert pg_str.endswith("]")
    # 쉼표로 구분된 float 값들
    inner = pg_str[1:-1].split(",")
    assert len(inner) == 3
    assert all(float(x) for x in inner)  # 모두 float으로 파싱 가능


@pytest.mark.asyncio
async def test_vector_search_source_tagging():
    """static_raw → _source='static', security_raw → _source='security' 태깅 확인"""
    from dev2.nodes.vector_search import vector_search_node

    state = {
        **SAMPLE_STATE,
        "static_raw": [RAW_ISSUES_SAMPLE[1]],    # 복잡도 이슈
        "security_raw": [RAW_ISSUES_SAMPLE[0]],  # SQL 이슈
    }

    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}):
        result = await vector_search_node(state)

    enriched = result["enriched"]
    assert len(enriched) == 2

    # 모든 이슈에 _source 태깅 확인
    sources = {i["_source"] for i in enriched}
    assert sources == {"static", "security"}

    # 어느 것이 static/security인지 확인
    static_issue = next(i for i in enriched if i["_source"] == "static")
    assert static_issue["rule_id"] == "CC-001"  # 복잡도 이슈

    security_issue = next(i for i in enriched if i["_source"] == "security")
    assert security_issue["rule_id"] == "SEC-B608"  # SQL 이슈


# ── Task 4-f: store 노드 ─────────────────────────────────────────────────────

# store 테스트용 payload (Dev1 → Dev2 입력 계약)
PAYLOAD = {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "pr_id": "42",
    "pr_diff": "",
    "developer": {
        "id": "eval-dev",
        "skill_level": "junior",
        "tech_stack": ["python"],
    },
}


@pytest.mark.asyncio
async def test_store_node_returns_final_output():
    """
    store_node가 enriched(_source 포함) → final_output 2개 (AgentOutput 형식) 반환.
    내부 필드(_source, llm_judged, llm_model)는 Output Contract에서 제거됨.
    """
    from dev2.nodes.store import store_node

    issues = [
        {
            "severity": "Critical", "line": 42, "file": "auth.py",
            "message": "SQL 인젝션", "rule_id": "SEC-001",
            "suggestion": "파라미터 바인딩 사용", "similar_issues": [],
            "_source": "security",
            "llm_judged": True, "llm_model": "claude-sonnet-4-6",
        },
        {
            "severity": "Major", "line": 10, "file": "app.py",
            "message": "복잡도 높음", "rule_id": "SA-COMPLEXITY",
            "suggestion": "함수 분리 권장", "similar_issues": [],
            "_source": "static",
            "llm_judged": True, "llm_model": "claude-haiku-4-5-20251001",
        },
    ]

    state = {
        **SAMPLE_STATE,
        "payload": PAYLOAD,
        "enriched": issues,
        "final_output": [],
    }

    with patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):
        result = await store_node(state)

    # 에이전트 2개 결과 반환
    assert len(result["final_output"]) == 2

    agents = {r["agent"] for r in result["final_output"]}
    assert agents == {"static_analysis", "security_scan"}

    # 내부 필드 제거 확인 (Pydantic 경계 검증)
    for output in result["final_output"]:
        for issue in output["issues"]:
            assert "_source" not in issue, "_source 필드가 Output Contract에 노출됨"
            assert "llm_judged" not in issue, "llm_judged 필드가 Output Contract에 노출됨"
            assert "llm_model" not in issue, "llm_model 필드가 Output Contract에 노출됨"


@pytest.mark.asyncio
async def test_store_node_empty_enriched():
    """enriched 비어 있음 → final_output=[] (예외 없음, CLAUDE.md §12)"""
    from dev2.nodes.store import store_node

    state = {**SAMPLE_STATE, "payload": PAYLOAD, "enriched": [], "final_output": []}

    with patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):
        result = await store_node(state)

    assert result["final_output"] == []


@pytest.mark.asyncio
async def test_store_node_postgres_failure_reraises():
    """
    PostgreSQL 적재 실패 → re-raise (CLAUDE.md §10-4: 핵심 기능 실패 = 상위 전파).
    BigQuery와 달리 DB 실패는 파이프라인을 멈춰야 한다.
    """
    from dev2.nodes.store import store_node

    issues = [
        {
            "severity": "Critical", "line": 1, "file": "a.py",
            "message": "보안 이슈", "rule_id": "SEC-001",
            "suggestion": "수정 필요", "similar_issues": [],
            "_source": "security",
        }
    ]
    state = {**SAMPLE_STATE, "payload": PAYLOAD, "enriched": issues, "final_output": []}

    with patch(
        "dev2.nodes.store._persist",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB 연결 끊김"),
    ):
        with pytest.raises(RuntimeError, match="DB 연결 끊김"):
            await store_node(state)


@pytest.mark.asyncio
async def test_store_node_bigquery_failure_skipped():
    """
    BigQuery 적재 실패 → 스킵 (파이프라인 중단 없음).
    BigQuery는 analytics DW — 장애가 PR 리뷰를 막으면 안 됨 (CLAUDE.md §12 패턴).
    """
    from dev2.nodes.store import store_node

    issues = [
        {
            "severity": "Minor", "line": 5, "file": "app.py",
            "message": "코드 스멜", "rule_id": "STYLE-001",
            "suggestion": "개선 권장", "similar_issues": [],
            "_source": "static",
        }
    ]
    state = {**SAMPLE_STATE, "payload": PAYLOAD, "enriched": issues, "final_output": []}

    with patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch(
             "dev2.nodes.store._load_bigquery",
             side_effect=RuntimeError("BigQuery 다운"),
         ):
        # BigQuery 예외가 누출되어도 store_node가 잡아서 스킵
        result = await store_node(state)

    # final_output은 정상 반환
    assert len(result["final_output"]) == 1
    assert result["final_output"][0]["agent"] == "static_analysis"


@pytest.mark.asyncio
async def test_store_node_summary_counts_correctly():
    """summary.critical/major/minor 카운트가 정확한지 확인"""
    from dev2.nodes.store import store_node

    issues = [
        {
            "severity": "Critical", "line": 1, "file": "a.py",
            "message": "이슈1", "rule_id": "SEC-001",
            "suggestion": "fix", "similar_issues": [], "_source": "security",
        },
        {
            "severity": "Critical", "line": 2, "file": "a.py",
            "message": "이슈2", "rule_id": "SEC-002",
            "suggestion": "fix", "similar_issues": [], "_source": "security",
        },
        {
            "severity": "Minor", "line": 3, "file": "a.py",
            "message": "이슈3", "rule_id": "STYLE-001",
            "suggestion": "fix", "similar_issues": [], "_source": "security",
        },
    ]
    state = {**SAMPLE_STATE, "payload": PAYLOAD, "enriched": issues, "final_output": []}

    with patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):
        result = await store_node(state)

    # security_scan 에이전트 하나만 존재 (static 이슈 없음)
    assert len(result["final_output"]) == 1
    output = result["final_output"][0]
    assert output["agent"] == "security_scan"
    assert output["summary"]["critical"] == 2
    assert output["summary"]["major"] == 0
    assert output["summary"]["minor"] == 1


@pytest.mark.asyncio
async def test_store_trace_id_format():
    """trace_id가 CLAUDE.md §3 형식(pr_{12hex})인지 확인"""
    from dev2.nodes.store import _make_trace_id

    task_id = "550e8400-e29b-41d4-a716-446655440000"
    trace_id = _make_trace_id(task_id)

    assert trace_id.startswith("pr_"), f"trace_id가 'pr_'로 시작해야 함: {trace_id}"
    hex_part = trace_id[3:]
    assert len(hex_part) == 12, f"hex 부분이 12자여야 함: {hex_part}"
    # 16진수 문자만 포함 (하이픈 제거 후)
    int(hex_part, 16)  # 파싱 실패 시 ValueError

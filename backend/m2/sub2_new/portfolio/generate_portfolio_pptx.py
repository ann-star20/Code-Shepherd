"""
Task-Link 포트폴리오 PPT 생성 스크립트
실행: python generate_portfolio_pptx.py
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── 색상 팔레트 ────────────────────────────────────────────────────────────────
DARK_BG    = RGBColor(0x1A, 0x1A, 0x2E)
ACCENT     = RGBColor(0x4C, 0xAF, 0x50)
ACCENT2    = RGBColor(0x42, 0xA5, 0xF5)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xB0, 0xBE, 0xC5)
CARD_BG    = RGBColor(0x16, 0x21, 0x3E)
YELLOW     = RGBColor(0xFF, 0xCA, 0x28)
CARD2      = RGBColor(0x1E, 0x2A, 0x4A)

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def set_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, left, top, width, height, fill_color):
    shape = slide.shapes.add_shape(1, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape


def add_text(slide, text, left, top, width, height,
             font_size=14, bold=False, color=WHITE,
             align=PP_ALIGN.LEFT, wrap=True):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
    return tb


def add_divider(slide, top, color=ACCENT):
    line = slide.shapes.add_shape(1, Inches(0.4), top, Inches(12.53), Pt(2))
    line.fill.solid()
    line.fill.fore_color.rgb = color
    line.line.fill.background()


def page_num(slide, num):
    add_text(slide, f"{num} / 4", Inches(12.2), Inches(0.12),
             Inches(0.9), Inches(0.35), font_size=11,
             color=LIGHT_GRAY, align=PP_ALIGN.RIGHT)


# ── Slide 1: 프로젝트 소개 + 배경·목적 ───────────────────────────────────────

def slide1(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    # 헤더
    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.4), CARD_BG)
    add_text(slide, "Task-Link",
             Inches(0.5), Inches(0.1), Inches(9), Inches(0.65),
             font_size=38, bold=True, color=ACCENT)
    add_text(slide, "AI 멀티 에이전트 기반 PR 코드 리뷰 자동화 플랫폼",
             Inches(0.5), Inches(0.72), Inches(11), Inches(0.45),
             font_size=16, color=LIGHT_GRAY)
    add_text(slide, "Dev2 — 정적 분석 + 보안 스캔 에이전트  |  단독 설계·구현",
             Inches(0.5), Inches(1.1), Inches(11), Inches(0.35),
             font_size=13, bold=True, color=YELLOW)
    page_num(slide, 1)

    # 왼쪽: 프로젝트 정보
    add_rect(slide, Inches(0.4), Inches(1.6), Inches(5.9), Inches(2.8), CARD_BG)
    add_text(slide, "프로젝트 정보", Inches(0.6), Inches(1.7),
             Inches(5.5), Inches(0.4), font_size=13, bold=True, color=ACCENT2)

    info = [
        ("기간 / 인원", "2026년 5월  ·  6주  ·  6명"),
        ("내 역할",     "Dev2 — 정적 분석 + 보안 스캔 단독 구현"),
        ("기술 스택",   "LangGraph · Claude API · pgVector · FastAPI"),
        ("",           "BigQuery · Airflow · LangSmith · Bandit · ESLint"),
    ]
    for i, (lbl, val) in enumerate(info):
        top = Inches(2.15 + i * 0.52)
        if lbl:
            add_text(slide, lbl, Inches(0.6), top, Inches(1.6), Inches(0.45),
                     font_size=11, bold=True, color=YELLOW)
        add_text(slide, val, Inches(2.25), top, Inches(3.9), Inches(0.45),
                 font_size=11, color=WHITE)

    # 오른쪽: 배경·목적
    add_rect(slide, Inches(6.6), Inches(1.6), Inches(6.3), Inches(2.8), CARD_BG)
    add_text(slide, "왜 만들었나", Inches(6.8), Inches(1.7),
             Inches(5.9), Inches(0.4), font_size=13, bold=True, color=ACCENT2)

    problems = [
        "시니어, 신입 PR 리뷰에  하루 1~2시간 소비",
        "SQL 인젝션 · N+1 쿼리 반복 실수에 매번 같은 피드백",
        "PR 피드백 지연  ->  개발 흐름 단절, 성장 추적 불가",
        "반복 실수 패턴을 조직 차원에서 데이터로 파악 불가",
    ]
    for i, prob in enumerate(problems):
        add_text(slide, f"  {prob}", Inches(6.8), Inches(2.15 + i * 0.52),
                 Inches(5.9), Inches(0.45), font_size=11.5, color=WHITE)

    # 하단: 기대 효과 3박스
    add_divider(slide, Inches(4.55))
    add_text(slide, "기대 효과", Inches(0.4), Inches(4.65),
             Inches(3), Inches(0.35), font_size=12, bold=True, color=ACCENT)

    effects = [
        ("시니어 리뷰 부담", "70% 감소"),
        ("PR 피드백 속도", "즉시 자동화"),
        ("실수 패턴", "데이터 정량화"),
        ("AI 비용", "모델 라우팅 통제"),
    ]
    for i, (lbl, val) in enumerate(effects):
        lft = Inches(0.4 + i * 3.22)
        add_rect(slide, lft, Inches(5.05), Inches(3.0), Inches(1.9), CARD2)
        add_text(slide, lbl, lft + Inches(0.15), Inches(5.15),
                 Inches(2.7), Inches(0.4), font_size=11.5, color=LIGHT_GRAY)
        add_text(slide, val, lft + Inches(0.15), Inches(5.55),
                 Inches(2.7), Inches(0.6), font_size=20, bold=True, color=YELLOW)

    add_text(slide, "AX / DX Portfolio", Inches(0), Inches(7.1),
             SLIDE_W, Inches(0.3), font_size=10, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)


# ── Slide 2: 문제-원인-해결 + 나의 액션 ──────────────────────────────────────

def slide2(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.85), CARD_BG)
    add_text(slide, "문제 — 원인 — 해결  +  나의 액션",
             Inches(0.5), Inches(0.14), Inches(11), Inches(0.55),
             font_size=22, bold=True, color=WHITE)
    page_num(slide, 2)

    # 테이블
    headers = ["문제", "핵심 원인", "해결 방향"]
    rows = [
        ("반복 실수를 사람이 매번 검토",    "CLI 도구가 CI에 통합 안 됨",    "PR 수신 시 자동 분석 파이프라인"),
        ("severity 기준이 주관적",          "도구 판단만으론 context 부족",  "RAG + LLM Judge severity 재판단"),
        ("과거 실수와 학습 연결 안 됨",     "이슈 이력 연결 체계 없음",      "pgVector 유사 이슈 LLM context 주입"),
    ]
    col_bg   = [RGBColor(0x6A,0x1B,0x9A), RGBColor(0x0D,0x47,0xA1), RGBColor(0x1B,0x5E,0x20)]
    col_w, gap = Inches(4.1), Inches(0.12)
    col_x = [Inches(0.4), Inches(0.4)+col_w+gap, Inches(0.4)+2*(col_w+gap)]

    for ci, (hdr, bg) in enumerate(zip(headers, col_bg)):
        add_rect(slide, col_x[ci], Inches(0.95), col_w, Inches(0.38), bg)
        add_text(slide, hdr, col_x[ci], Inches(0.95), col_w, Inches(0.38),
                 font_size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            bg = CARD_BG if ri % 2 == 0 else CARD2
            top = Inches(1.37 + ri * 0.52)
            add_rect(slide, col_x[ci], top, col_w, Inches(0.48), bg)
            add_text(slide, cell, col_x[ci]+Inches(0.1), top+Inches(0.04),
                     col_w-Inches(0.2), Inches(0.42), font_size=11, color=WHITE)

    # 나의 액션
    add_divider(slide, Inches(3.0))
    add_text(slide, "나의 액션  (Dev2 단독 구현)",
             Inches(0.4), Inches(3.1), Inches(6), Inches(0.38),
             font_size=13, bold=True, color=ACCENT)

    actions = [
        ("①", "LangGraph 5-노드 Agentic Workflow",
               "conditional edge — Critical 감지 시 실행 경로 자동 분기"),
        ("②", "7개 언어 분석 도구 통합",
               "Python · JS · C# · HTML · CSS — Pydantic으로 통일 스키마 정규화"),
        ("③", "pgVector RAG 유사 이슈 검색",
               "코사인 유사도 0.7 이상 과거 이슈 -> LLM context 주입"),
        ("④", "비용 최적화 모델 라우팅",
               "Critical->Sonnet  /  Major->Haiku  /  Minor->LLM 생략(비용 0)"),
        ("⑤", "OLTP + OLAP 이중 적재",
               "PostgreSQL(운영 조회) + BigQuery(분석) 목적별 분리"),
        ("⑥", "Airflow DAG 자동화",
               "일일 ETL + 주간 개발자별 실수 패턴 리포트 자동 스케줄링"),
        ("⑦", "LangSmith Observability",
               "AI 판단 전 과정 트레이싱 — config 주입, 코드 내 하드코딩 없음"),
        ("⑧", "Mock/실제 전환 설계",
               "USE_MOCK_LLM 환경변수 하나로 전환 -> 팀 6명 병렬 개발 실현"),
    ]

    col2_x = Inches(6.9)
    for i, (num, title, desc) in enumerate(actions):
        row_i = i % 4
        col_i = i // 4
        top = Inches(3.57 + row_i * 0.92)
        lft = Inches(0.4) if col_i == 0 else col2_x

        add_rect(slide, lft, top, Inches(6.3), Inches(0.85),
                 CARD_BG if i % 2 == 0 else CARD2)
        add_text(slide, num, lft+Inches(0.1), top+Inches(0.04),
                 Inches(0.35), Inches(0.38), font_size=13, bold=True, color=ACCENT)
        add_text(slide, title, lft+Inches(0.5), top+Inches(0.04),
                 Inches(2.5), Inches(0.38), font_size=11.5, bold=True, color=WHITE)
        add_text(slide, desc, lft+Inches(0.5), top+Inches(0.42),
                 Inches(5.7), Inches(0.38), font_size=10.5, color=LIGHT_GRAY)

    add_text(slide, "AX / DX Portfolio", Inches(0), Inches(7.1),
             SLIDE_W, Inches(0.3), font_size=10, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)


# ── Slide 3: 결과물 + 성장한 점 ───────────────────────────────────────────────

def slide3(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.85), CARD_BG)
    add_text(slide, "결과물  +  성장한 점",
             Inches(0.5), Inches(0.14), Inches(10), Inches(0.55),
             font_size=22, bold=True, color=WHITE)
    page_num(slide, 3)

    # 파이프라인
    add_text(slide, "구현 파이프라인",
             Inches(0.4), Inches(0.95), Inches(5), Inches(0.35),
             font_size=12, bold=True, color=ACCENT2)

    nodes = [
        ("run_tools",     "Bandit · Pylint\nESLint · Semgrep\n7개 언어"),
        ("vector_search", "pgVector RAG\n유사 이슈 검색\n유사도 >= 0.7"),
        ("llm_judge",     "Claude\nSonnet / Haiku\n모델 라우팅"),
        ("escalate",      "Critical->Dev4\n조건부 분기\nLangSmith 추적"),
        ("store",         "PostgreSQL\n+ BigQuery\nAirflow DAG"),
    ]
    nc = [RGBColor(0x0D,0x47,0xA1), RGBColor(0x1B,0x5E,0x20),
          RGBColor(0x4A,0x14,0x8C), RGBColor(0x7B,0x1F,0x1F), RGBColor(0x4E,0x34,0x2E)]
    nw = Inches(2.3)
    for i, ((name, desc), color) in enumerate(zip(nodes, nc)):
        lft = Inches(0.4 + i * 2.58)
        add_rect(slide, lft, Inches(1.35), nw, Inches(1.1), color)
        add_text(slide, name, lft+Inches(0.1), Inches(1.38),
                 nw-Inches(0.2), Inches(0.38), font_size=11.5, bold=True, color=WHITE)
        add_text(slide, desc, lft+Inches(0.1), Inches(1.76),
                 nw-Inches(0.2), Inches(0.65), font_size=9.5, color=LIGHT_GRAY)
        if i < 4:
            add_text(slide, "->", lft+nw, Inches(1.72),
                     Inches(0.28), Inches(0.38), font_size=16, bold=True,
                     color=ACCENT, align=PP_ALIGN.CENTER)

    # 완성물 리스트
    add_text(slide, "완성물",
             Inches(0.4), Inches(2.6), Inches(3), Inches(0.32),
             font_size=12, bold=True, color=ACCENT2)
    deliverables = [
        "FastAPI:  POST /scan  /  GET /insights  /  GET /issues  /  PATCH /dismiss",
        "Airflow DAG:  일일 ETL + 주간 개발자별 실수 패턴 리포트 자동화",
        "PostgreSQL 3-테이블:  scan_executions -> scan_issues -> scan_summaries",
        "E2E 테스트 통과  /  LangSmith Observability 체계  /  Dev2 단독 구현 완료",
    ]
    for i, d in enumerate(deliverables):
        add_text(slide, f"  {d}", Inches(0.4), Inches(2.97 + i*0.38),
                 Inches(12.5), Inches(0.35), font_size=11, color=WHITE)

    # 성장한 점
    add_divider(slide, Inches(4.5))
    add_text(slide, "성장한 점",
             Inches(0.4), Inches(4.6), Inches(3), Inches(0.35),
             font_size=12, bold=True, color=ACCENT)

    growths = [
        ("기술",     "LangGraph Agentic Workflow\nRAG 파이프라인 설계\nasyncio 에러 격리\nLangSmith Observability\nAirflow DAG"),
        ("설계",     "에러 케이스 먼저 정의\n-> fallback 선 구현\nasyncio 타임아웃 버그\n발견 -> 팀 규칙 문서화"),
        ("협업",     "Pydantic Output Contract\n명문화 -> 팀 병렬 개발\nMock 전환 구조 설계\n연동 가이드 문서 작성"),
        ("비즈니스", "기술 선택을 비즈니스\n목표에서 역산\nAI 비용을 설계 단계\n에서 통제하는 경험"),
    ]
    gc = [RGBColor(0x0D,0x47,0xA1), RGBColor(0x1B,0x5E,0x20),
          RGBColor(0x4A,0x14,0x8C), RGBColor(0x4E,0x34,0x2E)]
    for i, ((lbl, content), color) in enumerate(zip(growths, gc)):
        lft = Inches(0.4 + i * 3.22)
        add_rect(slide, lft, Inches(5.0), Inches(3.0), Inches(2.3), color)
        add_text(slide, lbl, lft+Inches(0.15), Inches(5.08),
                 Inches(2.7), Inches(0.38), font_size=12, bold=True, color=YELLOW)
        add_text(slide, content, lft+Inches(0.15), Inches(5.5),
                 Inches(2.7), Inches(1.7), font_size=10.5, color=WHITE)

    add_text(slide, "AX / DX Portfolio", Inches(0), Inches(7.1),
             SLIDE_W, Inches(0.3), font_size=10, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)


# ── Slide 4: 역량·기여 + 면접 한 줄 어필 ─────────────────────────────────────

def slide4(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, DARK_BG)

    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.85), CARD_BG)
    add_text(slide, "역량·기여  +  면접 한 줄 어필",
             Inches(0.5), Inches(0.14), Inches(10), Inches(0.55),
             font_size=22, bold=True, color=WHITE)
    page_num(slide, 4)

    # 역량 테이블
    add_text(slide, "역량  ->  AX/DX 직무 기여",
             Inches(0.4), Inches(0.95), Inches(7), Inches(0.38),
             font_size=13, bold=True, color=ACCENT2)

    table = [
        ("AI 파이프라인 설계",   "LangGraph Agentic Workflow end-to-end",      "AI 내재화 과제 직접 설계·실행"),
        ("업무 자동화 전환",     "수동 리뷰 -> 자동 분석+에스컬레이션 체계",   "반복 업무의 AI 전환 기획"),
        ("데이터 기반 의사결정", "BigQuery + Airflow 분석 파이프라인 구축",    "성과 측정 지표 설계"),
        ("AI 비용 최적화",       "모델 라우팅으로 LLM 호출 비용 구조 설계",    "LLM 도입 TCO 관리"),
        ("AI Observability",     "LangSmith 트레이싱 — config 주입 설계",      "AI 품질 모니터링 체계 구축"),
        ("협업 설계 역량",       "Mock 전환 + Pydantic Contract 명문화",        "팀 AI 도입 인터페이스 설계"),
    ]
    col_x = [Inches(0.4), Inches(3.3), Inches(8.8)]
    col_w = [Inches(2.8), Inches(5.35), Inches(4.3)]
    hdrs  = ["역량", "프로젝트 근거", "직무 기여"]
    hdr_c = [RGBColor(0x0D,0x47,0xA1), RGBColor(0x1B,0x5E,0x20), RGBColor(0x4A,0x14,0x8C)]

    for ci in range(3):
        add_rect(slide, col_x[ci], Inches(1.38), col_w[ci], Inches(0.35), hdr_c[ci])
        add_text(slide, hdrs[ci], col_x[ci], Inches(1.38), col_w[ci], Inches(0.35),
                 font_size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    for ri, row in enumerate(table):
        bg = CARD_BG if ri % 2 == 0 else CARD2
        rt = Inches(1.77 + ri * 0.44)
        for ci, (cell, cx, cw) in enumerate(zip(row, col_x, col_w)):
            add_rect(slide, cx, rt, cw, Inches(0.41), bg)
            fc = YELLOW if ci == 0 else (WHITE if ci == 1 else ACCENT)
            add_text(slide, cell, cx+Inches(0.08), rt+Inches(0.03),
                     cw-Inches(0.12), Inches(0.36), font_size=10.5,
                     color=fc, bold=(ci == 0))

    # 핵심 시행착오 박스
    add_rect(slide, Inches(0.4), Inches(4.48), Inches(12.5), Inches(0.62),
             RGBColor(0x2E,0x1A,0x00))
    add_rect(slide, Inches(0.4), Inches(4.48), Inches(0.07), Inches(0.62), YELLOW)
    add_text(slide,
             "핵심 시행착오: asyncio.TimeoutError를 async with 블록 안에서 잡으면 DB에 success 기록 버그"
             "  ->  try/except를 블록 바깥으로 이동 + 팀 규칙 문서화",
             Inches(0.6), Inches(4.52), Inches(12.1), Inches(0.52),
             font_size=11, color=YELLOW)

    # 면접 한 줄 어필
    add_divider(slide, Inches(5.22))
    add_text(slide, "면접 한 줄 어필",
             Inches(0.4), Inches(5.3), Inches(5), Inches(0.38),
             font_size=13, bold=True, color=ACCENT)

    add_rect(slide, Inches(0.4), Inches(5.75), Inches(12.5), Inches(1.3),
             RGBColor(0x0A, 0x2A, 0x1A))
    add_rect(slide, Inches(0.4), Inches(5.75), Inches(0.07), Inches(1.3), ACCENT)
    quote = (
        '"AI를 도구로 쓰는 것에 그치지 않고, '
        'AI 판단이 실제 업무 프로세스의 실행 경로를 바꾸는 Agentic Workflow를 설계·구현했고,\n'
        'Observability와 비용 통제까지 처음부터 설계한 경험이 있습니다.\n'
        'AX/DX 현장에서 AI 내재화 과제에 바로 기여할 수 있습니다."'
    )
    add_text(slide, quote, Inches(0.65), Inches(5.8),
             Inches(12.1), Inches(1.2), font_size=13.5, color=WHITE)

    # 기술 태그
    tags = ["LangGraph", "Claude API", "RAG / pgVector",
            "FastAPI", "BigQuery", "Airflow", "LangSmith"]
    lft = Inches(0.4)
    for tag in tags:
        tw = Inches(len(tag) * 0.11 + 0.4)
        add_rect(slide, lft, Inches(7.1), tw, Inches(0.32), RGBColor(0x1A,0x3A,0x5C))
        add_text(slide, tag, lft+Inches(0.08), Inches(7.12),
                 tw-Inches(0.1), Inches(0.28), font_size=10, color=ACCENT2)
        lft += tw + Inches(0.13)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H

    slide1(prs)
    slide2(prs)
    slide3(prs)
    slide4(prs)

    out = "portfolio_TaskLink_AX_DX.pptx"
    prs.save(out)
    print(f"[OK] 저장 완료: {out}")


if __name__ == "__main__":
    main()

"""
AX/DX 포트폴리오 PPTX 생성 스크립트
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import os

# ── 색상 팔레트 ──────────────────────────────────────────
NAVY    = RGBColor(0x1A, 0x23, 0x3A)   # 슬라이드 배경 (짙은 네이비)
DARK    = RGBColor(0x1E, 0x29, 0x3B)   # 카드 배경
ACCENT  = RGBColor(0x38, 0xBD, 0xF8)   # 포인트 블루
GREEN   = RGBColor(0x34, 0xD3, 0x99)   # 성과 녹색
ORANGE  = RGBColor(0xFB, 0xBF, 0x24)   # 경고/강조 오렌지
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
GRAY    = RGBColor(0xB0, 0xBE, 0xC5)
LIGHT_BG = RGBColor(0xF0, 0xF4, 0xF8)  # 밝은 슬라이드용 배경
CARD_DARK = RGBColor(0x0F, 0x17, 0x2A) # 진한 카드

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)

# ── 헬퍼 함수 ────────────────────────────────────────────

def new_prs():
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs

def blank_slide(prs):
    layout = prs.slide_layouts[6]  # 완전 빈 레이아웃
    return prs.slides.add_slide(layout)

def fill_bg(slide, color):
    """슬라이드 배경 단색 채우기"""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_rect(slide, l, t, w, h, fill_color, alpha=None):
    shape = slide.shapes.add_shape(1, l, t, w, h)  # MSO_SHAPE_TYPE.RECTANGLE=1
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    return shape

def add_text(slide, text, l, t, w, h,
             font_size=18, bold=False, color=WHITE,
             align=PP_ALIGN.LEFT, wrap=True,
             italic=False, font_name="맑은 고딕"):
    txb = slide.shapes.add_textbox(l, t, w, h)
    txb.word_wrap = wrap
    tf = txb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font_name
    return txb

def add_multiline(slide, lines, l, t, w, h,
                  font_size=14, color=WHITE, line_spacing=1.15,
                  bold_first=False, font_name="맑은 고딕"):
    """lines: [(text, bold, color_override)] or [str]"""
    txb = slide.shapes.add_textbox(l, t, w, h)
    txb.word_wrap = True
    tf = txb.text_frame
    tf.word_wrap = True
    first = True
    for item in lines:
        if isinstance(item, str):
            text, bold, col = item, False, color
        else:
            text = item[0]
            bold = item[1] if len(item) > 1 else False
            col  = item[2] if len(item) > 2 else color
        if first:
            p = tf.paragraphs[0]
            first = False
        else:
            p = tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = text
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.color.rgb = col
        run.font.name = font_name
    return txb

def accent_bar(slide, l, t, w=Inches(0.07), h=Inches(0.6)):
    add_rect(slide, l, t, w, h, ACCENT)

# ── 슬라이드 제작 ─────────────────────────────────────────

def slide_cover(prs):
    """표지"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    # 배경 장식 사각형
    add_rect(s, Inches(0), Inches(5.5), SLIDE_W, Inches(2.0), RGBColor(0x0F, 0x17, 0x2A))
    add_rect(s, Inches(10.5), Inches(0), Inches(2.83), SLIDE_H, RGBColor(0x0D, 0x14, 0x26))

    # 포인트 라인
    add_rect(s, Inches(0.7), Inches(1.6), Inches(5.5), Inches(0.06), ACCENT)

    # 태그
    add_text(s, "AX / DX  포트폴리오", Inches(0.7), Inches(0.85),
             Inches(8), Inches(0.5), font_size=13, color=ACCENT, bold=True)

    # 메인 타이틀
    add_text(s, "AI 기반 코드\n정적분석·보안스캔\n자동화 에이전트",
             Inches(0.7), Inches(1.8), Inches(9.5), Inches(2.5),
             font_size=42, bold=True, color=WHITE)

    # 부제
    add_text(s,
             "GitHub PR 제출 즉시 — AI가 품질·보안을 자동 진단하고\n"
             "심각도를 판단해 팀에 전달하는 멀티에이전트 파이프라인",
             Inches(0.7), Inches(4.35), Inches(9.5), Inches(1.0),
             font_size=16, color=GRAY)

    # 하단 메타
    meta = [
        ("Python  ·  LangGraph  ·  Claude Sonnet/Haiku  ·  pgVector  ·  BigQuery  ·  FastAPI  ·  Airflow", False, GRAY),
        ("2026.05  |  Dev2 서브에이전트 설계·구현 전담", False, RGBColor(0x64, 0x74, 0x8B)),
    ]
    add_multiline(s, meta, Inches(0.7), Inches(5.7), Inches(11), Inches(1.0),
                  font_size=12)


def slide_problem(prs):
    """슬라이드 2: Problem — 왜 이 프로젝트가 필요했나"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.3), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.3), ACCENT)

    add_text(s, "01  Problem", Inches(0.5), Inches(0.1), Inches(6), Inches(0.55),
             font_size=13, bold=True, color=ACCENT)
    add_text(s, "왜 이 프로젝트가 필요했나",
             Inches(0.5), Inches(0.55), Inches(10), Inches(0.6),
             font_size=26, bold=True, color=WHITE)

    # 3개 카드
    cards = [
        {
            "icon": "🛠",
            "title": "수동 도구 실행",
            "num": "언어별 파편화",
            "num_desc": "Python·JS·C# 각각 다른 도구를\n개발자가 직접 골라 실행해야 했음",
            "body": "· Pylint, Bandit, ESLint 등 도구마다\n  실행법이 달라 표준화 불가\n· 팀마다 사용 도구가 달라 결과 비교 어려움",
        },
        {
            "icon": "⚠",
            "title": "심각도 맥락 부재",
            "num": "Critical = Minor?",
            "num_desc": "CLI raw 결과는 모든 이슈를\n동일 무게로 출력",
            "body": "· Bandit 출력 그대로는 HIGH/LOW 구분만\n· 실제 코드 맥락 없이 리뷰어가 직접 판단\n· Critical 취약점이 묻히는 사례 발생",
        },
        {
            "icon": "🔁",
            "title": "조직 지식 단절",
            "num": "매번 처음부터",
            "num_desc": "과거 유사 이슈가 의사결정에\n전혀 반영되지 않음",
            "body": "· 동일 패턴 이슈도 매 PR마다 새로 판단\n· 리뷰 품질이 리뷰어 개인 역량에 의존\n· 오탐·누락이 반복되어도 학습 불가",
        },
    ]

    card_w = Inches(3.9)
    card_h = Inches(5.4)
    tops = Inches(1.45)
    lefts = [Inches(0.35), Inches(4.55), Inches(8.75)]

    for i, c in enumerate(cards):
        l = lefts[i]
        add_rect(s, l, tops, card_w, card_h, DARK)
        add_rect(s, l, tops, card_w, Inches(0.06), ACCENT)

        add_text(s, c["icon"], l + Inches(0.2), tops + Inches(0.15),
                 Inches(0.6), Inches(0.5), font_size=22, color=WHITE)
        add_text(s, c["title"], l + Inches(0.2), tops + Inches(0.65),
                 card_w - Inches(0.4), Inches(0.45),
                 font_size=16, bold=True, color=WHITE)

        # 강조 수치/키워드
        add_rect(s, l + Inches(0.2), tops + Inches(1.2),
                 card_w - Inches(0.4), Inches(0.5), RGBColor(0x0D, 0x23, 0x40))
        add_text(s, c["num"], l + Inches(0.3), tops + Inches(1.25),
                 card_w - Inches(0.5), Inches(0.3),
                 font_size=14, bold=True, color=ORANGE)
        add_text(s, c["num_desc"], l + Inches(0.2), tops + Inches(1.75),
                 card_w - Inches(0.4), Inches(0.7),
                 font_size=11, color=GRAY)
        add_text(s, c["body"], l + Inches(0.2), tops + Inches(2.55),
                 card_w - Inches(0.4), Inches(2.5),
                 font_size=12, color=RGBColor(0xCB, 0xD5, 0xE1))

    # 하단 요약
    add_rect(s, Inches(0), Inches(7.0), SLIDE_W, Inches(0.5), RGBColor(0x0D, 0x14, 0x26))
    add_text(s,
             "→ AX/DX 관점: 반복 수작업 제거 + 판단 기준 표준화 + 조직 학습 자산화가 동시에 필요한 상황",
             Inches(0.5), Inches(7.05), Inches(12), Inches(0.4),
             font_size=12, color=ACCENT, bold=True)


def slide_architecture(prs):
    """슬라이드 3: 시스템 아키텍처"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.2), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.2), GREEN)

    add_text(s, "02  Solution Architecture", Inches(0.5), Inches(0.08),
             Inches(6), Inches(0.5), font_size=13, bold=True, color=GREEN)
    add_text(s, "5-노드 LangGraph 자동화 파이프라인",
             Inches(0.5), Inches(0.5), Inches(10), Inches(0.6),
             font_size=26, bold=True, color=WHITE)

    # 파이프라인 노드 5개 + 화살표
    nodes = [
        ("1\nrun_tools",    "언어 자동 감지\nCLI 병렬 실행",      ACCENT,  Inches(0.4)),
        ("2\nvector_search","pgVector\nRAG 검색",                  GREEN,   Inches(2.9)),
        ("3\nllm_judge",    "Claude\n심각도 판단",                  ORANGE,  Inches(5.4)),
        ("4\nescalate",     "Critical ≥ 1\n자동 에스컬레이션",     RGBColor(0xF8, 0x71, 0x71), Inches(7.9)),
        ("5\nstore",        "PostgreSQL\n+ BigQuery 적재",         RGBColor(0xA7, 0x8B, 0xFA), Inches(10.4)),
    ]

    node_top = Inches(1.55)
    node_w   = Inches(2.3)
    node_h   = Inches(2.0)

    for label, desc, color, left in nodes:
        add_rect(s, left, node_top, node_w, node_h, DARK)
        add_rect(s, left, node_top, node_w, Inches(0.1), color)
        add_text(s, label, left + Inches(0.1), node_top + Inches(0.18),
                 node_w - Inches(0.2), Inches(0.75),
                 font_size=13, bold=True, color=color)
        add_text(s, desc, left + Inches(0.1), node_top + Inches(1.0),
                 node_w - Inches(0.2), Inches(0.85),
                 font_size=11, color=GRAY)

    # 화살표 텍스트
    arrow_lefts = [Inches(2.72), Inches(5.22), Inches(7.72), Inches(10.22)]
    for al in arrow_lefts:
        add_text(s, "→", al, node_top + Inches(0.7),
                 Inches(0.2), Inches(0.5),
                 font_size=20, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)

    # 조건부 분기 설명
    add_rect(s, Inches(7.9), Inches(3.7), Inches(4.8), Inches(0.55),
             RGBColor(0x1A, 0x1F, 0x35))
    add_text(s,
             "※  Critical 없으면 escalate 스킵 → 바로 store (조건부 분기)",
             Inches(8.0), Inches(3.75), Inches(4.6), Inches(0.45),
             font_size=11, color=ORANGE)

    # 하단 기술 레이어 설명
    layers = [
        ("입력 계약", "Pydantic TaskPayload\n(Dev1 → Dev2)"),
        ("AI 레이어", "Few-shot + CoT + RAG\n+ Structured Output"),
        ("비용 제어", "모델 라우팅\nMinor 이슈 LLM 스킵 ($0)"),
        ("데이터 저장", "PostgreSQL (실시간)\n+ BigQuery (분석 DW)"),
        ("모니터링", "LangSmith @traceable\n전 노드 자동 추적"),
    ]

    layer_top = Inches(4.45)
    layer_w   = Inches(2.3)
    layer_h   = Inches(2.55)
    layer_lefts = [Inches(0.4), Inches(2.9), Inches(5.4), Inches(7.9), Inches(10.4)]

    for (title, body), left in zip(layers, layer_lefts):
        add_rect(s, left, layer_top, layer_w, layer_h, RGBColor(0x0F, 0x17, 0x2A))
        add_text(s, title, left + Inches(0.1), layer_top + Inches(0.15),
                 layer_w - Inches(0.2), Inches(0.4),
                 font_size=11, bold=True, color=ACCENT)
        add_text(s, body, left + Inches(0.1), layer_top + Inches(0.65),
                 layer_w - Inches(0.2), Inches(1.6),
                 font_size=11, color=GRAY)


def slide_action(prs):
    """슬라이드 4: 내가 직접 한 일"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.2), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.2), ORANGE)

    add_text(s, "03  My Actions", Inches(0.5), Inches(0.08),
             Inches(6), Inches(0.5), font_size=13, bold=True, color=ORANGE)
    add_text(s, "내가 직접 설계하고 구현한 것들",
             Inches(0.5), Inches(0.5), Inches(10), Inches(0.6),
             font_size=26, bold=True, color=WHITE)

    actions = [
        {
            "no": "①",
            "title": "LangGraph StateGraph 설계",
            "tag": "파이프라인 설계",
            "tag_color": ACCENT,
            "points": [
                "5-노드 흐름 + 조건부 엣지(_route_after_judge) 직접 구현",
                "PRReviewState 팀 공통 인터페이스 상속 → 멀티에이전트 통합 호환성",
                "LangSmith 트레이서 lazy 초기화 (환경변수로 on/off)",
            ],
        },
        {
            "no": "②",
            "title": "다국어 CLI 병렬 실행",
            "tag": "자동화",
            "tag_color": GREEN,
            "points": [
                "파일 확장자 자동 감지 → 언어별 도구 자동 선택 (tools/router.py)",
                "asyncio.gather로 병렬 실행 (타임아웃 30초, hang 방지)",
                "시행착오: 언어 감지 분산 → router.py 단일 모듈화로 해결",
            ],
        },
        {
            "no": "③",
            "title": "pgVector RAG + LLM 판단",
            "tag": "AI 설계",
            "tag_color": ORANGE,
            "points": [
                "이슈 임베딩 → 유사도 0.7↑ 과거 이슈 자동 검색 → Claude 프롬프트 주입",
                "Few-shot 3개 + CoT 5단계 + Structured Output 조합",
                "시행착오: 비일관 JSON → Structured Output + Few-shot 결합으로 파싱 실패율 감소",
            ],
        },
        {
            "no": "④",
            "title": "모델 라우팅 + 이중 DB 적재",
            "tag": "LLMOps / 데이터",
            "tag_color": RGBColor(0xA7, 0x8B, 0xFA),
            "points": [
                "Critical→Sonnet 4.6 / Major→Haiku 4.5 / Minor→LLM 스킵 ($0)",
                "PostgreSQL(실시간 추적) + BigQuery(분석 DW) asyncio.gather 병렬 적재",
                "Airflow 일별 ETL DAG + 주간 오탐률 자동 집계",
            ],
        },
    ]

    col_w  = Inches(6.2)
    col_h  = Inches(2.65)
    lefts  = [Inches(0.35), Inches(6.75)]
    tops   = [Inches(1.35), Inches(4.15)]

    positions = [(lefts[0], tops[0]), (lefts[1], tops[0]),
                 (lefts[0], tops[1]), (lefts[1], tops[1])]

    for act, (l, t) in zip(actions, positions):
        add_rect(s, l, t, col_w, col_h, DARK)
        add_rect(s, l, t, Inches(0.06), col_h, act["tag_color"])

        # 번호 + 제목
        add_text(s, act["no"] + "  " + act["title"],
                 l + Inches(0.2), t + Inches(0.12),
                 col_w - Inches(0.3), Inches(0.45),
                 font_size=15, bold=True, color=WHITE)

        # 태그
        add_rect(s, l + Inches(0.2), t + Inches(0.62),
                 Inches(1.5), Inches(0.3), RGBColor(0x0D, 0x23, 0x40))
        add_text(s, act["tag"],
                 l + Inches(0.25), t + Inches(0.64),
                 Inches(1.4), Inches(0.28),
                 font_size=10, bold=True, color=act["tag_color"])

        # 포인트
        for j, pt in enumerate(act["points"]):
            add_text(s, "· " + pt,
                     l + Inches(0.2), t + Inches(1.05) + Inches(j * 0.5),
                     col_w - Inches(0.3), Inches(0.48),
                     font_size=11, color=RGBColor(0xCB, 0xD5, 0xE1))


def slide_result(prs):
    """슬라이드 5: 성과"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.2), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.2), GREEN)

    add_text(s, "04  Results", Inches(0.5), Inches(0.08),
             Inches(6), Inches(0.5), font_size=13, bold=True, color=GREEN)
    add_text(s, "무엇이 달라졌나",
             Inches(0.5), Inches(0.5), Inches(10), Inches(0.6),
             font_size=26, bold=True, color=WHITE)

    # ── 정량 성과 (상단 3개 카드) ──
    quant = [
        {
            "num": "병렬 실행",
            "unit": "asyncio.gather",
            "desc": "언어별 CLI 도구를 순서 없이\n동시에 실행해 분석 시간 단축\n(직렬 대비 언어 수에 비례)",
            "color": ACCENT,
        },
        {
            "num": "Minor 비용",
            "unit": "$0",
            "desc": "심각도 낮은 이슈는 LLM 호출 자체 스킵\n→ 불필요한 API 비용 완전 제거\n(모델 라우팅 설계 효과)",
            "color": GREEN,
        },
        {
            "num": "유사도 임계값",
            "unit": "0.7↑",
            "desc": "pgVector 검색 시 유사도 70% 이상\n이슈만 컨텍스트로 활용\n→ 오탐 방지 기준 수립",
            "color": ORANGE,
        },
    ]

    q_w   = Inches(3.9)
    q_h   = Inches(2.7)
    q_top = Inches(1.35)
    q_lefts = [Inches(0.35), Inches(4.55), Inches(8.75)]

    for q, ql in zip(quant, q_lefts):
        add_rect(s, ql, q_top, q_w, q_h, DARK)
        add_rect(s, ql, q_top, q_w, Inches(0.07), q["color"])

        add_text(s, q["num"], ql + Inches(0.2), q_top + Inches(0.18),
                 q_w - Inches(0.3), Inches(0.4),
                 font_size=12, color=GRAY)
        add_text(s, q["unit"], ql + Inches(0.2), q_top + Inches(0.6),
                 q_w - Inches(0.3), Inches(0.65),
                 font_size=28, bold=True, color=q["color"])
        add_text(s, q["desc"], ql + Inches(0.2), q_top + Inches(1.35),
                 q_w - Inches(0.3), Inches(1.15),
                 font_size=11, color=GRAY)

    # ── 정성 성과 (하단 4개) ──
    qual = [
        ("수작업 → 자동화",       "PR 리뷰 전 과정을 파이프라인으로 대체\n개인 역량 의존 제거, 표준화 달성"),
        ("지식 자산화",           "산발된 이슈 데이터를 pgVector RAG로\n재활용 가능한 조직 지식으로 구조화"),
        ("품질 트렌드 측정 기반", "BigQuery 이중 적재로 팀 코드 품질\n장기 트렌드 분석 데이터 기반 확보"),
        ("재현 가능한 파이프라인","LangSmith 전 노드 추적 + Mock LLM\n환경변수 전환으로 테스트 재현 보장"),
    ]

    qa_w   = Inches(2.9)
    qa_h   = Inches(1.9)
    qa_top = Inches(4.3)
    qa_lefts = [Inches(0.35), Inches(3.45), Inches(6.55), Inches(9.65)]

    for (title, body), ql in zip(qual, qa_lefts):
        add_rect(s, ql, qa_top, qa_w, qa_h, RGBColor(0x0F, 0x17, 0x2A))
        add_rect(s, ql, qa_top, Inches(0.06), qa_h, GREEN)

        add_text(s, title, ql + Inches(0.2), qa_top + Inches(0.15),
                 qa_w - Inches(0.3), Inches(0.4),
                 font_size=13, bold=True, color=WHITE)
        add_text(s, body, ql + Inches(0.2), qa_top + Inches(0.65),
                 qa_w - Inches(0.3), Inches(1.1),
                 font_size=11, color=GRAY)

    # 레이블
    add_text(s, "▶  정량 성과", Inches(0.35), Inches(1.1),
             Inches(3), Inches(0.3), font_size=11, bold=True, color=ACCENT)
    add_text(s, "▶  정성 성과 (업무·조직 관점)", Inches(0.35), Inches(4.1),
             Inches(5), Inches(0.3), font_size=11, bold=True, color=GREEN)


def slide_growth(prs):
    """슬라이드 6: 성장한 점"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.2), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.2), RGBColor(0xA7, 0x8B, 0xFA))

    add_text(s, "05  Growth", Inches(0.5), Inches(0.08),
             Inches(6), Inches(0.5), font_size=13, bold=True,
             color=RGBColor(0xA7, 0x8B, 0xFA))
    add_text(s, "이 프로젝트가 내게 준 것",
             Inches(0.5), Inches(0.5), Inches(10), Inches(0.6),
             font_size=26, bold=True, color=WHITE)

    categories = [
        {
            "icon": "⚙",
            "title": "기술적 성장",
            "color": ACCENT,
            "items": [
                ("LLM 파이프라인 설계", "CLI·RAG·LLM을 레이어드하게 결합하는\n실무 AI 시스템 설계 방법 체득"),
                ("비용 인식 엔지니어링", "모델 라우팅 + Minor 스킵으로\n기능 저하 없이 LLM 비용 통제 (LLMOps)"),
                ("비동기 resilient 설계", "asyncio.gather + return_exceptions=True로\n부분 실패가 전체를 멈추지 않는 구조"),
            ],
        },
        {
            "icon": "🧠",
            "title": "문제 해결 방식",
            "color": ORANGE,
            "items": [
                ("레이어 분리 사고", "'LLM 하나로 다 해결' → 도구 적합성에 따라\n레이어를 나누는 설계 원칙 확립"),
                ("파이프라인 지속성", "에러 처리 = '예외 방지'가 아닌\n'파이프라인이 멈추지 않는 것'으로 재정의"),
            ],
        },
        {
            "icon": "📊",
            "title": "비즈니스 이해",
            "color": GREEN,
            "items": [
                ("리스크 관리 자동화", "보안 이슈 탐지·에스컬레이션 =\n단순 개발 도구가 아닌 리스크 관리"),
                ("DX 관점 데이터 활용", "BigQuery 장기 누적 → 코드 품질 트렌드를\n데이터 기반으로 측정하는 DX 가치 이해"),
            ],
        },
    ]

    cat_w = Inches(3.9)
    cat_lefts = [Inches(0.35), Inches(4.55), Inches(8.75)]

    for cat, cl in zip(categories, cat_lefts):
        add_rect(s, cl, Inches(1.35), cat_w, Inches(5.65), DARK)
        add_rect(s, cl, Inches(1.35), cat_w, Inches(0.07), cat["color"])

        add_text(s, cat["icon"] + "  " + cat["title"],
                 cl + Inches(0.2), Inches(1.5),
                 cat_w - Inches(0.3), Inches(0.5),
                 font_size=15, bold=True, color=cat["color"])

        item_top = Inches(2.1)
        for title, body in cat["items"]:
            add_rect(s, cl + Inches(0.2), item_top,
                     cat_w - Inches(0.4), Inches(0.07), cat["color"])
            add_text(s, title,
                     cl + Inches(0.2), item_top + Inches(0.12),
                     cat_w - Inches(0.4), Inches(0.38),
                     font_size=12, bold=True, color=WHITE)
            add_text(s, body,
                     cl + Inches(0.2), item_top + Inches(0.55),
                     cat_w - Inches(0.4), Inches(0.75),
                     font_size=11, color=GRAY)
            item_top += Inches(1.5)


def slide_competency(prs):
    """슬라이드 7: 나의 역량 + 어필"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.2), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.2), ACCENT)

    add_text(s, "06  Competency  →  AX/DX Fit", Inches(0.5), Inches(0.08),
             Inches(8), Inches(0.5), font_size=13, bold=True, color=ACCENT)
    add_text(s, "이 프로젝트로 보여줄 수 있는 역량",
             Inches(0.5), Inches(0.5), Inches(10), Inches(0.6),
             font_size=26, bold=True, color=WHITE)

    # 왼쪽: 역량 매핑 테이블
    table_items = [
        ("AI 파이프라인 설계",     "LangGraph 5-노드 StateGraph,\nRAG 패턴 직접 구현"),
        ("LLM 비용 최적화",        "모델 라우팅 + Minor 스킵\n→ 기능 저하 없이 비용 통제"),
        ("데이터 파이프라인 자동화","PostgreSQL+BigQuery 이중 적재\nAirflow ETL DAG 구현"),
        ("비동기 병렬 처리",        "asyncio.gather 기반\nresilient 파이프라인"),
        ("LLMOps",                  "LangSmith 자동 추적\nMock LLM 환경 분리"),
    ]

    tbl_top = Inches(1.45)
    tbl_l   = Inches(0.35)
    for i, (skill, evidence) in enumerate(table_items):
        row_t = tbl_top + Inches(i * 1.05)
        add_rect(s, tbl_l, row_t, Inches(5.8), Inches(0.95),
                 DARK if i % 2 == 0 else RGBColor(0x16, 0x1E, 0x30))
        add_rect(s, tbl_l, row_t, Inches(0.06), Inches(0.95), ACCENT)
        add_text(s, skill, tbl_l + Inches(0.2), row_t + Inches(0.08),
                 Inches(2.0), Inches(0.38), font_size=12, bold=True, color=WHITE)
        add_text(s, evidence, tbl_l + Inches(2.35), row_t + Inches(0.08),
                 Inches(3.6), Inches(0.8), font_size=11, color=GRAY)

    # 오른쪽: AX/DX 연결 강점
    right_l = Inches(6.5)
    strengths = [
        (ACCENT,  "업무 자동화 설계 경험",
                  "수작업 코드 리뷰를 AI 파이프라인으로 대체.\n'무엇을 자동화할지'와 '어떻게 설계할지' 모두 경험."),
        (GREEN,   "데이터 기반 의사결정 기반 구축",
                  "이슈 데이터를 BigQuery에 구조화해 팀의 코드 품질\n트렌드를 데이터로 측정 가능하게 만든 DX 경험."),
        (ORANGE,  "비용 인식 AI 적용",
                  "LLM 도입을 넘어 '어디에 얼마만큼 써야 하는지'\n모델 라우팅으로 직접 설계한 실무 역량."),
    ]

    str_top = Inches(1.45)
    for i, (color, title, body) in enumerate(strengths):
        rt = str_top + Inches(i * 1.9)
        add_rect(s, right_l, rt, Inches(6.5), Inches(1.75),
                 RGBColor(0x0F, 0x17, 0x2A))
        add_rect(s, right_l, rt, Inches(0.06), Inches(1.75), color)
        add_text(s, title, right_l + Inches(0.2), rt + Inches(0.15),
                 Inches(6.2), Inches(0.42), font_size=13, bold=True, color=color)
        add_text(s, body, right_l + Inches(0.2), rt + Inches(0.65),
                 Inches(6.2), Inches(0.95), font_size=11, color=GRAY)

    # 핵심 어필 문장 (하단 강조 박스)
    add_rect(s, Inches(0.35), Inches(7.0), Inches(12.63), Inches(0.42),
             RGBColor(0x06, 0x3A, 0x5C))
    add_text(s,
             "\"저는 AI를 도입하는 것이 아니라, 기존 업무 흐름의 어느 지점에 AI가 들어가야 효과적인지를 설계하는 경험을 했습니다.\"",
             Inches(0.55), Inches(7.05), Inches(12.4), Inches(0.35),
             font_size=13, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)


def slide_closing(prs):
    """마지막 슬라이드: 자기소개서 + 면접 60초"""
    s = blank_slide(prs)
    fill_bg(s, NAVY)

    add_rect(s, Inches(0), Inches(0), SLIDE_W, Inches(1.2), CARD_DARK)
    add_rect(s, Inches(0), Inches(0), Inches(0.25), Inches(1.2), ORANGE)

    add_text(s, "Appendix  |  자기소개서 / 면접 답변", Inches(0.5), Inches(0.08),
             Inches(9), Inches(0.5), font_size=13, bold=True, color=ORANGE)
    add_text(s, "한 장으로 정리하는 나의 스토리",
             Inches(0.5), Inches(0.5), Inches(10), Inches(0.6),
             font_size=24, bold=True, color=WHITE)

    # 왼쪽: 자기소개서 핵심 흐름
    add_rect(s, Inches(0.35), Inches(1.4), Inches(6.0), Inches(5.7), DARK)
    add_rect(s, Inches(0.35), Inches(1.4), Inches(6.0), Inches(0.07), ORANGE)
    add_text(s, "자기소개서 핵심 흐름 (700자)", Inches(0.55), Inches(1.5),
             Inches(5.6), Inches(0.4), font_size=13, bold=True, color=ORANGE)

    cv_lines = [
        ("[ Problem ]", True, ACCENT),
        ("PR마다 언어별 도구를 수동 실행, 심각도 맥락 없는 raw 결과, 과거 이슈 재활용 불가.", False, WHITE),
        ("", False, WHITE),
        ("[ Action ]", True, ACCENT),
        ("LangGraph 5-노드 파이프라인 직접 설계.", False, WHITE),
        ("언어 자동 감지 → CLI 병렬 실행 → pgVector RAG → Claude 재판단 → 이중 적재.", False, WHITE),
        ("모델 라우팅으로 Minor 이슈 LLM 호출 스킵 ($0).", False, WHITE),
        ("", False, WHITE),
        ("[ Result ]", True, ACCENT),
        ("수작업 리뷰 → 표준화된 자동화 파이프라인.", False, WHITE),
        ("이슈 데이터 → 재활용 가능한 RAG 지식 자산.", False, WHITE),
        ("BigQuery 장기 누적 → 팀 코드 품질 트렌드 측정 기반 구축.", False, WHITE),
        ("", False, WHITE),
        ("→ AX/DX 직무: 업무 자동화 + 데이터 기반 의사결정 환경 구축에 바로 기여 가능.", True, GREEN),
    ]
    add_multiline(s, cv_lines, Inches(0.55), Inches(1.95),
                  Inches(5.6), Inches(4.9), font_size=11)

    # 오른쪽: 면접 60초
    add_rect(s, Inches(6.65), Inches(1.4), Inches(6.3), Inches(5.7), DARK)
    add_rect(s, Inches(6.65), Inches(1.4), Inches(6.3), Inches(0.07), GREEN)
    add_text(s, "면접 답변 (60초)", Inches(6.85), Inches(1.5),
             Inches(5.9), Inches(0.4), font_size=13, bold=True, color=GREEN)

    interview = (
        "저는 개발팀의 코드 리뷰 수작업을 AI 에이전트 파이프라인으로 자동화한 프로젝트를 담당했습니다.\n\n"
        "기존에는 PR이 올라오면 개발자가 직접 도구를 실행하고 결과를 해석해야 했는데, "
        "언어마다 도구가 달라 파편화되어 있었고, 심각도 맥락 없는 결과를 사람이 직접 판단해야 하는 비효율이 있었습니다.\n\n"
        "저는 LangGraph로 5단계 파이프라인을 직접 설계했습니다. "
        "파일 언어를 자동 감지해서 CLI 도구들을 병렬로 실행하고, "
        "과거 유사 이슈를 pgVector로 검색해서 Claude에 컨텍스트로 주입한 뒤 심각도를 재판단합니다. "
        "Critical 이슈는 자동 에스컬레이션되고, 결과는 PostgreSQL과 BigQuery에 이중 저장됩니다.\n\n"
        "LLM 비용도 직접 설계해, 심각도 낮은 이슈는 LLM 호출 자체를 스킵하는 모델 라우팅을 적용했습니다.\n\n"
        "이 경험으로 '업무 자동화는 AI를 도입하는 것보다, 어느 지점에 AI를 넣어야 효과적인지 설계하는 것이 핵심'임을 체득했습니다."
    )
    add_text(s, interview, Inches(6.85), Inches(1.95),
             Inches(5.9), Inches(5.0), font_size=11, color=GRAY)


# ── 메인 ─────────────────────────────────────────────────

def main():
    prs = new_prs()

    slide_cover(prs)
    slide_problem(prs)
    slide_architecture(prs)
    slide_action(prs)
    slide_result(prs)
    slide_growth(prs)
    slide_competency(prs)
    slide_closing(prs)

    out_path = os.path.join(os.path.dirname(__file__), "portfolio_AX_DX.pptx")
    prs.save(out_path)
    print(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()

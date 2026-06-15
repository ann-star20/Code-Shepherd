"""
KMS 파이프라인 아키텍처 PDF 생성기
코드 기준 수정사항 반영:
  - Stage 5b trace_id: trc_0005b (코드: DocPipelineStage.METADATA_VALIDATE = "trc_0005b")
  - Stage 6 임베딩: bge-m3 (소규모) / OpenAI small (>50 chunks 폴백)
  - Agent/Tool 표 StoreRouteTool 모델 컬럼 수정
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.patheffects as pe
import numpy as np

# ---------------------------------------------------------------------------
# 색상 팔레트
# ---------------------------------------------------------------------------
C = {
    "bg":          "#F8F9FA",
    "title_bg":    "#1a2744",
    "agent_bg":    "#EBF3FF",
    "agent_bd":    "#4A7FC1",
    "tool_bg":     "#F0F7F0",
    "tool_bd":     "#5A9A5A",
    "workflow_bg": "#FFF8EC",
    "workflow_bd": "#D4A017",
    "hitl_bg":     "#FFF0F0",
    "hitl_bd":     "#E05050",
    "store_bg":    "#F0F4FF",
    "store_bd":    "#6B7FBF",
    "section_bg":  "#EAEEF8",
    "section_bd":  "#8898C8",
    "arrow":       "#444466",
    "cond_arrow":  "#CC4444",
    "yes":         "#2E7D32",
    "no":          "#C62828",
    "text_dark":   "#1A1A2E",
    "text_mid":    "#3A3A5A",
    "text_light":  "#666688",
    "trace_bg":    "#F5F0FF",
    "trace_bd":    "#8B5CF6",
    "lg_bg":       "#EDF2FF",
    "storage_blue":"#1565C0",
    "storage_green":"#2E7D32",
    "storage_red": "#C62828",
    "storage_neo": "#006064",
}

# ---------------------------------------------------------------------------
# 폰트 설정 (Windows: Malgun Gothic)
# ---------------------------------------------------------------------------
import matplotlib.font_manager as fm
import os

_KR_FONT = None
for name in ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]:
    try:
        f = fm.findfont(fm.FontProperties(family=name), fallback_to_default=False)
        if f and os.path.exists(f):
            _KR_FONT = name
            break
    except Exception:
        pass

def kf(size=8, bold=False):
    w = "bold" if bold else "normal"
    if _KR_FONT:
        return {"fontfamily": _KR_FONT, "fontsize": size, "fontweight": w}
    return {"fontsize": size, "fontweight": w}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def rbox(ax, x, y, w, h, fc, ec, lw=1.2, radius=0.012, alpha=1.0):
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle=f"round,pad=0,rounding_size={radius}",
                         fc=fc, ec=ec, lw=lw, alpha=alpha,
                         transform=ax.transAxes, zorder=3)
    ax.add_patch(box)
    return box

def txt(ax, x, y, s, **kw):
    size = kw.pop("size", 7)
    bold = kw.pop("bold", False)
    kw.setdefault("transform", ax.transAxes)
    kw.setdefault("zorder", 4)
    kw.setdefault("va", "center")
    kw.setdefault("ha", "center")
    kw.setdefault("color", C["text_dark"])
    return ax.text(x, y, s, **kw, **kf(size, bold))

def arrow(ax, x0, y0, x1, y1, color=None, lw=1.4, style="-|>", mutation=6):
    c = color or C["arrow"]
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle=style, color=c, lw=lw,
                                mutation_scale=mutation),
                zorder=5)

def divider(ax, y, lw=0.6, color="#C0C8E0"):
    ax.plot([0, 1], [y, y], color=color, lw=lw,
            transform=ax.transAxes, zorder=2)


# ---------------------------------------------------------------------------
# 메인 그리기
# ---------------------------------------------------------------------------
def draw(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(C["bg"])

    # =========================================================
    # 0. 배경
    # =========================================================
    rbox(ax, 0, 0, 1, 1, C["bg"], C["bg"], lw=0)

    # =========================================================
    # 1. 타이틀 바
    # =========================================================
    rbox(ax, 0.005, 0.955, 0.99, 0.040, C["title_bg"], C["title_bg"], radius=0.008)
    txt(ax, 0.50, 0.975, "KMS 파이프라인 아키텍처  (LangGraph 기반 Agentic AI Workflow)",
        color="white", size=11, bold=True)
    txt(ax, 0.50, 0.960, "AI Agent 기반 문서 정제 파이프라인  (HITL + Harness Engineering 포함)",
        color="#B0C4DE", size=7.5)

    # =========================================================
    # 2. 메인 파이프라인 (Stage 1-6) 영역
    # =========================================================
    PIPE_Y  = 0.640   # 파이프라인 영역 하단
    PIPE_H  = 0.305   # 파이프라인 영역 높이
    PIPE_T  = PIPE_Y + PIPE_H  # 파이프라인 상단 y

    # 왼쪽 입력 문서 섹션
    rbox(ax, 0.005, PIPE_Y, 0.070, PIPE_H, "#F0F4FF", C["section_bd"], radius=0.008)
    txt(ax, 0.040, PIPE_T - 0.015, "입력\n문서", size=7.5, bold=True)
    for i, (icon, lbl) in enumerate([("PDF","pdf"),("DOCX","docx"),("PPTX","pptx"),("TXT","txt")]):
        yi = PIPE_T - 0.055 - i * 0.040
        rbox(ax, 0.012, yi-0.012, 0.050, 0.026,
             "#DDEEFF", "#7799CC", lw=0.8, radius=0.005)
        txt(ax, 0.037, yi+0.001, icon, size=6.5, bold=True, color="#1A3A6A")

    # 각 Stage 정의
    stages = [
        {
            "id": "S1", "x": 0.082, "w": 0.138,
            "title": "Stage 1\nDocumentParserAgent",
            "icon": "[A]", "fc": C["agent_bg"], "ec": C["agent_bd"],
            "bullets": [
                "파일 유형/복잡도 판단",
                "최적 파서 선택",
                "Markdown 변환",
                "(Upstage / PyMuPDF",
                "/ Gemini OCR)",
            ],
            "output": "raw_markdown\nparser_used",
            "trace": "trc_0001",
            "node_type": "Agent",
        },
        {
            "id": "S2", "x": 0.228, "w": 0.138,
            "title": "Stage 2\nMarkdownValidateAgent",
            "icon": "[A]", "fc": C["agent_bg"], "ec": C["agent_bd"],
            "bullets": [
                "구조 품질 점수화",
                "누락/손실 검증",
                "자동 수정 (최대 2회)",
                "임계값: PDF≥0.65",
                "기타≥0.80",
            ],
            "output": "quality_score\nvalidated_markdown",
            "trace": "trc_0002",
            "node_type": "Agent",
            "hitl": True,
        },
        {
            "id": "S3", "x": 0.393, "w": 0.122,
            "title": "Stage 3\nChunkingTool",
            "icon": "[T]", "fc": C["tool_bg"], "ec": C["tool_bd"],
            "bullets": [
                "Header 기반 분할",
                "Parent/Child 생성",
                "Overlap 설정",
                "(tiktoken 512/128)",
            ],
            "output": "chunks[ ]",
            "trace": "trc_0003",
            "node_type": "Tool",
        },
        {
            "id": "S4", "x": 0.522, "w": 0.130,
            "title": "Stage 4\nChunkValidateTool",
            "icon": "[T]", "fc": C["tool_bg"], "ec": C["tool_bd"],
            "bullets": [
                "chunk 크기 검증",
                "Parent/Child 연결 검증",
                "토큰 범위 검증",
                "(300~500 / 800~1500)",
            ],
            "output": "hitl_required\nchunk_issues",
            "trace": "trc_0004",
            "node_type": "Tool",
            "hitl": True,
        },
        {
            "id": "S5", "x": 0.660, "w": 0.133,
            "title": "Stage 5\nMetadataExtractAgent",
            "icon": "[A]", "fc": C["agent_bg"], "ec": C["agent_bd"],
            "bullets": [
                "title / category 추출",
                "tags 추출",
                "entities 추출",
                "관계 후보 추출",
            ],
            "output": "metadata\nentities / relations",
            "trace": "trc_0005",
            "node_type": "Agent",
        },
    ]

    # Stage 5b 별도 (오른쪽으로 붙이기)
    S5B = {
        "id": "S5b", "x": 0.660, "w": 0.133,
        "title": "Stage 5b\nMetadataValidateAgent",
        "icon": "[A]", "fc": C["agent_bg"], "ec": C["agent_bd"],
        "bullets": [
            "메타데이터-문서",
            "일치 여부 검증",
            "정확도 점수화",
            "(임계값 ≥ 0.70)",
        ],
        "output": "metadata_score\nmetadata_valid",
        "trace": "trc_0005b",   # ← 코드 기준 수정
        "node_type": "Agent",
        "hitl": True,
    }

    # Stage 6
    S6 = {
        "id": "S6", "x": 0.803, "w": 0.130,
        "title": "Stage 6\nStoreRouteTool",
        "icon": "[T]", "fc": C["tool_bg"], "ec": C["tool_bd"],
        "bullets": [
            "임베딩 생성",
            "  bge-m3 (소규모)",           # ← 수정
            "  OpenAI small (>50 chunks)", # ← 수정
            "PostgreSQL 저장",
            "pgVector / GCS / Neo4j",
        ],
        "output": "stored",
        "trace": "trc_0006",
        "node_type": "Tool",
    }

    def draw_stage(s, y_top, y_bot, show_hitl=False, hitl_y=None):
        x, w = s["x"], s["w"]
        rbox(ax, x, y_bot, w, y_top - y_bot, s["fc"], s["ec"], lw=1.5, radius=0.010)

        # 타이틀 배경
        rbox(ax, x, y_top - 0.042, w, 0.042, s["ec"], s["ec"],
             lw=0, radius=0.008, alpha=0.85)
        # 타이틀 텍스트 (두 줄)
        lines = s["title"].split("\n")
        txt(ax, x + w/2, y_top - 0.010, lines[0],
            color="white", size=6, bold=True)
        txt(ax, x + w/2, y_top - 0.026, lines[1] if len(lines)>1 else "",
            color="white", size=6.5, bold=True)

        # 불릿
        for i, b in enumerate(s["bullets"]):
            yi = y_top - 0.055 - i * 0.026
            if yi > y_bot + 0.025:
                txt(ax, x + w/2, yi, ("• " if not b.startswith(" ") else "") + b.strip(),
                    size=6, color=C["text_mid"], ha="center")

        # 출력 라벨
        rbox(ax, x + 0.005, y_bot + 0.022, w - 0.010, 0.022,
             "#FFFFFF", s["ec"], lw=0.8, radius=0.004, alpha=0.8)
        txt(ax, x + w/2, y_bot + 0.033, "출력: " + s["output"].replace("\n", "  "),
            size=5.5, color=C["text_mid"])

        # trace_id 라벨
        rbox(ax, x + 0.005, y_bot + 0.002, w - 0.010, 0.018,
             s["trace_bg"] if "trace_bg" in s else C["trace_bg"],
             C["trace_bd"], lw=0.7, radius=0.003, alpha=0.8)
        txt(ax, x + w/2, y_bot + 0.011,
            f"trace_id: {s['trace']}",
            size=5.5, color="#6B46C1")

        # HITL 다이아몬드
        if show_hitl:
            hx = x + w/2
            hy = hitl_y if hitl_y else y_bot - 0.065
            d = 0.020
            diamond = plt.Polygon(
                [[hx, hy+d], [hx+d*1.8, hy], [hx, hy-d], [hx-d*1.8, hy]],
                fc="#FFF8F0", ec="#E06020", lw=1.2, zorder=4,
                transform=ax.transAxes
            )
            ax.add_patch(diamond)
            txt(ax, hx, hy, "품질\n기준?", size=5.5, color="#C04000", bold=True)
            # Yes 화살표 (오른쪽으로)
            arrow(ax, hx + d*1.8, hy, x + w + 0.005, hy,
                  color=C["yes"], lw=1.2)
            txt(ax, hx + d*1.8 + 0.015, hy + 0.010, "Yes", size=5.5,
                color=C["yes"], bold=True)
            # No 화살표 (아래쪽)
            arrow(ax, hx, hy - d, hx, hy - 0.055, color=C["no"], lw=1.2)
            txt(ax, hx + 0.015, hy - d - 0.020, "No/Low", size=5.5,
                color=C["no"], bold=True)
            # HITL 박스
            hbx, hby = hx - 0.040, hy - 0.055 - 0.045
            rbox(ax, hbx, hby, 0.080, 0.045,
                 C["hitl_bg"], C["hitl_bd"], lw=1.2, radius=0.006)
            txt(ax, hbx + 0.040, hby + 0.030,
                "[H] Human Review", size=6, color="#C00000", bold=True)
            txt(ax, hbx + 0.040, hby + 0.015,
                "(예외 상황)", size=5.5, color="#C00000")

    # --- 레이아웃 계산 ---
    STAGE_TOP  = PIPE_T - 0.008
    STAGE_BOT  = PIPE_Y + 0.010
    MID_Y      = (STAGE_TOP + STAGE_BOT) / 2

    # Stage 1
    draw_stage(stages[0], STAGE_TOP, STAGE_BOT)
    # Stage 2 + HITL
    draw_stage(stages[1], STAGE_TOP, STAGE_BOT + 0.110, show_hitl=True,
               hitl_y=STAGE_BOT + 0.080)
    # Stage 3
    draw_stage(stages[2], STAGE_TOP, STAGE_BOT)
    # Stage 4 + HITL
    draw_stage(stages[3], STAGE_TOP, STAGE_BOT + 0.110, show_hitl=True,
               hitl_y=STAGE_BOT + 0.080)

    # Stage 5 → 5b 세로 배치
    S5_TOP  = STAGE_TOP
    S5_MID  = MID_Y + 0.010
    S5B_BOT = STAGE_BOT

    draw_stage(stages[4], S5_TOP, S5_MID + 0.005)
    draw_stage(S5B, S5_MID - 0.005, S5B_BOT + 0.110,
               show_hitl=True, hitl_y=S5B_BOT + 0.080)

    # Stage 6
    draw_stage(S6, STAGE_TOP, STAGE_BOT)

    # --- 스테이지 간 화살표 ---
    arrow_y = MID_Y + 0.085
    # S1 → S2
    arrow(ax, stages[0]["x"] + stages[0]["w"], arrow_y,
              stages[1]["x"], arrow_y)
    # S2 → S3 (Yes 경로의 연결)
    arrow(ax, stages[1]["x"] + stages[1]["w"], arrow_y,
              stages[2]["x"], arrow_y)
    # S3 → S4
    arrow(ax, stages[2]["x"] + stages[2]["w"], arrow_y,
              stages[3]["x"], arrow_y)
    # S4 → S5
    arrow(ax, stages[3]["x"] + stages[3]["w"], arrow_y,
              stages[4]["x"], arrow_y)
    # S5 → S5b (아래 방향)
    s5cx = stages[4]["x"] + stages[4]["w"] / 2
    arrow(ax, s5cx, S5_MID + 0.005, s5cx, S5_MID - 0.005)
    # S5b → S6
    arrow(ax, S5B["x"] + S5B["w"], (S5_MID + S5B_BOT) / 2 + 0.055,
              S6["x"], (S5_MID + S5B_BOT) / 2 + 0.055)

    # 입력→S1 화살표
    arrow(ax, 0.075, arrow_y, stages[0]["x"], arrow_y)

    # =========================================================
    # 3. 저장소 섹션 (우상단)
    # =========================================================
    ST_X, ST_Y, ST_W, ST_H = 0.940, PIPE_Y, 0.057, PIPE_H
    rbox(ax, ST_X, ST_Y, ST_W, ST_H, "#F0F4FF", C["section_bd"], radius=0.008)
    txt(ax, ST_X + ST_W/2, ST_Y + ST_H - 0.015, "저장소\n(멀티)", size=7, bold=True)

    stores = [
        ("Storage", "원본/MD\n(GCS/Local)", "#1E88E5"),
        ("PostgreSQL", "documents\nchunks", "#43A047"),
        ("pgVector", "임베딩\n(1024dim)", "#8E24AA"),
        ("Neo4j\nGraphDB", "Doc/Chunk\nEntity/MENTIONS", "#00ACC1"),
    ]
    for i, (name, desc, color) in enumerate(stores):
        sy = ST_Y + ST_H - 0.065 - i * 0.063
        rbox(ax, ST_X + 0.004, sy - 0.010, ST_W - 0.008, 0.050,
             "#FFFFFF", color, lw=1.0, radius=0.005)
        txt(ax, ST_X + ST_W/2, sy + 0.020, name,
            size=5.5, bold=True, color=color)
        txt(ax, ST_X + ST_W/2, sy + 0.005, desc,
            size=5, color=C["text_mid"])

    # S6 → Storage 화살표
    for i in range(4):
        sy = ST_Y + ST_H - 0.065 - i * 0.063 + 0.010
        arrow(ax, S6["x"] + S6["w"], sy + 0.005,
              ST_X, sy + 0.005, lw=1.0, mutation=5)

    # =========================================================
    # 4. 하단 4개 섹션 분할선
    # =========================================================
    divider(ax, PIPE_Y - 0.003)

    SEC_TOP = PIPE_Y - 0.008
    SEC_BOT = 0.002
    SEC_H   = SEC_TOP - SEC_BOT

    # 섹션 경계 x
    sx = [0.005, 0.250, 0.520, 0.750, 0.995]

    for i in range(4):
        rbox(ax, sx[i]+0.002, SEC_BOT, sx[i+1]-sx[i]-0.004, SEC_H,
             C["section_bg"], C["section_bd"], lw=0.8, radius=0.008)

    # =========================================================
    # 4a. LangGraph 구조 (섹션 0)
    # =========================================================
    LX = sx[0] + 0.006
    LY = SEC_TOP - 0.010
    LW = sx[1] - sx[0] - 0.012

    txt(ax, LX + LW/2, LY, "LangGraph 구조 (StateGraph)",
        size=8, bold=True, color=C["title_bg"])

    # 노드 정의 (x 위치)
    lg_nodes = [
        ("S1\nParser",   0.020, "agent"),
        ("S2\nValidate", 0.060, "agent"),
        ("S3\nChunk",    0.108, "tool"),
        ("S4\nChunk\nValidate", 0.148, "tool"),
        ("S5\nMeta\nExtract",  0.192, "agent"),
        ("S5b\nMeta\nValidate",0.218, "agent"),
        ("S6\nStore",    0.258, "tool"),
    ]
    LN_Y  = SEC_TOP - 0.075
    LN_R  = 0.014
    HITL_Y = SEC_TOP - 0.120

    node_colors = {"agent": (C["agent_bg"], C["agent_bd"]),
                   "tool":  (C["tool_bg"],  C["tool_bd"])}

    for label, nx, ntype in lg_nodes:
        fc, ec = node_colors[ntype]
        circle = plt.Circle((LX + nx + LN_R, LN_Y), LN_R,
                             fc=fc, ec=ec, lw=1.2, zorder=4,
                             transform=ax.transAxes)
        ax.add_patch(circle)
        txt(ax, LX + nx + LN_R, LN_Y, label,
            size=4.5, color=C["text_dark"])

    # 연결 화살표
    for i in range(len(lg_nodes) - 1):
        _, nx0, _ = lg_nodes[i]
        _, nx1, _ = lg_nodes[i+1]
        arrow(ax, LX + nx0 + LN_R*2, LN_Y, LX + nx1, LN_Y, lw=1.0, mutation=5)

    # S2, S4, S5b → HITL 분기
    for _, nx, _ in [lg_nodes[1], lg_nodes[3], lg_nodes[5]]:
        cx = LX + nx + LN_R
        # No 화살표 아래로
        arrow(ax, cx, LN_Y - LN_R, cx, HITL_Y + 0.010,
              color=C["no"], lw=0.9, mutation=4)
        # HITL 박스
        rbox(ax, cx - 0.022, HITL_Y - 0.016, 0.044, 0.026,
             C["hitl_bg"], C["hitl_bd"], lw=0.9, radius=0.004)
        txt(ax, cx, HITL_Y - 0.003, "HITL\nPending",
            size=5, color=C["hitl_bd"], bold=True)

    # END 노드
    end_x = LX + lg_nodes[-1][1] + LN_R * 2 + 0.012
    circle_end = plt.Circle((end_x, LN_Y), LN_R,
                             fc="#555577", ec="#333355", lw=1.2, zorder=4,
                             transform=ax.transAxes)
    ax.add_patch(circle_end)
    txt(ax, end_x, LN_Y, "END", size=5, color="white", bold=True)
    arrow(ax, LX + lg_nodes[-1][1] + LN_R*2, LN_Y,
              end_x - LN_R, LN_Y, lw=1.0, mutation=5)

    # 범례
    leg_y = SEC_BOT + 0.010
    for lx, label, fc, ec in [
        (LX + 0.005, "Agent Node (LLM)",    C["agent_bg"], C["agent_bd"]),
        (LX + 0.075, "Tool Node",            C["tool_bg"],  C["tool_bd"]),
        (LX + 0.140, "Workflow Node",        C["workflow_bg"], C["workflow_bd"]),
        (LX + 0.200, "End",                  "#555577", "#333355"),
    ]:
        c = plt.Circle((lx + 0.007, leg_y + 0.010), 0.007,
                        fc=fc, ec=ec, lw=0.8, zorder=4,
                        transform=ax.transAxes)
        ax.add_patch(c)
        txt(ax, lx + 0.017, leg_y + 0.010, label,
            ha="left", size=5, color=C["text_mid"])

    # 설명 텍스트
    for i, line in enumerate([
        "총 8개 노드  •  Conditional Edge 3개 (Stage 2 / 4 / 5b)",
        "HITL 분기 3지점  •  실패 시 END  •  성공 시 다음 Stage",
    ]):
        txt(ax, LX + LW/2, SEC_BOT + 0.048 - i*0.018, line,
            size=5.5, color=C["text_mid"])

    # =========================================================
    # 4b. Agent / Tool / Workflow 구분표 (섹션 1)
    # =========================================================
    TX = sx[1] + 0.008
    TY = SEC_TOP - 0.010
    TW = sx[2] - sx[1] - 0.016

    txt(ax, TX + TW/2, TY, "Agent / Tool / Workflow Node 구분",
        size=8, bold=True, color=C["title_bg"])

    # 표 헤더
    cols = ["노드명", "분류", "모델", "역할 요약"]
    col_w = [0.068, 0.032, 0.048, 0.114]
    col_x = [TX]
    for cw in col_w[:-1]:
        col_x.append(col_x[-1] + cw)

    HDR_Y = TY - 0.032
    rbox(ax, TX, HDR_Y, TW, 0.022, C["title_bg"], C["title_bg"],
         lw=0, radius=0.004)
    for i, (cx, cw, ch) in enumerate(zip(col_x, col_w, cols)):
        txt(ax, cx + cw/2, HDR_Y + 0.011, ch,
            color="white", size=6, bold=True)

    rows_data = [
        ("DocumentParserAgent",   "Agent", "Gemini 2.5 Flash",
         "파일 복잡도 판단, 최적 파서 선택, Markdown 변환",
         C["agent_bg"], C["agent_bd"]),
        ("MarkdownValidateAgent", "Agent", "Gemini 2.5 Flash",
         "Markdown 품질 점수화, 자동 수정/재시도",
         C["agent_bg"], C["agent_bd"]),
        ("ChunkingTool",          "Tool",  "—",
         "Header 기반 Parent-Child 청크 생성",
         C["tool_bg"], C["tool_bd"]),
        ("ChunkValidateTool",     "Tool",  "—",
         "청크 크기, 연결, 토큰 범위 검증",
         C["tool_bg"], C["tool_bd"]),
        ("MetadataExtractAgent",  "Agent", "Gemini 2.5 Flash",
         "메타데이터(title/category/tags/entities) 추출",
         C["agent_bg"], C["agent_bd"]),
        ("MetadataValidateAgent", "Agent", "Gemini 2.5 Flash",
         "메타데이터 정확도 2차 검증 (점수화)",
         C["agent_bg"], C["agent_bd"]),
        # ← 수정: StoreRouteTool 모델 컬럼
        ("StoreRouteTool",        "Tool",  "bge-m3 /\nOpenAI small*",
         "임베딩 + 4개 스토리지 멀티 저장",
         C["tool_bg"], C["tool_bd"]),
        ("hitl_pending",          "Workflow", "—",
         "HITL 큐 INSERT 및 파이프라인 중단 제어",
         C["workflow_bg"], C["workflow_bd"]),
    ]

    ROW_H = 0.030
    for ri, (name, typ, model, role, rfc, rec) in enumerate(rows_data):
        ry = HDR_Y - (ri + 1) * ROW_H - 0.002
        bg = rfc if ri % 2 == 0 else "#FAFBFF"
        rbox(ax, TX, ry, TW, ROW_H - 0.001, bg, "#CCCCDD",
             lw=0.4, radius=0.002)
        txt(ax, col_x[0] + col_w[0]/2, ry + ROW_H/2, name,
            size=5.5, color=rec, bold=True)
        txt(ax, col_x[1] + col_w[1]/2, ry + ROW_H/2, typ,
            size=5.5, color=C["text_mid"])
        txt(ax, col_x[2] + col_w[2]/2, ry + ROW_H/2, model,
            size=5, color=C["text_mid"])
        txt(ax, col_x[3] + col_w[3]/2, ry + ROW_H/2, role,
            size=5.5, color=C["text_mid"])

    txt(ax, TX + TW/2, SEC_BOT + 0.010,
        "* StoreRouteTool: child chunk ≤ 50 → bge-m3,  > 50 → OpenAI text-embedding-3-small (1024dim)",
        size=5, color="#884400")

    # =========================================================
    # 4c. Trace & Observability (섹션 2)
    # =========================================================
    OX = sx[2] + 0.008
    OY = SEC_TOP - 0.010
    OW = sx[3] - sx[2] - 0.016

    txt(ax, OX + OW/2, OY,
        "Trace & Observability  (Harness Engineering + LangSmith)",
        size=8, bold=True, color=C["title_bg"])

    # trace_id 생성 흐름
    rbox(ax, OX, OY - 0.058, OW, 0.045, C["trace_bg"], C["trace_bd"],
         lw=1.2, radius=0.007)
    txt(ax, OX + OW/2, OY - 0.023, "trace_id 생성",
        size=7, bold=True, color="#5B21B6")
    txt(ax, OX + OW/2, OY - 0.038,
        "new_pipeline_trace(stage, doc_id)",
        size=6, color="#7C3AED")
    txt(ax, OX + OW/2, OY - 0.050,
        "형식: trc_0001_{doc_id_8hex}",
        size=6, color="#6D28D9")

    arrow(ax, OX + OW/2, OY - 0.058, OX + OW/2, OY - 0.072, lw=1.0, mutation=5)

    # agent_traces 테이블
    rbox(ax, OX, OY - 0.145, OW, 0.072, "#FFFEF5", "#D4A017",
         lw=1.2, radius=0.007)
    txt(ax, OX + OW/2, OY - 0.082,
        "agent_traces 테이블 (PostgreSQL)",
        size=7, bold=True, color="#92400E")
    at_fields = [
        "trace_id  •  agent_name  •  doc_id",
        "status (running / success / fail)",
        "started_at / ended_at / execution_ms",
        "error_message (if any)",
    ]
    for i, f in enumerate(at_fields):
        txt(ax, OX + OW/2, OY - 0.098 - i * 0.013, f,
            size=5.5, color=C["text_mid"])

    arrow(ax, OX + OW/2, OY - 0.145, OX + OW/2, OY - 0.158, lw=1.0, mutation=5)

    # LangSmith 연동
    rbox(ax, OX, OY - 0.196, OW, 0.048, "#F0FFF4", "#2E7D32",
         lw=1.2, radius=0.007)
    txt(ax, OX + OW/2, OY - 0.163, "LangSmith 연동 (선택적)",
        size=7, bold=True, color="#166534")
    for i, line in enumerate([
        "LANGCHAIN_TRACING_V2=true 설정 시 자동 전송",
        "대시보드 trace_id 검색/조회 가능",
    ]):
        txt(ax, OX + OW/2, OY - 0.178 - i * 0.013, line,
            size=5.5, color="#15803D")

    # 체크리스트
    checks = [
        "모든 Agent 실행 추적",
        "실행 시간/성공·실패 기록",
        "재현성 및 디버깅 지원",
        "LangSmith 대시보드 조회 가능",
    ]
    for i, c in enumerate(checks):
        txt(ax, OX + 0.012, SEC_BOT + 0.090 - i * 0.018,
            "[v]  " + c, ha="left", size=6, color="#166534")

    # =========================================================
    # 4d. HITL + 저장 구조 (섹션 3)
    # =========================================================
    HX = sx[3] + 0.008
    HY = SEC_TOP - 0.010
    HW = sx[4] - sx[3] - 0.016

    txt(ax, HX + HW/2, HY, "HITL (Human-in-the-Loop) + 저장 구조",
        size=8, bold=True, color=C["title_bg"])

    # HITL 흐름
    hitl_checks = [
        "품질 기준 미달 시 자동 HITL 분기",
        "Human Review에서 수정/보완 후 승인",
        "승인 시 해당 Stage 재처리 후 재개",
        "모든 재처리도 trace_id로 추적",
    ]
    for i, c in enumerate(hitl_checks):
        txt(ax, HX + 0.005, HY - 0.030 - i * 0.018,
            "[v]  " + c, ha="left", size=6, color="#991B1B")

    # HITL 발동 기준
    rbox(ax, HX, HY - 0.130, HW, 0.090, C["hitl_bg"], C["hitl_bd"],
         lw=1.2, radius=0.007)
    txt(ax, HX + HW/2, HY - 0.045, "HITL 발동 기준 (3지점)",
        size=7, bold=True, color="#991B1B")
    hitl_crit = [
        ("Stage 2 (Markdown 검증)",
         "quality_score < 0.65 (PDF)  /  < 0.80 (기타)"),
        ("Stage 4 (Chunk 검증)",
         "토큰 범위 초과 또는 Parent-Child 연결 실패"),
        ("Stage 5b (Metadata 검증)",
         "metadata_score < 0.70"),
    ]
    for i, (title, crit) in enumerate(hitl_crit):
        hy2 = HY - 0.062 - i * 0.023
        txt(ax, HX + HW/2, hy2, f"{i+1}. {title}",
            size=6, bold=True, color="#7F1D1D")
        txt(ax, HX + HW/2, hy2 - 0.012, crit,
            size=5.5, color=C["text_mid"])

    # 저장 구조
    rbox(ax, HX, HY - 0.250, HW, 0.115, C["store_bg"], C["store_bd"],
         lw=1.2, radius=0.007)
    txt(ax, HX + HW/2, HY - 0.138, "저장 구조 (멀티 스토리지)",
        size=7, bold=True, color=C["title_bg"])

    store_items = [
        ("PostgreSQL", "메타데이터\n(documents, chunks)",  "#1565C0"),
        ("pgVector",   "벡터 저장\n(임베딩 검색)",          "#6A1B9A"),
        ("GCS/Local",  "파일 저장\n(원본, Markdown)",       "#1B5E20"),
        ("Neo4j\nGraphDB", "관계 저장\n(Entity, 그래프 탐색)", "#006064"),
    ]
    s_col_w = (HW - 0.010) / 4
    for i, (name, desc, color) in enumerate(store_items):
        sx2 = HX + 0.005 + i * s_col_w
        rbox(ax, sx2, HY - 0.235, s_col_w - 0.004, 0.085,
             "#FFFFFF", color, lw=1.0, radius=0.005)
        txt(ax, sx2 + (s_col_w-0.004)/2, HY - 0.175, name,
            size=6, bold=True, color=color)
        txt(ax, sx2 + (s_col_w-0.004)/2, HY - 0.198, desc,
            size=5, color=C["text_mid"])

    # RAG / 그래프 탐색 라벨
    rbox(ax, HX, HY - 0.265, HW, 0.018, "#E8EAF6", "#3949AB",
         lw=0.8, radius=0.003)
    txt(ax, HX + HW/2, HY - 0.256,
        "→  RAG 검색 (pgVector)  +  그래프 탐색 (Neo4j)  +  원본 접근 (Storage)",
        size=5.5, color="#3949AB", bold=True)


# ---------------------------------------------------------------------------
# PDF 출력
# ---------------------------------------------------------------------------
def main():
    out = r"d:\Code-Shepherd\docs\kms_pipeline_architecture.pdf"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    fig = plt.figure(figsize=(23.4, 16.5))   # A2 landscape (inch)
    fig.patch.set_facecolor(C["bg"])
    ax = fig.add_axes([0, 0, 1, 1])

    draw(ax)

    with PdfPages(out) as pdf:
        pdf.savefig(fig, bbox_inches="tight", dpi=300,
                    facecolor=C["bg"])

    print("PDF saved: " + out)
    plt.close(fig)


if __name__ == "__main__":
    main()

"""
PDF 보고서 생성 모듈 (ReportLab + NanumGothic)
4-Chapter 구조:
  COVER
  CH01: 경쟁사 분석 (균형·영업·마케팅·경영)
  CH02: 자사 vs 경쟁사 비교 분석
  CH03: 대응 전략 로드맵
  CH04: 법적 검토
"""
import os
import io
import base64
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, Image as RLImage
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── 색상 ────────────────────────────────────────────────────
C_K0   = colors.HexColor("#0A0A0A")
C_K1   = colors.HexColor("#171717")
C_K2   = colors.HexColor("#262626")
C_G1   = colors.HexColor("#404040")
C_G2   = colors.HexColor("#737373")
C_G3   = colors.HexColor("#A3A3A3")
C_G4   = colors.HexColor("#D4D4D4")
C_G5   = colors.HexColor("#E5E5E5")
C_G6   = colors.HexColor("#F0F0F0")
C_G7   = colors.HexColor("#F7F7F7")
C_WH   = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ── 폰트 등록 ────────────────────────────────────────────────

def _register_fonts():
    font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")
    regular = os.path.join(font_dir, "NanumGothic.ttf")
    bold    = os.path.join(font_dir, "NanumGothicBold.ttf")
    extra   = os.path.join(font_dir, "NanumGothicExtraBold.ttf")
    if os.path.exists(regular) and os.path.getsize(regular) > 10000:
        pdfmetrics.registerFont(TTFont("NanumGothic", regular))
        pdfmetrics.registerFont(TTFont("NanumGothicBold",
                                       bold if os.path.exists(bold) else regular))
        pdfmetrics.registerFont(TTFont("NanumGothicExtraBold",
                                       extra if os.path.exists(extra) else regular))
        return "NanumGothic", "NanumGothicBold", "NanumGothicExtraBold"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Bold"


FONT_REG, FONT_BOLD, FONT_XBOLD = _register_fonts()


# ── 스타일 ────────────────────────────────────────────────────

def _styles():
    return {
        "body": ParagraphStyle("body", fontName=FONT_REG, fontSize=9,
                               leading=15, textColor=C_K0, spaceAfter=4),
        "body_sm": ParagraphStyle("body_sm", fontName=FONT_REG, fontSize=8,
                                  leading=13, textColor=C_K0),
        "bold": ParagraphStyle("bold", fontName=FONT_BOLD, fontSize=9,
                               leading=15, textColor=C_K0),
        "heading2": ParagraphStyle("heading2", fontName=FONT_BOLD, fontSize=11,
                                   leading=16, textColor=C_WH, spaceAfter=4),
        "section_title": ParagraphStyle("section_title", fontName=FONT_BOLD, fontSize=10,
                                        leading=15, textColor=C_K0, spaceAfter=6, spaceBefore=10),
        "table_hdr": ParagraphStyle("table_hdr", fontName=FONT_BOLD, fontSize=8,
                                    leading=12, textColor=C_WH, alignment=TA_CENTER),
        "table_cell": ParagraphStyle("table_cell", fontName=FONT_REG, fontSize=8,
                                     leading=13, textColor=C_K0),
        "table_cell_b": ParagraphStyle("table_cell_b", fontName=FONT_BOLD, fontSize=8,
                                       leading=13, textColor=C_K0),
        "center": ParagraphStyle("center", fontName=FONT_REG, fontSize=9,
                                 leading=14, textColor=C_K0, alignment=TA_CENTER),
        "cover_title": ParagraphStyle("cover_title", fontName=FONT_XBOLD, fontSize=26,
                                      leading=34, textColor=C_WH, alignment=TA_CENTER),
        "cover_sub": ParagraphStyle("cover_sub", fontName=FONT_BOLD, fontSize=12,
                                    leading=18, textColor=C_G4, alignment=TA_CENTER),
        "cover_body": ParagraphStyle("cover_body", fontName=FONT_REG, fontSize=9,
                                     leading=15, textColor=C_G3, alignment=TA_CENTER),
        "conclusion": ParagraphStyle("conclusion", fontName=FONT_REG, fontSize=9,
                                     leading=16, textColor=C_K0, alignment=TA_JUSTIFY),
        "risk_high": ParagraphStyle("risk_high", fontName=FONT_BOLD, fontSize=9,
                                    leading=14, textColor=colors.HexColor("#CC0000")),
        "risk_mid": ParagraphStyle("risk_mid", fontName=FONT_BOLD, fontSize=9,
                                   leading=14, textColor=colors.HexColor("#B35900")),
        "risk_low": ParagraphStyle("risk_low", fontName=FONT_BOLD, fontSize=9,
                                   leading=14, textColor=colors.HexColor("#1A6B1A")),
    }


# ── 커스텀 플로어블 ──────────────────────────────────────────

class DarkRect(Flowable):
    """단색 배경 헤더 박스."""
    def __init__(self, text, width, height=22, bg=C_K0, fg=C_WH, font_size=10):
        super().__init__()
        self.text = text; self.width = width; self.height = height
        self.bg = bg; self.fg = fg; self.font_size = font_size

    def draw(self):
        self.canv.setFillColor(self.bg)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        self.canv.setFillColor(self.fg)
        self.canv.setFont(FONT_BOLD, self.font_size)
        self.canv.drawString(8, self.height / 2 - self.font_size / 2 + 1, self.text)


class ChapterPage(Flowable):
    """챕터 구분 전체 페이지."""
    def __init__(self, chapter_no, chapter_title, subtitle=""):
        super().__init__()
        self.chapter_no = chapter_no; self.chapter_title = chapter_title
        self.subtitle = subtitle

    def wrap(self, availWidth, availHeight):
        self.availWidth = availWidth; self.availHeight = availHeight
        return (availWidth, availHeight)

    def draw(self):
        c = self.canv
        # 프레임 좌하단 → 페이지 좌하단으로 이동
        c.translate(-MARGIN, -MARGIN)
        W, H = PAGE_W, PAGE_H
        c.setFillColor(C_K0)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        # 상단 흰색 가로선
        c.setStrokeColor(C_G1)
        c.setLineWidth(1)
        c.line(MARGIN, H - 22 * mm, W - MARGIN, H - 22 * mm)
        # 챕터 번호
        c.setFillColor(C_G3)
        c.setFont(FONT_BOLD, 11)
        c.drawCentredString(W / 2, H / 2 + 52, f"CHAPTER  {self.chapter_no:02d}")
        # 구분선
        c.setStrokeColor(C_G2)
        c.setLineWidth(1)
        c.line(W / 2 - 60, H / 2 + 40, W / 2 + 60, H / 2 + 40)
        # 제목
        c.setFillColor(C_WH)
        c.setFont(FONT_XBOLD, 26)
        c.drawCentredString(W / 2, H / 2, self.chapter_title)
        # 서브타이틀
        if self.subtitle:
            c.setFillColor(C_G3)
            c.setFont(FONT_REG, 10)
            c.drawCentredString(W / 2, H / 2 - 26, self.subtitle)
        # 하단 라인
        c.setStrokeColor(C_G1)
        c.line(MARGIN, 22 * mm, W - MARGIN, 22 * mm)


# ── 헬퍼 ────────────────────────────────────────────────────

def _p(text, style_key, s=None):
    if s is None:
        s = _styles()
    return Paragraph(str(text) if text is not None else "", s[style_key])


def _sec(text):
    return DarkRect(text, CONTENT_W, height=22, bg=C_K0)


def _sub(text):
    return DarkRect(text, CONTENT_W, height=18, bg=C_G1, font_size=9)


def _bullet(items: list, s) -> list:
    return [_p(f"▶  {item}", "body", s) for item in items if item]


def _safe(val, default="정보 없음"):
    if val is None:
        return default
    v = str(val).strip()
    return v if v else default


def _lst(lst: list, sep=", ") -> str:
    if not lst:
        return "없음"
    return sep.join(str(x) for x in lst if x)


def _tbl(data, col_widths, hdr_rows=1):
    tbl = Table(data, colWidths=col_widths, repeatRows=hdr_rows)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, hdr_rows - 1), C_K0),
        ("TEXTCOLOR",     (0, 0), (-1, hdr_rows - 1), C_WH),
        ("FONTNAME",      (0, 0), (-1, hdr_rows - 1), FONT_BOLD),
        ("FONTSIZE",      (0, 0), (-1, hdr_rows - 1), 8),
        ("FONTNAME",      (0, hdr_rows), (-1, -1), FONT_REG),
        ("FONTSIZE",      (0, hdr_rows), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_G4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS",(0, hdr_rows), (-1, -1), [C_WH, C_G7]),
    ]))
    return tbl


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=C_G4, spaceAfter=4, spaceBefore=6)


# ── 페이지 콜백 ──────────────────────────────────────────────

def _on_page(canvas, doc, url=""):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(C_K0)
    canvas.rect(0, 0, w, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(C_G3)
    canvas.setFont(FONT_REG, 7)
    canvas.drawString(MARGIN, 3.2 * mm, f"경쟁사 홈페이지 분석 보고서  |  {url}")
    canvas.drawRightString(w - MARGIN, 3.2 * mm, f"— {doc.page} —")
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════

def _build_cover(url: str, analysis: dict, s) -> list:
    comp = analysis.get("competitor", {})
    overview = comp.get("overview", {})
    company  = _safe(overview.get("company_name"), "경쟁사")
    industry = _safe(overview.get("industry"), "")
    now      = datetime.now().strftime("%Y년 %m월 %d일")
    has_own  = analysis.get("own_company") is not None

    elems = []

    class CoverPage(Flowable):
        def __init__(self):
            super().__init__()

        def wrap(self, availWidth, availHeight):
            return (availWidth, availHeight)

        def draw(self):
            c = self.canv
            # 프레임 좌하단 → 페이지 좌하단으로 이동
            c.translate(-MARGIN, -MARGIN)
            W, H = PAGE_W, PAGE_H
            # 배경
            c.setFillColor(C_K0)
            c.rect(0, 0, W, H, fill=1, stroke=0)
            # 상단 장식선
            c.setFillColor(C_WH)
            c.rect(0, H - 4, W, 4, fill=1, stroke=0)
            c.setFillColor(C_G2)
            c.rect(0, H - 10, W, 4, fill=1, stroke=0)
            # 메인 제목
            c.setFillColor(C_WH)
            c.setFont(FONT_XBOLD, 30)
            c.drawCentredString(W / 2, H * 0.58, "경쟁사 홈페이지")
            c.drawCentredString(W / 2, H * 0.58 - 38, "분석 보고서")
            # 구분선
            c.setStrokeColor(C_G2)
            c.setLineWidth(0.8)
            c.line(MARGIN * 3, H * 0.52, W - MARGIN * 3, H * 0.52)
            # 회사명
            c.setFillColor(C_G4)
            c.setFont(FONT_BOLD, 14)
            txt = company + (f"  ·  {industry}" if industry else "")
            c.drawCentredString(W / 2, H * 0.49, txt)
            # URL
            c.setFillColor(C_G3)
            c.setFont(FONT_REG, 9)
            c.drawCentredString(W / 2, H * 0.455, url)
            # 분석 포함 항목
            tags = ["균형 분석", "영업 중심", "마케팅 중심", "경영 중심",
                    "대응 전략", "법적 검토"]
            if has_own:
                tags.insert(4, "자사 비교")
            tag_w = 70
            total = len(tags) * tag_w + (len(tags) - 1) * 6
            sx = (W - total) / 2
            ty = H * 0.37
            for i, tag in enumerate(tags):
                tx = sx + i * (tag_w + 6)
                c.setFillColor(C_G1)
                c.roundRect(tx, ty, tag_w, 16, 3, fill=1, stroke=0)
                c.setFillColor(C_G4)
                c.setFont(FONT_BOLD, 7.5)
                c.drawCentredString(tx + tag_w / 2, ty + 5, tag)
            # 날짜
            c.setFillColor(C_G2)
            c.setFont(FONT_REG, 8)
            c.drawCentredString(W / 2, H * 0.09, f"생성일: {now}")
            # 하단 라인
            c.setFillColor(C_WH)
            c.rect(0, 0, W, 3, fill=1, stroke=0)

    elems.append(CoverPage())
    elems.append(PageBreak())
    return elems


# ══════════════════════════════════════════════════════════════
# CH01: 경쟁사 분석
# ══════════════════════════════════════════════════════════════

def _img_block(img, caption: str, s) -> list:
    """스크린샷 이미지 + 캡션 블록 (섹션 분석 위에 삽입)."""
    cap_style = ParagraphStyle(
        "img_cap", fontName=FONT_REG, fontSize=7.5, leading=11,
        textColor=C_G2, spaceAfter=6, spaceBefore=2,
    )
    return [
        img,
        Paragraph(f"▲ 실제 홈페이지 캡처  |  {caption}", cap_style),
        _hr(),
        Spacer(1, 4),
    ]


def _build_ch01(analysis: dict, s, rl_images: list = None) -> list:
    """CH01 경쟁사 분석 — 스크린샷을 각 섹션 위에 배치."""
    if rl_images is None:
        rl_images = []
    imgs = list(rl_images)   # 복사본, pop으로 소비

    def next_img(caption: str) -> list:
        """다음 이미지가 있으면 이미지 블록 반환, 없으면 빈 리스트."""
        if imgs:
            return _img_block(imgs.pop(0), caption, s)
        return []

    comp  = analysis.get("competitor", {})
    ov    = comp.get("overview", {})
    elems = []

    elems.append(ChapterPage(1, "경쟁사 분석", "홈페이지 전략 종합 분석"))
    elems.append(PageBreak())

    # ── 1-1 기본 개요 (이미지 없음) ─────────────────────────
    elems.append(_sec("1-1  경쟁사 기본 개요"))
    elems.append(Spacer(1, 4))
    overview_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("회사/브랜드명",  "table_cell_b", s), _p(_safe(ov.get("company_name")),      "table_cell", s)],
        [_p("업종/카테고리",  "table_cell_b", s), _p(_safe(ov.get("industry")),           "table_cell", s)],
        [_p("타겟 고객층",    "table_cell_b", s), _p(_safe(ov.get("target_audience")),    "table_cell", s)],
        [_p("브랜드 포지셔닝","table_cell_b", s), _p(_safe(ov.get("brand_positioning")), "table_cell", s)],
        [_p("핵심 가치 제안", "table_cell_b", s), _p(_safe(ov.get("key_message")),       "table_cell", s)],
        [_p("홈페이지 목적",  "table_cell_b", s), _p(_safe(ov.get("website_purpose")),   "table_cell", s)],
    ]
    elems.append(_tbl(overview_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    elems.append(Spacer(1, 10))

    # ── 1-2 비주얼 & 이미지 전략 ── 캡처 p.1 ────────────────
    img_strat = comp.get("image_strategy", {})
    elems.append(PageBreak())
    elems.append(_sec("1-2  비주얼 & 이미지 전략"))
    elems.append(Spacer(1, 6))
    elems.extend(next_img("상단 히어로 · 비주얼 전략 확인"))
    vis_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("전체 스타일",    "table_cell_b", s), _p(_safe(img_strat.get("overall_style")),      "table_cell", s)],
        [_p("색상 팔레트",    "table_cell_b", s), _p(_safe(img_strat.get("color_palette")),      "table_cell", s)],
        [_p("시각적 일관성",  "table_cell_b", s), _p(_safe(img_strat.get("visual_consistency")), "table_cell", s)],
        [_p("감성적 톤앤매너","table_cell_b", s), _p(_safe(img_strat.get("emotional_tone")),     "table_cell", s)],
    ]
    elems.append(_tbl(vis_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if img_strat.get("analysis"):
        elems.append(Spacer(1, 4))
        elems.append(_p(img_strat["analysis"], "body", s))
    elems.append(Spacer(1, 10))

    # ── 1-3 UX/UI 분석 ── 캡처 p.2 ─────────────────────────
    ux = comp.get("ux_ui", {})
    elems.append(PageBreak())
    elems.append(_sec(f"1-3  UX / UI 분석  (점수: {ux.get('score', '—')} / 10)"))
    elems.append(Spacer(1, 6))
    elems.extend(next_img("레이아웃 · CTA · 전환 흐름 확인"))
    ux_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("레이아웃 구조",  "table_cell_b", s), _p(_safe(ux.get("layout_structure")),    "table_cell", s)],
        [_p("CTA 전략",       "table_cell_b", s), _p(_safe(ux.get("cta_strategy")),        "table_cell", s)],
        [_p("전환 플로우",    "table_cell_b", s), _p(_safe(ux.get("conversion_flow")),     "table_cell", s)],
        [_p("신뢰 구축 요소", "table_cell_b", s), _p(_safe(ux.get("trust_elements")),      "table_cell", s)],
        [_p("모바일 최적화",  "table_cell_b", s), _p(_safe(ux.get("mobile_optimization")), "table_cell", s)],
    ]
    elems.append(_tbl(ux_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if ux.get("improvements"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("개선 포인트"))
        elems.extend(_bullet(ux["improvements"], s))
    elems.append(Spacer(1, 10))

    # ── 1-4 트래킹/마테크 ── 캡처 p.3 ──────────────────────
    trk = comp.get("tracking_analysis", {})
    elems.append(PageBreak())
    elems.append(_sec("1-4  트래킹 & 마테크 도구"))
    elems.append(Spacer(1, 6))
    elems.extend(next_img("트래킹 스크립트 · 광고 픽셀 영역 확인"))
    tools = trk.get("tools_detected", [])
    trk_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("감지된 도구",    "table_cell_b", s), _p(_lst(tools),                                     "table_cell", s)],
        [_p("마케팅 고도화",  "table_cell_b", s), _p(_safe(trk.get("marketing_sophistication")),      "table_cell", s)],
        [_p("데이터 전략",    "table_cell_b", s), _p(_safe(trk.get("data_strategy")),                 "table_cell", s)],
        [_p("리마케팅 역량",  "table_cell_b", s), _p(_safe(trk.get("remarketing_capability")),        "table_cell", s)],
        [_p("추정 광고 채널", "table_cell_b", s), _p(_lst(trk.get("ad_channels", [])),                "table_cell", s)],
    ]
    elems.append(_tbl(trk_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if trk.get("analysis"):
        elems.append(Spacer(1, 4))
        elems.append(_p(trk["analysis"], "body", s))
    elems.append(Spacer(1, 10))

    # ── 1-5 영업 전략 ── 캡처 p.4 ──────────────────────────
    sales = comp.get("sales_strategy", {})
    elems.append(PageBreak())
    elems.append(_sec("1-5  영업 전략 분석  (CTA · 퍼널 · 전환)"))
    elems.append(Spacer(1, 6))
    elems.extend(next_img("CTA 배치 · 영업 퍼널 · 신뢰 요소 확인"))
    sales_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("리드 생성 방식",  "table_cell_b", s), _p(_safe(sales.get("lead_generation_method")), "table_cell", s)],
        [_p("영업 퍼널 구조",  "table_cell_b", s), _p(_safe(sales.get("sales_funnel_design")),    "table_cell", s)],
        [_p("반론 처리",       "table_cell_b", s), _p(_safe(sales.get("objection_handling")),     "table_cell", s)],
        [_p("신뢰 구축 전략",  "table_cell_b", s), _p(_safe(sales.get("trust_building")),         "table_cell", s)],
        [_p("긴박감/희소성",   "table_cell_b", s), _p(_safe(sales.get("urgency_tactics")),        "table_cell", s)],
    ]
    elems.append(_tbl(sales_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if sales.get("key_insights"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("영업 핵심 인사이트"))
        elems.extend(_bullet(sales["key_insights"], s))
    if sales.get("action_items"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("영업팀 즉시 적용 방안"))
        elems.extend(_bullet(sales["action_items"], s))
    elems.append(Spacer(1, 10))

    # ── 1-6 마케팅 전략 ── 캡처 p.5 ────────────────────────
    mkt = comp.get("marketing_strategy", {})
    elems.append(PageBreak())
    elems.append(_sec("1-6  마케팅 전략 분석  (브랜드 · 콘텐츠 · 광고)"))
    elems.append(Spacer(1, 6))
    elems.extend(next_img("브랜드 메시지 · 콘텐츠 배치 확인"))
    mkt_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("메시징 프레임워크","table_cell_b", s), _p(_safe(mkt.get("brand_messaging_framework")), "table_cell", s)],
        [_p("콘텐츠 전략",      "table_cell_b", s), _p(_safe(mkt.get("content_strategy")),          "table_cell", s)],
        [_p("차별화 포인트",    "table_cell_b", s), _p(_lst(mkt.get("differentiators", [])),         "table_cell", s)],
        [_p("감성적 소구",      "table_cell_b", s), _p(_safe(mkt.get("emotional_appeal")),           "table_cell", s)],
    ]
    elems.append(_tbl(mkt_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if mkt.get("key_insights"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("마케팅 핵심 인사이트"))
        elems.extend(_bullet(mkt["key_insights"], s))
    if mkt.get("action_items"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("마케팅팀 즉시 적용 방안"))
        elems.extend(_bullet(mkt["action_items"], s))
    elems.append(Spacer(1, 10))

    # ── 1-7 경영 전략 ── 캡처 p.6 ──────────────────────────
    mgmt = comp.get("management_strategy", {})
    elems.append(PageBreak())
    elems.append(_sec("1-7  경영 전략 분석  (전략 · 포지셔닝)"))
    elems.append(Spacer(1, 6))
    elems.extend(next_img("비즈니스 모델 · 포지셔닝 확인"))
    mgmt_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("비즈니스 모델",   "table_cell_b", s), _p(_safe(mgmt.get("business_model_estimate")),   "table_cell", s)],
        [_p("경쟁 포지셔닝",   "table_cell_b", s), _p(_safe(mgmt.get("competitive_positioning")),   "table_cell", s)],
        [_p("성장 방향 신호",  "table_cell_b", s), _p(_safe(mgmt.get("growth_signals")),             "table_cell", s)],
        [_p("자원 투자 영역",  "table_cell_b", s), _p(_safe(mgmt.get("resource_investment_focus")), "table_cell", s)],
    ]
    elems.append(_tbl(mgmt_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if mgmt.get("key_insights"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("경영 핵심 인사이트"))
        elems.extend(_bullet(mgmt["key_insights"], s))
    if mgmt.get("action_items"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("경영진 전략 제언"))
        elems.extend(_bullet(mgmt["action_items"], s))
    elems.append(Spacer(1, 10))

    # ── 1-8 남은 스크린샷 (추가 캡처) ───────────────────────
    if imgs:
        elems.append(PageBreak())
        elems.append(_sec(f"1-8  홈페이지 추가 캡처  ({len(imgs)}페이지)"))
        elems.append(Spacer(1, 6))
        for i, extra_img in enumerate(imgs, 1):
            elems.append(_p(f"추가 캡처 {i}", "bold", s))
            elems.append(Spacer(1, 3))
            elems.append(extra_img)
            elems.append(Spacer(1, 10))

    return elems


# ══════════════════════════════════════════════════════════════
# 첨부 이미지 → ReportLab Image 변환
# ══════════════════════════════════════════════════════════════

def _attachment_images_to_rl(attachment_paths: list, max_pages: int = 6) -> list:
    """PDF/이미지 첨부파일을 ReportLab Image 리스트로 변환 (PyMuPDF 사용)."""
    result = []
    for path in attachment_paths:
        if len(result) >= max_pages:
            break
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(path)
                for page_idx in range(min(len(doc), max_pages - len(result))):
                    page = doc[page_idx]
                    mat = fitz.Matrix(1.5, 1.5)  # 1.5× 해상도
                    pix = page.get_pixmap(matrix=mat)
                    buf = io.BytesIO(pix.tobytes("jpeg"))
                    buf.seek(0)
                    orig_w, orig_h = pix.width, pix.height
                    aspect = orig_h / orig_w
                    img_w = CONTENT_W
                    img_h = min(img_w * aspect, 220 * mm)
                    result.append(RLImage(buf, width=img_w, height=img_h))
                doc.close()
            except Exception as e:
                print(f"PDF 이미지 변환 실패 ({path}): {e}")
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            try:
                from PIL import Image as PILImage
                img = PILImage.open(path)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                orig_w, orig_h = img.size
                aspect = orig_h / orig_w
                img_w = CONTENT_W
                img_h = min(img_w * aspect, 220 * mm)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=82)
                buf.seek(0)
                result.append(RLImage(buf, width=img_w, height=img_h))
            except Exception as e:
                print(f"이미지 변환 실패 ({path}): {e}")
    return result


# ══════════════════════════════════════════════════════════════
# CH02: 자사 vs 경쟁사 비교
# ══════════════════════════════════════════════════════════════

def _build_ch02(analysis: dict, own_url: str, s) -> list:
    own  = analysis.get("own_company")
    cmp  = analysis.get("comparison")
    elems = []

    elems.append(PageBreak())  # 이전 챕터 끝에서 새 페이지
    elems.append(ChapterPage(2, "자사 vs 경쟁사", "비교 분석 및 개선 제안"))
    elems.append(PageBreak())

    if not own or not cmp:
        elems.append(Spacer(1, 20))
        elems.append(_p("자사 홈페이지 URL이 입력되지 않아 비교 분석이 생략되었습니다.", "body", s))
        elems.append(_p("비교 분석을 원하시면 분석 시 자사 URL을 함께 입력해주세요.", "body", s))
        return elems

    # 2-1 자사 현황
    ov = own.get("overview", {})
    elems.append(_sec("2-1  자사 현황"))
    elems.append(Spacer(1, 4))
    if own_url:
        elems.append(_p(f"자사 URL: {own_url}", "body_sm", s))
        elems.append(Spacer(1, 3))
    own_rows = [
        [_p("항목", "table_hdr", s), _p("내용", "table_hdr", s)],
        [_p("회사/브랜드명", "table_cell_b", s), _p(_safe(ov.get("company_name")), "table_cell", s)],
        [_p("업종", "table_cell_b", s), _p(_safe(ov.get("industry")), "table_cell", s)],
        [_p("현재 포지셔닝", "table_cell_b", s), _p(_safe(ov.get("brand_positioning")), "table_cell", s)],
        [_p("홈페이지 목적", "table_cell_b", s), _p(_safe(ov.get("website_purpose")), "table_cell", s)],
    ]
    elems.append(_tbl(own_rows, [CONTENT_W * 0.28, CONTENT_W * 0.72]))
    if own.get("current_strengths"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("자사 현재 강점"))
        elems.extend(_bullet(own["current_strengths"], s))
    if own.get("current_weaknesses"):
        elems.append(Spacer(1, 4))
        elems.append(_sub("자사 현재 약점"))
        elems.extend(_bullet(own["current_weaknesses"], s))
    elems.append(Spacer(1, 10))

    # 2-2 개선 필요 항목
    improvements = cmp.get("improvements", [])
    if improvements:
        elems.append(_sec("2-2  개선 필요 항목"))
        elems.append(Spacer(1, 4))
        imp_hdr = [
            _p("개선 영역", "table_hdr", s),
            _p("경쟁사 방식", "table_hdr", s),
            _p("자사 현황", "table_hdr", s),
            _p("우선순위", "table_hdr", s),
        ]
        imp_rows = [imp_hdr]
        for item in improvements[:12]:
            imp_rows.append([
                _p(_safe(item.get("area")), "table_cell_b", s),
                _p(_safe(item.get("competitor_approach")), "table_cell", s),
                _p(_safe(item.get("our_current")), "table_cell", s),
                _p(_safe(item.get("priority")), "table_cell", s),
            ])
        elems.append(_tbl(imp_rows, [CONTENT_W * 0.2, CONTENT_W * 0.32,
                                     CONTENT_W * 0.32, CONTENT_W * 0.16]))

        # 개선 제안 상세
        elems.append(Spacer(1, 6))
        elems.append(_sub("개선 제안 상세"))
        for item in improvements[:8]:
            rec = item.get("recommendation", "")
            area = item.get("area", "")
            if rec:
                elems.append(_p(f"[{area}] {rec}", "body", s))
        elems.append(Spacer(1, 10))

    # 2-3 경쟁사 우위 / 자사 우위
    comp_adv = cmp.get("competitor_advantages", [])
    own_adv  = cmp.get("our_advantages", [])
    if comp_adv or own_adv:
        elems.append(_sec("2-3  우위 비교"))
        elems.append(Spacer(1, 4))
        col_w = (CONTENT_W - 4) / 2
        adv_hdr = [_p("경쟁사 우위", "table_hdr", s), _p("자사 우위", "table_hdr", s)]
        max_rows = max(len(comp_adv), len(own_adv), 1)
        adv_rows = [adv_hdr]
        for i in range(max_rows):
            adv_rows.append([
                _p(comp_adv[i] if i < len(comp_adv) else "—", "table_cell", s),
                _p(own_adv[i]  if i < len(own_adv)  else "—", "table_cell", s),
            ])
        elems.append(_tbl(adv_rows, [col_w, col_w]))

    return elems


# ══════════════════════════════════════════════════════════════
# CH03: 대응 전략
# ══════════════════════════════════════════════════════════════

def _build_ch03(analysis: dict, s) -> list:
    cm    = analysis.get("countermeasures", {})
    elems = []

    elems.append(PageBreak())  # 이전 챕터 끝에서 새 페이지
    elems.append(ChapterPage(3, "대응 전략", "경쟁사 대비 전략 로드맵"))
    elems.append(PageBreak())

    # 3-1 전략 요약
    strategic = cm.get("strategic_response", "")
    if strategic:
        elems.append(_sec("3-1  종합 대응 전략 요약"))
        elems.append(Spacer(1, 6))
        elems.append(_p(strategic, "conclusion", s))
        elems.append(Spacer(1, 10))

    # 3-2 로드맵 테이블
    elems.append(_sec("3-2  실행 로드맵"))
    elems.append(Spacer(1, 4))

    def _roadmap_col(items: list, label: str):
        if not items:
            return _p("—", "table_cell", s)
        return _p("\n".join(f"· {x}" for x in items), "table_cell", s)

    road_hdr = [
        _p("즉시 실행", "table_hdr", s),
        _p("1개월 내", "table_hdr", s),
        _p("3개월 내", "table_hdr", s),
        _p("6개월+", "table_hdr", s),
    ]
    road_rows = [road_hdr, [
        _roadmap_col(cm.get("immediate", []), "즉시"),
        _roadmap_col(cm.get("month_1",   []), "1개월"),
        _roadmap_col(cm.get("month_3",   []), "3개월"),
        _roadmap_col(cm.get("month_6",   []), "6개월"),
    ]]
    col_w = CONTENT_W / 4
    elems.append(_tbl(road_rows, [col_w, col_w, col_w, col_w]))
    elems.append(Spacer(1, 10))

    # 3-3 즉시 실행 항목 상세
    immediate = cm.get("immediate", [])
    if immediate:
        elems.append(_sub("즉시 실행 항목 상세"))
        elems.extend(_bullet(immediate, s))
        elems.append(Spacer(1, 8))

    # 3-4 중기 계획
    m1 = cm.get("month_1", []); m3 = cm.get("month_3", [])
    if m1 or m3:
        elems.append(_sub("중기 계획 (1~3개월)"))
        for item in m1 + m3:
            elems.append(_p(f"▶  {item}", "body", s))
        elems.append(Spacer(1, 8))

    # 3-5 장기 전략
    m6 = cm.get("month_6", [])
    if m6:
        elems.append(_sub("장기 전략 (6개월 이상)"))
        elems.extend(_bullet(m6, s))

    return elems


# ══════════════════════════════════════════════════════════════
# CH04: 법적 검토
# ══════════════════════════════════════════════════════════════

def _build_ch04(analysis: dict, s) -> list:
    legal = analysis.get("legal_check", {})
    elems = []

    elems.append(PageBreak())  # 이전 챕터 끝에서 새 페이지
    elems.append(ChapterPage(4, "법적 검토", "저작권 · 광고법 · 개인정보보호"))
    elems.append(PageBreak())

    # 4-1 위험도 종합
    risk = _safe(legal.get("overall_risk"), "평가 불가")
    risk_style = "risk_high" if "고위험" in risk else ("risk_mid" if "중위험" in risk else "risk_low")
    elems.append(_sec("4-1  종합 법적 위험도"))
    elems.append(Spacer(1, 6))
    elems.append(_p(f"종합 위험 등급: {risk}", risk_style, s))
    elems.append(Spacer(1, 4))

    privacy = legal.get("data_privacy", "")
    if privacy:
        elems.append(_p(privacy, "body", s))
    elems.append(Spacer(1, 10))

    # 4-2 잠재 법적 이슈
    issues = legal.get("potential_issues", [])
    if issues:
        elems.append(_sec("4-2  잠재 법적 이슈"))
        elems.append(Spacer(1, 4))
        issue_rows = [[_p("No.", "table_hdr", s), _p("이슈 내용", "table_hdr", s)]]
        for i, iss in enumerate(issues, 1):
            issue_rows.append([
                _p(str(i), "table_cell_b", s),
                _p(_safe(iss), "table_cell", s),
            ])
        elems.append(_tbl(issue_rows, [CONTENT_W * 0.1, CONTENT_W * 0.9]))
        elems.append(Spacer(1, 10))

    # 4-3 저작권 / 광고법
    col_w = (CONTENT_W - 4) / 2
    copy_items = legal.get("copyright_concerns", [])
    ad_items   = legal.get("advertising_compliance", [])

    if copy_items or ad_items:
        elems.append(_sec("4-3  저작권 · 광고법 검토"))
        elems.append(Spacer(1, 4))
        hdr = [_p("저작권 검토", "table_hdr", s), _p("광고법 검토", "table_hdr", s)]
        max_r = max(len(copy_items), len(ad_items), 1)
        rows = [hdr]
        for i in range(max_r):
            rows.append([
                _p(copy_items[i] if i < len(copy_items) else "—", "table_cell", s),
                _p(ad_items[i]   if i < len(ad_items)   else "—", "table_cell", s),
            ])
        elems.append(_tbl(rows, [col_w, col_w]))
        elems.append(Spacer(1, 10))

    # 4-4 법적 권고사항
    recs = legal.get("recommendations", [])
    if recs:
        elems.append(_sec("4-4  법적 권고사항"))
        elems.append(Spacer(1, 4))
        elems.extend(_bullet(recs, s))

    return elems


# ══════════════════════════════════════════════════════════════
# 결론
# ══════════════════════════════════════════════════════════════

def _build_conclusion(analysis: dict, s) -> list:
    conclusion = analysis.get("conclusion", "")
    if not conclusion:
        return []
    elems = [PageBreak()]
    elems.append(_sec("종합 결론"))
    elems.append(Spacer(1, 8))
    elems.append(_p(conclusion, "conclusion", s))
    return elems


# ══════════════════════════════════════════════════════════════
# 메인 진입점
# ══════════════════════════════════════════════════════════════

def generate_pdf(url: str, crawl_data: dict, analysis: dict, attachment_paths: list,
                 output_path: str, own_url: str = "", own_crawl_data: dict | None = None):
    """4-Chapter PDF 보고서 생성."""

    s = _styles()

    # 첨부파일 → ReportLab 이미지 변환 (최대 6페이지)
    rl_images = _attachment_images_to_rl(attachment_paths, max_pages=6)
    print(f"[PDF] 첨부 이미지 {len(rl_images)}장 삽입 예정")

    def on_page(canvas, doc):
        _on_page(canvas, doc, url)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=14 * mm,
    )

    story = []
    story += _build_cover(url, analysis, s)
    story += _build_ch01(analysis, s, rl_images=rl_images)  # 스크린샷을 각 섹션에 분배
    story += _build_ch02(analysis, own_url, s)
    story += _build_ch03(analysis, s)
    story += _build_ch04(analysis, s)
    story += _build_conclusion(analysis, s)

    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=on_page)

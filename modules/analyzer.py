"""
Claude API 분석 모듈
- 경쟁사 크롤링 데이터 + 자사 크롤링 데이터(선택) + 첨부파일 → Claude vision 분석
- 4개 모드 통합(균형·영업·마케팅·경영) + 자사 비교 + 대응전략 + 법적검토
"""
import os
import io
import json
import re
import base64
from pathlib import Path
import anthropic


SYSTEM_PROMPT = (
    "당신은 15년 경력의 마케팅 & 비즈니스 전략 전문 분석가입니다.\n"
    "경쟁사 홈페이지를 분석하여 영업/마케팅/경영 전략 인사이트를 도출하고,\n"
    "자사 홈페이지와 비교해 개선점·대응 전략·법적 검토 결과를 함께 제시합니다.\n\n"
    "중요: 한국어 맞춤법을 정확히 지켜 작성하세요. (예: 프리미엄, 솔루션, 플랫폼, 마케팅, 브랜드 등 외래어도 표준 표기법 준수)\n"
    "반드시 순수 JSON만 반환하세요. 마크다운 코드블록(```json)이나 추가 텍스트 없이 JSON 객체만 반환합니다."
)


# ── 이미지 처리 ──────────────────────────────────────────────

def get_images_from_attachments(attachment_paths: list) -> list:
    images = []
    for path in attachment_paths:
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            images.extend(_pdf_to_images(path))
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            img_data = _image_to_base64(path)
            if img_data:
                images.append({**img_data, "label": Path(path).name})
    return images[:5]


def _pdf_to_images(pdf_path: str) -> list:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        result = []
        for i in range(min(len(doc), 2)):  # 최대 2페이지만 Claude 분석에 사용
            page = doc[i]
            mat = fitz.Matrix(1.2, 1.2)
            pix = page.get_pixmap(matrix=mat)
            b64 = base64.standard_b64encode(pix.tobytes("jpeg")).decode()
            result.append({"data": b64, "media_type": "image/jpeg",
                           "label": f"{Path(pdf_path).name} - p.{i+1}"})
        doc.close()
        return result
    except Exception as e:
        print(f"PDF 변환 실패 ({pdf_path}): {e}")
        return []


def _image_to_base64(image_path: str) -> dict | None:
    try:
        from PIL import Image
        img = Image.open(image_path)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((1400, 1400), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        b64 = base64.standard_b64encode(buf.getvalue()).decode()
        return {"data": b64, "media_type": "image/jpeg"}
    except Exception as e:
        print(f"이미지 처리 실패 ({image_path}): {e}")
        return None


# ── 프롬프트 빌더 ─────────────────────────────────────────────

def _crawl_summary(crawl_data: dict, label: str) -> str:
    tracking_list   = list(crawl_data.get("tracking", {}).keys())
    nav_items       = [n["text"] for n in crawl_data.get("navigation", [])]
    cta_texts       = [c["text"] for c in crawl_data.get("ctas", [])]
    image_list      = ["- " + img["src"].split("/")[-1] + ": " + img["alt"]
                       for img in crawl_data.get("images", [])[:10]]
    sections_parts  = []
    for s in crawl_data.get("sections", [])[:8]:
        heading = s.get("heading") or s.get("label", "")
        sections_parts.append(f"  섹션{s['index']} [{heading}]: {s['text'][:180]}")
    sections_summary = "\n".join(sections_parts)
    meta   = crawl_data.get("meta", {})
    forms  = crawl_data.get("forms", [])
    form_t = "\n폼 구조: " + json.dumps(forms, ensure_ascii=False) if forms else ""
    full_text = crawl_data.get("full_text", "")[:2500]

    lines = [
        f"=== [{label}] 기본 정보 ===",
        f"URL: {crawl_data.get('url', '')}",
        f"페이지 제목: {crawl_data.get('title', '')}",
        f"메타 설명: {meta.get('description', '')}",
        f"OG 제목: {meta.get('og_title', '')}",
        f"\n=== [{label}] 감지된 트래킹/마테크 도구 ===",
        ", ".join(tracking_list) if tracking_list else "없음",
        f"\n=== [{label}] 네비게이션 구조 ===",
        " > ".join(nav_items) if nav_items else "감지 안됨",
        f"\n=== [{label}] 주요 CTA ===",
        ", ".join(cta_texts[:12]) if cta_texts else "없음",
        form_t,
        f"\n=== [{label}] 섹션 구조 ===",
        sections_summary if sections_summary else "구조 추출 실패",
        f"\n=== [{label}] 홈페이지 전체 텍스트 ===",
        full_text,
        f"\n=== [{label}] 이미지 목록 ===",
        "\n".join(image_list) if image_list else "없음",
    ]
    return "\n".join(lines)


def build_analysis_prompt(crawl_data: dict, own_crawl_data: dict | None) -> str:
    has_own = own_crawl_data is not None

    comp_section = _crawl_summary(crawl_data, "경쟁사")
    own_section  = ("\n\n" + _crawl_summary(own_crawl_data, "자사")) if has_own else ""

    own_schema = (
        'null' if not has_own else
        '{"company_name":"자사명","brand_positioning":"포지셔닝","strengths":["강점1","강점2"],"weaknesses":["약점1","약점2"]}'
    )
    cmp_schema = (
        'null' if not has_own else
        '{"competitor_advantages":["경쟁우위1","경쟁우위2"],'
        '"our_advantages":["자사강점1","자사강점2"],'
        '"improvements":['
        '{"area":"개선영역",'
        '"competitor_approach":"경쟁사가 이 영역에서 실제로 하고 있는 방식 (구체적으로)",'
        '"our_current":"자사의 현재 이 영역 현황 (구체적으로)",'
        '"recommendation":"개선 제안",'
        '"priority":"높음/중간/낮음"}'
        ']}'
    )

    prompt = (
        "아래 홈페이지 데이터를 분석해서 JSON만 반환하세요 (코드블록 없이 중괄호로 시작).\n\n"
        + comp_section
        + own_section
        + "\n\n"
        + ("★ 자사 데이터가 있으므로 own_company와 comparison을 반드시 채우세요." if has_own
           else "★ 자사 데이터 없음 — own_company, comparison은 null.")
        + "\n\n반환 형식 (값은 모두 한국어, 구체적으로):\n"
        "{\n"
        '  "competitor":{\n'
        '    "overview":{"company_name":"","industry":"","target_audience":"","brand_positioning":"","key_message":"","website_purpose":""},\n'
        '    "ux_ui":{"layout":"","cta_strategy":"","trust_elements":"","score":7,"improvements":[""]},\n'
        '    "image_strategy":{"style":"","color_palette":"","emotional_tone":"","analysis":""},\n'
        '    "tracking":{"tools":[""],"sophistication":"중급","ad_channels":[""],"analysis":""},\n'
        '    "sales":{"lead_gen":"","funnel":"","trust_tactic":"","insights":["","",""],"actions":["","",""]},\n'
        '    "marketing":{"messaging":"","content_strategy":"","differentiators":["",""],"insights":["","",""],"actions":["","",""]},\n'
        '    "management":{"biz_model":"","positioning":"","growth_signals":"","insights":["","",""],"actions":["","",""]}\n'
        "  },\n"
        '  "own_company":' + own_schema + ',\n'
        '  "comparison":' + cmp_schema + ',\n'
        '  "countermeasures":{\n'
        '    "immediate":["","",""],\n'
        '    "month_1":["",""],\n'
        '    "month_3":["",""],\n'
        '    "month_6":["",""],\n'
        '    "strategic_response":""\n'
        "  },\n"
        '  "legal_check":{\n'
        '    "issues":["",""],"copyright":[""],"ad_law":[""],"data_privacy":"","risk":"중위험","recs":["",""]\n'
        "  },\n"
        '  "conclusion":""\n'
        "}"
    )
    return prompt


# ── 결과 정규화 (compact → 기존 pdf_generator 키 형식) ──────────

def _normalize(result: dict) -> dict:
    """compact 응답을 pdf_generator가 기대하는 키 구조로 변환."""
    comp = result.get("competitor", {})

    # tracking
    trk_raw = comp.get("tracking", comp.get("tracking_analysis", {}))
    trk = {
        "tools_detected":          trk_raw.get("tools", trk_raw.get("tools_detected", [])),
        "marketing_sophistication": trk_raw.get("sophistication", trk_raw.get("marketing_sophistication", "")),
        "data_strategy":           trk_raw.get("data_strategy", ""),
        "remarketing_capability":  trk_raw.get("remarketing_capability", ""),
        "ad_channels":             trk_raw.get("ad_channels", []),
        "analysis":                trk_raw.get("analysis", ""),
    }

    # ux_ui
    ux_raw = comp.get("ux_ui", {})
    ux = {
        "layout_structure":   ux_raw.get("layout", ux_raw.get("layout_structure", "")),
        "cta_strategy":       ux_raw.get("cta_strategy", ""),
        "conversion_flow":    ux_raw.get("conversion_flow", ""),
        "trust_elements":     ux_raw.get("trust_elements", ""),
        "mobile_optimization":ux_raw.get("mobile_optimization", ""),
        "score":              ux_raw.get("score", 0),
        "improvements":       ux_raw.get("improvements", []),
    }

    # image_strategy
    img_raw = comp.get("image_strategy", {})
    img = {
        "overall_style":      img_raw.get("style", img_raw.get("overall_style", "")),
        "color_palette":      img_raw.get("color_palette", ""),
        "visual_consistency": img_raw.get("visual_consistency", ""),
        "emotional_tone":     img_raw.get("emotional_tone", ""),
        "analysis":           img_raw.get("analysis", ""),
    }

    # sales_strategy
    s_raw = comp.get("sales", comp.get("sales_strategy", {}))
    sales = {
        "lead_generation_method": s_raw.get("lead_gen", s_raw.get("lead_generation_method", "")),
        "sales_funnel_design":    s_raw.get("funnel", s_raw.get("sales_funnel_design", "")),
        "objection_handling":     s_raw.get("objection_handling", ""),
        "trust_building":         s_raw.get("trust_tactic", s_raw.get("trust_building", "")),
        "urgency_tactics":        s_raw.get("urgency_tactics", ""),
        "key_insights":           s_raw.get("insights", s_raw.get("key_insights", [])),
        "action_items":           s_raw.get("actions", s_raw.get("action_items", [])),
    }

    # marketing_strategy
    m_raw = comp.get("marketing", comp.get("marketing_strategy", {}))
    mkt = {
        "brand_messaging_framework": m_raw.get("messaging", m_raw.get("brand_messaging_framework", "")),
        "content_strategy":          m_raw.get("content_strategy", ""),
        "differentiators":           m_raw.get("differentiators", []),
        "emotional_appeal":          m_raw.get("emotional_appeal", ""),
        "key_insights":              m_raw.get("insights", m_raw.get("key_insights", [])),
        "action_items":              m_raw.get("actions", m_raw.get("action_items", [])),
    }

    # management_strategy
    g_raw = comp.get("management", comp.get("management_strategy", {}))
    mgmt = {
        "business_model_estimate":  g_raw.get("biz_model", g_raw.get("business_model_estimate", "")),
        "competitive_positioning":  g_raw.get("positioning", g_raw.get("competitive_positioning", "")),
        "growth_signals":           g_raw.get("growth_signals", ""),
        "resource_investment_focus":g_raw.get("resource_investment_focus", ""),
        "key_insights":             g_raw.get("insights", g_raw.get("key_insights", [])),
        "action_items":             g_raw.get("actions", g_raw.get("action_items", [])),
    }

    comp_norm = {**comp,
                 "tracking_analysis": trk,
                 "ux_ui": ux,
                 "image_strategy": img,
                 "sales_strategy": sales,
                 "marketing_strategy": mkt,
                 "management_strategy": mgmt}

    # own_company 정규화
    own_raw = result.get("own_company")
    if own_raw and isinstance(own_raw, dict):
        # compact: company_name, strengths, weaknesses 직접 키
        # 기존: overview.{company_name, ...}, current_strengths, current_weaknesses
        if "overview" not in own_raw:
            own_norm = {
                "overview": {
                    "company_name":      own_raw.get("company_name", ""),
                    "industry":          own_raw.get("industry", ""),
                    "brand_positioning": own_raw.get("brand_positioning", ""),
                    "website_purpose":   own_raw.get("website_purpose", ""),
                },
                "current_strengths":  own_raw.get("strengths", own_raw.get("current_strengths", [])),
                "current_weaknesses": own_raw.get("weaknesses", own_raw.get("current_weaknesses", [])),
            }
        else:
            own_norm = own_raw
    else:
        own_norm = own_raw  # None

    # comparison 정규화
    cmp_raw = result.get("comparison")
    if cmp_raw and isinstance(cmp_raw, dict):
        imps = cmp_raw.get("improvements", [])
        # compact improvements: {area, recommendation, priority}
        # 기존: {area, competitor_approach, our_current, recommendation, priority}
        imps_norm = []
        for item in imps:
            imps_norm.append({
                "area":                 item.get("area", ""),
                "competitor_approach":  item.get("competitor_approach", ""),
                "our_current":          item.get("our_current", ""),
                "recommendation":       item.get("recommendation", ""),
                "priority":             item.get("priority", ""),
            })
        cmp_norm = {**cmp_raw, "improvements": imps_norm}
    else:
        cmp_norm = cmp_raw  # None

    # legal_check 정규화
    legal_raw = result.get("legal_check", {})
    legal_norm = {
        "potential_issues":       legal_raw.get("issues", legal_raw.get("potential_issues", [])),
        "copyright_concerns":     legal_raw.get("copyright", legal_raw.get("copyright_concerns", [])),
        "advertising_compliance": legal_raw.get("ad_law", legal_raw.get("advertising_compliance", [])),
        "data_privacy":           legal_raw.get("data_privacy", ""),
        "overall_risk":           legal_raw.get("risk", legal_raw.get("overall_risk", "")),
        "recommendations":        legal_raw.get("recs", legal_raw.get("recommendations", [])),
    }

    return {
        **result,
        "competitor":  comp_norm,
        "own_company": own_norm,
        "comparison":  cmp_norm,
        "legal_check": legal_norm,
    }


# ── 메인 분석 함수 ────────────────────────────────────────────

def analyze_with_claude(crawl_data: dict, attachment_paths: list,
                        own_crawl_data: dict | None = None) -> dict:
    """Claude API를 통한 홈페이지 종합 분석."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    print(f"[DEBUG] ANTHROPIC_API_KEY present: {bool(api_key)}, length: {len(api_key)}")
    if not api_key:
        raise Exception("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=api_key)

    attachment_images = get_images_from_attachments(attachment_paths)

    user_content = []
    for img_data in attachment_images[:5]:
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img_data["media_type"],
                "data": img_data["data"],
            },
        })
        user_content.append({
            "type": "text",
            "text": f"[첨부 이미지: {img_data.get('label', '이미지')}]",
        })

    user_content.append({
        "type": "text",
        "text": build_analysis_prompt(crawl_data, own_crawl_data),
    })

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        timeout=300,   # 5분 타임아웃
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_text = response.content[0].text.strip()

    # 마크다운 코드블록 제거 (```json ... ``` 또는 ``` ... ```)
    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # {} 블록 추출 시도
        match = re.search(r"\{[\s\S]+\}", cleaned)
        if match:
            try:
                parsed = json.loads(match.group())
            except Exception:
                pass
            else:
                return _normalize(parsed)
        raise Exception(f"분석 결과 JSON 파싱 실패. 응답 시작: {raw_text[:300]}")
    return _normalize(parsed)

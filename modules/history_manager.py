"""
분석 히스토리 관리 모듈
- JSON 파일 기반 히스토리 저장/조회
- 같은 URL 이전 분석 감지
- 두 분석 결과 비교
"""
import os
import json
import uuid
from datetime import datetime


FOCUS_MODE_LABELS = {
    "sales": "영업중심",
    "marketing": "마케팅중심",
    "management": "경영중심",
    "balanced": "균형분석",
}


class HistoryManager:
    def __init__(self, history_dir: str = "history"):
        self.history_dir = history_dir
        os.makedirs(history_dir, exist_ok=True)

    def save(self, url: str, focus_mode: str, analysis: dict, pdf_filename: str, own_url: str = "") -> dict:
        """분석 결과를 히스토리에 저장."""
        entry_id = str(uuid.uuid4())
        comp = analysis.get("competitor", {})
        overview = comp.get("overview", analysis.get("overview", {}))

        entry = {
            "id": entry_id,
            "url": url,
            "own_url": own_url,
            "focus_mode": focus_mode,
            "focus_mode_label": "전체 분석",
            "created_at": datetime.now().isoformat(),
            "pdf_filename": pdf_filename,
            "analysis": analysis,
            "summary": {
                "company_name": overview.get("company_name", ""),
                "industry": overview.get("industry", ""),
                "target_audience": overview.get("target_audience", ""),
                "key_message": overview.get("key_message", ""),
                "brand_positioning": overview.get("brand_positioning", ""),
                "ux_score": comp.get("ux_ui", analysis.get("ux_ui", {})).get("score", 0),
                "tracking_tools": list(comp.get("tracking_analysis", analysis.get("tracking_analysis", {})).get("tools_detected", [])),
                "overall_risk": analysis.get("legal_check", {}).get("overall_risk", ""),
                "conclusion_preview": (analysis.get("conclusion", "") or "")[:150],
            },
        }

        path = os.path.join(self.history_dir, f"{entry_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        return entry

    def list_all(self) -> list:
        """모든 히스토리 목록 반환 (최신순)."""
        entries = []
        for filename in os.listdir(self.history_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.history_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries.append({
                    "id": data["id"],
                    "url": data["url"],
                    "own_url": data.get("own_url", ""),
                    "focus_mode": data.get("focus_mode", "all"),
                    "focus_mode_label": data.get("focus_mode_label", "전체 분석"),
                    "created_at": data["created_at"],
                    "pdf_filename": data.get("pdf_filename", ""),
                    "summary": data.get("summary", {}),
                })
            except Exception:
                continue

        entries.sort(key=lambda x: x["created_at"], reverse=True)
        return entries

    def get(self, entry_id: str) -> dict | None:
        """특정 히스토리 항목 전체 데이터 반환."""
        path = os.path.join(self.history_dir, f"{entry_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def find_by_url(self, url: str) -> list:
        """같은 URL의 이전 분석 결과 목록 반환."""
        all_entries = self.list_all()
        # URL 정규화 (scheme, trailing slash 무시)
        normalized = _normalize_url(url)
        return [
            e for e in all_entries
            if _normalize_url(e["url"]) == normalized
        ]

    def delete(self, entry_id: str) -> bool:
        """히스토리 항목 삭제."""
        path = os.path.join(self.history_dir, f"{entry_id}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def compare(self, entry1: dict, entry2: dict) -> dict:
        """두 분석 결과 비교."""
        a1 = entry1.get("analysis", {})
        a2 = entry2.get("analysis", {})

        return {
            "meta": {
                "entry1": _entry_meta(entry1),
                "entry2": _entry_meta(entry2),
                "same_url": _normalize_url(entry1["url"]) == _normalize_url(entry2["url"]),
            },
            "overview_comparison": {
                "fields": ["company_name", "industry", "target_audience", "key_message", "brand_positioning"],
                "entry1": a1.get("overview", {}),
                "entry2": a2.get("overview", {}),
            },
            "scores": {
                "ux_score": {
                    "entry1": a1.get("ux_ui", {}).get("score", 0),
                    "entry2": a2.get("ux_ui", {}).get("score", 0),
                    "diff": (a1.get("ux_ui", {}).get("score", 0) or 0)
                            - (a2.get("ux_ui", {}).get("score", 0) or 0),
                }
            },
            "tracking_comparison": {
                "entry1_tools": list(a1.get("tracking_analysis", {}).get("tools_detected", [])),
                "entry2_tools": list(a2.get("tracking_analysis", {}).get("tools_detected", [])),
                "only_in_entry1": _set_diff(
                    a1.get("tracking_analysis", {}).get("tools_detected", []),
                    a2.get("tracking_analysis", {}).get("tools_detected", []),
                ),
                "only_in_entry2": _set_diff(
                    a2.get("tracking_analysis", {}).get("tools_detected", []),
                    a1.get("tracking_analysis", {}).get("tools_detected", []),
                ),
            },
            "competitive_benchmark": {
                "entry1": a1.get("competitive_benchmark", {}),
                "entry2": a2.get("competitive_benchmark", {}),
            },
            "strategy_comparison": {
                "sales": {
                    "entry1_insights": a1.get("sales_strategy", {}).get("key_insights", []),
                    "entry2_insights": a2.get("sales_strategy", {}).get("key_insights", []),
                },
                "marketing": {
                    "entry1_insights": a1.get("marketing_strategy", {}).get("key_insights", []),
                    "entry2_insights": a2.get("marketing_strategy", {}).get("key_insights", []),
                },
                "management": {
                    "entry1_insights": a1.get("management_strategy", {}).get("key_insights", []),
                    "entry2_insights": a2.get("management_strategy", {}).get("key_insights", []),
                },
            },
            "key_differences": _generate_differences(a1, a2),
            "application_synthesis": _synthesize_applications(a1, a2),
        }


def _normalize_url(url: str) -> str:
    """URL을 비교를 위해 정규화."""
    url = url.lower().strip()
    url = url.rstrip("/")
    for prefix in ("https://", "http://", "www."):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url


def _entry_meta(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "url": entry["url"],
        "focus_mode": entry.get("focus_mode", "balanced"),
        "focus_mode_label": entry.get("focus_mode_label", "균형분석"),
        "created_at": entry["created_at"],
        "company_name": entry.get("summary", {}).get("company_name", ""),
    }


def _set_diff(list1: list, list2: list) -> list:
    set2 = set(list2)
    return [x for x in list1 if x not in set2]


def _generate_differences(a1: dict, a2: dict) -> list:
    """두 분석의 주요 차이점 생성."""
    differences = []

    # UX 점수 차이
    s1 = a1.get("ux_ui", {}).get("score", 0) or 0
    s2 = a2.get("ux_ui", {}).get("score", 0) or 0
    if abs(s1 - s2) >= 2:
        better = "분석1" if s1 > s2 else "분석2"
        differences.append({
            "category": "UX/UI 점수",
            "description": f"UX 점수 차이: 분석1({s1}점) vs 분석2({s2}점) → {better}이 더 높음",
        })

    # 트래킹 도구 차이
    tools1 = set(a1.get("tracking_analysis", {}).get("tools_detected", []))
    tools2 = set(a2.get("tracking_analysis", {}).get("tools_detected", []))
    if tools1 != tools2:
        only1 = tools1 - tools2
        only2 = tools2 - tools1
        if only1:
            differences.append({
                "category": "마테크 도구",
                "description": f"분석1에만 있는 도구: {', '.join(only1)}",
            })
        if only2:
            differences.append({
                "category": "마테크 도구",
                "description": f"분석2에만 있는 도구: {', '.join(only2)}",
            })

    # 브랜드 포지셔닝 차이
    pos1 = a1.get("overview", {}).get("brand_positioning", "")
    pos2 = a2.get("overview", {}).get("brand_positioning", "")
    if pos1 and pos2 and pos1[:30] != pos2[:30]:
        differences.append({
            "category": "브랜드 포지셔닝",
            "description": f"포지셔닝 변화 감지: '{pos1[:50]}' → '{pos2[:50]}'",
        })

    # 마케팅 고도화 수준
    soph1 = a1.get("tracking_analysis", {}).get("marketing_sophistication", "")
    soph2 = a2.get("tracking_analysis", {}).get("marketing_sophistication", "")
    if soph1 and soph2 and soph1 != soph2:
        differences.append({
            "category": "마케팅 고도화",
            "description": f"마케팅 고도화 변화: '{soph1}' → '{soph2}'",
        })

    return differences


def _synthesize_applications(a1: dict, a2: dict) -> dict:
    """두 분석의 우리 브랜드 적용 방안을 통합."""
    actions1 = a1.get("our_brand_application", {}).get("immediate_actions", [])
    actions2 = a2.get("our_brand_application", {}).get("immediate_actions", [])

    # 중복 제거 후 통합
    all_actions = list(dict.fromkeys(actions1 + actions2))

    return {
        "combined_immediate_actions": all_actions[:5],
        "learning1": a1.get("our_brand_application", {}).get("key_learnings", ""),
        "learning2": a2.get("our_brand_application", {}).get("key_learnings", ""),
    }

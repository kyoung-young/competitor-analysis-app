"""
홈페이지 크롤링 모듈
- HTML 소스 수집
- 텍스트/카피/섹션 구조 추출
- 트래킹 스크립트 감지
- 이미지 목록 수집
"""
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

TRACKING_PATTERNS = {
    "Facebook Pixel": ["fbq(", "facebook.net/en_US/fbevents.js", "connect.facebook.net"],
    "Google Tag Manager": ["googletagmanager.com/gtm.js", "GTM-"],
    "Google Analytics (UA)": ["google-analytics.com/analytics.js", "'UA-", '"UA-'],
    "Google Analytics 4": ["gtag('config'", 'gtag("config"', "G-", "googletagmanager.com/gtag"],
    "Naver Analytics": ["wcs.naver.com", "naver_wcslog", "wcslog.js"],
    "Kakao Pixel": ["kakao_pixel", "kpf.kakao.com", "kakaoplus"],
    "Kakao AdFit": ["AdFit", "ad.kakao.com"],
    "Piwik/Matomo": ["piwik.js", "matomo.js", "_paq.push"],
    "HotJar": ["hotjar.com", "hjid"],
    "Amplitude": ["amplitude.com/libs", "amplitude.getInstance"],
    "Mixpanel": ["mixpanel.com/lib", "mixpanel.track"],
    "Criteo": ["static.criteo.net", "criteo_q"],
    "Naver GFA": ["widerplanet.com", "naver.com/analytics"],
    "Channel.io": ["channel.io", "ChannelIO"],
    "Intercom": ["widget.intercom.io", "intercomSettings"],
    "Zendesk": ["zendesk.com/embeddable"],
    "Kakao Talk Chat": ["pf.kakao.com"],
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def crawl_website(url: str) -> dict:
    """메인 크롤링 함수. 홈페이지 전체 정보를 수집."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        final_url = resp.url
    except requests.exceptions.SSLError:
        # SSL 오류 시 검증 비활성화로 재시도
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30, verify=False)
        html = resp.text
        final_url = resp.url
    except Exception as e:
        raise Exception(f"크롤링 실패: {str(e)}")

    soup = BeautifulSoup(html, "html.parser")

    # 스크립트/스타일 제거 전 원본 HTML에서 트래킹 분석
    tracking = detect_tracking(html)
    forms = extract_forms(soup)

    # 스크립트/스타일 태그 제거
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    return {
        "url": final_url,
        "original_url": url,
        "title": _get_title(soup),
        "meta": extract_meta(soup),
        "navigation": extract_navigation(soup),
        "sections": extract_sections(soup),
        "full_text": _clean_text(soup.get_text(separator="\n"), max_chars=10000),
        "images": extract_images(soup, final_url),
        "ctas": extract_ctas(soup),
        "tracking": tracking,
        "forms": forms,
        "links": extract_links(soup, final_url),
    }


def _get_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _clean_text(text: str, max_chars: int = 10000) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)[:max_chars]


def extract_meta(soup: BeautifulSoup) -> dict:
    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name", tag.get("property", "")).lower()
        content = tag.get("content", "")
        if not content:
            continue
        if name in ("description", "keywords"):
            meta[name] = content
        elif name == "og:title":
            meta["og_title"] = content
        elif name == "og:description":
            meta["og_description"] = content
        elif name == "og:image":
            meta["og_image"] = content
    return meta


def extract_navigation(soup: BeautifulSoup) -> list:
    items = []
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    if nav:
        for a in nav.find_all("a", limit=20):
            text = a.get_text(strip=True)
            if text and len(text) < 40:
                items.append({"text": text, "href": a.get("href", "")})
    return items


def extract_sections(soup: BeautifulSoup) -> list:
    sections = []
    candidates = soup.find_all(
        ["section", "article", "header", "main", "footer",
         lambda tag: tag.name == "div" and tag.get("id") or
                     tag.name == "div" and tag.get("class")],
        limit=20
    )

    for i, tag in enumerate(candidates[:15]):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) < 40:
            continue

        heading = ""
        for h in tag.find_all(["h1", "h2", "h3"], limit=1):
            heading = h.get_text(strip=True)
            break

        tag_id = tag.get("id", "")
        tag_class = " ".join(tag.get("class", []))[:50]
        label = tag_id or tag_class or f"section_{i+1}"

        sections.append({
            "index": i + 1,
            "tag": tag.name,
            "label": label,
            "heading": heading,
            "text": text[:600],
        })
    return sections


def extract_images(soup: BeautifulSoup, base_url: str) -> list:
    images = []
    seen = set()
    for img in soup.find_all("img", limit=30):
        src = img.get("src", img.get("data-src", ""))
        if not src or src in seen:
            continue
        seen.add(src)
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            parsed = urlparse(base_url)
            src = f"{parsed.scheme}://{parsed.netloc}{src}"
        images.append({
            "src": src,
            "alt": img.get("alt", ""),
            "width": img.get("width", ""),
            "height": img.get("height", ""),
        })
    return images[:20]


def extract_ctas(soup: BeautifulSoup) -> list:
    ctas = []
    seen = set()
    for el in soup.find_all(["button", "a"], limit=50):
        text = el.get_text(strip=True)
        if not text or len(text) > 60 or text in seen:
            continue
        href = el.get("href", "")
        # 의미 있는 CTA만 수집 (이미지나 아이콘 제외)
        if len(text) > 1:
            seen.add(text)
            ctas.append({"text": text, "href": href, "tag": el.name})
    return ctas[:20]


def detect_tracking(html: str) -> dict:
    """HTML 소스에서 트래킹 도구 감지."""
    detected = {}
    for tool_name, patterns in TRACKING_PATTERNS.items():
        for pattern in patterns:
            if pattern in html:
                detected[tool_name] = True
                break
    return detected


def extract_forms(soup: BeautifulSoup) -> list:
    forms = []
    for form in soup.find_all("form", limit=5):
        action = form.get("action", "")
        method = form.get("method", "get").upper()
        inputs = []
        for inp in form.find_all(["input", "select", "textarea"]):
            inp_type = inp.get("type", inp.name)
            inp_name = inp.get("name", inp.get("placeholder", ""))
            if inp_type not in ("hidden", "submit", "button"):
                inputs.append({"type": inp_type, "name": inp_name})
        if inputs:
            forms.append({"action": action, "method": method, "inputs": inputs})
    return forms


def extract_links(soup: BeautifulSoup, base_url: str) -> list:
    """외부/내부 링크 분류."""
    parsed_base = urlparse(base_url)
    internal, external = [], []
    for a in soup.find_all("a", href=True, limit=50):
        href = a["href"]
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        try:
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != parsed_base.netloc:
                external.append(href)
            else:
                internal.append(href)
        except Exception:
            pass
    return {"internal_count": len(internal), "external": external[:10]}

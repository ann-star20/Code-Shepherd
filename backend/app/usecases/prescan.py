"""G3: Pre-scan Layer — URL 패턴 + HTML 메타 추론."""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class PreScanResult:
    framework: str | None = None
    version: str | None = None
    lang: str | None = None  # "EN" | "KO" | None
    confidence: float = 0.0


# (pattern, framework, version_group_idx)
_URL_FRAMEWORK_PATTERNS: list[tuple[re.Pattern, str, int | None]] = [
    (re.compile(r"docs\.djangoproject\.com/(\w+)/(\d+\.\d+)/"), "Django", 2),
    (re.compile(r"docs\.spring\.io"), "Spring", None),
    (re.compile(r"fastapi\.tiangolo\.com"), "FastAPI", None),
    (re.compile(r"flask\.palletsprojects\.com/en/(\d+\.x)/"), "Flask", 1),
    (re.compile(r"laravel\.com/docs/(\d+\.\d+)/"), "Laravel", 1),
    (re.compile(r"reactjs\.org|react\.dev"), "React", None),
    (re.compile(r"nextjs\.org/docs"), "Next.js", None),
    (re.compile(r"vuejs\.org"), "Vue", None),
    (re.compile(r"angular\.io"), "Angular", None),
]

_URL_LANG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"/en/|/en-us/|/english/", re.IGNORECASE), "EN"),
    (re.compile(r"/ko/|/ko-kr/|/korean/", re.IGNORECASE), "KO"),
    (re.compile(r"\.com/en/"), "EN"),
    (re.compile(r"djangoproject\.com/en/"), "EN"),
]

_TITLE_FRAMEWORK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bDjango\b", re.IGNORECASE), "Django"),
    (re.compile(r"\bSpring\b", re.IGNORECASE), "Spring"),
    (re.compile(r"\bFastAPI\b", re.IGNORECASE), "FastAPI"),
    (re.compile(r"\bFlask\b", re.IGNORECASE), "Flask"),
    (re.compile(r"\bLaravel\b", re.IGNORECASE), "Laravel"),
    (re.compile(r"\bReact\b", re.IGNORECASE), "React"),
    (re.compile(r"\bNext\.js\b", re.IGNORECASE), "Next.js"),
    (re.compile(r"\bVue\b", re.IGNORECASE), "Vue"),
    (re.compile(r"\bAngular\b", re.IGNORECASE), "Angular"),
]


def prescan_url(url: str) -> PreScanResult:
    result = PreScanResult()

    for pattern, framework, ver_group in _URL_FRAMEWORK_PATTERNS:
        m = pattern.search(url)
        if m:
            result.framework = framework
            result.confidence = min(result.confidence + 0.6, 1.0)
            if ver_group is not None and ver_group <= len(m.groups()):
                result.version = m.group(ver_group)
            break

    for pattern, lang in _URL_LANG_PATTERNS:
        if pattern.search(url):
            result.lang = lang
            result.confidence = min(result.confidence + 0.3, 1.0)
            break

    return result


def prescan_html(html: str) -> PreScanResult:
    result = PreScanResult()

    if not html.strip():
        return result

    soup = BeautifulSoup(html, "html.parser")

    # <html lang> 속성
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):  # type: ignore[union-attr]
        lang_attr: str = html_tag.get("lang", "").lower()  # type: ignore[assignment]
        if lang_attr.startswith("ko"):
            result.lang = "KO"
            result.confidence = min(result.confidence + 0.3, 1.0)
        elif lang_attr.startswith("en"):
            result.lang = "EN"
            result.confidence = min(result.confidence + 0.3, 1.0)

    # <title> + <h1> 텍스트
    title_text = soup.title.string if soup.title else ""
    h1_tag = soup.find("h1")
    h1_text = h1_tag.get_text() if h1_tag else ""
    candidate = f"{title_text} {h1_text}"

    for pattern, framework in _TITLE_FRAMEWORK_PATTERNS:
        if pattern.search(candidate):
            result.framework = framework
            result.confidence = min(result.confidence + 0.4, 1.0)
            break

    return result


def prescan(url: str, html: str) -> PreScanResult:
    url_result = prescan_url(url)
    html_result = prescan_html(html)

    merged = PreScanResult(
        framework=url_result.framework or html_result.framework,
        version=url_result.version or html_result.version,
        lang=url_result.lang or html_result.lang,
        confidence=min(url_result.confidence + html_result.confidence, 1.0),
    )
    return merged

"""HTML parsing, date filtering, and duplicate detection for SEMAS notices."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from loan.semas.keywords import POLICY_LOAN_KEYWORDS, detect_keywords, normalize_space


SKIP_NAV_TITLES = {
    "소상공인정책자금",
    "사이트맵",
    "정책자금한눈에보기",
    "금리안내",
    "공지사항",
    "직접대출",
    "대리대출",
    "도로명주소안내",
    "자주하는질문과답변",
    "상환스케줄계산기",
    "지역센터찾기",
    "지역본부찾기",
    "로그인",
    "회원가입",
    "검색",
}


@dataclass(frozen=True)
class SemasNotice:
    title: str
    url: str
    posted_date: str = ""
    keywords: list[str] = field(default_factory=list)
    raw_text: str = ""

    @property
    def key(self) -> str:
        return make_notice_key(self)


def parse_date(text: str) -> str:
    """Extract a date as YYYY-MM-DD from common Korean/list formats."""
    if not text:
        return ""
    patterns = [
        r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})",
        r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            try:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                return ""
    return ""


def page_text_from_html(html: str) -> str:
    """Extract visible text from a page without logging or storing raw HTML."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return normalize_space(soup.get_text(" ", strip=True))


def make_notice_key(notice: SemasNotice) -> str:
    """Hash title, URL, and date; fall back to title+URL when date is missing."""
    parts = [notice.title.strip(), notice.url.strip()]
    if notice.posted_date:
        parts.append(notice.posted_date.strip())
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def _candidate_from_anchor(anchor, base_url: str) -> SemasNotice | None:
    title = normalize_space(anchor.get_text(" ", strip=True))
    if not title or len(title) < 4:
        return None
    compact_title = title.replace(" ", "")
    if compact_title in SKIP_NAV_TITLES:
        return None
    href = (anchor.get("href") or "").strip()
    href_lower = href.lower()
    if any(blocked in href_lower for blocked in ("login", "logout", "javascript:login", "juso.go.kr")):
        return None
    url = urljoin(base_url, href) if href and not href_lower.startswith("javascript") else base_url
    parent = anchor
    for _ in range(4):
        if parent.parent is None:
            break
        parent = parent.parent
        if parent.name in {"tr", "li", "article", "section"}:
            break
    raw_text = normalize_space(parent.get_text(" ", strip=True))
    keywords = detect_keywords(f"{title} {raw_text}")
    if not keywords and not any(term in title for term in POLICY_LOAN_KEYWORDS):
        return None
    return SemasNotice(
        title=title,
        url=url,
        posted_date=parse_date(raw_text),
        keywords=keywords,
        raw_text=raw_text[:300],
    )


def parse_notices(html: str, base_url: str) -> list[SemasNotice]:
    """Parse relevant SEMAS notice candidates from login-free HTML."""
    soup = BeautifulSoup(html or "", "html.parser")
    notices: list[SemasNotice] = []
    seen_keys: set[str] = set()
    for anchor in soup.find_all("a"):
        notice = _candidate_from_anchor(anchor, base_url)
        if not notice:
            continue
        if notice.key in seen_keys:
            continue
        seen_keys.add(notice.key)
        notices.append(notice)
    return notices


def is_recent_notice(notice: SemasNotice, lookback_days: int, *, today: date | None = None) -> bool | None:
    """Return True/False for dated notices and None when the posted date is unknown."""
    if not notice.posted_date:
        return None
    current_date = today or datetime.now().date()
    try:
        posted = datetime.strptime(notice.posted_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    start = current_date - timedelta(days=max(0, lookback_days - 1))
    return start <= posted <= current_date


def classify_notices(
    notices: list[SemasNotice],
    seen_keys: set[str],
    lookback_days: int,
    *,
    today: date | None = None,
) -> dict[str, list[SemasNotice] | int]:
    """Deduplicate notices, split new/existing, and keep same-run duplicates out."""
    unique: list[SemasNotice] = []
    duplicate: list[SemasNotice] = []
    batch_seen: set[str] = set()
    for notice in notices:
        if notice.key in batch_seen:
            duplicate.append(notice)
            continue
        batch_seen.add(notice.key)
        unique.append(notice)

    recent_or_unknown = [
        notice for notice in unique
        if is_recent_notice(notice, lookback_days, today=today) is not False
    ]
    new = [notice for notice in recent_or_unknown if notice.key not in seen_keys]
    existing = [notice for notice in recent_or_unknown if notice.key in seen_keys]
    return {
        "unique": unique,
        "recent_or_unknown": recent_or_unknown,
        "new": new,
        "existing": existing,
        "duplicate": duplicate,
        "duplicate_removed_count": len(duplicate),
    }


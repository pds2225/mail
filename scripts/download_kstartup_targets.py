"""K-Startup target notice attachment downloader.

Usage:
    python scripts/download_kstartup_targets.py --dry-run
    python scripts/download_kstartup_targets.py
    python scripts/download_kstartup_targets.py --target-file config/targets/kstartup_20260623.txt --out-dir downloads/kstartup/20260623

This script is intentionally separated from monitor.py send mode. It matches only
the target titles listed in the target file, opens each K-Startup detail page,
extracts likely attachment/download links, and stores files by notice title.
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from email.message import Message
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote, urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# monitor.py requires these env vars at import time although K-Startup collection
# does not need the real values. Keep local downloader runnable without sending mail.
os.environ.setdefault("BIZINFO_API_KEY", "dummy")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
os.environ.setdefault("GMAIL_ADDRESS", "dummy@example.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "dummy")

import httpx  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

import monitor  # noqa: E402

log = logging.getLogger(__name__)

KSTARTUP_SITE = {
    "id": "kstartup",
    "name": "K-Startup",
    "type": "kstartup_html",
    "url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do",
    "enabled": True,
    "is_aggregator": False,
}

ATTACHMENT_TEXT_RE = re.compile(
    r"첨부|붙임|파일|다운로드|download|공고문|신청서|사업계획서|양식|서식|안내문|모집공고|운영지침|zip|hwp|hwpx|pdf|docx?|xlsx?",
    re.IGNORECASE,
)
ATTACHMENT_URL_RE = re.compile(
    r"/afile/fileDownload/|download|fileDown|FileDown|attach|atch|cmm/fms|\.hwp|\.hwpx|\.pdf|\.docx?|\.xlsx?|\.zip",
    re.IGNORECASE,
)
EXT_RE = re.compile(r"\.(hwp|hwpx|pdf|doc|docx|xls|xlsx|ppt|pptx|zip|7z|rar)(?:$|[?#])", re.IGNORECASE)
# eGovFrame 표준 첨부 다운로드 JS: fn_egov_downFile('FILE_000000000013068','0')
# (캠코 등 전자정부 표준프레임워크 사이트 — href 없이 onclick 만 있어 URL 합성 필요)
EGOV_DOWNFILE_RE = re.compile(
    r"fn_egov_downFile(?:_cs)?\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]?(\w+)['\"]?",
    re.IGNORECASE,
)
EGOV_FILEDOWN_PATH = "/cmm/fms/FileDown.do"
# 사이트 공통 영역(footer·GNB·배너 등) — 인증서 PDF 같은 '게시물 첨부 아님' 링크의 서식지
CHROME_TAGS = {"footer", "nav", "aside"}
CHROME_TOKEN_RE = re.compile(
    r"^(footer|foot|gnb|lnb|snb|quick|banner|bnr|copyright|sitemap|breadcrumb|util|skipnav)([-_].*)?$",
    re.IGNORECASE,
)
WINDOWS_BAD_CHARS = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")
SCRIPT_NOISE_RE = re.compile(
    r"function\s*\(|JSON\.parse|console\.|var\s+|const\s+|let\s+|<script|</|\{\s*|\}\s*|\$\(",
    re.IGNORECASE,
)


@dataclass
class AttachmentCandidate:
    url: str
    label: str
    source: str


@dataclass
class DownloadResult:
    target_title: str
    matched_title: str
    match_score: float
    detail_url: str
    status: str
    file_name: str = ""
    save_path: str = ""
    file_url: str = ""
    error: str = ""
    match_source: str = ""


BIZINFO_SITE = {
    "id": "bizinfo",
    "name": "기업마당",
    "type": "bizinfo_api",
    "url": "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do",
    "enabled": True,
    "is_aggregator": True,
}

OUTBOUND_LABEL_RE = re.compile(r"원본|사업안내|공고\s*보기|접수|공고문|붙임|첨부", re.IGNORECASE)
OUTBOUND_SKIP_RE = re.compile(
    r"magicsso|tokenInfoRelay|openNews_letter|applNwsLtr|#container|javascript:void|"
    r"k-startup\.go\.kr/?$|webPMSBizUnvs|/passni/kstartup",
    re.IGNORECASE,
)
SEARCH_STOPWORDS = {
    "참여기업", "참가기업", "참가자", "모집공고", "모집", "공고", "지원사업",
    "프로그램", "년도", "통합공고", "재공고", "연장", "차", "참여", "지원", "기업",
    "모집공고", "공모", "참가", "신청",
}

# Host-site pools used when K-Startup / bizinfo title pools miss.
EXTRA_SOURCE_IDS = (
    "sba", "mss", "kosme", "gsp", "gtp", "ccei_biz", "nipa", "bizok",
    "imp_46829488", "kotra", "mssmiv", "smtech",
)

MATCH_MIN_SCORE = 0.72


def norm_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("새로운게시글", "")
    value = re.sub(r"\([^)]{0,24}\)", "", value)
    value = re.sub(r"\s+", "", value.lower())
    value = re.sub(r"[\[\]【】()（）『』「」<>〈〉·ㆍ,._~\-–—:;/'\"!@#$%^&*+=?]", "", value)
    return value


def safe_filename(value: str, max_len: int = 140) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = WINDOWS_BAD_CHARS.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    return (value[:max_len].strip(" ._") or "untitled")


def load_targets(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")]


def _parse_kstartup_cards(html: str, clss: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for card in soup.select(".notice"):
        a = card.select_one("a")
        title = monitor.norm(a.get_text() if a else "")
        if not title:
            continue
        sn = ""
        for btn in card.select("button[onclick]"):
            m = re.search(r"\d+", btn.get("onclick", ""))
            if m:
                sn = m.group(0)
                break
        if not sn and a:
            m = re.search(r"\d+", a.get("href", ""))
            if m:
                sn = m.group(0)
        link = (f"{KSTARTUP_SITE['url']}?pbancClssCd={clss}&schM=view&pbancSn={sn}") if sn else KSTARTUP_SITE["url"]
        spans = card.select("span.list")
        org = monitor.norm(spans[0].get_text()) if spans else ""
        dl = next((monitor.norm(sp.get_text().replace("마감일자", "")) for sp in spans if "마감일자" in sp.get_text()), "")
        pm = re.search(r"등록일자\s*([\d.\-]{8,10})", card.get_text(" ", strip=True))
        posted = monitor.extract_date_from_text(pm.group(1)) if pm else ""
        flag = card.select_one(".flag:not(.day):not(.flag_agency)")
        iid = f"kstartup_{sn}" if sn else f"kstartup_{monitor.stable_id(title + org)}"
        items.append({
            "id": iid,
            "title": title,
            "link": link,
            "author": org,
            "description": monitor.norm(flag.get_text()) if flag else "",
            "deadline": dl,
            "source": KSTARTUP_SITE["name"],
            "posted_date": posted,
            "is_aggregator": False,
        })
    return items


def _token_set(value: str) -> set[str]:
    return {t for t in re.findall(r"[\w가-힣·]+", norm_text(value)) if len(t) >= 2}


def _anchor_tokens(value: str) -> set[str]:
    return {t for t in _token_set(value) if len(t) >= 4 and t not in SEARCH_STOPWORDS}


def _apply_anchor_boost(target: str, title: str, score: float) -> float:
    anchors_t = _anchor_tokens(target)
    if not anchors_t:
        return score
    shared = anchors_t & _anchor_tokens(title)
    if len(shared) >= 2:
        return max(score, 0.92)
    if len(shared) == 1:
        tok = next(iter(shared))
        if len(tok) >= 8:
            return max(score, 0.85)
        if len(tok) >= 5 and score >= 0.45:
            return max(score, 0.76)
    ratio = len(shared) / len(anchors_t)
    if ratio >= 0.45 and score >= 0.40:
        return max(score, 0.72 + ratio * 0.22)
    return score


def accept_match(target: str, title: str, score: float, min_score: float = MATCH_MIN_SCORE) -> bool:
    """Decide whether a fuzzy title match is good enough to use."""
    t = monitor.norm(title or "")
    if len(t) < 4 or t in {"공고", "공지", "알림", "notice", "[2]", "[1]"}:
        return False
    if score >= min_score:
        return True
    floor = min(min_score, 0.65)
    if score < floor:
        return False
    anchors_t = _anchor_tokens(target)
    shared = anchors_t & _anchor_tokens(title) if anchors_t else set()
    if shared:
        if any(len(t) >= 6 for t in shared):
            return True
        if len(shared) >= 2:
            return True
        if len(shared) / len(anchors_t) >= 0.35 and score >= 0.62:
            return True
    return score >= max(0.70, min_score - 0.02)


def search_keywords_from_title(title: str) -> list[str]:
    """Derive K-Startup search keywords from a target notice title."""
    title = monitor.norm(title)
    keywords: list[str] = []
    seen_kw: set[str] = set()

    def add(kw: str) -> None:
        kw = kw.strip()
        if len(kw) < 2 or kw in seen_kw:
            return
        seen_kw.add(kw)
        keywords.append(kw)

    for m in re.finditer(r"[「『\[【]([^\]」』】]+)[」』\]】]", title):
        add(m.group(1))
    for tok in re.findall(r"[\w가-힣·@!]+", title):
        if len(tok) < 3 or tok in SEARCH_STOPWORDS or re.fullmatch(r"20\d{2}", tok):
            continue
        add(tok)
    trimmed = re.sub(r"^20\d{2}년\s*", "", title)
    trimmed = re.sub(r"(모집|공고|참여).*$", "", trimmed).strip(" ·-")
    if len(trimmed) >= 6:
        add(trimmed[:40])
    return keywords[:8]


def collect_bizinfo_items() -> list[dict]:
    return monitor.fetch_bizinfo(BIZINFO_SITE)


def collect_extra_source_items() -> list[dict]:
    """Fetch high-value host sites (SBA, MSS, KOSME, …) for title matching."""
    by_id = {s["id"]: s for s in monitor.load_sites()}
    sites = [by_id[sid] for sid in EXTRA_SOURCE_IDS if sid in by_id and by_id[sid].get("enabled", True)]
    if not sites:
        return []
    items = monitor.fetch_all(sites, max_workers=min(8, len(sites)))
    deduped = monitor.dedup_items(items)
    log.info("Extra source pools: %d sites -> %d notices", len(sites), len(deduped))
    return deduped


def collect_full_monitor_items(max_workers: int = 10) -> list[dict]:
    """Fetch all enabled monitor sites — last-resort pool to avoid title misses."""
    sites = monitor.load_sites()
    items = monitor.fetch_all(sites, max_workers=max_workers)
    deduped = monitor.dedup_items(items)
    log.info("Full monitor pool: %d sites -> %d notices", len(sites), len(deduped))
    return deduped


def collect_kstartup_items(max_pages: int = 30, client: httpx.Client | None = None) -> list[dict]:
    """Collect K-Startup public/private ongoing notices across multiple pages.

    monitor.fetch_kstartup() is intentionally conservative and reads page 1 only.
    Bulk title downloads need deeper pagination because user-provided title lists
    often come from page 2+ or from K-Startup search results.
    """
    items: list[dict] = []
    seen_ids: set[str] = set()
    headers = {**monitor.HTTP_HEADERS, "Referer": KSTARTUP_SITE["url"]}

    def _collect_with(http_client: httpx.Client) -> None:
        for clss in ("PBC010", "PBC020"):
            empty_pages = 0
            for page in range(1, max_pages + 1):
                r = http_client.get(KSTARTUP_SITE["url"], params={
                    "schMenuId": "10090",
                    "pageIndex": str(page),
                    "viewCount": "100",
                    "pbancSttus": "ing",
                    "pbancClssCd": clss,
                })
                r.raise_for_status()
                page_items = _parse_kstartup_cards(r.text, clss)
                new_count = 0
                for item in page_items:
                    iid = str(item.get("id", ""))
                    if iid in seen_ids:
                        continue
                    seen_ids.add(iid)
                    items.append(item)
                    new_count += 1
                if not page_items or new_count == 0:
                    empty_pages += 1
                else:
                    empty_pages = 0
                if empty_pages >= 2:
                    break

    if client is not None:
        _collect_with(client)
    else:
        with httpx.Client(timeout=60, headers=headers, follow_redirects=True, verify=False) as owned:
            _collect_with(owned)
    log.info("K-Startup multi-page: %d건", len(items))
    return items


def search_kstartup_for_target(
    target: str,
    client: httpx.Client,
    *,
    min_score: float,
) -> tuple[dict | None, float]:
    """Search K-Startup by title keywords and locally re-rank the returned cards."""
    nt = norm_text(target)
    best: tuple[dict | None, float] = (None, 0.0)
    for kw in search_keywords_from_title(target):
        nkw = norm_text(kw)
        if len(nkw) < 2:
            continue
        for clss in ("PBC010", "PBC020"):
            r = client.get(KSTARTUP_SITE["url"], params={
                "schMenuId": "10090",
                "pageIndex": "1",
                "viewCount": "100",
                "schPbancNm": kw,
                "pbancClssCd": clss,
            })
            r.raise_for_status()
            page_items = _parse_kstartup_cards(r.text, clss)
            filtered = [
                it for it in page_items
                if nkw in norm_text(str(it.get("title", ""))) or norm_text(str(it.get("title", ""))) in nt
            ]
            item, score = match_notice(target, filtered or page_items)
            if score > best[1]:
                best = (item, score)
            if item and score >= min_score:
                return item, score
    if best[1] >= min_score:
        return best
    return None, best[1]


def search_pool_for_target(
    target: str,
    pool: list[dict],
    *,
    min_score: float,
) -> tuple[dict | None, float]:
    """Match against a pool, then keyword-filtered subsets of the same pool."""
    item, score = match_notice(target, pool)
    if item and accept_match(target, str(item.get("title", "")), score, min_score):
        return item, score
    best_item, best_score = item, score
    for kw in search_keywords_from_title(target):
        nkw = norm_text(kw)
        if len(nkw) < 3:
            continue
        filtered = [
            it for it in pool
            if nkw in norm_text(str(it.get("title", "")))
            or norm_text(str(it.get("title", ""))) in norm_text(target)
        ]
        if not filtered:
            continue
        item, score = match_notice(target, filtered)
        if score > best_score:
            best_item, best_score = item, score
        if item and accept_match(target, str(item.get("title", "")), score, min_score):
            return item, score
    if best_item and accept_match(target, str(best_item.get("title", "")), best_score, min_score):
        return best_item, best_score
    return None, best_score


def find_notice_for_target(
    target: str,
    kstartup_pool: list[dict],
    client: httpx.Client,
    *,
    bizinfo_pool: list[dict] | None,
    extra_pool: list[dict] | None,
    monitor_pool: list[dict] | None,
    min_score: float,
    use_bizinfo: bool = True,
    use_extra_sources: bool = True,
) -> tuple[dict | None, float, str]:
    """Find a notice by target title. Returns (item, score, source)."""
    best_item: dict | None = None
    best_score = 0.0
    best_source = ""

    def consider(item: dict | None, score: float, source: str) -> tuple[dict | None, float, str] | None:
        nonlocal best_item, best_score, best_source
        if score > best_score:
            best_item, best_score, best_source = item, score, source
        title = str((item or {}).get("title", ""))
        if item and accept_match(target, title, score, min_score):
            return item, score, source
        return None

    item, score = search_pool_for_target(target, kstartup_pool, min_score=min_score)
    hit = consider(item, score, "kstartup")
    if hit:
        return hit

    if use_bizinfo and bizinfo_pool:
        item, score = search_pool_for_target(target, bizinfo_pool, min_score=min_score)
        hit = consider(item, score, "bizinfo")
        if hit:
            return hit

    if use_extra_sources and extra_pool:
        item, score = search_pool_for_target(target, extra_pool, min_score=min_score)
        hit = consider(item, score, "extra")
        if hit:
            return hit

    if monitor_pool:
        item, score = search_pool_for_target(target, monitor_pool, min_score=min_score)
        hit = consider(item, score, "monitor")
        if hit:
            return hit

    item, score = search_kstartup_for_target(target, client, min_score=min_score)
    hit = consider(item, score, "kstartup_search")
    if hit:
        return hit

    return None, best_score, ""


def match_notice(target: str, items: Iterable[dict]) -> tuple[dict | None, float]:
    nt = norm_text(target)
    target_tokens = _token_set(target)
    best: tuple[dict | None, float] = (None, 0.0)
    for item in items:
        title = str(item.get("title", ""))
        ni = norm_text(title)
        if not nt or not ni:
            continue
        if nt == ni:
            return item, 1.0
        if nt in ni or ni in nt:
            score = min(len(nt), len(ni)) / max(len(nt), len(ni))
            score = max(score, 0.92)
        else:
            score = SequenceMatcher(None, nt, ni).ratio()
        item_tokens = _token_set(title)
        if target_tokens and item_tokens:
            overlap = len(target_tokens & item_tokens) / len(target_tokens)
            if overlap >= 0.55:
                score = max(score, 0.72 + overlap * 0.25)
        score = _apply_anchor_boost(target, title, score)
        if score > best[1]:
            best = (item, score)
    if best[0] and accept_match(target, str(best[0].get("title", "")), best[1]):
        return best
    return None, best[1]


def extract_quoted_strings(value: str) -> list[str]:
    if not value:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", value)


def _looks_like_real_download_url(raw_url: str) -> bool:
    raw_url = (raw_url or "").strip()
    if not raw_url or raw_url == "#" or len(raw_url) > 500:
        return False
    if re.search(r"orgFileNm=$|orgFileNm=\s*['\"]?\s*['\"]?(?:$|[&#])", raw_url, re.IGNORECASE):
        return False
    if SCRIPT_NOISE_RE.search(raw_url):
        return False
    low = raw_url.lower()
    if low.startswith(("javascript:", "mailto:", "tel:", "data:")):
        return False
    if raw_url.startswith(("http://", "https://", "/", "./", "../")):
        return bool(ATTACHMENT_URL_RE.search(raw_url) or EXT_RE.search(raw_url))
    if EXT_RE.search(raw_url):
        return True
    # Reject bare JS tokens such as downloadBtn, fileName, fileIdx.
    if "/" not in raw_url and "=" not in raw_url:
        return False
    return bool(ATTACHMENT_URL_RE.search(raw_url))


def candidate_from_url(raw_url: str, label: str, base_url: str, source: str) -> AttachmentCandidate | None:
    raw_url = (raw_url or "").strip()
    raw_url = unquote(raw_url)
    if not _looks_like_real_download_url(raw_url):
        return None
    abs_url = urljoin(base_url, raw_url)
    haystack = f"{label} {raw_url}"
    if not (ATTACHMENT_URL_RE.search(haystack) or EXT_RE.search(haystack)):
        return None
    return AttachmentCandidate(url=abs_url, label=label.strip() or "첨부파일", source=source)


def egov_context_fallback_url(file_url: str, detail_url: str) -> str:
    """루트 `/cmm/fms/FileDown.do` 합성 URL 의 컨텍스트 패스 폴백 변형을 만든다.

    eGovFrame 이 컨텍스트 패스 하위에 배포된 사이트(예: /portal/cmm/fms/FileDown.do)
    에서는 루트 합성이 404 라 — 상세 URL 의 첫 디렉터리 세그먼트(/portal 등)를
    접두로 붙인 변형을 반환한다. 폴백이 불가능하면 ""(TASK-010).
    """
    parsed = urlparse(file_url)
    if not parsed.path.startswith(EGOV_FILEDOWN_PATH):
        return ""
    # 마지막 세그먼트(view.do 등 리소스)는 제외하고 디렉터리만 본다
    segs = [s for s in urlparse(detail_url).path.split("/") if s][:-1]
    if not segs or segs[0].lower() == "cmm":
        return ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}/{segs[0]}{parsed.path}{query}"


def _in_site_chrome(el, body_text_len: int | None = None) -> bool:
    """링크가 사이트 공통 영역(footer·네비게이션 등) 안에 있는지 판별.

    캠코 회귀: footer 의 KSQI·웹접근성 인증 PDF 직링크가 공고 첨부로 오탐됐다.
    게시물 본문/첨부 영역 밖(사이트 chrome)의 문서 링크는 첨부 후보에서 제외한다.

    가드(TASK-009): 미닫힘 <nav>/<footer> 같은 malformed HTML 에서는 파서가 본문
    전체를 chrome 자손으로 삼킨다 — 매치된 조상이 body 텍스트의 절반 이상을
    담고 있으면 chrome 이 아니라 '본문을 삼킨 컨테이너'로 보고 계속 위로 탐색한다.
    (정상 footer/gnb 는 페이지의 소분율이라 무영향)
    """
    if body_text_len is None:
        body = el.find_parent("body")
        body_text_len = len(body.get_text()) if body is not None else 0
    for parent in el.parents:
        name = getattr(parent, "name", None)
        if not name:
            continue
        matched = name in CHROME_TAGS
        if not matched:
            tokens = list(parent.get("class") or [])
            pid = parent.get("id")
            if pid:
                tokens.append(pid)
            matched = any(CHROME_TOKEN_RE.match(t) for t in tokens)
        if matched:
            if body_text_len and len(parent.get_text()) >= 0.5 * body_text_len:
                continue
            return True
    return False


def _nearby_label(el) -> str:
    label = " ".join(el.get_text(" ", strip=True).split())
    if label:
        return label
    parent = el.find_parent(["li", "tr", "div"])
    if parent:
        return " ".join(parent.get_text(" ", strip=True).split())[:180]
    return "첨부파일"


def extract_attachment_candidates(html: str, detail_url: str) -> list[AttachmentCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[AttachmentCandidate] = []

    def add(c: AttachmentCandidate | None) -> None:
        if not c:
            return
        key = c.url
        if key in seen:
            return
        seen.add(key)
        out.append(c)

    # 1) Direct anchors/buttons with actual URL attributes.
    chrome_skipped = 0
    body_el = soup.body if soup.body is not None else soup
    body_text_len = len(body_el.get_text())
    for el in soup.select("a, button"):
        if _in_site_chrome(el, body_text_len):
            blob = " ".join(
                str(el.get(a, "")) for a in
                ("href", "data-url", "data-href", "data-download-url", "formaction", "onclick"))
            if ATTACHMENT_URL_RE.search(blob) or EXT_RE.search(blob) or EGOV_DOWNFILE_RE.search(blob):
                chrome_skipped += 1
            continue
        label = _nearby_label(el)
        for attr in ("href", "data-url", "data-href", "data-download-url", "formaction"):
            add(candidate_from_url(str(el.get(attr, "")), label, detail_url, attr))
        onclick = str(el.get("onclick", ""))
        m = EGOV_DOWNFILE_RE.search(onclick)
        if m:
            # eGovFrame 표준: onclick 인자 → /cmm/fms/FileDown.do URL 합성
            # (엔드포인트가 다른 사이트면 4xx → 다운로드 단계에서 NOT_A_FILE 로 조용히 제외)
            synthesized = urljoin(
                detail_url,
                f"{EGOV_FILEDOWN_PATH}?atchFileId={quote(m.group(1))}&fileSn={quote(m.group(2))}",
            )
            add(AttachmentCandidate(url=synthesized, label=label.strip() or "첨부파일",
                                    source="egov-downfile"))
        elif ATTACHMENT_URL_RE.search(onclick):
            # egov 매치 시 인자('FILE_x'·파일명)는 URL 이 아니므로 generic 추출을 건너뛴다
            for q in extract_quoted_strings(onclick):
                add(candidate_from_url(q, label, detail_url, "onclick"))

    # 2) K-Startup often renders ax5 uploader data with downloadPath.
    for m in re.finditer(r"downloadPath\s*[:=]\s*['\"]([^'\"]+)['\"]", html, re.IGNORECASE):
        add(candidate_from_url(m.group(1), "첨부파일", detail_url, "downloadPath"))

    # 3) Conservative fallback: only real-looking quoted download URLs, not all JS strings.
    for m in re.finditer(r"['\"]([^'\"]*(?:/afile/fileDownload/|fileDownload|FileDown|cmm/fms)[^'\"]*)['\"]", html, re.IGNORECASE):
        add(candidate_from_url(m.group(1), "첨부파일", detail_url, "quoted-download-url"))

    # 관측성: 최종 0건인데 chrome 필터가 첨부 모양 링크를 제외했다면 경고
    # (미닫힘 footer/nav 등 malformed HTML 이 본문을 삼킨 경우 NO_ATTACHMENTS 와 구분용)
    if not out and chrome_skipped:
        log.warning("첨부 후보 %d건이 사이트 공통영역(chrome) 필터로 제외됨: %s",
                    chrome_skipped, detail_url)

    return out


def _normalize_outbound_url(raw_url: str, base_url: str) -> str:
    raw_url = unquote((raw_url or "").strip())
    if not raw_url or raw_url.startswith("#"):
        return ""
    if not raw_url.startswith(("http://", "https://")):
        if re.match(r"[\w.-]+\.[A-Za-z]{2,}", raw_url):
            raw_url = "https://" + raw_url.lstrip("/")
        else:
            raw_url = urljoin(base_url, raw_url)
    return raw_url


def extract_outbound_urls(html: str, detail_url: str) -> list[str]:
    """Extract original-site / apply-guide URLs from a K-Startup detail page."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        abs_url = _normalize_outbound_url(raw, detail_url)
        if not abs_url or abs_url in seen:
            return
        if OUTBOUND_SKIP_RE.search(abs_url):
            return
        if "k-startup.go.kr" in abs_url.lower():
            return
        seen.add(abs_url)
        urls.append(abs_url)

    for m in re.finditer(r"fn_open_window\(\s*['\"]([^'\"]+)['\"]", html, re.IGNORECASE):
        add(m.group(1))

    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("a, button"):
        label = _nearby_label(el)
        if not OUTBOUND_LABEL_RE.search(label):
            continue
        if re.search(r"뉴스레터", label) and not re.search(r"사업|접수|원본|공고", label):
            continue
        href = str(el.get("href", ""))
        onclick = str(el.get("onclick", ""))
        if href and not href.lower().startswith("javascript"):
            add(href)
        for q in extract_quoted_strings(onclick):
            if "." in q or q.startswith("http"):
                add(q)
    return urls


def gather_attachment_candidates(detail_url: str, html: str | None = None) -> list[AttachmentCandidate]:
    """Collect attachments from the detail page and linked original-site pages."""
    if html is None:
        html = fetch_detail_html(detail_url)
    seen: set[str] = set()
    out: list[AttachmentCandidate] = []

    def merge(cands: list[AttachmentCandidate]) -> None:
        for cand in cands:
            if cand.url in seen:
                continue
            seen.add(cand.url)
            out.append(cand)

    merge(extract_attachment_candidates(html, detail_url))
    if "k-startup.go.kr" in detail_url.lower():
        for outbound in extract_outbound_urls(html, detail_url)[:5]:
            try:
                outbound_html = fetch_detail_html(outbound)
                merge(extract_attachment_candidates(outbound_html, outbound))
            except Exception as exc:
                log.warning("outbound page fetch failed (%s): %s", outbound, exc)
    return out


def content_disposition_filename(value: str) -> str:
    if not value:
        return ""
    msg = Message()
    msg["content-disposition"] = value
    filename = msg.get_filename()
    if filename:
        return unquote(filename)
    m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", value, re.IGNORECASE)
    return unquote(m.group(1).strip()) if m else ""


def guess_filename(candidate: AttachmentCandidate, response: httpx.Response | None = None, idx: int = 1) -> str:
    if response is not None:
        cd = response.headers.get("content-disposition", "")
        from_cd = content_disposition_filename(cd)
        if from_cd:
            return safe_filename(from_cd, 180)
    parsed = urlparse(candidate.url)
    base = safe_filename(unquote(Path(parsed.path).name), 180)
    if base and "." in base:
        return base
    label = safe_filename(candidate.label or f"attachment_{idx}", 120)
    ext = ""
    if response is not None:
        ext = mimetypes.guess_extension(response.headers.get("content-type", "").split(";")[0].strip()) or ""
    if not ext:
        m = EXT_RE.search(candidate.url)
        ext = f".{m.group(1).lower()}" if m else ".bin"
    return f"{idx:02d}_{label}{ext}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot create unique path for {path}")


def get_with_ssl_fallback(url: str, headers: dict, timeout: int) -> httpx.Response:
    """SSL 3단 폴백 GET: strict → no_verify → legacy(구식 TLS 컨텍스트).

    일부 정부기관 사이트는 인증서 체인 불량(no_verify 로 해소)이나 구식 TLS
    스택(renegotiation·약한 cipher — monitor._legacy_ssl_ctx 로 해소)으로
    핸드셰이크 자체가 실패한다. 폴백은 연결/SSL 예외일 때만 다음 단계로
    넘어가고, HTTP 상태 오류(4xx/5xx)는 SSL 문제가 아니므로 즉시 올린다
    (기존 요청 경로의 동작 보존 — 응답이 오는 사이트는 결과 동일).
    """
    last_err: Exception | None = None
    for stage in ("strict", "no_verify", "legacy"):
        verify = (
            True if stage == "strict"
            else False if stage == "no_verify"
            else monitor._legacy_ssl_ctx()
        )
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers,
                              verify=verify) as client:
                r = client.get(url)
                r.raise_for_status()
                return r
        except httpx.HTTPStatusError:
            raise  # 서버가 응답한 오류 — SSL 폴백 대상 아님
        except Exception as exc:  # SSL/연결 계열 → 다음 단계로 폴백
            last_err = exc
            continue
    if last_err:
        raise last_err
    raise RuntimeError(f"Failed to fetch {url}")


def fetch_detail_html(url: str) -> str:
    headers = {**monitor.HTTP_HEADERS, "Referer": KSTARTUP_SITE["url"]}
    return get_with_ssl_fallback(url, headers, timeout=60).text


def download_candidate(candidate: AttachmentCandidate, detail_url: str, notice_dir: Path, idx: int) -> tuple[str, Path]:
    headers = {**monitor.HTTP_HEADERS, "Referer": detail_url}
    r = get_with_ssl_fallback(candidate.url, headers, timeout=120)
    # Do not save HTML error pages as attachments.
    ctype = r.headers.get("content-type", "").lower()
    if "text/html" in ctype and not EXT_RE.search(candidate.url):
        raise RuntimeError(f"download returned HTML, not a file: {candidate.url}")
    file_name = guess_filename(candidate, r, idx)
    save_path = unique_path(notice_dir / file_name)
    save_path.write_bytes(r.content)
    return file_name, save_path


def run(
    target_file: Path,
    out_dir: Path,
    dry_run: bool,
    min_score: float,
    max_pages: int,
    *,
    use_bizinfo: bool = True,
    use_extra_sources: bool = True,
    use_full_monitor: bool = True,
) -> dict:
    targets = load_targets(target_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadResult] = []
    headers = {**monitor.HTTP_HEADERS, "Referer": KSTARTUP_SITE["url"]}
    bizinfo_pool: list[dict] | None = None
    extra_pool: list[dict] | None = None
    monitor_pool: list[dict] | None = None
    if use_bizinfo:
        try:
            bizinfo_pool = collect_bizinfo_items()
        except Exception as exc:
            log.warning("bizinfo pool load failed: %s", exc)
    if use_extra_sources:
        try:
            extra_pool = collect_extra_source_items()
        except Exception as exc:
            log.warning("extra source pool load failed: %s", exc)
    if use_full_monitor:
        try:
            monitor_pool = collect_full_monitor_items()
        except Exception as exc:
            log.warning("full monitor pool load failed: %s", exc)

    with httpx.Client(timeout=60, headers=headers, follow_redirects=True, verify=False) as client:
        items = collect_kstartup_items(max_pages=max_pages, client=client)

        for target in targets:
            item, score, match_source = find_notice_for_target(
                target,
                items,
                client,
                bizinfo_pool=bizinfo_pool,
                extra_pool=extra_pool,
                monitor_pool=monitor_pool,
                min_score=min_score,
                use_bizinfo=use_bizinfo,
                use_extra_sources=use_extra_sources,
            )
            if not item or not accept_match(target, str(item.get("title", "")), score, min_score):
                results.append(DownloadResult(
                    target_title=target,
                    matched_title=str(item.get("title", "")) if item else "",
                    match_score=round(score, 4),
                    detail_url=str(item.get("link", "")) if item else "",
                    status="NOT_FOUND",
                    match_source=match_source,
                ))
                continue

            matched_title = str(item.get("title", ""))
            detail_url = str(item.get("link", ""))
            notice_dir = out_dir / safe_filename(matched_title, 120)

            try:
                candidates = gather_attachment_candidates(detail_url)
            except Exception as exc:
                results.append(DownloadResult(
                    target, matched_title, round(score, 4), detail_url,
                    "DETAIL_FETCH_FAILED", error=str(exc), match_source=match_source,
                ))
                continue

            if not candidates:
                results.append(DownloadResult(
                    target, matched_title, round(score, 4), detail_url,
                    "NO_ATTACHMENTS", match_source=match_source,
                ))
                continue

            notice_dir.mkdir(parents=True, exist_ok=True)
            for idx, cand in enumerate(candidates, start=1):
                if dry_run:
                    predicted = notice_dir / guess_filename(cand, None, idx)
                    results.append(DownloadResult(
                        target_title=target,
                        matched_title=matched_title,
                        match_score=round(score, 4),
                        detail_url=detail_url,
                        status="DRY_RUN",
                        file_name=predicted.name,
                        save_path=str(predicted),
                        file_url=cand.url,
                        match_source=match_source,
                    ))
                    continue
                try:
                    file_name, save_path = download_candidate(cand, detail_url, notice_dir, idx)
                    results.append(DownloadResult(
                        target_title=target,
                        matched_title=matched_title,
                        match_score=round(score, 4),
                        detail_url=detail_url,
                        status="DOWNLOADED",
                        file_name=file_name,
                        save_path=str(save_path),
                        file_url=cand.url,
                        match_source=match_source,
                    ))
                except Exception as exc:
                    results.append(DownloadResult(
                        target_title=target,
                        matched_title=matched_title,
                        match_score=round(score, 4),
                        detail_url=detail_url,
                        status="DOWNLOAD_FAILED",
                        file_url=cand.url,
                        error=str(exc),
                        match_source=match_source,
                    ))

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_file": str(target_file),
        "out_dir": str(out_dir),
        "dry_run": dry_run,
        "max_pages": max_pages,
        "collected_items": len(items),
        "extra_source_items": len(extra_pool or []),
        "monitor_items": len(monitor_pool or []),
        "bizinfo_items": len(bizinfo_pool or []),
        "total_targets": len(targets),
        "total_rows": len(results),
        "status_counts": {},
        "results": [asdict(r) for r in results],
    }
    for r in results:
        summary["status_counts"][r.status] = summary["status_counts"].get(r.status, 0) + 1

    manifest = out_dir / ("download_manifest_dry_run.json" if dry_run else "download_manifest.json")
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Download attachments for selected K-Startup notices.")
    parser.add_argument("--target-file", default="config/targets/kstartup_20260623.txt")
    parser.add_argument("--out-dir", default="downloads/kstartup/20260623")
    parser.add_argument("--dry-run", action="store_true", help="Do not write attachment files; write planned manifest only.")
    parser.add_argument("--min-score", type=float, default=0.72)
    parser.add_argument("--max-pages", type=int, default=30, help="K-Startup pages to scan for each class(PBC010/PBC020).")
    parser.add_argument("--no-bizinfo", action="store_true", help="Do not fall back to bizinfo title search.")
    parser.add_argument("--no-extra-sources", action="store_true", help="Do not fetch SBA/MSS/KOSME etc. host-site pools.")
    parser.add_argument("--no-full-monitor", action="store_true", help="Skip fetching all enabled monitor sites (faster, more NOT_FOUND).")
    args = parser.parse_args()

    summary = run(
        target_file=(ROOT / args.target_file).resolve() if not Path(args.target_file).is_absolute() else Path(args.target_file),
        out_dir=(ROOT / args.out_dir).resolve() if not Path(args.out_dir).is_absolute() else Path(args.out_dir),
        dry_run=args.dry_run,
        min_score=args.min_score,
        max_pages=args.max_pages,
        use_bizinfo=not args.no_bizinfo,
        use_extra_sources=not args.no_extra_sources,
        use_full_monitor=not args.no_full_monitor,
    )
    print(json.dumps({
        "dry_run": summary["dry_run"],
        "max_pages": summary["max_pages"],
        "collected_items": summary["collected_items"],
        "total_targets": summary["total_targets"],
        "total_rows": summary["total_rows"],
        "status_counts": summary["status_counts"],
        "manifest": str(Path(summary["out_dir"]) / ("download_manifest_dry_run.json" if summary["dry_run"] else "download_manifest.json")),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

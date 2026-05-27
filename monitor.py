"""수출·지원사업 모니터링 에이전트 v6
기능: 수집 → 중복제거(주관기관 우선) → 날짜필터(D-1) → 그룹별 조건필터 → Claude요약 → 발송
설정: sites.json / groups.json / settings.json / seen_ids.json
"""
from __future__ import annotations

import hashlib, html, json, logging, os, re, smtplib, unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, quote

import httpx
from anthropic import Anthropic
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent

# ── Playwright fetcher 모듈 동적 임포트 ──────────────────────────────────────
try:
    from fetchers.playwright_fetcher import (
        fetch_keit   as _pw_fetch_keit,
        fetch_kiat   as _pw_fetch_kiat,
        fetch_thevc  as _pw_fetch_thevc,
        fetch_connectworks as _pw_fetch_connectworks,
        fetch_semas  as _pw_fetch_semas,
        fetch_pw_table as _pw_fetch_table,
    )
    _PW_OK = True
except ImportError:
    _PW_OK = False
    def _pw_noop(site):
        log.warning("playwright 미설치 — %s 건너뜀", site.get("name"))
        return []
    _pw_fetch_keit = _pw_fetch_kiat = _pw_fetch_thevc = _pw_noop
    _pw_fetch_connectworks = _pw_fetch_semas = _pw_fetch_table = _pw_noop

# ── 환경변수 ─────────────────────────────────────────────────────────────────
def _require_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"필수 환경변수 누락: {key}\n"
            f"  → .env 파일에 {key}=<값> 을 추가하세요."
        )
    return val

BIZINFO_API_KEY    = _require_env("BIZINFO_API_KEY")
ANTHROPIC_API_KEY  = _require_env("ANTHROPIC_API_KEY")
GMAIL_ADDRESS      = _require_env("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = _require_env("GMAIL_APP_PASSWORD")

# ── 경로 ─────────────────────────────────────────────────────────────────────
SITES_PATH    = BASE_DIR / "sites.json"
GROUPS_PATH   = BASE_DIR / "groups.json"
SETTINGS_PATH = BASE_DIR / "settings.json"
SEEN_IDS_PATH = BASE_DIR / "seen_ids.json"

# ── 상수 ─────────────────────────────────────────────────────────────────────
KST            = timezone(timedelta(hours=9))
MAX_SEEN_IDS   = 1000
MAX_FOR_CLAUDE = 15
SEMAS_LOAN_SOURCE = "소진공 정책자금 온라인신청"
SEMAS_LOAN_TITLE = "소상공인 정책자금 공고"
HTTP_HEADERS   = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

# 지원유형 분류 규칙
SUPPORT_TYPE_RULES: dict[str, list[str]] = {
    "투자":           ["투자", "엔젤", "벤처캐피탈", "시드투자", "지분투자", "VC"],
    "지원금/바우처":   ["지원금", "바우처", "보조금", "참가비", "지원비", "수출바우처",
                       "R&D", "사업화자금", "자금지원", "매칭지원", "보조"],
    "컨설팅·교육·상담": ["컨설팅", "교육", "상담", "멘토링", "코칭", "역량강화",
                         "인력양성", "훈련", "세미나", "워크숍", "설명회"],
}
ALL_SUPPORT_TYPES = list(SUPPORT_TYPE_RULES.keys()) + ["그외"]

# 지역 키워드 (전국 판별용)
KNOWN_REGIONS = {
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "충청", "전라", "경상", "수도권", "호남", "영남",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════════

def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:20]

def norm(value: Any) -> str:
    return " ".join(str(value).split()).strip() if value else ""

def html_pre(value: str) -> str:
    return html.escape(value).replace("\n", "<br>")

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception as e:
        log.warning("%s 로드 실패: %s", path, e)
        return default

def save_json(path: Path, data) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        log.error("파일 저장 실패 %s: %s", path, e)
        tmp.unlink(missing_ok=True)
        raise

def normalize_title(title: str) -> str:
    """중복 판별용 제목 정규화: 소문자 + 특수문자/공백 제거"""
    t = unicodedata.normalize("NFKC", title.lower())
    return re.sub(r"[\s\W]+", "", t)

def is_imminent(deadline: str) -> bool:
    cleaned = deadline.replace(".", "-").replace("/", "-").replace("~", " ").replace("까지", " ")
    today = datetime.now(KST).date()
    for tok in cleaned.split():
        if len(tok) >= 10 and tok[4:5] == "-" and tok[7:8] == "-":
            try:
                if 0 <= (datetime.strptime(tok[:10], "%Y-%m-%d").date() - today).days <= 7:
                    return True
            except ValueError:
                pass
    return False

def extract_date_from_text(text: str) -> str:
    """텍스트에서 날짜 추출 (YYYY-MM-DD). 다양한 포맷 지원."""
    if not text:
        return ""
    # 1. 표준 ISO: 2026-05-15 또는 2026.05.15 또는 2026/05/15
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 2. 한국어: 2026년 05월 15일 또는 2026년 5월 15일
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 3. 간격 있는 ISO: 2026 - 05 - 15
    m = re.search(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def previous_business_day(from_dt: datetime | None = None, days_back: int = 1):
    """주말을 건너뛴 직전 영업일 계산."""
    day = (from_dt or datetime.now(KST)).date()
    remaining = max(1, days_back)
    while remaining:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def select_text(root: Any, selector: str) -> str:
    """CSS selector로 찾은 첫 요소의 텍스트를 반환."""
    if not selector:
        return ""
    node = root.select_one(selector)
    return norm(node.get_text(" ", strip=True)) if node else ""


def select_date(root: Any, selector: str) -> str:
    """CSS selector로 찾은 영역에서 등록일/마감일 날짜를 YYYY-MM-DD로 반환."""
    return extract_date_from_text(select_text(root, selector))

def load_seen_ids() -> set[str]:
    raw = load_json(SEEN_IDS_PATH, [])
    return {str(x) for x in raw if x} if isinstance(raw, list) else set()

def save_seen_ids(ids: set[str]) -> None:
    # 날짜 포함 ID(bizinfo_20260415 등)는 날짜순, 나머지는 알파벳순 → 최신 MAX_SEEN_IDS 유지
    def _sort_key(s: str) -> str:
        m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{8})", s)
        return m.group(1) if m else s
    save_json(SEEN_IDS_PATH, sorted(ids, key=_sort_key)[-MAX_SEEN_IDS:])

def load_sites() -> list[dict]:
    sites = load_json(SITES_PATH, [])
    active = [s for s in sites if s.get("enabled", True)]
    log.info("사이트: %d개 활성", len(active))
    return active

def load_groups() -> list[dict]:
    groups = load_json(GROUPS_PATH, [])
    active = [g for g in groups if g.get("active", True)]
    log.info("그룹: %d개 활성", len(active))
    return active

def load_settings() -> dict:
    default = {
        "date_filter_enabled": True,
        "days_back": 1,
        "raw_all_enabled": True,
        "raw_all_recipients": [],
        "claude_model": "claude-sonnet-4-6",
        "claude_max_tokens": 4000,
        "fetch_max_workers": 10,
    }
    return {**default, **load_json(SETTINGS_PATH, {})}


# ══════════════════════════════════════════════════════════════════
# 크롤러
# ══════════════════════════════════════════════════════════════════

def _soup(url: str, extra_headers: dict | None = None, **kwargs):
    try:
        hdrs = {**HTTP_HEADERS, **(extra_headers or {})}
        with httpx.Client(timeout=30, headers=hdrs, follow_redirects=True) as c:
            r = c.get(url, **kwargs); r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.error("접속 실패 %s: %s", url, e); return None

def _item(id_, title, link, author, desc, deadline, source,
          posted_date="", is_aggregator=False) -> dict:
    return {"id": id_, "title": title, "link": link, "author": author,
            "description": desc, "deadline": deadline, "source": source,
            "posted_date": posted_date, "is_aggregator": is_aggregator}


def fetch_bizinfo(site: dict) -> list[dict]:
    try:
        with httpx.Client(timeout=30, headers=HTTP_HEADERS) as c:
            r = c.get(site["url"], params={
                "crtfcKey": BIZINFO_API_KEY, "dataType": "json",
                "searchLclasId": "04", "searchCnt": "100"})
            r.raise_for_status(); data = r.json()
    except Exception as e:
        log.error("기업마당 API 실패: %s", e); return []
    raw = data.get("jsonArray", data.get("channel", {}).get("item", []))
    if isinstance(raw, dict): raw = [raw]
    items = []
    agg = site.get("is_aggregator", True)
    for it in raw:
        iid = norm(it.get("pblancId", it.get("seq", "")))
        ttl = norm(it.get("pblancNm", it.get("title", "")))
        lnk = norm(it.get("pblancUrl", it.get("link", "")))
        if not iid: iid = f"bizinfo_{stable_id(ttl + lnk)}"
        # 등록일 추출 시도 (다양한 키 이름 지원)
        posted = norm(it.get("regDt", it.get("pblancDt", it.get("creatPnttm", it.get("updtPnttm", "")))))
        if posted and len(posted) >= 10:
            posted = posted[:10]  # YYYY-MM-DD HH:MM:SS → YYYY-MM-DD
        if not posted:
            posted = extract_date_from_text(norm(it.get("bsnsSumryCn", "")))
        items.append(_item(iid, ttl, lnk,
            norm(it.get("jrsdInsttNm", it.get("author", ""))),
            norm(it.get("bsnsSumryCn", it.get("description", ""))),
            norm(it.get("reqstBeginEndDe", it.get("reqstDt", ""))),
            site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_myfair_legacy(site: dict) -> list[dict]:
    # 하위호환용 - fetch_myfair로 대체됨
    return fetch_myfair(site)


def fetch_kstartup(site: dict) -> list[dict]:
    soup = _soup(site["url"], params={
        "schMenuId": "10090", "pageIndex": "1", "viewCount": "100", "pbancSttus": "ing"})
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for card in soup.select(".notice"):
        a = card.select_one("a")
        title = norm(a.get_text() if a else "")
        if not title: continue
        sn = ""
        for btn in card.select("button[onclick]"):
            m = re.search(r"\d+", btn.get("onclick", ""))
            if m: sn = m.group(0); break
        if not sn and a:
            m = re.search(r"\d+", a.get("href", ""))
            if m: sn = m.group(0)
        link = (f"https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
                f"?pbancClssCd=PBC010&schM=view&pbancSn={sn}") if sn else site["url"]
        spans = card.select("span.list")
        org = norm(spans[0].get_text()) if spans else ""
        dl = next((norm(sp.get_text().replace("마감일자", ""))
                   for sp in spans if "마감일자" in sp.get_text()), "")
        # 등록일: D-n 뱃지에서 역산 (D-0~D-7 이면 최근)
        posted = ""
        day_flag = card.select_one(".flag.day")
        if day_flag:
            dm = re.search(r"D-?(\d+)", day_flag.get_text())
            if dm:
                days_left = int(dm.group(1))
                # 마감일에서 역산은 부정확 → 빈 문자열 유지
        flag = card.select_one(".flag:not(.day):not(.flag_agency)")
        iid = f"kstartup_{sn}" if sn else f"kstartup_{stable_id(title+org)}"
        items.append(_item(iid, title, link, org,
                           norm(flag.get_text()) if flag else "", dl,
                           site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_html_generic(site: dict) -> list[dict]:
    selectors = site.get("selectors", {})
    sel    = selectors.get("row", "table tbody tr")
    date_selector = site.get("date_selector") or selectors.get("date", "")
    deadline_selector = site.get("deadline_selector") or selectors.get("deadline", "")
    soup   = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for row in soup.select(sel):
        title_selector = selectors.get("title", "")
        link_selector = selectors.get("link", "a")
        a = row.select_one(link_selector) if link_selector else row.select_one("a")
        title = norm(a.get_text() if a else row.get_text())
        if title_selector:
            title = select_text(row, title_selector) or title
        if not title: continue
        href = a.get("href", "") if a else ""
        link = urljoin(site["url"], href) if href else site["url"]
        if not href or link.split("#")[0] == site["url"].split("#")[0] or href.startswith("javascript:"):
            continue
        row_text = row.get_text()
        dates    = re.findall(r"\d{4}[.\-/]\d{2}[.\-/]\d{2}", row_text)
        # 첫 날짜 = 등록일, 마지막 날짜 = 마감일 (두 개 이상)
        posted   = dates[0].replace(".", "-").replace("/", "-") if dates else ""
        deadline = dates[-1].replace(".", "-").replace("/", "-") if len(dates) >= 2 else ""
        posted = select_date(row, date_selector) or posted
        deadline = select_date(row, deadline_selector) or deadline
        author = select_text(row, selectors.get("author", ""))
        desc = select_text(row, selectors.get("description", ""))
        items.append(_item(f"{site['id']}_{stable_id(title+link)}",
                           title, link, author, desc, deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_semas_loan_ols(site: dict) -> list[dict]:
    """소진공 정책자금 온라인신청 공지 목록 AJAX 수집."""
    search_url = urljoin(site["url"], "/ols/man/SMAN051M/search.do")
    headers = {
        **HTTP_HEADERS,
        "Accept": "application/json,text/html,*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": site["url"],
        "X-Requested-With": "XMLHttpRequest",
    }
    items, agg = [], site.get("is_aggregator", False)
    try:
        max_pages = max(1, int(site.get("max_pages", 3)))
    except (TypeError, ValueError):
        max_pages = 3

    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as c:
            for page_no in range(1, max_pages + 1):
                r = c.post(search_url, data={
                    "bltwtrClcd": "",
                    "bltwtrTitNm": "",
                    "searchStd": "",
                    "pageNo": str(page_no),
                })
                r.raise_for_status()
                data = r.json()
                rows = data.get("result") or []
                if not rows:
                    break
                for row in rows:
                    loan_type = norm(row.get("loanSeCdNm", ""))
                    category = norm(row.get("bltwtrClcd", ""))
                    title = norm(row.get("bltwtrTitNm", ""))
                    seq = norm(row.get("bltwtrSeq", ""))
                    bbs_type = norm(row.get("bbsTypeCd", ""))
                    if not title or not _is_semas_policy_fund_notice(title, category):
                        continue
                    posted = extract_date_from_text(norm(row.get("frstRegDt", "")))
                    desc_parts = [
                        part for part in [
                            f"대출구분: {loan_type}" if loan_type else "",
                            f"구분: {category}" if category else "",
                            f"공지번호: {seq}" if seq else "",
                        ] if part
                    ]
                    iid = f"{site['id']}_{seq}_{bbs_type}" if seq else f"{site['id']}_{stable_id(title)}"
                    items.append(_item(
                        iid, title, site["url"], "소상공인시장진흥공단",
                        " / ".join(desc_parts), "", site["name"], posted, agg,
                    ))
    except Exception as e:
        log.error("소진공 정책자금 공지 API 실패: %s", e)
        return []

    log.info("%s: %d건", site["name"], len(items))
    return items


def _is_semas_policy_fund_notice(title: str, category: str) -> bool:
    if category == "대출정보":
        return True
    return any(keyword in title for keyword in ("정책자금", "자금", "대출", "상환", "융자"))


def fetch_kita(site: dict) -> list[dict]:
    """한국무역협회(KITA) 진행중인 사업 크롤러
    URL: https://www.kita.net/asocBiz/asocBiz/asocBizOngoingList.do
    onclick: goDetailPage('202603046') → sn 파라미터로 상세 URL 구성
    """
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    BASE       = "https://www.kita.net"
    DETAIL_URL = BASE + "/asocBiz/asocBiz/asocBizOngoingView.do"

    # 실제 공고 a태그: parent가 div.subject, onclick=goDetailPage('숫자')
    for a in soup.find_all("a", onclick=re.compile(r"goDetailPage")):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue

        # onclick에서 ID 추출
        m_id = re.search(r"goDetailPage\(['\"](\d+)['\"]\)", a.get("onclick", ""))
        if not m_id: continue
        sn   = m_id.group(1)
        link = f"{DETAIL_URL}?sn={sn}"

        # 카드 전체 텍스트 (조상 li 기준)
        card = a
        for _ in range(4):   # 최대 4단계 위로
            if card.parent: card = card.parent
            if card.name == "li": break
        full_text = card.get_text()

        # 모집기간 시작일 → posted_date
        posted = ""
        m_p = re.search(r"모집기간\s*[:\s]\s*(\d{4}[.\-]\d{2}[.\-]\d{2})", full_text)
        if m_p: posted = m_p.group(1).replace(".", "-")
        else:   posted = extract_date_from_text(full_text)

        # 모집기간 마감일 → deadline
        deadline = ""
        m_d = re.search(r"모집기간.+?~\s*(\d{4}[.\-]\d{2}[.\-]\d{2})", full_text)
        if m_d: deadline = m_d.group(1).replace(".", "-")

        # 사업유형 / 지역
        parts = []
        m_type = re.search(r"사업\s*[:\s]\s*([^\n|／]+)", full_text)
        if m_type: parts.append(norm(m_type.group(1)))
        m_reg  = re.search(r"지역\s*[:\s]\s*([^\n|／]+)", full_text)
        if m_reg:  parts.append(f"지역: {norm(m_reg.group(1))}")
        desc = " / ".join(parts)

        iid = f"kita_{sn}"
        items.append(_item(iid, title, link, "한국무역협회(KITA)",
                           desc, deadline, site["name"], posted, agg))

    log.info("%s: %d건", site["name"], len(items))
    return items


# ── IRIS (범부처통합연구지원시스템) ─────────────────────────────────────────
def fetch_iris(site: dict) -> list[dict]:
    """IRIS JSON API: POST /contents/retrieveBsnsAncmBtinSituList.do"""
    api_url = "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do"
    detail_base = "https://www.iris.go.kr/contents/retrieveBsnsAncmView.do"
    hdrs = {**HTTP_HEADERS,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json,*/*",
            "Referer": site["url"]}
    try:
        with httpx.Client(timeout=30, headers=hdrs) as c:
            r = c.post(api_url, data={
                "pageIndex": "1", "recordCountPerPage": "50",
                "searchCondition": "", "searchKeyword": "", "orderBy": "latest"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.error("IRIS API 실패: %s", e); return []
    items, agg = [], site.get("is_aggregator", False)
    for it in data.get("listBsnsAncmBtinSitu", []):
        iid      = f"iris_{it.get('ancmId','')}"
        title    = norm(it.get("ancmTl", ""))
        author   = norm(it.get("sorgnNm", ""))
        deadline = norm(it.get("rcveEndDe", "")).replace(".", "-")
        posted   = norm(it.get("ancmDe", "")).replace(".", "-")
        desc     = norm(it.get("pbofrTpSeNmLst", ""))
        link     = f"{detail_base}?ancmId={it.get('ancmId','')}"
        if not title: continue
        items.append(_item(iid, title, link, author, desc, deadline,
                           site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── SMTECH (중소기업기술개발사업종합관리시스템) ──────────────────────────────
def fetch_smtech(site: dict) -> list[dict]:
    """SMTECH 공고 리스트: table tbody tr, jsessionid 제거"""
    BASE = "https://www.smtech.go.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a")
        if not a: continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href = a.get("href", "")
        # jsessionid 제거
        href = re.sub(r";jsessionid=[^?#]*", "", href)
        if href.startswith("javascript") or not href:
            # goMove() 타입 → 리스트 URL 자체를 링크로
            link = site["url"]
        else:
            link = href if href.startswith("http") else BASE + href
        # 날짜: td 텍스트에서
        tds = tr.select("td")
        td_text = " ".join(td.get_text(strip=True) for td in tds)
        posted   = extract_date_from_text(td_text)
        deadline = ""
        dates = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", td_text)
        if len(dates) >= 2: deadline = dates[-1].replace(".", "-")
        iid = f"smtech_{stable_id(title + link)}"
        items.append(_item(iid, title, link, "중소기업기술개발지원", "",
                           deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── KOCCA 공고 ───────────────────────────────────────────────────────────────
def fetch_kocca_pims(site: dict) -> list[dict]:
    """/kocca/pims/view.do?intcNo=... 패턴"""
    BASE = "https://www.kocca.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for a in soup.find_all("a", href=re.compile(r"/kocca/pims/view")):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href  = a.get("href", "")
        link  = href if href.startswith("http") else BASE + href.split("&pageInd")[0]
        iid   = f"kocca_{stable_id(title + link)}"
        # 카드 전체에서 날짜 추출
        card = a
        for _ in range(5):
            if card.parent: card = card.parent
            if card.name in ("li", "tr", "div"): break
        dates = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", card.get_text())
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        items.append(_item(iid, title, link, "한국콘텐츠진흥원", "",
                           deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── KOCCA 금융 ───────────────────────────────────────────────────────────────
def fetch_kocca_bbs(site: dict) -> list[dict]:
    """/kocca/bbs/view/... 패턴"""
    BASE = "https://www.kocca.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for a in soup.find_all("a", href=re.compile(r"/kocca/bbs/view")):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href  = a.get("href", "")
        link  = href if href.startswith("http") else BASE + href.split("&searchCnd")[0]
        iid   = f"kocca_bbs_{stable_id(title + link)}"
        card = a
        for _ in range(5):
            if card.parent: card = card.parent
            if card.name in ("li", "tr", "div"): break
        dates = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", card.get_text())
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[1].replace(".", "-") if len(dates) >= 3 else (dates[-1].replace(".", "-") if dates else "")
        items.append(_item(iid, title, link, "한국콘텐츠진흥원", "금융지원",
                           deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── 경기TP ───────────────────────────────────────────────────────────────────
def fetch_gtp(site: dict) -> list[dict]:
    """onclick: fn_goView('172225') → /web/business/webBusinessView.do?seq=N"""
    BASE   = "https://pms.gtp.or.kr"
    DETAIL = BASE + "/web/business/webBusinessView.do"
    soup   = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for a in soup.find_all("a", onclick=re.compile(r"fn_goView")):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        m = re.search(r"fn_goView\(['\"]?(\w+)", a.get("onclick", ""))
        if not m: continue
        seq  = m.group(1)
        link = f"{DETAIL}?seq={seq}"
        iid  = f"gtp_{seq}"
        card = a
        for _ in range(5):
            if card.parent: card = card.parent
            if card.name in ("li", "tr", "div"): break
        dates = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}|\d{4}\.\d{2}\.\d{2}", card.get_text())
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        desc_m   = re.search(r"(지원|모집|공고)[^\n]{0,30}", card.get_text())
        desc     = norm(desc_m.group(0)) if desc_m else ""
        items.append(_item(iid, title, link, "경기테크노파크", desc,
                           deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── 경기스타트업 ─────────────────────────────────────────────────────────────
def fetch_gsp(site: dict) -> list[dict]:
    """onclick: go_detail('6189') → /supportProject/UVSL0001View.do?seq=N"""
    DETAIL = "https://www.gsp.or.kr/supportProject/UVSL0001View.do"
    soup   = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for a in soup.find_all("a", onclick=re.compile(r"go_detail")):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        m = re.search(r"go_detail\(['\"]?(\d+)", a.get("onclick", ""))
        if not m: continue
        seq  = m.group(1)
        link = f"{DETAIL}?seq={seq}"
        iid  = f"gsp_{seq}"
        card = a
        for _ in range(5):
            if card.parent: card = card.parent
            if card.name in ("li", "tr", "div"): break
        full  = card.get_text(" ", strip=True)
        dates = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}|\d{4}\.\d{1,2}\.\d{1,2}", full)
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        # 상태 제거 후 깔끔한 제목
        title = re.sub(r"^(모집중|접수중|마감)\s*\S+\s*", "", title).strip()
        items.append(_item(iid, title, link, "경기스타트업플랫폼", "",
                           deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── 창조경제혁신센터 (공고/행사 공통) ────────────────────────────────────────
def fetch_ccei(site: dict) -> list[dict]:
    """CCEI 공고/행사: a[href*='/service/'] 패턴, onclick 백업"""
    BASE = "https://ccei.creativekorea.or.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    # table tr 또는 li에서 공고 링크 추출
    for row in soup.select("table tbody tr, ul li, .list-wrap li, .board-list li"):
        a = row.select_one("a[href]")
        if not a: continue
        href  = a.get("href", "")
        if not href or href in ("#", "javascript:void(0)"): continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        # 비공고 링크 제외 (마이페이지, 로그인, 메뉴 등)
        SKIP_TITLES = {"마이페이지", "로그인", "회원가입", "지원서비스 신청", "지원서비스 신청+"}
        if title in SKIP_TITLES: continue
        SKIP_HREFS = {"/counsel/", "/login", "/join", "/mypage", "/member"}
        if any(s in href for s in SKIP_HREFS): continue
        # 실제 공고 URL 패턴만 허용 (/service/business, /service/event 등)
        if not any(p in href for p in ["/service/biz", "/service/bus", "/service/event",
                                        "/service/notice", "view", "detail", "seq=", "idx="]): continue
        link  = href if href.startswith("http") else BASE + href
        if link in seen: continue
        seen.add(link)
        full     = row.get_text(" ", strip=True)
        dates    = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}|\d{4}\.\d{1,2}\.\d{1,2}", full)
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        iid      = f"ccei_{stable_id(title + link)}"
        items.append(_item(iid, title, link, "창조경제혁신센터", "",
                           deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── ITP (인천테크노파크) ─────────────────────────────────────────────────────
def fetch_itp(site: dict) -> list[dict]:
    """ITP 게시판: a[href='javascript:fncShow(seq)'] → 상세 URL 구성
    tmid 파라미터로 게시판 구분 (15=공지, 36=마케팅센터 등)
    """
    BASE   = "https://www.itp.or.kr"
    DETAIL = BASE + "/intro.asp"
    soup   = _soup(site["url"], extra_headers={"Referer": BASE + "/"})
    if not soup: return []

    # tmid 추출
    tmid_m = re.search(r"tmid=(\d+)", site["url"])
    tmid   = tmid_m.group(1) if tmid_m else "15"

    items, agg = [], site.get("is_aggregator", False)
    # ITP는 <tbody> 없이 <table><tr> 직접 구조
    for tr in soup.find_all("tr"):
        a = tr.select_one("a[href]")
        if not a: continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href = a.get("href", "")
        m    = re.search(r"fncShow\(['\"]?(\d+)", href)
        if not m: continue
        seq  = m.group(1)
        link = f"{DETAIL}?tmid={tmid}&mode=view&seq={seq}"
        iid  = f"itp_{tmid}_{seq}"
        tds  = tr.select("td")
        td_text = " ".join(td.get_text(strip=True) for td in tds)
        dates   = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", td_text)
        posted  = dates[0].replace(".", "-") if dates else ""
        items.append(_item(iid, title, link, "인천테크노파크(ITP)",
                           "", "", site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_nipa(site: dict) -> list[dict]:
    """a[href*='nttDetail'] 패턴, relative → absolute 변환"""
    BASE = "https://www.nipa.kr/home/bsnsAll/0/"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"nttDetail")):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href = a.get("href", "")
        link = href if href.startswith("http") else BASE + href.lstrip("./")
        if link in seen: continue
        seen.add(link)
        iid  = f"nipa_{stable_id(title + link)}"
        # nttNo 추출 → 안정적 ID
        m = re.search(r"nttNo=(\d+)", link)
        if m: iid = f"nipa_{m.group(1)}"
        card = a
        for _ in range(5):
            if card.parent: card = card.parent
            if card.name in ("li", "tr", "div", "dl"): break
        dates    = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", card.get_text())
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        items.append(_item(iid, title, link, "정보통신산업진흥원(NIPA)",
                           "", deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── MSS (중소벤처기업부) ─────────────────────────────────────────────────────
def fetch_mss(site: dict) -> list[dict]:
    """table tbody tr, a href='#view', td[0]=bcIdx → detail URL 구성"""
    BASE   = "https://www.mss.go.kr"
    DETAIL = BASE + "/site/smba/ex/bbs/View.do?cbIdx=310&bcIdx="
    soup   = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a")
        if not a: continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        tds   = tr.select("td")
        # 첫 번째 td = 번호(bcIdx)
        bc_idx = norm(tds[0].get_text()) if tds else ""
        link   = DETAIL + bc_idx if bc_idx.isdigit() else site["url"]
        iid    = f"mss_{bc_idx}" if bc_idx.isdigit() else f"mss_{stable_id(title)}"
        # 날짜: td 중 YYYY.MM.DD 패턴
        td_text  = " ".join(td.get_text(strip=True) for td in tds)
        dates    = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", td_text)
        posted   = dates[0].replace(".", "-") if dates else ""
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        items.append(_item(iid, title, link, "중소벤처기업부",
                           "", deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items



# ── BizOK (비즈오케이 - 인천기업지원) ─────────────────────────────────────
def fetch_bizok(site: dict) -> list[dict]:
    """BizOK 인천기업지원: a[href*='act=detail&policyno='] 패턴
    제목에 분야·번호·상태가 붙어있어 정리 필요
    """
    BASE = "https://bizok.incheon.go.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"act=detail&policyno=")):
        raw_title = norm(a.get_text())
        if not raw_title or len(raw_title) < 5: continue
        href = a.get("href", "")
        m = re.search(r"policyno=(\d+)", href)
        if not m: continue
        pno = m.group(1)
        if pno in seen: continue
        seen.add(pno)
        link = href if href.startswith("http") else BASE + href
        iid  = f"bizok_{pno}"
        # 제목 정제: "(No.6874)접수중[뷰티] 실제제목신청기간..." → 실제제목만
        title = re.sub(r"^.*?\)\s*(?:접수중|마감|예정)?\s*", "", raw_title)
        title = re.sub(r"\s*신청기간.*$", "", title).strip()
        if not title: title = raw_title[:50]
        # 날짜
        dates = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", raw_title)
        posted = dates[0].replace(".", "-") if dates else ""
        items.append(_item(iid, title, link, "비즈오케이(인천기업지원)",
                           "", "", site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items



def fetch_mssmiv(site: dict) -> list[dict]:
    """중소기업 혁신바우처 공고: table tbody tr, onclick=goDetail(seq)
    상세 URL: /portal/board/BoardView?seq=N (GET 방식 작동)
    """
    BASE = "https://www.mssmiv.com"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a[onclick]")
        if not a: continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        m = re.search(r"goDetail\((\d+)\)", a.get("onclick", ""))
        if not m: continue
        seq  = m.group(1)
        link = f"{BASE}/portal/board/BoardView?seq={seq}"
        iid  = f"mssmiv_{seq}"
        tds  = tr.select("td")
        td_text = " ".join(td.get_text(strip=True) for td in tds)
        dates   = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", td_text)
        posted  = dates[0].replace(".", "-") if dates else ""
        items.append(_item(iid, title, link, "중소기업혁신바우처(중소벤처기업부)",
                           "", "", site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items



def fetch_exportvoucher(site: dict) -> list[dict]:
    """수출바우처 공고: 메인 페이지에서 goDetail('ntt_id','bbs_id') 추출
    bbs_id=1 → 공지사항(/portal/board/boardView POST)
    bbs_id=2 → 자료실
    상세 링크는 POST 방식이므로 boardView URL에 파라미터 붙여 GET 링크로 구성
    """
    BASE   = "https://www.exportvoucher.com"
    soup   = _soup(site["url"], extra_headers={"Referer": BASE + "/"})
    if not soup: return []

    items, agg = [], site.get("is_aggregator", False)
    seen = set()

    for a in soup.find_all("a"):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        # href 또는 태그 전체 문자열에서 goDetail 추출
        tag_str = str(a)
        m = re.search(r"goDetail\(['\"](\d+)['\"],\s*['\"](\d+)['\"]", tag_str)
        if not m: continue
        ntt_id, bbs_id = m.group(1), m.group(2)
        # 노이즈 제목 제거 (보안점검, 공지 등)
        NOISE = re.compile(r"보안점검|열람금지|시스템\s*점검|서비스\s*중단")
        if NOISE.search(title): continue

        if bbs_id == "1":   # 공지사항 (사업공고 포함)
            menu = "EZ005004000"
        elif bbs_id == "2": # 자료실
            menu = "EZ005005000"
        else:
            continue  # FAQ 등 제외

        link = f"{BASE}/portal/board/boardView?bbs_id={bbs_id}&ntt_id={ntt_id}&active_menu_cd={menu}"
        iid  = f"exportvoucher_{ntt_id}"

        # 날짜는 목록에서 확인 불가 → 빈 값
        items.append(_item(iid, title, link, "수출바우처(KOTRA/중진공)",
                           "", "", site["name"], "", agg))

    log.info("%s: %d건", site["name"], len(items))
    return items



# ── KEIT (한국산업기술평가관리원) ────────────────────────────────────────────
def fetch_keit(site: dict) -> list[dict]:
    """KEIT 사업공고: onclick=goView('list_no') → 상세 URL 구성
    URL: /board.es?mid=a10304000000&bid=0013&act=view&list_no=N
    """
    BASE = "https://www.keit.re.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a[onclick]")
        if not a: continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        m = re.search(r"goView\(['\"]?(\d+)", a.get("onclick", ""))
        if not m: continue
        list_no = m.group(1)
        link = f"{BASE}/board.es?mid=a10304000000&bid=0013&act=view&list_no={list_no}"
        iid  = f"keit_{list_no}"
        tds  = tr.select("td")
        td_text = " ".join(td.get_text(strip=True) for td in tds)
        dates   = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", td_text)
        posted  = dates[0].replace(".", "-") if dates else ""
        items.append(_item(iid, title, link, "한국산업기술평가관리원(KEIT)",
                           "", "", site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── SBA (서울산업진흥원) ─────────────────────────────────────────────────────
def fetch_sba(site: dict) -> list[dict]:
    """SBA 홈페이지에서 NoticeDetail/PostingDetail/BusinessApply href 추출"""
    BASE = "https://www.sba.seoul.kr"
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    pats = re.compile(r"NoticeDetail|PostingDetail|BusinessApply")
    for a in soup.find_all("a", href=pats):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href = a.get("href", "")
        link = href if href.startswith("http") else BASE + href
        if link in seen: continue
        seen.add(link)
        iid = f"sba_{stable_id(link)}"
        # 날짜: 부모 텍스트에서
        parent = a
        for _ in range(4):
            if parent.parent: parent = parent.parent
        ptxt = parent.get_text(" ", strip=True)
        dates  = re.findall(r"\d{4}-\d{2}-\d{2}", ptxt)
        posted = dates[0] if dates else ""
        items.append(_item(iid, title, link, "서울산업진흥원(SBA)",
                           "", "", site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


# ── myfair 수정 (table tbody tr 기반) ────────────────────────────────────────
def fetch_myfair(site: dict) -> list[dict]:
    """마이페어: table tbody tr, 마감일 td에서 추출"""
    soup = _soup(site["url"])
    if not soup: return []
    items, agg = [], site.get("is_aggregator", True)
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a[href]")
        if not a: continue
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        href  = a.get("href", "")
        link  = href if href.startswith("http") else "https://myfair.co" + href
        iid   = f"myfair_{stable_id(title + link)}"
        tds   = tr.select("td")
        td_text = " ".join(td.get_text(strip=True) for td in tds)
        # 날짜 범위에서 시작일/종료일 추출
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", td_text)
        posted   = dates[0] if dates else ""
        deadline = dates[-1] if len(dates) >= 2 else ""
        # 주관기관
        author = norm(tds[1].get_text()) if len(tds) > 1 else ""
        items.append(_item(iid, title, link, author or "마이페어",
                           "", deadline, site["name"], posted, agg))
    log.info("%s: %d건", site["name"], len(items))
    return items


FETCHERS = {
    "bizinfo_api":        fetch_bizinfo,
    "myfair_html":        fetch_myfair,
    "kstartup_html":      fetch_kstartup,
    "kita_html":          fetch_kita,
    "iris_api":           fetch_iris,
    "smtech_html":        fetch_smtech,
    "kocca_pims":         fetch_kocca_pims,
    "kocca_bbs":          fetch_kocca_bbs,
    "gtp_html":           fetch_gtp,
    "gsp_html":           fetch_gsp,
    "ccei_html":          fetch_ccei,
    "nipa_html":          fetch_nipa,
    "mss_html":           fetch_mss,
    "itp_html":           fetch_itp,
    "bizok_html":         fetch_bizok,
    "exportvoucher_html": fetch_exportvoucher,
    "mssmiv_html":        fetch_mssmiv,
    "keit_html":          fetch_keit,
    "sba_html":           fetch_sba,
    "semas_loan_ols":     fetch_semas_loan_ols,
    "html_table":         fetch_html_generic,
    "html_card":          fetch_html_generic,
    # ── Playwright (JS 렌더링) ─────────────────────────────────────────────────
    "pw_keit":         _pw_fetch_keit,
    "pw_kiat":         _pw_fetch_kiat,
    "pw_thevc":        _pw_fetch_thevc,
    "pw_connectworks": _pw_fetch_connectworks,
    "pw_semas":        _pw_fetch_semas,
    "pw_table":        _pw_fetch_table,
}


def fetch_all(sites: list[dict], max_workers: int = 8) -> list[dict]:
    """병렬 수집 (ThreadPoolExecutor). playwright 포함 전체 사이트."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result: list[dict] = []

    def _fetch(s: dict) -> list[dict]:
        fn = FETCHERS.get(s.get("type", ""))
        if fn:
            return fn(s)
        log.warning("알 수 없는 타입: %s (%s)", s.get("type"), s.get("name"))
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, s): s for s in sites}
        for f in as_completed(futures):
            try:
                result.extend(f.result())
            except Exception as e:
                log.error("수집 실패 (%s): %s", futures[f].get("name"), e)
    return result


# ══════════════════════════════════════════════════════════════════
# 중복 제거 (주관기관 우선)
# ══════════════════════════════════════════════════════════════════

def dedup_items(items: list[dict]) -> list[dict]:
    """
    동일 공고가 여러 소스에 있을 때 주관기관(is_aggregator=False) 버전 우선 유지.
    두 제목의 정규화 결과가 동일하거나, 짧은 쪽이 긴 쪽에 포함되면 중복으로 판정.
    """
    kept: list[dict] = []
    norm_map: dict[str, dict] = {}  # normalized_title → kept item

    def similarity_key(title: str) -> str:
        return normalize_title(title)

    def is_duplicate(a_key: str, b_key: str) -> bool:
        if a_key == b_key:
            return True
        # 한 쪽이 다른 쪽의 부분문자열 (10자 이상)
        short, long = (a_key, b_key) if len(a_key) <= len(b_key) else (b_key, a_key)
        return len(short) >= 10 and short in long

    for item in items:
        key = similarity_key(item["title"])
        if not key:
            kept.append(item)
            continue

        dup_key = next((k for k in norm_map if is_duplicate(key, k)), None)

        if dup_key is None:
            # 신규
            norm_map[key] = item
            kept.append(item)
        else:
            existing = norm_map[dup_key]
            # 현재 아이템이 주관기관이고 기존이 집계처이면 교체
            if not item["is_aggregator"] and existing["is_aggregator"]:
                kept.remove(existing)
                kept.append(item)
                del norm_map[dup_key]
                norm_map[key] = item
                log.info("중복제거: '%s' (%s) → '%s' (%s) 로 교체",
                         existing["source"], existing["title"][:20],
                         item["source"], item["title"][:20])
            else:
                log.info("중복제거: '%s' 유지, '%s' 제거 (%s)",
                         existing["title"][:20], item["title"][:20], item["source"])

    log.info("중복제거: %d건 → %d건", len(items), len(kept))
    return kept


# ══════════════════════════════════════════════════════════════════
# 날짜 필터 (D-1: 어제 올라온 공고)
# ══════════════════════════════════════════════════════════════════

def date_filter(items: list[dict], days_back: int = 1) -> tuple[list[dict], list[dict]]:
    """
    posted_date가 있는 아이템은 직전 영업일 target_date와 비교.
    posted_date가 없으면 날짜 불명(unknown)으로 분류.
    반환: (target_date 아이템, 날짜불명 아이템)
    """
    target = previous_business_day(days_back=days_back)
    matched, unknown = [], []
    for it in items:
        pd = it.get("posted_date", "").strip()
        if not pd:
            unknown.append(it)
            continue
        try:
            item_date = datetime.strptime(pd[:10], "%Y-%m-%d").date()
            if item_date == target:
                matched.append(it)
            # else: 다른 날짜 → 제외
        except ValueError:
            unknown.append(it)
    log.info("날짜필터(직전영업일-%d, 기준=%s): 매칭 %d건 / 날짜불명 %d건 / 제외 %d건",
             days_back, target, len(matched), len(unknown),
             len(items) - len(matched) - len(unknown))
    return matched, unknown


# ══════════════════════════════════════════════════════════════════
# 그룹 필터
# ══════════════════════════════════════════════════════════════════

def classify_support_type(item: dict) -> list[str]:
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    matched = [t for t, kws in SUPPORT_TYPE_RULES.items() if any(k in text for k in kws)]
    return matched or ["그외"]


def region_match(item: dict, group_regions: list[str]) -> bool:
    """그룹 지역 조건 매칭. 지역 미설정 시 전체 통과."""
    if not group_regions:
        return True
    text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')}".lower()
    g_regions = [r.lower() for r in group_regions]
    # 그룹 지역 포함 → 통과
    if any(r in text for r in g_regions):
        return True
    # "전국" 명시 → 통과
    if "전국" in text:
        return True
    # 어떤 지역도 언급 안 됨 → 전국 공고로 판단 → 통과
    if not any(kr in text for kr in KNOWN_REGIONS):
        return True
    return False


def keyword_match(item: dict, kw_cfg: dict) -> bool:
    kws = [k.lower() for k in kw_cfg.get("keywords", []) if k.strip()]
    if not kws:
        return True
    logic = kw_cfg.get("logic", "OR").upper()
    text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')}".lower()
    return all(k in text for k in kws) if logic == "AND" else any(k in text for k in kws)


def _normalize_group(group: dict) -> dict:
    """구버전(keywords.logic) → 신버전(or_keywords/and_keyword_groups) 정규화.
    신버전 필드가 하나라도 있으면 그대로 반환."""
    if "or_keywords" in group or "and_keyword_groups" in group or "exclude_keywords" in group:
        if "required_conditions" not in group:
            group = {**group, "required_conditions": {"regions": group.get("regions", [])}}
        return group
    kw_cfg = group.get("keywords", {})
    kws    = kw_cfg.get("keywords", [])
    logic  = kw_cfg.get("logic", "OR").upper()
    norm   = {**group, "required_conditions": {"regions": group.get("regions", [])}}
    if logic == "AND":
        norm["or_keywords"]       = []
        norm["and_keyword_groups"] = [kws] if kws else []
    else:
        norm["or_keywords"]       = kws
        norm["and_keyword_groups"] = []
    norm.setdefault("exclude_keywords", [])
    return norm


def support_match(item: dict, enabled_types: list[str]) -> bool:
    if not enabled_types or set(enabled_types) == set(ALL_SUPPORT_TYPES):
        return True
    types = classify_support_type(item)
    return any(t in enabled_types for t in types)


def filter_for_group(items: list[dict], group: dict) -> list[dict]:
    """
    신버전 조건 구조(or_keywords / and_keyword_groups / exclude_keywords / required_conditions)
    로 필터링. 구버전(keywords.logic) 그룹은 _normalize_group 으로 자동 변환.
    처리 순서: ① 출처 무조건 포함 → ② 필수조건(지역) → ③ 제외 키워드
              → ④ OR/AND 키워드 → ⑤ 지원유형
    """
    g           = _normalize_group(group)
    result      = []
    always_srcs = [s.lower() for s in g.get("source_always_include", [])]
    req_regions = g.get("required_conditions", {}).get("regions", [])
    or_kws      = [k.lower() for k in g.get("or_keywords", []) if k.strip()]
    and_groups  = [[k.lower() for k in ag if k.strip()] for ag in g.get("and_keyword_groups", []) if ag]
    excl_kws    = [k.lower() for k in g.get("exclude_keywords", []) if k.strip()]

    for it in items:
        text = f"{it.get('title','')} {it.get('description','')} {it.get('author','')}".lower()
        src  = (it.get("source","") + " " + it.get("author","")).lower()

        # ① 출처 기반 무조건 포함
        if always_srcs and any(s in src for s in always_srcs):
            if support_match(it, g.get("support_types", ALL_SUPPORT_TYPES)):
                result.append({**it, "_types": classify_support_type(it)})
                continue

        # ② 필수조건: 지역 (OR 방식 — 하나라도 맞으면 통과, 비어 있으면 전체 통과)
        if not region_match(it, req_regions):
            continue

        # ③ 제외 키워드: 하나라도 포함되면 제외
        if excl_kws and any(k in text for k in excl_kws):
            continue

        # ④ 키워드 조건 (OR/AND 모두 비어 있으면 전체 통과)
        if or_kws or and_groups:
            or_pass  = any(k in text for k in or_kws)
            and_pass = any(all(k in text for k in ag) for ag in and_groups)
            if not (or_pass or and_pass):
                continue

        # ⑤ 지원유형
        if not support_match(it, g.get("support_types", ALL_SUPPORT_TYPES)):
            continue

        result.append({**it, "_types": classify_support_type(it)})

    log.info("그룹 '%s' 필터: %d → %d건", g.get("name"), len(items), len(result))
    return result



# ══════════════════════════════════════════════════════════════════
# 렌더링 / Claude 요약
# ══════════════════════════════════════════════════════════════════

def render_all(items: list[dict], dedup_count: int, date_unknown: int, include_unknown: bool = True) -> str:
    by_src: dict[str, list] = {}
    for it in items: by_src.setdefault(it.get("source", "기타"), []).append(it)
    unknown_note = f" / 날짜불명 {date_unknown}건 포함" if include_unknown and date_unknown else (f" / 날짜불명 {date_unknown}건 제외됨" if not include_unknown and date_unknown else "")
    lines = [f"전체 수집 — {len(items)}건 (중복제거 후){unknown_note}\n"]
    for src, src_items in by_src.items():
        lines += [f"\n【 {src} 】 {len(src_items)}건", "─" * 30]
        for it in src_items:
            lines += [f"▸ {it['title']}",
                      f"  기관: {it['author'] or '미기재'} | 마감: {it['deadline'] or '미기재'}"
                      f" | 등록: {it.get('posted_date') or '날짜불명'}"]
            if it.get("link"): lines.append(f"  링크: {it['link']}")
            lines.append("")
    return "\n".join(lines).strip()


def mail_topic(items: list[dict]) -> str:
    if items and all(it.get("source") == SEMAS_LOAN_SOURCE for it in items):
        return SEMAS_LOAN_TITLE
    return "수출·해외진출 공고"


def fallback_body(items: list[dict]) -> str:
    lines: list[str] = []
    imminent = [it for it in items if is_imminent(it.get("deadline", ""))]
    if imminent:
        lines += ["⚠️ 마감 임박 (7일 이내)"]
        for it in imminent:
            lines.append(f"- {it['title']} | 마감: {it['deadline']}")
        lines.append("")
    for it in items:
        lines += ["━━━━━━━━━━━━━━━━━━",
                  f"📌 {it['title']}",
                  f"• 지원유형: {' · '.join(it.get('_types', ['미분류']))}",
                  f"• 지원기관: {it['author'] or '미기재'}",
                  f"• 지원내용: {it['description'] or '미기재'}",
                  f"• 신청마감: {it['deadline'] or '미기재'}",
                  f"• 등록일: {it.get('posted_date') or '날짜불명'}",
                  f"• 출처: {it['source']}",
                  f"• 🔗 {it['link'] or '미기재'}",
                  "━━━━━━━━━━━━━━━━━━"]
    return "\n".join(lines)


def claude_summarize(items: list[dict], group: dict) -> str:
    if not items: return ""
    limited = items[:MAX_FOR_CLAUDE]
    client  = Anthropic(api_key=ANTHROPIC_API_KEY)
    g           = _normalize_group(group)
    req_regions = g.get("required_conditions", {}).get("regions", [])
    stypes      = g.get("support_types", ALL_SUPPORT_TYPES)
    or_kws      = g.get("or_keywords", [])
    and_groups  = g.get("and_keyword_groups", [])
    items_txt = "\n\n".join(
        f"[{i+1}] [{' · '.join(it.get('_types', ['미분류']))}] [등록:{it.get('posted_date','날짜불명')}]\n"
        f"제목: {it['title']}\n기관: {it['author']}\n내용: {it['description']}\n"
        f"마감: {it['deadline']}\n출처: {it['source']}\n링크: {it['link']}"
        for i, it in enumerate(limited)
    )
    region_ctx = f"대상지역: {', '.join(req_regions) if req_regions else '전국'}"
    kw_parts   = ([f"OR({', '.join(or_kws[:4])})"] if or_kws else []) + \
                 [f"AND({', '.join(ag)})" for ag in and_groups[:2]]
    kw_ctx     = "키워드: " + " | ".join(kw_parts) if kw_parts else "키워드: 전체"
    type_ctx   = f"지원유형: {', '.join(stypes)}"
    prompt = f"""아래는 [{region_ctx} / {kw_ctx} / {type_ctx}] 조건으로 선별된 공고입니다.
중소기업이 실제 활용 가능한 공고를 선별·정리해주세요.
마감 임박(7일 이내) 공고는 '⚠️ 마감 임박' 섹션을 앞에 배치하세요.

출력 형식:
━━━━━━━━━━━━━━━━━━
📌 [사업명]
• 지원유형:
• 지원기관:
• 지원내용/금액:
• 신청마감:
• 지역조건:
• 출처:
• 🔗 링크
━━━━━━━━━━━━━━━━━━

공고 목록:
{items_txt}"""
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=4000,
            messages=[{"role": "user", "content": prompt}])
        return resp.content[0].text.strip()
    except Exception as e:
        log.exception("Claude 요약 실패: %s", e)
        return fallback_body(limited)


# ══════════════════════════════════════════════════════════════════
# 이메일
# ══════════════════════════════════════════════════════════════════

def _mask_email(email: str) -> str:
    local, sep, domain = (email or "").partition("@")
    if not sep:
        return "***"
    if len(local) <= 2:
        local_masked = local[:1] + "*"
    else:
        local_masked = local[:2] + "*" * (len(local) - 2)
    return f"{local_masked}@{domain}"

def send_email(subject: str, body: str, to: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, GMAIL_ADDRESS, to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(
        f"<html><body style='font-family:Arial;line-height:1.7'>"
        f"<pre style='white-space:pre-wrap;font-family:inherit'>{html_pre(body)}</pre>"
        f"</body></html>", "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        srv.sendmail(GMAIL_ADDRESS, to, msg.as_string())
    log.info("발송 완료 → %s", _mask_email(to))

def send_to_list(subject: str, body: str, recipients: list[str]) -> None:
    for to in recipients:
        try:
            send_email(subject, body, to)
        except Exception as e:
            log.error("발송 실패 (%s): %s", _mask_email(to), e)


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def execute_monitor(
    *,
    allow_send: bool = False,
    include_raw_all: bool = False,
    persist_seen: bool = False,
) -> dict:
    now = datetime.now(KST)
    mode = "send" if allow_send else "preview"
    log.info("=== 모니터링 시작 v6 (%s) / mode=%s ===", now.strftime("%Y-%m-%d %H:%M KST"), mode)

    sites    = load_sites()
    groups   = load_groups()
    settings = load_settings()
    seen_ids = load_seen_ids()
    days_back = settings.get("days_back", 1)

    if not sites:
        log.info("활성 사이트 없음. 종료.")
        return {"ok": True, "mode": mode, "reason": "no_active_sites"}
    if not groups:
        log.info("활성 그룹 없음. 종료.")
        return {"ok": True, "mode": mode, "reason": "no_active_groups"}

    # ① 전체 수집
    all_items = fetch_all(sites)
    if not all_items:
        log.info("수집 0건. 종료.")
        return {"ok": True, "mode": mode, "reason": "no_items"}
    log.info("수집 완료: %d건", len(all_items))

    # ② 중복 제거
    deduped = dedup_items(all_items)
    dedup_removed = len(all_items) - len(deduped)

    # ③ 신규 필터 (seen_ids)
    new_items = [it for it in deduped if it["id"] and it["id"] not in seen_ids]
    log.info("신규(미발송): %d건 / 전체: %d건", len(new_items), len(deduped))

    # ④ 날짜 필터 (직전 영업일)
    target_date = previous_business_day(now, days_back)
    date_str    = now.strftime("%m/%d")

    include_unknown = settings.get("include_date_unknown", False)
    date_unknown: list = []
    if settings.get("date_filter_enabled", True):
        date_matched, date_unknown = date_filter(new_items, days_back)
        if include_unknown:
            filtered_new = date_matched + date_unknown
            log.info("날짜필터 후 처리 대상: %d건 (확정 %d + 날짜불명 %d 포함)",
                     len(filtered_new), len(date_matched), len(date_unknown))
        else:
            filtered_new = date_matched
            log.info("날짜필터 후 처리 대상: %d건 (확정만, 날짜불명 %d건 제외)",
                     len(filtered_new), len(date_unknown))
    else:
        filtered_new = new_items
        date_unknown = []

    # ⑤ 원본전체 메일 (settings.raw_all_recipients)
    if (
        allow_send
        and include_raw_all
        and settings.get("raw_all_enabled", True)
        and settings.get("raw_all_recipients")
    ):
        raw_topic = mail_topic(filtered_new)
        body_raw = (
            f"수집일시: {now.strftime('%Y-%m-%d %H:%M KST')}\n"
            f"기준일자: {target_date} (직전영업일-{days_back}) 공고\n"
            f"전체수집: {len(all_items)}건 → 중복제거: {dedup_removed}건 → 신규: {len(new_items)}건\n"
            f"날짜필터 후 발송대상: {len(filtered_new)}건\n\n"
        ) + render_all(filtered_new, dedup_removed, len(date_unknown), include_unknown)
        send_to_list(
            f"[원본전체] {raw_topic} ({date_str}) — {len(filtered_new)}건",
            body_raw, settings["raw_all_recipients"],
        )

    if not filtered_new:
        log.info("처리 대상 없음. 종료.")
        if persist_seen:
            seen_ids.update(it["id"] for it in deduped)
            save_seen_ids(seen_ids)
        return {
            "ok": True,
            "mode": mode,
            "collected": len(all_items),
            "deduped": len(deduped),
            "new_items": len(new_items),
            "filtered_items": 0,
            "date_unknown_items": len(date_unknown),
            "sent_groups": [],
        }

    # ⑥ 그룹별 필터 + 발송
    sent_groups: list[dict] = []
    for group in groups:
        g_items = filter_for_group(filtered_new, group)
        if not g_items:
            log.info("그룹 '%s': 조건 매칭 공고 없음", group.get("name"))
            continue
        sent_groups.append({"name": group.get("name"), "matched_items": len(g_items)})
        if allow_send:
            summary    = claude_summarize(g_items, group)
            g_norm     = _normalize_group(group)
            req_rgns   = g_norm.get("required_conditions", {}).get("regions", [])
            _or_kws    = g_norm.get("or_keywords", [])
            _and_grps  = g_norm.get("and_keyword_groups", [])
            _kw_parts  = ([f"OR({', '.join(_or_kws[:3])})"] if _or_kws else []) + \
                         [f"AND({', '.join(ag)})" for ag in _and_grps[:2]]
            kw_str     = " | ".join(_kw_parts) or "전체"
            header  = (
                f"수집일시: {now.strftime('%Y-%m-%d %H:%M KST')}\n"
                f"기준일자: {target_date} (직전영업일-{days_back}) 공고\n"
                f"그룹: {group.get('name')}\n"
                f"지역: {', '.join(req_rgns) or '전국'} / 키워드: {kw_str}\n"
                f"지원유형: {', '.join(g_norm.get('support_types', ALL_SUPPORT_TYPES))}\n"
                f"전체 {len(filtered_new)}건 → 그룹 매칭 {len(g_items)}건\n\n"
            )
            send_to_list(
                f"[{group.get('name')}] {mail_topic(g_items)} ({date_str}) — {len(g_items)}건",
                header + summary,
                group.get("recipients", []),
            )

    # ⑦ seen_ids 업데이트
    if persist_seen:
        seen_ids.update(it["id"] for it in deduped)
        save_seen_ids(seen_ids)
    log.info("=== 완료 ===")
    return {
        "ok": True,
        "mode": mode,
        "collected": len(all_items),
        "deduped": len(deduped),
        "new_items": len(new_items),
        "filtered_items": len(filtered_new),
        "date_unknown_items": len(date_unknown),
        "sent_groups": sent_groups,
    }

def main() -> None:
    execute_monitor(allow_send=True, include_raw_all=True, persist_seen=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.exception("치명적 오류: %s", e)
        raise

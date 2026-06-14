"""수출·지원사업 모니터링 에이전트 v6
기능: 수집 → 중복제거(주관기관 우선) → 날짜필터(D-1) → 그룹별 조건필터 → Claude요약 → 발송
설정: sites.json / groups.json / settings.json / seen_ids.json
"""
from __future__ import annotations

import hashlib, html, json, logging, os, re, smtplib, ssl, unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, quote

import httpx
from anthropic import Anthropic
from bs4 import BeautifulSoup

# ── 기업 맞춤 정밀 매칭(2차 컷오프) — 선택적 ────────────────────────────────────
# evaluate_notice(1차 필터) 통과분에 대해 기업 프로필(companies.json) 점수로
# 정밀 컷오프. 모듈/파일이 없거나 비활성이면 기존 동작 그대로(하위호환).
try:
    from company_match import (
        load_companies as _load_companies,
        match_for_company as _match_for_company,
    )
    _CM_OK = True
except ImportError:
    _CM_OK = False

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
MAX_SEEN_IDS   = 5000
MAX_FOR_CLAUDE = 15
COLLECTOR_FILE = "monitor.py"
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_ALLOW_SMTP_SEND = False
_ALLOW_PERSIST_SEEN = True
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

APPLICANT_REGION_CITY = "인천광역시"
APPLICANT_REGION_DISTRICT = "남동구"
INCHEON_DISTRICTS = [
    "강화군", "계양구", "남동구", "동구", "미추홀구",
    "부평구", "서구", "연수구", "옹진군", "중구",
]

GENERAL_INCLUDE_KEYWORD_ALIASES = [
    ("베트남", ["베트남"]),
    ("동남아", ["동남아"]),
    ("해외", ["해외"]),
    ("글로벌", ["글로벌"]),
    ("박람회", ["박람회"]),
    ("전시회", ["전시회", "해외전시회"]),
    ("소상공인", ["소상공인"]),
    ("지원금", ["지원금"]),
    ("공장", ["공장"]),
    ("스마트", ["스마트"]),
    ("스마트공장", ["스마트공장"]),
    ("스마트팩토리", ["스마트팩토리"]),
    ("제조DX", ["제조dx", "제조 dx"]),
    ("제조 디지털전환", ["제조 디지털전환"]),
    ("디지털전환", ["디지털전환"]),
    ("공정개선", ["공정개선"]),
    ("공정자동화", ["공정자동화"]),
    ("자동화", ["자동화"]),
    ("생산성 향상", ["생산성 향상"]),
    ("MES", ["mes"]),
    ("ERP", ["erp"]),
    ("제조혁신", ["제조혁신"]),
    ("제조AI", ["제조ai", "제조 ai"]),
    ("로봇", ["로봇"]),
    ("설비개선", ["설비개선"]),
]

PRIORITY_KEYWORD_ALIASES = [
    ("혁신바우처", ["혁신바우처", "혁신 바우처"]),
    ("수출바우처", ["수출바우처", "수출 바우처"]),
    ("스마트공장", ["스마트공장"]),
    ("스마트팩토리", ["스마트팩토리"]),
    ("제조DX", ["제조dx", "제조 dx"]),
    ("공정개선", ["공정개선"]),
    ("공정자동화", ["공정자동화"]),
    ("자동화", ["자동화"]),
    ("제조혁신", ["제조혁신"]),
]

FACTORY_KEYWORD_ALIASES = [
    ("공장", ["공장"]),
    ("공장등록", ["공장등록"]),
    ("공장등록증", ["공장등록증"]),
    ("제조시설", ["제조시설"]),
    ("생산시설", ["생산시설"]),
    ("제조공장", ["제조공장"]),
    ("사업장", ["사업장"]),
    ("제조업 영위", ["제조업 영위"]),
    ("제조기업", ["제조기업"]),
    ("공장 보유", ["공장 보유", "공장보유"]),
    ("공장 임차", ["공장 임차", "공장임차"]),
    ("임대공장", ["임대공장"]),
    ("산업단지", ["산업단지"]),
    ("입주기업", ["입주기업"]),
]

FACTORY_REQUIRED_TERMS = [
    "공장등록증", "제조시설", "생산시설", "제조업 영위", "공장 보유",
    "공장보유", "공장 임차", "공장임차", "임대공장", "입주기업",
]

APPLICATION_KEYWORDS = [
    "모집공고", "지원계획 공고", "참여기업 모집", "수요기업 모집", "신청접수",
    "지원사업 공고", "해외전시회", "박람회", "전시회", "수출상담회",
    "바이어 매칭", "마케팅 지원", "판로지원", "수출지원", "글로벌", "해외",
    "베트남", "동남아", "화장품", "뷰티", "k-beauty", "소상공인", "지원금",
    "혁신바우처", "혁신 바우처", "수출바우처", "수출 바우처", "스마트공장",
    "스마트팩토리", "공정개선", "공정자동화", "설비개선", "구축 지원사업",
]

GENERAL_SERVICE_EXCLUDE_KEYWORDS = ["설명회", "컨설팅지원", "멘토링"]

EXCLUSION_RULES = [
    ("GUIDELINE_OR_MANUAL", "guideline", "unknown", [
        "부정수급", "정부 지침", "관리지침", "운영지침", "지침 개정",
        "공동인증서", "공인인증서", "매뉴얼", "사용 안내", "유의사항", "시스템 이용 안내",
    ]),
    ("INFO_SESSION", "info_session", "unknown", ["설명회", "오리엔테이션"]),
    ("EDUCATION_ONLY", "education", "unknown", [
        "교육 일정", "교육일정", "분야별 교육", "선정기업 교육", "수요기업 교육", "공급기업 교육",
    ]),
    ("SUPPLIER_ONLY", "application_notice", "supplier", [
        "공급기업", "수행기관", "서비스 제공자", "컨설팅분야 수행", "수행 관련 안내", "공급기업 추가모집",
    ]),
    ("SELECTED_COMPANY_ONLY", "post_selection", "selected_company", [
        "선금신청", "정산", "협약", "결과보고", "중간점검", "기선정", "선정기업 대상",
    ]),
    ("NOT_GRANT_NOTICE", "general_info", "unknown", ["산재예방요율제", "보험료율", "제도 안내"]),
]

REGION_EXCLUDE_PHRASES = [
    "수도권 제외", "수도권 소재 기업 제외", "서울·경기·인천 제외", "서울 경기 인천 제외",
    "수도권 소재 기업 신청 불가", "인천 제외", "비수도권 기업 대상",
    "지역제조 중 수도권 제외", "인천 소재 기업 신청 불가",
]
OPEN_DEADLINE_TERMS = ["상시접수", "수시접수", "예산 소진 시까지", "예산소진 시까지", "예산 소진시까지"]

# 신청·모집 기간 라벨 (우선순위 순). 협약/사업기간과 구분한다.
APPLICATION_PERIOD_LABELS = (
    "신청기간", "모집기간", "접수기간", "지원신청기간", "참가신청기간",
    "신청 일정", "접수 일정", "모집 일정",
)
NON_APPLICATION_PERIOD_LABELS = (
    "협약기간", "사업기간", "수행기간", "지원기간", "운영기간", "서비스 완료",
    "사업 추진 기간", "지원 기간",
)
DETAIL_ENRICH_HOSTS = ("exportvoucher.com", "k-startup.go.kr")
MAX_DETAIL_ENRICH = 40

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# 보안: 로그(특히 httpx 요청 로그)에 평문 노출되는 API 인증키를 마스킹한다.
# 정부 공공데이터 인증키(crtfcKey 등)가 요청 URL 쿼리로 들어가 INFO 로그에
# 그대로 찍히던 문제 차단. 로깅 계층(핸들러)에서만 가리므로 실제 요청값엔 영향 없음.
class _RedactSecretsFilter(logging.Filter):
    _SECRET_RE = re.compile(
        r"\b((?:crtfcKey|serviceKey|apiKey|api_key|secretKey|authKey|key)=)[^&\s'\"]+",
        re.IGNORECASE,
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = self._SECRET_RE.sub(r"\1***", msg)
            if redacted != msg:
                record.msg, record.args = redacted, ()
        except Exception:
            pass
        return True


for _h in logging.getLogger().handlers:
    _h.addFilter(_RedactSecretsFilter())


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
    """텍스트에서 첫 날짜를 YYYY-MM-DD로 추출."""
    dates = _parse_date_candidates(text)
    return dates[0][1].isoformat() if dates else ""


def _valid_date(year: int, month: int, day: int):
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def _parse_date_candidates(text: str, base_year: int | None = None) -> list[tuple[int, Any]]:
    """공고 날짜 표현에서 날짜 후보를 원문 위치순으로 반환."""
    if not text:
        return []
    base_year = base_year or datetime.now(KST).year
    candidates: list[tuple[int, Any]] = []
    patterns = [
        (r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*\.?\s*[.\-/]\s*(\d{1,2})", 1),
        (r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", 1),
        (r"'?(\d{2})\s*[.\-/]\s*(\d{1,2})\s*\.?\s*[.\-/]\s*(\d{1,2})", 2000),
        (r"(?<!\d)(\d{1,2})\s*[.]\s*(\d{1,2})\.?(?!\d)", None),
    ]
    for pattern, year_mode in patterns:
        for m in re.finditer(pattern, text):
            if year_mode is None:
                year, month, day = base_year, int(m.group(1)), int(m.group(2))
            elif year_mode == 2000:
                year, month, day = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            parsed = _valid_date(year, month, day)
            if parsed:
                candidates.append((m.start(), parsed))
    deduped: dict[Any, tuple[int, Any]] = {}
    for pos, parsed in candidates:
        deduped.setdefault(parsed, (pos, parsed))
    return sorted(deduped.values(), key=lambda pair: pair[0])


def _parse_period_dates(segment: str, base_year: int | None = None) -> list[Any]:
    """신청·모집 구간 텍스트에서 시작·종료일 후보를 추출."""
    if not segment:
        return []
    base_year = base_year or datetime.now(KST).year
    ym = re.search(r"'?(\d{2})\s*년", segment)
    if ym:
        base_year = 2000 + int(ym.group(1))
    ym = re.search(r"(\d{4})\s*년", segment)
    if ym:
        base_year = int(ym.group(1))
    dates = [parsed for _, parsed in _parse_date_candidates(segment, base_year)]
    for m in re.finditer(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", segment):
        parsed = _valid_date(base_year, int(m.group(1)), int(m.group(2)))
        if parsed:
            dates.append(parsed)
    return sorted(set(dates))


def extract_application_period(text: str) -> dict[str, str]:
    """본문에서 신청·모집·접수 기간만 추출 (협약기간 등 제외)."""
    if not text:
        return {}
    normalized = text.replace("\xa0", " ")
    for label in APPLICATION_PERIOD_LABELS:
        pattern = rf"{re.escape(label)}\s*[:：]?\s*([^\nㅇ]+)"
        m = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not m:
            continue
        segment = m.group(1).strip()
        if "까지" in segment:
            segment = segment[: segment.index("까지") + 2]
        dates = _parse_period_dates(segment)
        if not dates:
            continue
        start, end = dates[0].isoformat(), dates[-1].isoformat()
        display = f"{start} ~ {end}" if start != end else end
        return {"start": start, "end": end, "display": display, "label": label}
    return {}


def resolve_item_deadline(item: dict) -> str:
    """표시·필터용 마감일: 신청기간 우선, 없으면 기존 deadline."""
    period = extract_application_period(_notice_body_text(item))
    if period.get("display"):
        return period["display"]
    return (item.get("deadline") or "").strip()


def _detect_target_regions(text: str) -> dict[str, Any]:
    """지원 대상 지역 힌트 (전국 / 특정 시·도)."""
    if not text:
        return {"regions": [], "nationwide": False}
    regions: list[str] = []
    nationwide = False
    for phrase in ("전국", "국내 전체", "국내전체", "제한 없음"):
        if phrase in text:
            nationwide = True
    patterns = [
        r"소재지가\s*([가-힣]+(?:도|광역시|특별시|특별자치시|특별자치도))",
        r"([가-힣]+(?:광역시|특별시|특별자치시|특별자치도|도))\s*소재",
        r"지역\s*[:：]\s*([가-힣]+(?:광역시|도|특별시|특별자치시|특별자치도))",
        r"지원\s*지역\s*[:：]\s*([가-힣]+(?:광역시|도|특별시))",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            val = norm(m.group(1))
            if val and val not in regions:
                regions.append(val)
    region_title_hints = [
        (r"경기도|경기\s", "경기"),
        (r"부산광역시|부산\s", "부산"),
        (r"서울특별시|서울\s", "서울"),
        (r"대구광역시|대구\s", "대구"),
        (r"광주광역시|광주\s", "광주"),
        (r"대전광역시|대전\s", "대전"),
        (r"울산광역시|울산\s", "울산"),
        (r"세종특별자치시|세종\s", "세종"),
        (r"인천광역시|인천\s", "인천"),
        (r"제주특별자치도|제주\s", "제주"),
        (r"강원특별자치도|강원도|강원\s", "강원"),
        (r"충청북도|충북\s", "충북"),
        (r"충청남도|충남\s", "충남"),
        (r"전라북도|전북\s", "전북"),
        (r"전라남도|전남\s", "전남"),
        (r"경상북도|경북\s", "경북"),
        (r"경상남도|경남\s", "경남"),
    ]
    for pattern, label in region_title_hints:
        if re.search(pattern, text):
            if label not in regions:
                regions.append(label)
    return {"regions": regions, "nationwide": nationwide}


def _parse_detail_from_page(soup: BeautifulSoup, url: str) -> dict[str, str]:
    """상세 페이지에서 본문·지역·신청기간 추출."""
    result: dict[str, str] = {}
    if "k-startup.go.kr" in url:
        for tit in soup.select("p.tit"):
            label = norm(tit.get_text())
            nxt = tit.find_next("p", class_="txt")
            if not nxt:
                continue
            val = norm(nxt.get_text())
            if label == "지역" and val:
                result["region_field"] = val
            if label == "신청기간" and val:
                result["application_period_text"] = val
        body = soup.select_one(".view_cont, .content_view, #contents")
        if body:
            result["body"] = body.get_text("\n", strip=True)[:12000]
    elif "exportvoucher.com" in url:
        body = soup.select_one(".board_view, .view_cont, .bbs_view, article, #contents")
        if not body:
            body = soup
        result["body"] = body.get_text("\n", strip=True)[:12000]
    else:
        body = soup.select_one("article, .view_cont, #contents, main")
        if body:
            result["body"] = body.get_text("\n", strip=True)[:12000]
    return result


def enrich_item_from_detail(item: dict) -> dict:
    """상세 페이지를 조회해 description·deadline·지역 정보를 보강."""
    link = (item.get("link") or "").strip()
    if not link or item.get("detail_enriched"):
        return item
    if not any(host in link for host in DETAIL_ENRICH_HOSTS):
        return item
    soup = _soup(link)
    if not soup:
        return item
    fields = _parse_detail_from_page(soup, link)
    updated = {**item, "detail_enriched": True}
    body = fields.get("body", "")
    if body:
        desc = (item.get("description") or "").strip()
        updated["description"] = f"{desc}\n{body}".strip() if desc else body
    if fields.get("region_field"):
        updated["region_field"] = fields["region_field"]
    period_src = fields.get("application_period_text") or updated.get("description", "")
    period = extract_application_period(period_src) or extract_application_period(body)
    if period.get("display"):
        updated["deadline"] = period["display"]
        updated["application_period"] = period
    elif not (updated.get("deadline") or "").strip():
        # 상세만 있고 라벨이 없을 때 — 협약기간 등 비신청 라벨 구간은 제외
        scrubbed = body
        for lbl in NON_APPLICATION_PERIOD_LABELS:
            scrubbed = re.sub(
                rf"{re.escape(lbl)}\s*[:：]?\s*[^\nㅇ]+",
                "",
                scrubbed,
                flags=re.IGNORECASE,
            )
        period = extract_application_period(scrubbed)
        if period.get("display"):
            updated["deadline"] = period["display"]
            updated["application_period"] = period
    posted = extract_date_from_text(body)
    if posted and not (updated.get("posted_date") or "").strip():
        updated["posted_date"] = posted
    return updated


def enrich_items(items: list[dict], limit: int = MAX_DETAIL_ENRICH) -> list[dict]:
    """신규 공고 중 상세 보강이 필요한 항목만 HTTP 상세 조회."""
    targets = [
        it for it in items
        if any(h in (it.get("link") or "") for h in DETAIL_ENRICH_HOSTS)
        and not it.get("detail_enriched")
    ][:limit]
    if not targets:
        return items
    log.info("상세 보강: %d건", len(targets))
    enriched_map = {it["id"]: enrich_item_from_detail(it) for it in targets}
    return [enriched_map.get(it["id"], it) if it["id"] in enriched_map else it for it in items]


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
    if not _ALLOW_PERSIST_SEEN or os.environ.get("MONITOR_NO_PERSIST_SEEN") == "1":
        log.info("seen_ids 저장 생략 (dry-run / persist 비활성)")
        return
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
        # 기업 맞춤 정밀 매칭(2차 컷오프). 그룹에 company_id 연결 + 이 값 true 일 때만 적용.
        "company_match_enabled": False,
        # 게시일이 기준일(today)보다 이 일수 넘게 지난 공고를 '옛날 공고'로 강제 제외.
        # null(기본)이면 미적용 — 기존 '직전영업일 정확일치' 로직만 사용.
        "max_posted_age_days": None,
    }
    return {**default, **load_json(SETTINGS_PATH, {})}


# ══════════════════════════════════════════════════════════════════
# 크롤러
# ══════════════════════════════════════════════════════════════════

def _legacy_ssl_ctx() -> ssl.SSLContext:
    """한국 정부/공공 사이트의 legacy SSL·cipher 호환용 컨텍스트."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT  # OpenSSL 3.x
    except AttributeError:
        pass
    return ctx


def _soup(url: str, extra_headers: dict | None = None, **kwargs):
    hdrs = {**HTTP_HEADERS, **(extra_headers or {})}
    # 3단계 SSL 폴백: (1) 표준 검증 (2) 검증 해제 (3) legacy SSL ctx
    # 정상 사이트는 (1)에서 즉시 성공 → 기존 동작·속도 보존. SSL 실패만 폴백.
    last_err: Exception | None = None
    for stage in ("strict", "no_verify", "legacy"):
        verify: Any = True if stage == "strict" else (
            False if stage == "no_verify" else _legacy_ssl_ctx())
        try:
            with httpx.Client(timeout=30, headers=hdrs, follow_redirects=True,
                              verify=verify) as c:
                r = c.get(url, **kwargs); r.raise_for_status()
                return BeautifulSoup(r.text, "html.parser")
        except httpx.HTTPStatusError as e:
            log.error("접속 실패 %s: %s", url, e); return None  # 404 등은 폴백 무의미
        except Exception as e:
            last_err = e; continue
    log.error("접속 실패 %s: %s", url, last_err); return None

def _item(id_, title, link, author, desc, deadline, source,
          posted_date="", is_aggregator=False) -> dict:
    return {"id": id_, "title": title, "link": link, "author": author,
            "description": desc, "deadline": deadline, "source": source,
            "posted_date": posted_date, "is_aggregator": is_aggregator}


def fetch_bizinfo(site: dict) -> list[dict]:
    # 전체 분류·전체 건수 수집(실측 1456건). 분류필터 없음 → 금융·기술·인력·수출·내수·창업·경영 등 전 분류.
    # (과거엔 수출(04)분류·100건 상한만 받아 1300건+ 누락)
    try:
        with httpx.Client(timeout=60, headers=HTTP_HEADERS) as c:
            r = c.get(site["url"], params={
                "crtfcKey": BIZINFO_API_KEY, "dataType": "json", "searchCnt": "99999"})
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
    # 사업공고가 공공(PBC010)·민간(PBC020)으로 분리됨 → 둘 다 수집.
    # 과거엔 pbancClssCd 미전송 → 서버 기본값 PBC010(공공)만 받아 민간 공고를 전부 누락.
    items, agg = [], site.get("is_aggregator", False)
    seen_sn = set()
    for clss in ("PBC010", "PBC020"):
        soup = _soup(site["url"], params={
            "schMenuId": "10090", "pageIndex": "1", "viewCount": "100",
            "pbancSttus": "ing", "pbancClssCd": clss})
        if not soup: continue
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
            if sn and sn in seen_sn: continue
            if sn: seen_sn.add(sn)
            link = (f"https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
                    f"?pbancClssCd={clss}&schM=view&pbancSn={sn}") if sn else site["url"]
            spans = card.select("span.list")
            org = norm(spans[0].get_text()) if spans else ""
            dl = next((norm(sp.get_text().replace("마감일자", ""))
                       for sp in spans if "마감일자" in sp.get_text()), "")
            posted = ""
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
        period   = extract_application_period(row_text)
        dates    = re.findall(r"\d{4}[.\-/]\d{2}[.\-/]\d{2}", row_text)
        posted   = dates[0].replace(".", "-").replace("/", "-") if dates else ""
        deadline = period.get("display", "")
        if not deadline:
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
    """a[href*='nttDetail'] 패턴, relative → absolute 변환.
    curPage 페이지네이션을 순회해 전체 수집(과거엔 1페이지 10건만 받아 대량 누락 — 실측 tab=2만 390건).
    """
    BASE = "https://www.nipa.kr/home/bsnsAll/0/"
    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    base_url  = site["url"]
    sep       = "&" if "?" in base_url else "?"
    max_pages = site.get("max_pages", 60)  # 안전 상한(실측 39페이지) — site 설정으로 조정 가능
    for cp in range(1, max_pages + 1):
        soup = _soup(f"{base_url}{sep}curPage={cp}")
        if not soup: break
        page_new = 0
        for a in soup.find_all("a", href=re.compile(r"nttDetail")):
            title = norm(a.get_text())
            if not title or len(title) < 5: continue
            href = a.get("href", "")
            link = href if href.startswith("http") else BASE + href.lstrip("./")
            if link in seen: continue
            seen.add(link)
            page_new += 1
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
        if page_new == 0:  # 새 공고 없음(끝 도달 또는 전부 중복) → 종료
            break
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


def fetch_incheon_city(site: dict) -> list[dict]:
    """인천광역시청 공고/고시: table 없이 a[href*='/view?repSeq='] 링크 목록."""
    BASE = "https://www.incheon.go.kr"
    soup = _soup(site["url"])
    if not soup:
        return []
    items, agg = [], site.get("is_aggregator", False)
    seen: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"/IC010205/view\?repSeq=")):
        href = a.get("href", "")
        m = re.search(r"repSeq=([^&]+)", href)
        if not m:
            continue
        rep_seq = m.group(1)
        if rep_seq in seen:
            continue
        seen.add(rep_seq)
        title = norm(a.get_text())
        if not title or len(title) < 4:
            continue
        link = href if href.startswith("http") else urljoin(BASE, href)
        parent = a.find_parent(["li", "tr", "div"])
        row_text = parent.get_text(" ", strip=True) if parent else ""
        dates = re.findall(r"\d{4}[.\-/]\d{2}[.\-/]\d{2}", row_text)
        posted = dates[0].replace(".", "-").replace("/", "-") if dates else ""
        deadline = dates[-1].replace(".", "-").replace("/", "-") if len(dates) >= 2 else ""
        items.append(_item(
            f"incheon_city_{rep_seq}", title, link, "인천광역시",
            "", deadline, site["name"], posted, agg,
        ))
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

    # 목록 URL의 bbs_id (신버전 goDetail(ntt_id) 1인자일 때 게시판 구분에 사용)
    mbbs = re.search(r"bbs_id=(\d+)", site["url"])
    default_bbs = mbbs.group(1) if mbbs else "1"
    # 노이즈 제목 제거 (보안점검, 공지 등)
    NOISE = re.compile(r"보안점검|열람금지|시스템\s*점검|서비스\s*중단")

    for a in soup.find_all("a"):
        title = norm(a.get_text())
        if not title or len(title) < 5: continue
        # href 또는 태그 전체 문자열에서 goDetail 추출
        tag_str = str(a)
        # 사이트 개편 대응: 신 goDetail(123) 1인자 / 구 goDetail('123','1') 2인자 모두 지원
        m2 = re.search(r"goDetail\(\s*['\"]?(\d+)['\"]?\s*,\s*['\"]?(\d+)['\"]?\s*\)", tag_str)
        m1 = re.search(r"goDetail\(\s*(\d+)\s*\)", tag_str)
        if m2:
            ntt_id, bbs_id = m2.group(1), m2.group(2)
        elif m1:
            ntt_id, bbs_id = m1.group(1), default_bbs
        else:
            continue
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
        iid = f"sba_{stable_id(title)}"
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
    "incheon_city_html":  fetch_incheon_city,
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


def _coverage_risk_level(row: dict) -> str:
    if not row.get("enabled", True):
        return "낮음"
    if row.get("fetch_error") or not row.get("fetch_success"):
        return "높음"
    if row.get("date_unknown_count", 0) > 0 and row.get("posted_parsed_count", 0) == 0:
        return "높음"
    if row.get("date_unknown_count", 0) > row.get("posted_parsed_count", 0):
        return "중간"
    return "낮음"


def fetch_site_coverage(
    sites: list[dict] | None = None,
    *,
    days_back: int = 1,
) -> list[dict]:
    """사이트별 수집·날짜 파싱 현황 (병렬 fetch_all과 별도 순차 실행)."""
    sites = sites if sites is not None else load_json(SITES_PATH, [])
    target = previous_business_day(days_back=days_back)
    rows: list[dict] = []
    for site in sites:
        stype = site.get("type", "")
        fn = FETCHERS.get(stype)
        row: dict[str, Any] = {
            "site_id": site.get("id", ""),
            "site_name": site.get("name", ""),
            "collector_type": stype,
            "collector_file": COLLECTOR_FILE,
            "collector_fn": fn.__name__ if fn else "",
            "url": site.get("url", ""),
            "enabled": site.get("enabled", True),
            "fetch_success": False,
            "fetch_error": "",
            "item_count": 0,
            "posted_parsed_count": 0,
            "date_unknown_count": 0,
            "today_target_count": 0,
            "dedup_removed_estimate": 0,
            "final_mail_target_estimate": 0,
            "missing_risk": "높음",
        }
        if not site.get("enabled", True):
            row["fetch_error"] = "disabled_in_config"
            row["missing_risk"] = "낮음"
            rows.append(row)
            continue
        if not fn:
            row["fetch_error"] = f"unknown_type:{stype}"
            rows.append(row)
            continue
        try:
            items = fn(site)
            row["fetch_success"] = True
            row["item_count"] = len(items)
            matched, unknown, _excl = partition_posted_dates(items, days_back)
            row["posted_parsed_count"] = len(matched)
            row["date_unknown_count"] = len(unknown)
            row["today_target_count"] = len(matched)
            row["dedup_removed_estimate"] = 0
            row["final_mail_target_estimate"] = len(matched) + len(unknown)
        except Exception as exc:
            row["fetch_error"] = str(exc)[:200]
        row["missing_risk"] = _coverage_risk_level(row)
        rows.append(row)
    return rows


def validate_recipients(recipients: list[str]) -> dict[str, list[str]]:
    """수신자 검증·중복제거. 원문은 valid/rejected, masked는 로그용."""
    valid: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in recipients or []:
        if raw is None:
            continue
        email = str(raw).strip()
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        if EMAIL_RE.match(email):
            valid.append(email)
        else:
            rejected.append(email)
    return {
        "valid": valid,
        "rejected": rejected,
        "masked": [_mask_email(e) for e in valid],
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

def partition_posted_dates(
    items: list[dict], days_back: int = 1, max_age_days: int | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    posted_date 기준 분류.
    반환: (직전영업일 확정, 날짜불명, 그 외 날짜·파싱실패 제외)

    max_age_days 가 지정되면, 게시일이 오늘 기준 그 일수보다 오래된 공고는
    '옛날 공고'로 간주해 강제 제외(_excluded_reason="too_old"). None 이면 미적용.
    """
    target = previous_business_day(days_back=days_back)
    today = datetime.now(KST).date()
    matched, unknown, excluded = [], [], []
    for it in items:
        pd = it.get("posted_date", "").strip()
        if not pd:
            unknown.append(it)
            continue
        try:
            item_date = datetime.strptime(pd[:10], "%Y-%m-%d").date()
        except ValueError:
            unknown.append(it)
            continue
        if max_age_days is not None and (today - item_date).days > max_age_days:
            excluded.append({**it, "_excluded_posted_date": pd[:10], "_excluded_reason": "too_old"})
            continue
        if item_date == target:
            matched.append(it)
        else:
            excluded.append({**it, "_excluded_posted_date": pd[:10]})
    log.info(
        "날짜분류(직전영업일-%d, 기준=%s): 확정 %d / 날짜불명 %d / 제외 %d",
        days_back, target, len(matched), len(unknown), len(excluded),
    )
    return matched, unknown, excluded


def date_filter(items: list[dict], days_back: int = 1) -> tuple[list[dict], list[dict]]:
    """하위 호환: (확정, 날짜불명)만 반환."""
    matched, unknown, _excluded = partition_posted_dates(items, days_back)
    return matched, unknown


def assess_date_unknown_risk(item: dict) -> str:
    """날짜불명 공고의 오늘 누락 위험도: 낮음 / 중간 / 높음."""
    text = _notice_body_text(item)
    if any(kw in text for kw in APPLICATION_KEYWORDS):
        if item.get("link") and any(h in item["link"] for h in DETAIL_ENRICH_HOSTS):
            return "높음"
        return "중간"
    if item.get("deadline") or extract_application_period(text):
        return "중간"
    return "낮음"


def build_date_review_queue(unknown_items: list[dict]) -> list[dict]:
    """date_unknown → 수동검토 큐 (메일 대상과 분리 기록)."""
    queue: list[dict] = []
    for it in unknown_items:
        queue.append({
            **it,
            "date_unknown_risk": assess_date_unknown_risk(it),
            "review_reason": "posted_date_missing_or_unparsed",
        })
    return queue


# ══════════════════════════════════════════════════════════════════
# 그룹 필터
# ══════════════════════════════════════════════════════════════════

def classify_support_type(item: dict) -> list[str]:
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    matched = [t for t, kws in SUPPORT_TYPE_RULES.items() if any(k.lower() in text for k in kws)]
    return matched or ["그외"]


def _notice_body_text(item: dict) -> str:
    """마감(deadline) 필드 제외 본문 — 잘못된 기간 오염 방지."""
    return f"{item.get('title','')} {item.get('description','')} {item.get('author','')}".lower()


def _notice_text(item: dict) -> str:
    body = _notice_body_text(item)
    deadline = (item.get("deadline") or "").strip().lower()
    return f"{body} {deadline}".strip()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _find_keyword_aliases(text: str, aliases: list[tuple[str, list[str]]]) -> list[str]:
    matches: list[str] = []
    for label, keys in aliases:
        if any(key.lower() in text for key in keys):
            matches.append(label)
    return _unique(matches)


def classify_deadline_status(item: dict, today=None) -> str:
    today = today or datetime.now(KST).date()
    text = _notice_text(item)
    if any(term in text for term in OPEN_DEADLINE_TERMS):
        return "open"
    body_text = _notice_body_text(item)
    period = item.get("application_period") or extract_application_period(body_text)
    if period.get("end"):
        try:
            end_date = datetime.strptime(period["end"], "%Y-%m-%d").date()
            start_date = datetime.strptime(period.get("start", period["end"]), "%Y-%m-%d").date()
        except ValueError:
            end_date = start_date = None
        if end_date:
            if end_date < today:
                return "closed"
            if start_date and start_date > today:
                return "upcoming"
            return "open"
    # 신청기간 라벨이 없을 때만 본문 날짜 사용 (협약기간·deadline 필드 오인 방지)
    scrubbed = body_text
    for lbl in NON_APPLICATION_PERIOD_LABELS:
        scrubbed = re.sub(
            rf"{re.escape(lbl.lower())}\s*[:：]?\s*[^\nㅇ]+",
            "",
            scrubbed,
            flags=re.IGNORECASE,
        )
    dates = [parsed for _, parsed in _parse_date_candidates(scrubbed, today.year)]
    if not dates:
        raw_deadline = (item.get("deadline") or "").strip()
        if raw_deadline:
            dates = [parsed for _, parsed in _parse_date_candidates(raw_deadline, today.year)]
    if not dates:
        return "unknown"
    start_date, end_date = dates[0], dates[-1]
    if end_date < today:
        return "closed"
    if len(dates) >= 2 and start_date > today:
        return "upcoming"
    if ("접수 예정" in text or "접수예정" in text) and start_date > today:
        return "upcoming"
    return "open"


# ── 업력 / 지원금액 / 일반 지역 (그룹에 해당 설정이 있을 때만 적용) ──────────────
# 기존 인천 그룹 동작에는 영향이 없도록, business_years / min_support_amount /
# 비(非)인천 applicant_region_city 가 설정된 그룹에서만 아래 로직이 동작한다.

_GF_YEARS = r"(\d+(?:\.\d+)?)"
_GF_BIZ_CTX = "창업|업력|설립|개업|사업|업종|기업|법인|소상공인|중소기업|업체|예비창업"


def _years_value(num: str, unit: str) -> float:
    return float(num) / 12.0 if "개월" in unit else float(num)


def extract_business_year_requirement(text: str) -> dict | None:
    """공고가 요구하는 업력(창업·설립 경과연수) 범위를 추출한다.
    반환: {"min": float|None, "max": float|None} (신청 가능 업력 구간) 또는 None(언급 없음)."""
    if not text:
        return None
    t = unicodedata.normalize("NFKC", text).replace(",", "")
    if not re.search(r"창업|업력|설립|개업|사업\s*개시|업종\s*영위|예비창업", t):
        return None
    found_min: float | None = None
    found_max: float | None = None

    def upd_max(v: float) -> None:
        nonlocal found_max
        found_max = v if found_max is None else min(found_max, v)

    def upd_min(v: float) -> None:
        nonlocal found_min
        found_min = v if found_min is None else max(found_min, v)

    # 범위: "창업 3~7년", "업력 3년 ~ 7년"
    for m in re.finditer(rf"(?:창업|업력|설립)[^\n]{{0,10}}?{_GF_YEARS}\s*년?\s*[~∼\-]\s*{_GF_YEARS}\s*년", t):
        upd_min(float(m.group(1)))
        upd_max(float(m.group(2)))
    # 상한: "7년 이내 / 미만 / 이하" (업력 문맥일 때만)
    for m in re.finditer(rf"{_GF_YEARS}\s*(년|개월)\s*(?:이내|미만|이하)", t):
        if re.search(_GF_BIZ_CTX, t[max(0, m.start() - 15):m.end() + 10]):
            upd_max(_years_value(m.group(1), m.group(2)))
    # 하한: "3년 이상 / 초과" (업력 문맥일 때만)
    for m in re.finditer(rf"{_GF_YEARS}\s*(년|개월)\s*(?:이상|초과)", t):
        if re.search(_GF_BIZ_CTX, t[max(0, m.start() - 15):m.end() + 10]):
            upd_min(_years_value(m.group(1), m.group(2)))
    if found_min is None and found_max is None:
        return None
    return {"min": found_min, "max": found_max}


def business_years_status(item: dict, group: dict) -> str:
    """그룹 신청자 업력 구간과 공고 업력 요건의 호환성. eligible/not_eligible/unknown/n/a."""
    cfg = group.get("business_years")
    if not cfg:
        return "n/a"
    req = extract_business_year_requirement(_notice_text(item))
    if req is None:
        return "unknown"
    lo_raw = cfg.get("min_exclusive")
    if lo_raw is None:
        lo_raw = cfg.get("min", 0)
    lo = float(lo_raw if lo_raw is not None else 0)
    hi_raw = cfg.get("max_inclusive", cfg.get("max"))
    hi = float(hi_raw) if hi_raw is not None else float("inf")
    plo = req["min"] if req["min"] is not None else 0.0
    phi = req["max"] if req["max"] is not None else float("inf")
    # 신청자 업력 구간 (lo, hi] 와 공고 허용 구간 [plo, phi] 의 교집합 존재 여부
    return "eligible" if max(lo, plo) <= min(hi, phi) else "not_eligible"


def extract_support_amount(text: str) -> int | None:
    """공고 본문에서 최대 지원금액(원)을 추출한다. 없으면 None."""
    if not text:
        return None
    t = unicodedata.normalize("NFKC", text).replace(",", "").replace(" ", "")
    amounts: list[int] = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*억", t):
        amounts.append(int(float(m.group(1)) * 100_000_000))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*천만", t):
        amounts.append(int(float(m.group(1)) * 10_000_000))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*백만", t):
        amounts.append(int(float(m.group(1)) * 1_000_000))
    for m in re.finditer(r"(?<![천백.\d])(\d{1,6})\s*만\s*원?", t):
        amounts.append(int(m.group(1)) * 10_000)
    for m in re.finditer(r"(?<!\d)(\d{7,})\s*원", t):
        amounts.append(int(m.group(1)))
    return max(amounts) if amounts else None


def support_amount_status(item: dict, group: dict) -> str:
    """그룹 최소 지원금액 기준과 공고 금액 비교. eligible/not_eligible/unknown/n/a."""
    threshold = group.get("min_support_amount")
    if not threshold:
        return "n/a"
    amt = extract_support_amount(_notice_text(item))
    if amt is None:
        return "unknown"
    threshold = int(threshold)
    if group.get("min_support_amount_inclusive", False):
        return "eligible" if amt >= threshold else "not_eligible"
    return "eligible" if amt > threshold else "not_eligible"


def _short_region(city: str) -> str:
    """'경기도' → '경기' 처럼 광역 명칭을 KNOWN_REGIONS 단축형으로 변환."""
    for r in sorted(KNOWN_REGIONS, key=len, reverse=True):
        if r and r in city:
            return r
    return city


def classify_region_for_group(item: dict, group: dict) -> dict:
    """그룹 신청자 지역(광역+시·군) 기준 일반 지역 적합성 판정.
    인천 전용 classify_region 과 달리 임의 시·도/시·군을 지원한다."""
    text = _notice_text(item)
    raw_text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')} {item.get('region_field','')}"
    city = group.get("applicant_region_city", "")
    label = (group.get("applicant_region_label") or _short_region(city) or city).lower()
    district = group.get("applicant_region_district", "")
    districts = [d for d in ([district] + group.get("applicant_districts", [])) if d]

    def result(rs: str, ds: str, elig: list[str], excl: list[str]) -> dict:
        return {"region_status": rs, "district_status": ds,
                "eligible_regions": _unique(elig), "excluded_regions": _unique(excl)}

    for phrase in group.get("region_exclude_phrases", []):
        if phrase in raw_text:
            return result("not_eligible", "not_eligible", [], [district or city])
    for d in districts:
        short_d = d.replace("시", "").replace("군", "").replace("구", "")
        if f"{d} 제외" in raw_text or (short_d and f"{short_d} 제외" in raw_text):
            return result("not_eligible", "not_eligible", [], [d])

    target = _detect_target_regions(raw_text)
    detected = [r.lower() for r in (target.get("regions") or [])]
    nationwide = target.get("nationwide") or "전국" in text

    district_hits = []
    for d in districts:
        short_d = d.replace("시", "").replace("군", "").replace("구", "")
        if d.lower() in text or (short_d and short_d.lower() in text):
            district_hits.append(d)

    if nationwide:
        return result("eligible", "eligible", [city or label], [])
    if district_hits:
        return result("eligible", "eligible", district_hits, [])

    region_hit = bool(label) and (label in detected or label in text)
    other_regions = [r for r in detected if r != label]
    if region_hit:
        # 우리 광역 언급 + 특정 타 시·군 한정 아님 → 적합(시·군 미상이나 포함 우선)
        return result("eligible", "eligible", [city or label], [])
    if other_regions:
        return result("not_eligible", "not_eligible", [], other_regions)
    if any(r.lower() in text for r in KNOWN_REGIONS):
        return result("not_eligible", "not_eligible", [], [])
    return result("unknown", "unknown", [], [])


def classify_region(item: dict) -> dict:
    text = _notice_text(item)
    raw_text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')} {item.get('region_field','')}"
    eligible_regions: list[str] = []
    excluded_regions: list[str] = []
    region_status = "unknown"
    district_status = "unknown"

    if any(phrase in raw_text for phrase in REGION_EXCLUDE_PHRASES):
        return {
            "region_status": "not_eligible",
            "district_status": "not_eligible",
            "eligible_regions": [],
            "excluded_regions": [APPLICANT_REGION_CITY, APPLICANT_REGION_DISTRICT],
        }

    target = _detect_target_regions(raw_text)
    explicit_regions = list(target.get("regions") or [])
    if item.get("region_field"):
        explicit_regions.append(norm(item["region_field"]))
    explicit_regions = _unique(explicit_regions)
    other_only = [r for r in explicit_regions if "인천" not in r]
    if other_only and not any("인천" in r for r in explicit_regions):
        return {
            "region_status": "not_eligible",
            "district_status": "not_eligible",
            "eligible_regions": [],
            "excluded_regions": _unique(other_only),
        }

    if "남동구 제외" in text or "남동구 소재 기업 제외" in text:
        excluded_regions.append(APPLICANT_REGION_DISTRICT)
        return {
            "region_status": "not_eligible",
            "district_status": "not_eligible",
            "eligible_regions": [],
            "excluded_regions": excluded_regions,
        }

    mentioned_districts = [district for district in INCHEON_DISTRICTS if district in text]
    if APPLICANT_REGION_DISTRICT in mentioned_districts:
        eligible_regions.append(APPLICANT_REGION_DISTRICT)
        region_status = "eligible"
        district_status = "eligible"
    elif mentioned_districts:
        excluded_regions.extend(mentioned_districts)
        region_status = "not_eligible"
        district_status = "not_eligible"
    elif target.get("nationwide") or "전국" in text:
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif "인천광역시 소재" in text or "인천 소재" in text or "인천 지역" in text or "인천지역" in text:
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif "인천" in text:
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif any(region.lower() in text for region in KNOWN_REGIONS):
        region_status = "not_eligible"
        district_status = "not_eligible"

    return {
        "region_status": region_status,
        "district_status": district_status,
        "eligible_regions": _unique(eligible_regions),
        "excluded_regions": _unique(excluded_regions),
    }


def region_match(item: dict, group_regions: list[str]) -> bool:
    """그룹 지역 조건 매칭. 남동구 신청 불가 공고는 인천 그룹에서 제외."""
    if not group_regions:
        return True
    region_info = classify_region(item)
    if region_info["region_status"] == "not_eligible" or region_info["district_status"] == "not_eligible":
        return False
    text = _notice_text(item)
    g_regions = [r.lower() for r in group_regions]
    if any(r in text for r in g_regions):
        return True
    if "전국" in text:
        return True
    if region_info["region_status"] == "eligible":
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
        group = {**group}
        group.setdefault("exclude_keywords", [])
        group.setdefault("priority_keywords", [label for label, _ in PRIORITY_KEYWORD_ALIASES])
        group.setdefault("applicant_region_city", APPLICANT_REGION_CITY)
        group.setdefault("applicant_region_district", APPLICANT_REGION_DISTRICT)
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
    norm.setdefault("priority_keywords", [label for label, _ in PRIORITY_KEYWORD_ALIASES])
    norm.setdefault("applicant_region_city", APPLICANT_REGION_CITY)
    norm.setdefault("applicant_region_district", APPLICANT_REGION_DISTRICT)
    return norm


def support_match(item: dict, enabled_types: list[str]) -> bool:
    if not enabled_types or set(enabled_types) == set(ALL_SUPPORT_TYPES):
        return True
    types = classify_support_type(item)
    return any(t in enabled_types for t in types)


def evaluate_notice(item: dict, group: dict | None = None, today=None) -> dict:
    """공고 1건에 필터링 판정 필드를 부여한다."""
    g = _normalize_group(group or {})
    text = _notice_text(item)
    result = {**item}
    reason_codes: list[str] = []
    excluded_keywords: list[str] = []
    target_type = "unknown"
    notice_type = "unknown"

    matched_keywords = _find_keyword_aliases(text, GENERAL_INCLUDE_KEYWORD_ALIASES)
    priority_keywords = _find_keyword_aliases(text, PRIORITY_KEYWORD_ALIASES)
    factory_keywords = _find_keyword_aliases(text, FACTORY_KEYWORD_ALIASES)
    matched_keywords = _unique(matched_keywords + factory_keywords)
    factory_required = any(term in text for term in FACTORY_REQUIRED_TERMS)
    factory_condition = bool(factory_keywords)
    service_hits = [kw for kw in GENERAL_SERVICE_EXCLUDE_KEYWORDS if kw in text]
    application_like = any(kw in text for kw in APPLICATION_KEYWORDS)
    smart_info = any(kw in priority_keywords for kw in ["스마트공장", "스마트팩토리", "제조DX", "공정개선", "공정자동화", "자동화", "제조혁신"])

    for code, rule_notice_type, rule_target_type, keywords in EXCLUSION_RULES:
        hits = [kw for kw in keywords if kw in text]
        if hits:
            reason_codes.append(code)
            excluded_keywords.extend(hits)
            if notice_type == "unknown":
                if code == "GUIDELINE_OR_MANUAL" and any("매뉴얼" in hit for hit in hits):
                    notice_type = "manual"
                elif code == "GUIDELINE_OR_MANUAL" and any("부정수급" in hit for hit in hits):
                    notice_type = "admin_notice"
                else:
                    notice_type = rule_notice_type
            if rule_target_type != "unknown":
                target_type = rule_target_type

    if service_hits:
        excluded_keywords.extend(service_hits)
        if "설명회" in service_hits:
            reason_codes.append("INFO_SESSION")
            notice_type = "info_session"
        elif not application_like or ("단독" in text and not priority_keywords):
            reason_codes.append("LOW_PRIORITY_SERVICE_KEYWORD")
            notice_type = "general_info"

    if smart_info and notice_type in {"education", "info_session", "general_info", "guideline", "manual"}:
        reason_codes.append("SMART_FACTORY_INFO_ONLY")

    if target_type == "unknown":
        if any(kw in text for kw in ["공급기업", "수행기관", "서비스 제공자"]):
            target_type = "supplier"
        elif any(kw in text for kw in ["기선정", "선정기업 대상", "협약", "정산", "결과보고"]):
            target_type = "selected_company"
        elif any(kw in text for kw in ["수요기업", "참여기업", "중소기업", "소상공인", "제조기업", "신청 기업"]):
            target_type = "demand_company"

    if notice_type == "unknown" and application_like:
        notice_type = "application_notice"
    elif notice_type == "unknown" and any(kw in text for kw in ["일반 안내", "안내"]):
        notice_type = "general_info"

    deadline_status = classify_deadline_status(item, today)
    if deadline_status == "closed":
        reason_codes.append("CLOSED_DEADLINE")
    elif deadline_status == "unknown":
        reason_codes.append("MISSING_APPLICATION_PERIOD")

    applicant_city = g.get("applicant_region_city", APPLICANT_REGION_CITY)
    use_generic_region = bool(group) and applicant_city != APPLICANT_REGION_CITY
    region_info = classify_region_for_group(item, g) if use_generic_region else classify_region(item)
    if region_info["region_status"] == "not_eligible":
        reason_codes.append("REGION_NOT_ELIGIBLE")
    if region_info["district_status"] == "not_eligible":
        reason_codes.append("DISTRICT_NOT_ELIGIBLE")
    if region_info["region_status"] == "unknown" or region_info["district_status"] == "unknown":
        reason_codes.append("LOW_CONFIDENCE")
    if not use_generic_region and "산업단지" in text and "입주기업" in text and APPLICANT_REGION_DISTRICT not in text:
        reason_codes.append("ONLY_SPECIFIC_INDUSTRIAL_COMPLEX")

    always_srcs = [s.lower() for s in g.get("source_always_include", [])]
    src = (item.get("source", "") + " " + item.get("author", "")).lower()
    source_bypass = always_srcs and any(s in src for s in always_srcs)
    req_regions = g.get("required_conditions", {}).get("regions", [])
    if group is not None and not source_bypass:
        region_ok = (region_info["region_status"] == "eligible") if use_generic_region else region_match(item, req_regions)
        if not region_ok:
            reason_codes.append("REGION_NOT_ELIGIBLE")

    excl_kws = [k.lower() for k in g.get("exclude_keywords", []) if k.strip()]
    group_excluded = [k for k in excl_kws if k in text]
    if group_excluded:
        reason_codes.append("NOT_GRANT_NOTICE")
        excluded_keywords.extend(group_excluded)

    or_kws = [k.lower() for k in g.get("or_keywords", []) if k.strip()]
    and_groups = [[k.lower() for k in ag if k.strip()] for ag in g.get("and_keyword_groups", []) if ag]
    group_keyword_pass = True
    if group is not None and not source_bypass and (or_kws or and_groups):
        group_keyword_pass = any(k in text for k in or_kws) or any(all(k in text for k in ag) for ag in and_groups)
        if not group_keyword_pass:
            reason_codes.append("INDUSTRY_NOT_MATCHED")

    if group is not None and not support_match(item, g.get("support_types", ALL_SUPPORT_TYPES)):
        reason_codes.append("INDUSTRY_NOT_MATCHED")

    if not application_like and not priority_keywords:
        reason_codes.append("NOT_GRANT_NOTICE")

    biz_years_status = business_years_status(item, g) if group is not None else "n/a"
    amount_status = support_amount_status(item, g) if group is not None else "n/a"
    if biz_years_status == "not_eligible":
        reason_codes.append("BUSINESS_YEARS_NOT_ELIGIBLE")
    if amount_status == "not_eligible":
        reason_codes.append("AMOUNT_TOO_LOW")

    relevance_score = 0
    relevance_score += len(set(matched_keywords)) * 2
    relevance_score += len(set(priority_keywords)) * 10
    relevance_score += 5 if application_like else 0
    relevance_score += 4 if factory_condition else 0
    if service_hits and not application_like:
        relevance_score -= 6
    if reason_codes:
        relevance_score -= 10

    reason_codes = _unique(reason_codes)
    excluded_keywords = _unique(excluded_keywords)
    region_status = region_info["region_status"]
    district_status = region_info["district_status"]
    hard_reasons = set(reason_codes) - {"FACTORY_REQUIRED_BUT_UNKNOWN"}
    is_relevant = (
        not hard_reasons
        and deadline_status in {"open", "upcoming"}
        and region_status == "eligible"
        and district_status == "eligible"
        and application_like
        and group_keyword_pass
    )
    review_needed = (
        not is_relevant
        and bool(priority_keywords)
        and not (set(reason_codes) & {
            "GUIDELINE_OR_MANUAL", "EDUCATION_ONLY", "INFO_SESSION", "SUPPLIER_ONLY",
            "SELECTED_COMPANY_ONLY", "REGION_NOT_ELIGIBLE", "DISTRICT_NOT_ELIGIBLE",
            "CLOSED_DEADLINE", "SMART_FACTORY_INFO_ONLY",
        })
    )

    required_conditions = []
    notes = []
    if factory_required:
        required_conditions.append("공장보유 또는 제조시설 조건")
        notes.append("공장 보유 여부 확인 필요")
    if district_status == "unknown":
        notes.append("남동구 소재 기업 신청 가능 여부 확인 필요")
    if "ONLY_SPECIFIC_INDUSTRIAL_COMPLEX" in reason_codes:
        notes.append("특정 산업단지 입주 여부 확인 필요")
    if biz_years_status == "unknown":
        notes.append("업력 조건 확인 필요 — 공고에 업력 명시 없음")
    if amount_status == "unknown":
        notes.append("지원금액 조건 확인 필요 — 공고에 금액 명시 없음")

    result.update({
        "is_relevant": is_relevant,
        "target_type": target_type,
        "notice_type": notice_type,
        "deadline_status": deadline_status,
        "region_status": region_status,
        "industry_status": "matched" if group_keyword_pass or matched_keywords or priority_keywords else "not_matched",
        "matched_keywords": matched_keywords,
        "excluded_keywords": excluded_keywords,
        "priority_keyword": bool(priority_keywords),
        "priority_keywords": priority_keywords,
        "relevance_score": relevance_score,
        "exclude_reason_codes": reason_codes,
        "filter_confidence": "high" if is_relevant or reason_codes else "medium",
        "applicant_region_city": g.get("applicant_region_city", APPLICANT_REGION_CITY),
        "applicant_region_district": g.get("applicant_region_district", APPLICANT_REGION_DISTRICT),
        "eligible_regions": region_info["eligible_regions"],
        "excluded_regions": region_info["excluded_regions"],
        "district_status": district_status,
        "factory_condition": factory_condition,
        "factory_required": True if factory_required else False,
        "required_conditions": required_conditions,
        "notes": notes,
        "review_needed": review_needed,
        "business_years_status": biz_years_status,
        "support_amount_status": amount_status,
        "_types": classify_support_type(item),
    })
    return result


def _notice_sort_key(item: dict) -> tuple[int, int, int]:
    return (
        0 if item.get("priority_keyword") else 1,
        -int(item.get("relevance_score", 0)),
        0 if item.get("deadline_status") == "open" else 1,
    )


def filter_for_group_with_diagnostics(items: list[dict], group: dict, today=None) -> dict:
    included: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []
    for item in items:
        evaluated = evaluate_notice(item, group, today)
        if evaluated.get("is_relevant"):
            included.append(evaluated)
        elif evaluated.get("review_needed"):
            review.append(evaluated)
        else:
            excluded.append(evaluated)
    included.sort(key=_notice_sort_key)
    review.sort(key=_notice_sort_key)
    excluded.sort(key=lambda it: (",".join(it.get("exclude_reason_codes", [])), it.get("title", "")))
    return {"included": included, "review": review, "excluded": excluded}


def filter_for_group(items: list[dict], group: dict) -> list[dict]:
    """그룹별 최종 추천 공고만 반환한다."""
    diagnostics = filter_for_group_with_diagnostics(items, group)
    result = diagnostics["included"]
    log.info("그룹 '%s' 필터: %d → %d건", group.get("name"), len(items), len(result))
    return result


def refine_included_by_company(
    included: list[dict], group: dict, settings: dict, companies_by_id: dict,
) -> tuple[list[dict], list[dict]]:
    """evaluate_notice 통과분(included)을 그룹에 연결된 기업 프로필로 2차 정밀 컷오프.

    그룹의 'company_id' 가 companies.json 의 기업과 연결되고
    settings.company_match_enabled 가 true 일 때만 적용한다.
    적용 시 기업 match_threshold 이상만 통과(점수 내림차순 정렬), 미달은 강등 목록으로 반환.
    비활성/미연결/프로필 부재 → (included 원본, []) 그대로 (하위호환).
    """
    if not (settings.get("company_match_enabled") and _CM_OK):
        return included, []
    cid = group.get("company_id")
    company = companies_by_id.get(cid) if cid else None
    if not company:
        return included, []
    result = _match_for_company(included, company)
    return result["matched"], result["rejected"]



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
            dl = resolve_item_deadline(it)
            lines += [f"▸ {it['title']}",
                      f"  기관: {it['author'] or '미기재'} | 마감: {dl or '미기재'}"
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
    items = sorted(items, key=_notice_sort_key)
    imminent = [it for it in items if is_imminent(it.get("deadline", ""))]
    if imminent:
        lines += ["⚠️ 마감 임박 (7일 이내)"]
        for it in imminent:
            lines.append(f"- {it['title']} | 마감: {it['deadline']}")
        lines.append("")
    sections = [
        ("1. 우선 추천 공고", [it for it in items if it.get("priority_keyword")]),
        ("2. 일반 추천 공고", [it for it in items if not it.get("priority_keyword")]),
    ]
    for section_title, section_items in sections:
        if not section_items:
            continue
        lines.append(section_title)
        for it in section_items:
            region_label = _region_label(it)
            factory_label = _factory_label(it)
            smart_label = _smart_relevance_label(it)
            matched = ", ".join(it.get("matched_keywords", [])) or "미기재"
            priority = ", ".join(it.get("priority_keywords", [])) or "없음"
            notes = " / ".join(it.get("notes", [])) or "없음"
            lines += ["━━━━━━━━━━━━━━━━━━",
                      f"📌 {it['title']}",
                      f"• 지원유형: {' · '.join(it.get('_types', ['미분류']))}",
                      f"• 지원기관: {it['author'] or '미기재'}",
                      f"• 지원내용: {it['description'] or '미기재'}",
                      f"• 신청마감: {resolve_item_deadline(it) or '미기재'} ({it.get('deadline_status', 'unknown')})",
                      f"• 지역 적합성: {region_label}",
                      f"• 공장 조건: {factory_label}",
                      f"• 스마트공장 관련성: {smart_label}",
                      f"• 매칭 키워드: {matched}",
                      f"• 우선 키워드: {priority}",
                      f"• 확인 메모: {notes}",
                      f"• 등록일: {it.get('posted_date') or '날짜불명'}",
                      f"• 출처: {it['source']}",
                      f"• 🔗 {it['link'] or '미기재'}",
                      "━━━━━━━━━━━━━━━━━━"]
        lines.append("")
    return "\n".join(lines).strip()


def _region_label(item: dict) -> str:
    district = item.get("applicant_region_district") or APPLICANT_REGION_DISTRICT
    city = item.get("applicant_region_city") or APPLICANT_REGION_CITY
    is_default = city == APPLICANT_REGION_CITY
    if item.get("district_status") == "not_eligible":
        return "남동구 불가" if is_default else f"{district} 불가"
    if item.get("region_status") == "eligible" and district in item.get("eligible_regions", []):
        return "남동구 가능" if is_default else f"{district} 가능"
    if item.get("region_status") == "eligible":
        return "인천 전체" if is_default else f"{city} 전체"
    return "확인 필요"


def _factory_label(item: dict) -> str:
    if item.get("factory_required") is True:
        return "공장보유 필요"
    if item.get("factory_condition"):
        return "공장보유 우대"
    if item.get("factory_required") == "unknown":
        return "확인 필요"
    return "해당 없음"


def _smart_relevance_label(item: dict) -> str:
    smart_terms = {"스마트", "스마트공장", "스마트팩토리", "제조DX", "공정개선", "공정자동화", "자동화", "제조혁신"}
    matched = set(item.get("matched_keywords", [])) | set(item.get("priority_keywords", []))
    if matched & smart_terms:
        return "높음"
    if "공장" in matched or item.get("factory_condition"):
        return "보통"
    return "낮음"


def render_excluded_summary(items: list[dict], limit: int = 30) -> str:
    if not items:
        return ""
    lines = ["| 공고명 | 제외 사유 코드 | 제외 판단 근거 |", "|---|---|---|"]
    for it in items[:limit]:
        title = str(it.get("title", "")).replace("|", "/")
        codes = ", ".join(it.get("exclude_reason_codes", [])) or "LOW_CONFIDENCE"
        basis_parts = []
        if it.get("excluded_keywords"):
            basis_parts.append("키워드: " + ", ".join(it.get("excluded_keywords", [])[:5]))
        if it.get("deadline_status") in {"closed", "unknown"}:
            basis_parts.append(f"접수기간: {it.get('deadline_status')}")
        if it.get("region_status") == "not_eligible" or it.get("district_status") == "not_eligible":
            basis_parts.append("지역/구 조건 불일치")
        if it.get("business_years_status") == "not_eligible":
            basis_parts.append("업력 조건 불일치")
        if it.get("support_amount_status") == "not_eligible":
            basis_parts.append("지원금액 기준 미달")
        basis = " / ".join(basis_parts) or "신청 가능성 낮음"
        lines.append(f"| {title} | {codes} | {basis} |")
    if len(items) > limit:
        lines.append(f"| 외 {len(items) - limit}건 | - | 표시 제한 |")
    return "\n".join(lines)


def claude_summarize(items: list[dict], group: dict) -> str:
    if not items: return ""
    limited = sorted(items, key=_notice_sort_key)[:MAX_FOR_CLAUDE]
    client  = Anthropic(api_key=ANTHROPIC_API_KEY)
    g           = _normalize_group(group)
    req_regions = g.get("required_conditions", {}).get("regions", [])
    stypes      = g.get("support_types", ALL_SUPPORT_TYPES)
    or_kws      = g.get("or_keywords", [])
    and_groups  = g.get("and_keyword_groups", [])
    items_txt = "\n\n".join(
        f"[{i+1}] [{' · '.join(it.get('_types', ['미분류']))}] [등록:{it.get('posted_date','날짜불명')}]\n"
        f"제목: {it['title']}\n기관: {it['author']}\n내용: {it['description']}\n"
        f"마감: {resolve_item_deadline(it)} ({it.get('deadline_status', 'unknown')})\n"
        f"지역 적합성: {_region_label(it)}\n공장 조건: {_factory_label(it)}\n"
        f"스마트공장 관련성: {_smart_relevance_label(it)}\n"
        f"매칭 키워드: {', '.join(it.get('matched_keywords', [])) or '미기재'}\n"
        f"우선 키워드: {', '.join(it.get('priority_keywords', [])) or '없음'}\n"
        f"점수: {it.get('relevance_score', 0)}\n출처: {it['source']}\n링크: {it['link']}"
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
• 공장 조건:
• 스마트공장 관련성:
• 매칭 키워드:
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
    if not _ALLOW_SMTP_SEND:
        checked = validate_recipients(recipients)
        log.info(
            "발송 생략 (allow_send=False): subject=%s recipients=%s",
            subject[:60], ", ".join(checked["masked"]) or "(없음)",
        )
        return
    for to in validate_recipients(recipients)["valid"]:
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
    global _ALLOW_SMTP_SEND, _ALLOW_PERSIST_SEEN
    _ALLOW_SMTP_SEND = allow_send
    _ALLOW_PERSIST_SEEN = persist_seen

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

    new_items = enrich_items(new_items)

    # ④ 날짜 필터 (직전 영업일)
    target_date = previous_business_day(now, days_back)
    date_str    = now.strftime("%m/%d")

    include_unknown = settings.get("include_date_unknown", False)
    date_matched: list = []
    date_unknown: list = []
    date_excluded: list = []
    date_review_queue: list = []
    if settings.get("date_filter_enabled", True):
        date_matched, date_unknown, date_excluded = partition_posted_dates(
            new_items, days_back, max_age_days=settings.get("max_posted_age_days"),
        )
        date_review_queue = build_date_review_queue(date_unknown)
        if include_unknown:
            filtered_new = date_matched + date_unknown
            log.info(
                "날짜필터 후 처리 대상: %d건 (확정 %d + 날짜불명 %d 메일포함, review %d건)",
                len(filtered_new), len(date_matched), len(date_unknown), len(date_review_queue),
            )
        else:
            filtered_new = date_matched
            log.info(
                "날짜필터 후 메일 대상: %d건 (확정만) / review queue: %d건 / 제외 %d건",
                len(filtered_new), len(date_review_queue), len(date_excluded),
            )
    else:
        filtered_new = new_items
        date_unknown = []
        date_excluded = []

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
            "date_review_queue": date_review_queue,
            "date_excluded_count": len(date_excluded),
            "mail_sent": False,
            "seen_ids_persisted": bool(persist_seen and _ALLOW_PERSIST_SEEN),
            "sent_groups": [],
            "preview_groups": [],
        }

    # ⑥ 그룹별 필터 + 발송
    # 기업 맞춤 정밀 매칭(2차 컷오프)용 기업 프로필 로드 (활성화 시에만)
    companies_by_id: dict = {}
    if settings.get("company_match_enabled") and _CM_OK:
        try:
            companies_by_id = {c["id"]: c for c in _load_companies()}
            log.info("기업 프로필 로드: %d개 (정밀 매칭 활성)", len(companies_by_id))
        except Exception as e:
            log.warning("기업 프로필 로드 실패 — 정밀 매칭 건너뜀: %s", e)

    sent_groups: list[dict] = []
    preview_groups: list[dict] = []
    for group in groups:
        diagnostics = filter_for_group_with_diagnostics(filtered_new, group)
        g_items = diagnostics["included"]
        review_items = diagnostics["review"]
        excluded_items = diagnostics["excluded"]
        # 2차 정밀 컷오프: 그룹에 연결된 기업 프로필 점수 미달은 검토로 강등
        g_items, _demoted = refine_included_by_company(g_items, group, settings, companies_by_id)
        if _demoted:
            review_items = review_items + _demoted
            log.info("그룹 '%s' 기업매칭 컷오프: %d건 → 검토 강등", group.get("name"), len(_demoted))
        if not allow_send:
            preview_groups.append({
                "name": group.get("name"),
                "priority_items": sum(1 for it in g_items if it.get("priority_keyword")),
                "matched_items": len(g_items),
                "review_items": len(review_items),
                "excluded_items": len(excluded_items),
                "sample_titles": [it.get("title") for it in g_items[:5]],
                "review_titles": [it.get("title") for it in review_items[:5]],
                "excluded_summary": render_excluded_summary(excluded_items),
            })
        if not g_items:
            log.info("그룹 '%s': 조건 매칭 공고 없음", group.get("name"))
            continue
        sent_groups.append({
            "name": group.get("name"),
            "matched_items": len(g_items),
            "priority_items": sum(1 for it in g_items if it.get("priority_keyword")),
            "review_items": len(review_items),
            "excluded_items": len(excluded_items) if not allow_send else 0,
        })
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

    # ⑦ seen_ids 업데이트 (date_unknown도 포함 — 날짜불명 공고 재발송 방지)
    if persist_seen:
        seen_ids.update(it["id"] for it in deduped)
        seen_ids.update(it["id"] for it in date_unknown if it.get("id"))
        save_seen_ids(seen_ids)
    log.info("=== 완료 ===")
    # 실제 발송분(기업 정밀 컷오프 반영)과 일치하도록 sent_groups 집계 사용
    final_mail_count = sum(g.get("matched_items", 0) for g in sent_groups)
    return {
        "ok": True,
        "mode": mode,
        "collected": len(all_items),
        "deduped": len(deduped),
        "dedup_removed": dedup_removed,
        "new_items": len(new_items),
        "filtered_items": len(filtered_new),
        "date_matched_count": len(date_matched) if settings.get("date_filter_enabled", True) else len(filtered_new),
        "date_unknown_items": len(date_unknown),
        "date_review_queue": date_review_queue,
        "date_review_queue_count": len(date_review_queue),
        "date_excluded_count": len(date_excluded),
        "final_mail_target_count": final_mail_count,
        "mail_sent": bool(allow_send and _ALLOW_SMTP_SEND),
        "seen_ids_persisted": bool(persist_seen and _ALLOW_PERSIST_SEEN),
        "sent_groups": sent_groups,
        "preview_groups": preview_groups,
    }


def main() -> None:
    execute_monitor(allow_send=True, include_raw_all=True, persist_seen=True)


def _write_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "/") for c in row) + " |")
    return "\n".join(lines)


def write_coverage_report(
    rows: list[dict],
    path: Path | None = None,
    *,
    run_at: datetime | None = None,
) -> Path:
    run_at = run_at or datetime.now(KST)
    path = path or (BASE_DIR / "logs" / "site_collection_coverage_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "사이트", "collector", "URL", "수집", "건수", "날짜파싱", "date_unknown",
        "오늘기준", "누락위험", "오류",
    ]
    table_rows = []
    for r in rows:
        table_rows.append([
            r.get("site_name", ""),
            r.get("collector_type", ""),
            (r.get("url", "") or "")[:50],
            "OK" if r.get("fetch_success") else "FAIL",
            r.get("item_count", 0),
            r.get("posted_parsed_count", 0),
            r.get("date_unknown_count", 0),
            r.get("today_target_count", 0),
            r.get("missing_risk", ""),
            r.get("fetch_error", "")[:40],
        ])
    body = (
        f"# 사이트별 수집 커버리지\n\n"
        f"- 생성: {run_at.strftime('%Y-%m-%d %H:%M KST')}\n"
        f"- collector 파일: `{COLLECTOR_FILE}`\n\n"
        + _write_markdown_table(headers, table_rows)
        + "\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def write_today_missing_risk_report(
    result: dict,
    path: Path | None = None,
    *,
    run_at: datetime | None = None,
) -> Path:
    run_at = run_at or datetime.now(KST)
    path = path or (BASE_DIR / "logs" / "today_notice_missing_risk_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    queue = result.get("date_review_queue") or []
    high = [it for it in queue if it.get("date_unknown_risk") == "높음"]
    lines = [
        "# 오늘 공고 누락 위험 보고",
        "",
        f"- 생성: {run_at.strftime('%Y-%m-%d %H:%M KST')}",
        f"- 직전영업일 확정: {result.get('date_matched_count', 0)}건",
        f"- date_unknown (review queue): {result.get('date_review_queue_count', 0)}건",
        f"- 날짜 제외(전일·기타): {result.get('date_excluded_count', 0)}건",
        f"- include_date_unknown: 설정값에 따름",
        "",
        "## 위험도 높음 (수동 확인 권장)",
        "",
    ]
    if not high:
        lines.append("(없음)")
    else:
        for it in high[:50]:
            lines.append(f"- [{it.get('date_unknown_risk')}] {it.get('title', '')[:80]} ({it.get('source', '')})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_review_queue_report(
    queue: list[dict],
    path: Path | None = None,
    *,
    run_at: datetime | None = None,
) -> Path:
    run_at = run_at or datetime.now(KST)
    stamp = run_at.strftime("%Y%m%d")
    path = path or (BASE_DIR / "logs" / f"review_queue_{stamp}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Review queue — {run_at.strftime('%Y-%m-%d %H:%M KST')}",
        "",
        "posted_date가 없거나 파싱되지 않은 공고입니다. 메일 설정에 따라 발송 대상에서 빠질 수 있습니다.",
        "",
    ]
    if not queue:
        lines.append("(항목 없음)")
    else:
        for it in queue:
            lines.append(
                f"- **{it.get('date_unknown_risk', '?')}** | {it.get('title', '')[:100]} | "
                f"{it.get('source', '')} | {it.get('link', '')[:80]}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_dry_run(
    *,
    write_reports: bool = True,
    fetch_coverage: bool = True,
) -> dict:
    """실제 발송·seen_ids 저장 없이 전체 파이프라인 검증."""
    os.environ["MONITOR_NO_PERSIST_SEEN"] = "1"
    seen_before = SEEN_IDS_PATH.stat().st_mtime if SEEN_IDS_PATH.exists() else None

    coverage_rows: list[dict] = []
    if fetch_coverage:
        all_sites = load_json(SITES_PATH, [])
        coverage_rows = fetch_site_coverage(all_sites)

    result = execute_monitor(allow_send=False, include_raw_all=False, persist_seen=False)
    result["coverage"] = coverage_rows
    result["recipient_audit"] = {
        g.get("name"): validate_recipients(g.get("recipients", []))
        for g in load_groups()
    }
    settings = load_settings()
    result["recipient_audit"]["raw_all"] = validate_recipients(
        settings.get("raw_all_recipients", []),
    )

    seen_after = SEEN_IDS_PATH.stat().st_mtime if SEEN_IDS_PATH.exists() else None
    result["seen_ids_file_changed"] = seen_before != seen_after

    if write_reports:
        write_coverage_report(coverage_rows)
        write_today_missing_risk_report(result)
        write_review_queue_report(result.get("date_review_queue") or [])

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="수출·지원사업 모니터")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="발송·seen_ids 저장 없이 preview 및 logs/ 보고서 생성",
    )
    parser.add_argument(
        "--skip-coverage-fetch",
        action="store_true",
        help="dry-run 시 사이트별 순차 수집 생략(네트워크 절약)",
    )
    args = parser.parse_args()
    try:
        if args.dry_run:
            summary = run_dry_run(fetch_coverage=not args.skip_coverage_fetch)
            log.info(
                "dry-run 완료: 수집=%s 신규=%s review_queue=%s mail_sent=%s seen_changed=%s",
                summary.get("collected"),
                summary.get("new_items"),
                summary.get("date_review_queue_count"),
                summary.get("mail_sent"),
                summary.get("seen_ids_file_changed"),
            )
        else:
            main()
    except Exception as e:
        log.exception("치명적 오류: %s", e)
        raise

"""수출·지원사업 모니터링 에이전트 v6
기능: 수집 → 중복제거(주관기관 우선) → 날짜필터(D-1) → 그룹별 조건필터 → Claude요약 → 발송
설정: config/sites.json / config/groups.json / config/settings.json / var/state/seen_ids.json
"""
from __future__ import annotations

import hashlib, html, imaplib, json, logging, os, re, smtplib, ssl, threading, time, unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, quote, urlsplit

import httpx
from bs4 import BeautifulSoup

# ── 기업 맞춤 정밀 매칭(2차 컷오프) — 선택적 ────────────────────────────────────
# evaluate_notice(1차 필터) 통과분에 대해 기업 프로필(companies.json) 점수로
# 정밀 컷오프. 모듈/파일이 없거나 비활성이면 기존 동작 그대로(하위호환).
try:
    from mail_core.matching.company_match import (
        load_companies as _load_companies,
        match_for_company as _match_for_company,
    )
    _CM_OK = True
except ImportError:
    _CM_OK = False

try:
    from mail_core.matching.scoring import score_and_filter as _score_and_filter
    _SCORE_OK = True
except ImportError:
    _SCORE_OK = False

from mail_core.delivery import outbox as delivery_outbox
from mail_core.delivery import state as delivery_state
from mail_core.operations import run_lock
from mail_core.paths import CONFIG_DIR, LOGS_DIR, REPO_ROOT, STATE_DIR
from mail_core.security import net_guard, private_config
from mail_core.storage.seen_ids_prune import MAX_SEEN_IDS, prune_seen_ids
from mail_core.storage.state_store import atomic_write_json, load_json_with_recovery

BASE_DIR = REPO_ROOT

try:
    from mail_core.storage.raw_store import RawStore as _RawStore
except ImportError:
    _RawStore = None  # type: ignore[misc, assignment]

_RAW_STORE: Any = None  # 실행 중 원문 저장 (execute_monitor 스코프)

# ── .env 자동 로딩 (단독 실행 시 환경변수 주입) ──────────────────────────────
# monitor.py 를 직접 실행하면 .env / .env.shared 의 키(BIZINFO_API_KEY 등)를
# 환경변수로 주입한다. load_dotenv 는 override=False 가 기본이라, 이미 설정된
# 환경변수(스케줄러/상위 프로세스 주입분)는 덮어쓰지 않는다(멱등·무해).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")                # 로컬 전용 키
    load_dotenv(BASE_DIR.parent / ".env.shared")  # 공통 키(BIZINFO_API_KEY 등)
except ImportError:
    pass

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
# 선택: 공공데이터포털(data.go.kr) 기업마당 지원사업정보 서비스키.
#   bizinfo.go.kr 직결 API 가 GitHub Actions 러너 IP 에서 WAF/지역차단(timeout)될 때의
#   영구 폴백 경로. 값이 있으면 직결 실패 시 data.go.kr 로 재시도한다(없으면 폴백 비활성).
DATA_GO_KR_KEY     = os.environ.get("DATA_GO_KR_KEY", "").strip()
ANTHROPIC_API_KEY  = _require_env("ANTHROPIC_API_KEY")
GMAIL_ADDRESS      = _require_env("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = _require_env("GMAIL_APP_PASSWORD")

# ── 경로 ─────────────────────────────────────────────────────────────────────
SITES_PATH    = CONFIG_DIR / "sites.json"
GROUPS_PATH   = CONFIG_DIR / "groups.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
SEEN_IDS_PATH = STATE_DIR / "seen_ids.json"
NOTICE_VERSIONS_PATH = STATE_DIR / "notice_versions.json"
# (기준일·그룹·수신자) 단위 발송 멱등 상태 — 크래시/부분실패 후 재실행 시 중복발송 방지.
DELIVERY_STATE_PATH = STATE_DIR / "delivery_state.json"

# ── 상수 ─────────────────────────────────────────────────────────────────────
KST            = timezone(timedelta(hours=9))
MAX_FOR_CLAUDE = 15
COLLECTOR_FILE = "monitor.py"
_HTTP_RETRY_BACKOFF = 1.0  # 초 단위. 재시도 간 대기(선형 백오프). 테스트는 이 값을 낮춰 즉시 실행.
_HTTP_RETRIES = 1          # _soup 네트워크/타임아웃 일시적 실패 재시도 횟수(4xx/5xx는 재시도 안 함).
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_ALLOW_SMTP_SEND = False
_ALLOW_PERSIST_SEEN = True
# 발송 결과 카운터(이번 run) — 실패/0통 폰 알림용
_SEND_OK = 0
_SEND_FAIL = 0
_LAST_SEND_ERR = ""
# 초안(Gmail Drafts) 모드 — True 면 실제 발송(SMTP) 대신 IMAP APPEND 로 초안만 만든다.
# safe-by-default 유지: 사람이 Gmail 초안함에서 확인 후 직접 보낸다(자동 발송 아님).
_DRAFT_MODE = False
_DRAFT_OK = 0
_DRAFT_FAIL = 0
_LAST_DRAFT_ERR = ""
SEMAS_LOAN_SOURCE = "소진공 정책자금 온라인신청"
SEMAS_LOAN_TITLE = "소상공인 정책자금 공고"
HTTP_HEADERS   = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    # brotli(br) 미광고: httpx 런타임에 brotli 디코더가 없어 서버가 br 로 응답하면
    # 압축 바이트를 그대로 받아 파싱 0건이 됨(예: myfair). 디코딩 가능한 gzip/deflate 만 광고한다.
    "Accept-Encoding": "gzip, deflate",
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
                       "R&D", "사업화자금", "자금지원", "매칭지원", "보조",
                       # 표시 완성도 보강(field 헌터 발굴, 기존 버킷 확장=게이트 중립): 전시·수출·판로·융자·도입지원
                       "전시회", "박람회", "엑스포", "출품", "기획전", "수출지원", "판로개척", "판로지원",
                       "해외바이어", "신용대출", "융자", "도입지원"],
    "컨설팅·교육·상담": ["컨설팅", "교육", "상담", "멘토링", "코칭", "역량강화",
                         "인력양성", "훈련", "세미나", "워크숍", "설명회",
                         "기술지원단", "기술지원", "기술닥터"],
}
ALL_SUPPORT_TYPES = list(SUPPORT_TYPE_RULES.keys()) + ["그외"]

# K-Startup 상세 '지원분야'(공식 카테고리=권위값) → 우리 지원유형 버킷 매핑.
# 제목 키워드 추측이 놓치는 '사업화/정책자금/융자' 등을 지원금/바우처로 정확화하고,
# '멘토링·컨설팅·교육'은 컨설팅으로 확정한다. 키들은 소문자 비교(한글은 영향 없음).
# '그외'로 가는 분야(시설·행사·글로벌 등)는 매핑하지 않는다(기본값과 동일 → 잡음 방지).
KSTARTUP_FIELD_TO_TYPE = {
    "사업화": "지원금/바우처", "정책자금": "지원금/바우처", "융자": "지원금/바우처",
    "보증": "지원금/바우처", "기술개발": "지원금/바우처", "r&d": "지원금/바우처",
    "팁스": "지원금/바우처", "tips": "지원금/바우처",
    "수출": "지원금/바우처", "글로벌": "지원금/바우처",
    "투자": "투자",
    "멘토링": "컨설팅·교육·상담", "컨설팅": "컨설팅·교육·상담", "교육": "컨설팅·교육·상담",
}

# 지역 키워드 (전국 판별용)
KNOWN_REGIONS = {
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "충청", "전라", "경상", "수도권", "호남", "영남",
}

# ── K-Startup 상세 구조화 필드(p.tit/p.txt 라벨) → item 전용 키 매핑 ──────
# 본문(.view_cont 등) 셀렉터가 현행 K-Startup 페이지에서 비어, 업력/대상/지역 등
# 핵심 신호가 통째로 누락됐다. 라벨쌍에서 직접 거둔다.
# ★숫자(년/만세)가 든 값(창업업력·대상연령)은 description/body 에 합치지 않는다 —
#   extract_business_year_requirement 가 '1년미만,…,10년미만' 멀티셀렉트를 max=1 로
#   잘못 접어 정당공고를 대량 누락시키기 때문(전용 매퍼가 따로 해석).
KSTARTUP_DETAIL_LABELS = {
    "지역": "region_field",
    "신청기간": "application_period_text",
    "창업업력": "business_age_text",
    "대상": "target_field",
    "대상연령": "target_age_field",
    "주관기관명": "organizer_field",
    "제외대상": "exclude_target_field",
    "지원분야": "support_field",
}

# 기업마당 상세(selectSIIA200Detail 등) — span.s_title + div.txt 라벨쌍
BIZINFO_DETAIL_LABELS = {
    "지원지역": "region_field",
    "지역": "region_field",
    "신청기간": "application_period_text",
    "사업개요": "body",
    "지원대상": "target_field",
    "소관부처·지자체": "organizer_field",
}

# 비경기 '광역권' 토큰(강원권·충청권·호남권 등). 수도권/경기권/서울권은 경기를
# 포함·인접하므로 차단 대상에서 제외한다(recall 보호).
_NON_GG_KWON_RE = re.compile(
    r"(?:강원|충청|충북|충남|호남|전북|전남|영남|경북|경남|제주|부산|대구|광주|대전|울산)\s*권"
)
# 기초자치단체/지역재단 주관 신호(강한 지역귀속). 비경기 지역명과 함께 있을 때만
# 타지역 한정으로 본다.
_LOCAL_GOV_ORG_RE = re.compile(r"구청|시청|군청|도청|문화재단|문화관광재단")
# 지역명이 들어가도 전국사업을 운영하는 기관 — (B) 차단에서 제외(서울창조경제혁신센터
# 주관 KAMCO 등 전국 정당공고 보호).
_NATIONAL_SCOPE_ORG_RE = re.compile(
    r"창조경제혁신센터|테크노파크|산학협력단|대학교|대학원|진흥원|진흥공단|연구원|협회|진흥재단"
)
# 비경기 지역명(광역 + 서울 자치구 + 명확한 비경기 도시). ★경기 지역명은 절대
# 넣지 않는다 — 넣으면 정당한 경기 공고를 누락(recall 위반)한다.
_NON_GG_LOCALITIES = (
    # ★'광주'는 경기도 광주시와 광주광역시가 충돌 → '광주광역'으로 좁혀 경기 광주시 보호.
    "서울", "인천", "부산", "대구", "광주광역", "대전", "울산", "세종",
    "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "종로", "용산", "성동", "광진", "동대문", "중랑", "성북", "강북", "도봉",
    "노원", "은평", "서대문", "마포", "양천", "강서", "구로", "금천", "영등포",
    "동작", "관악", "서초", "강남", "송파", "강동",
)

# ── 타지역 override 일반화(전 그룹: 경기/서울/인천 …) ───────────────────
# 수도권 family: 권역(A) 차단에서 상호 제외(예: 인천 그룹에 '경기권/서울권/수도권'은
# 차단 안 함). ★(B) 기초자치 지역명에는 family 를 적용하지 않는다 — 적용하면 경기 그룹이
# 서울자치구(성북/동대문) 차단을 잃는다(검증으로 확인된 함정).
_METRO_FAMILY = {"서울", "인천", "경기", "수도권"}

# ── 신청자 '지역 한정' 강신호 vs 문의·운영 보일러플레이트 구분 ─────────────
# 충북공고 누출 원인: '충북지역 중소기업 대상'처럼 신청자를 타지역으로 한정한 공고가
# 본문 '문의: 서울특별시 …' 한 줄 때문에 서울 그룹에 적격으로 새어든다(2026-06-25).
# (1) 신청자-지역 한정 패턴: {광역}{소재/지역/도내/관내/내} {기업/소상공인/…}.
#     단순 지역명 언급(문의처 주소 등)과 달리 '그 지역 기업만 신청 가능'의 강한 신호.
_APPLICANT_REGION_TOKEN = (
    "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"
    "|충청북도|충청남도|전라북도|전라남도|경상북도|경상남도|강원특별자치도"
)
_APPLICANT_LOCATOR = r"(?:특별시|광역시|특별자치시|특별자치도|도)?\s*(?:지역|소재(?:지)?(?:를?\s*둔)?|관내|도내|시내|내|에\s*소재(?:한)?)"
_APPLICANT_NOUN = r"(?:중소기업|중견기업|소기업|창업기업|스타트업|소상공인|사업자|기업|업체|법인|소재\s*기업)"
_APPLICANT_RESTRICT_RE = re.compile(
    rf"(?P<r>{_APPLICANT_REGION_TOKEN})\s*{_APPLICANT_LOCATOR}\s*{_APPLICANT_NOUN}"
)
# ㆍ/·/및/, 로 이어진 다지역 나열 "서울ㆍ인천ㆍ강원 소재 중소기업" — 나열 전체가 신청자격 강신호.
# 단일 규칙(_APPLICANT_RESTRICT_RE)은 '소재' 바로 앞 광역만 잡아 앞쪽 나열(서울·인천)을 놓쳤음.
_REGION_LIST_SEP = r"(?:\s*(?:[ㆍ·・,、/]|및)\s*)"
_APPLICANT_RESTRICT_LIST_RE = re.compile(
    rf"(?P<list>(?:{_APPLICANT_REGION_TOKEN})(?:{_REGION_LIST_SEP}(?:{_APPLICANT_REGION_TOKEN}))+)"
    rf"\s*{_APPLICANT_LOCATOR}\s*{_APPLICANT_NOUN}"
)
_REGION_TOKEN_RE = re.compile(_APPLICANT_REGION_TOKEN)
# 인라인 다지역 나열 "서울·인천", "서울ㆍ인천ㆍ강원 권역" — interpunct(가운뎃점류)로 이어진 광역 2개+.
# 대괄호 밖 표기라 _title_region_tags·소재나열 정규식이 못 잡던 '권역 묶음' own 오차단을 막는다.
_INLINE_REGION_LIST_RE = re.compile(
    rf"(?:{_APPLICANT_REGION_TOKEN})(?:\s*[ㆍ·・•‧∙/]\s*(?:{_APPLICANT_REGION_TOKEN}))+"
)
# 광역 풀네임 → 약칭(restricted set 비교용)
_REGION_LONG_TO_SHORT = {
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "강원특별자치도": "강원",
}
# (2) 문의·운영 보일러플레이트 구간 — own 지역이 여기에만 있으면 신청자 신호로 보지 않음.
_CONTACT_SPAN_RE = re.compile(
    r"(?:문의|연락|접수처|담당자?|전화|이메일|메일|운영\s*사무국|사무국|콜센터|주관기관|운영기관|"
    r"접수\s*기관|소재지|☎|tel|fax)[^\n]*",
    flags=re.IGNORECASE,
)


def _applicant_restricted_regions(text: str) -> set[str]:
    """신청자를 특정 광역으로 한정하는 강신호('{광역}{소재/지역…} {기업…}')의 광역 약칭 집합."""
    if not text:
        return set()
    out: set[str] = set()
    # (a) 다지역 나열 "서울ㆍ인천ㆍ강원 소재 기업" — 나열된 광역 전부를 강신호로(대칭·recall).
    for mch in _APPLICANT_RESTRICT_LIST_RE.finditer(text):
        for r in _REGION_TOKEN_RE.findall(mch.group("list")):
            out.add(_REGION_LONG_TO_SHORT.get(r, r))
    # (b) 단일 "{광역} 소재 기업".
    for mch in _APPLICANT_RESTRICT_RE.finditer(text):
        r = mch.group("r")
        out.add(_REGION_LONG_TO_SHORT.get(r, r))
    return out


def _strip_contact_spans(text: str) -> str:
    """문의·운영 보일러플레이트 구간 제거 — 신청자 지역 신호만 남긴다."""
    return _CONTACT_SPAN_RE.sub(" ", text or "")
# 광역권 토큰(명명그룹). 매치된 광역이 own family 가 아니면 타지역 한정으로 본다.
_KWON_NAMED_RE = re.compile(
    r"(?P<r>강원|충청|충북|충남|호남|전북|전남|영남|경북|경남|제주|부산|대구|광주|대전|울산|서울|인천|경기|수도)\s*권"
)
# 전 지역명(광역 + 서울 자치구). own 지역명은 헬퍼가 런타임에 제외한다(★own 자치구는
# 풀네임 정확매칭만 — 인천 '동구→동' short-form 이 '동대문'을 substring 으로 삼키는 함정 방지).
_ALL_LOCALITIES = _NON_GG_LOCALITIES + ("경기",)

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
    # 사업화 직접지원(현금·제작비) — 최우선 추천 신호 (사용자 정책)
    ("사업화지원금", ["사업화지원금", "사업화 지원금", "사업화자금", "사업화 자금"]),
    ("시제품제작비", ["시제품제작비", "시제품 제작비", "시제품제작", "시제품 제작"]),
    ("사업화비용", ["사업화비용", "사업화 비용"]),
    ("지원금", ["지원금"]),
    ("직접지원", ["직접지원", "현금지원", "현금 지원"]),
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

# 메일 '우선 추천' 정렬에서 사업화 직접지원을 최상단으로 올린다.
FUND_PRIORITY_LABELS = frozenset({
    "사업화지원금", "시제품제작비", "사업화비용", "지원금", "직접지원",
})

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

# ※'입주기업'은 공장 신호가 아니다 — AI허브·창업보육센터 '입주기업 모집'에
#   '공장보유 필요'가 오표시되던 원인(2026-07-24). 산업단지 입주 판정은
#   ONLY_SPECIFIC_INDUSTRIAL_COMPLEX(산업단지+입주기업 동시 등장)가 따로 담당한다.
FACTORY_REQUIRED_TERMS = [
    "공장등록증", "제조시설", "생산시설", "제조업 영위", "공장 보유",
    "공장보유", "공장 임차", "공장임차", "임대공장",
]

APPLICATION_KEYWORDS = [
    "모집공고", "지원계획 공고", "참여기업 모집", "수요기업 모집", "신청접수",
    "지원사업 공고", "해외전시회", "박람회", "전시회", "수출상담회",
    "바이어 매칭", "마케팅 지원", "판로지원", "수출지원", "글로벌", "해외",
    "베트남", "동남아", "화장품", "뷰티", "k-beauty", "소상공인", "지원금",
    "혁신바우처", "혁신 바우처", "수출바우처", "수출 바우처", "스마트공장",
    "스마트팩토리", "공정개선", "공정자동화", "설비개선", "구축 지원사업",
    "공모", "참가신청",
]

GENERAL_SERVICE_EXCLUDE_KEYWORDS = ["설명회", "컨설팅지원"]

# ── 지자체 고시/공고 게시판의 '비지원 행정고지' 노이즈 ────────────────────────────
# 김포·남양주시청 등 일반 고시/공고 게시판은 주민등록·CCTV·입찰 등 지원사업과 무관한
# 행정고지를 함께 올린다. 원본전체 메일에서 이를 걸러낸다(그룹메일은 키워드로 이미 차단).
ADMIN_NOTICE_KEYWORDS = [
    "주민등록", "무단전출", "전출자", "행정예고", "행정 예고",
    "입찰공고", "입찰 공고", "낙찰", "개찰", "수의계약", "긴급입찰", "재입찰",
    "의견청취", "도시관리계획", "도시계획변경", "지적재조사", "지적공부",
    "공람공고", "공람 공고", "열람공고", "최고 공고", "최고공고",
    "발급 통지", "통지 반송", "반송 공고", "공시송달",
    "체납", "압류", "공매", "과태료", "명단 공개", "명단공개",
    "후보자등록", "위원 위촉", "위원 위촉 공고", "소집공고", "소집 공고",
    "교통통제", "도로명주소", "정비구역", "보상계획", "감정평가", "환지계획",
    "청문 공고", "공유재산", "매각공고", "대부공고", "cctv 설치", "방범용 cctv",
]
GRANT_SIGNAL_KEYWORDS = [
    "지원사업", "지원 사업", "지원금", "보조금", "바우처", "사업화", "사업 공고",
    "모집공고", "모집 공고", "참여기업", "수요기업", "공모", "융자", "정책자금",
    "창업", "육성", "r&d", "연구개발", "기술개발", "수출", "판로", "마케팅",
    # 컨설팅·멘토링은 GRANT 신호에서 제외 — 단독 안내가 application_like 로 통과하던 과출 방지.
    # (실지원 공고는 모집/신청/지원사업 등 다른 신호로 충분하다.)
    "인증지원", "시제품", "입주기업", "투자유치",
    "장려금", "지원 안내", "지원계획", "지원대상", "참가기업", "참가신청",
]


def is_admin_noise(item: dict) -> bool:
    """지자체 고시/공고 게시판에 섞이는 '비지원 행정고지'(주민등록·CCTV·입찰·행정예고 등)인지.
    행정 신호가 있고 지원사업 신호가 전혀 없을 때만 True. 지원 신호가 하나라도 있으면
    False(recall 보호) — 진짜 지원공고는 놓치지 않는다."""
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    if not any(k.lower() in text for k in ADMIN_NOTICE_KEYWORDS):
        return False
    if any(k.lower() in text for k in GRANT_SIGNAL_KEYWORDS):
        return False
    return True


# [원본전체] 보고 메일에서 뺄 잡공고 — 공지·결과발표·채용·입찰·총회 등 '지원 기회'가 아닌 게시물.
REPORT_JUNK_KEYWORDS = [
    "공지사항", "결과발표", "결과 발표", "선정결과", "선정 결과", "모집결과", "모집 결과",
    "합격자", "최종선정", "최종 선정", "평가결과", "채용공고", "직원채용", "신규채용",
    "입찰공고", "낙찰", "계약체결", "정기총회", "임시총회", "공청회", "성료", "개최결과",
    "후기", "보도자료", "휴관", "휴무", "시스템 점검", "점검 안내", "일정변경", "일정 변경",
    "연기 안내", "당첨자", "간담회 개최", "설명회 개최", "공지 안내", "운영 중단",
    "교육생 모집", "수강생 모집", "서포터즈", "체험단", "기자단", "홍보단", "자원봉사",
    # '모니터링단'은 REPORT_JUNK hard 제외에서 빼고 AMBIGUOUS_NOTICE(검토 분리)로 보낸다.
    "회원 모집", "평가위원", "심사위원", "멘토 모집", "운영위원", "강사 모집",
    "기획위원", "자문위원", "전문위원",
]


def is_report_junk(item: dict) -> bool:
    """[원본전체] 보고 메일용 잡공고 판정. 제목에 위 표현이 있으면 True(지원 기회 아님)."""
    title = str(item.get("title", ""))
    return any(j in title for j in REPORT_JUNK_KEYWORDS)


EXCLUSION_RULES = [
    ("GUIDELINE_OR_MANUAL", "guideline", "unknown", [
        "부정수급", "정부 지침", "관리지침", "운영지침", "지침 개정",
        "공동인증서", "공인인증서", "매뉴얼", "사용 안내", "유의사항", "시스템 이용 안내",
    ]),
    ("INFO_SESSION", "info_session", "unknown", [
        "설명회", "오리엔테이션", "사업설명회", "사전설명회", "투자유치설명회",
    ]),
    ("EDUCATION_ONLY", "education", "unknown", [
        "교육 일정", "교육일정", "분야별 교육", "선정기업 교육", "수요기업 교육", "공급기업 교육",
        "교육참여기업", "교육 참여기업", "교육생 모집", "수강생 모집", "교육과정 모집", "교육 과정 모집",
    ]),
    ("SUPPLIER_ONLY", "application_notice", "supplier", [
        "공급기업", "수행기관", "서비스 제공자", "컨설팅분야 수행", "수행 관련 안내", "공급기업 추가모집",
        "운영기관 모집", "운영기관 사업비", "수행기관 위탁비",
    ]),
    ("SELECTED_COMPANY_ONLY", "post_selection", "selected_company", [
        "선금신청", "정산", "협약", "결과보고", "중간점검", "기선정", "선정기업 대상",
    ]),
    # NOT_GRANT_NOTICE: 지원사업이 아닌 제도·요율·안내성 게시. soft/hard 분리는 _split_exclusion_hits.
    # 키워드 출처: var/state/notice_versions 제목 히스토리(공시송달 53·제도안내 2 등) + 기존 규칙.
    # 잡공고(결과·채용·총회 등)는 REPORT_JUNK, 행정고지는 ADMIN_NOISE 로 분리.
    ("NOT_GRANT_NOTICE", "general_info", "unknown", [
        "산재예방요율제", "보험료율", "제도 안내", "요율 변경", "요율변경",
        "수수료 안내", "수수료안내", "제도 개편", "제도개편", "규정 개정", "규정개정",
        "운영 안내", "이용 안내", "사이트 안내",
        "공시송달", "결정통지", "정보부존재", "과태료 전자고지", "전자고지 서비스",
        "대출 제도 안내", "온렌딩 대출",
    ]),
]

# 제목 앵커: '교육참여기업모집'처럼 공백 없이 붙어도 교육 모집으로 본다.
_EDUCATION_RECRUIT_TITLE_RE = re.compile(
    r"교육\s*참여\s*기업\s*모집|교육생\s*모집|수강생\s*모집|교육\s*과정\s*모집"
)

# 설명회가 '모집 본체'인 제목(설명회 참여기업 모집 등) → 본문 추천 제외·review 분리(hard 제외 아님).
_INFO_SESSION_AS_RECRUIT_RE = re.compile(
    r"(?:사업|투자\s*유치)?설명회\s*(?:개최\s*)?(?:참여자|참여기업|참가기업|참석자|참가)\s*모집|"
    r"설명회\s*참여기업\s*모집|"
    r"모집\s*설명회"
)
# 실모집 본체 + 부대 설명회(모집 및 설명회 / 설명회 일정 추가) → soft 통과 유지.
_INFO_SESSION_SECONDARY_RE = re.compile(
    r"모집\s*및\s*설명회|설명회\s*일정\s*(?:추가|안내)"
)

# 애매 비지원(부분일치로 hard 금지하되 본문 추천에서 분리해 review로 보냄).
_AMBIGUOUS_GRANT_OK = ("지원사업", "바우처", "지원금", "보조금", "사업화", "융자", "정책자금")

# ── 위원(개인 전문가) 위촉·모집 공고 제외 — 기업 지원사업이 아니다 ────────────────
# '기획위원(후보자) 모집공고'(경남TP, 2026-07-24 그룹메일 오발송 실사례) 같은 공고를
# 제목만 보고 거른다. 본문의 '평가위원회 심의를 거쳐' 등 우연 언급으로 진짜 공고를
# 막지 않도록 제목 앵커(title-only)로 보수적으로 판정한다(recall 원칙).
_COMMITTEE_TITLE_RE = re.compile(
    r"(?:기획|평가|심사|자문|운영|전문|선정)\s*위원(?:단|회)?"
    r"\s*(?:\([^)]*\)\s*)?(?:후보자?\s*)?(?:모집|위촉|공모)"
)

# ── [제목 앵커] 비공고 정적 페이지 제외 (2026-07-20, 사용자 O/X 피드백: '사전정보공표' ❌) ──
# 배경: 일부 소스의 리스트 셀렉터가 본문 게시판이 아니라 헤더/푸터/사이드 nav 의 <a> 를 통째로
#       긁어, 기관 소개·정보공개·약관 같은 '정적 페이지'가 공고로 발송됐다.
#
# ★설계 원칙 (이 repo 평생 원칙: 누락 제로(recall) > 정확도(precision))
#   1) EXCLUSION_RULES 에 넣지 않는다. 그쪽은 제목+본문을 합친 text 를 보므로, 본문에 우연히
#      그 단어가 있는 '진짜 공고'까지 함께 막혀 누락이 난다. 여기는 오직 제목·링크만 본다.
#   2) 부분포함(substring) 금지 — '제목 전체 완전일치'만 판정한다. 실측 반례:
#      '정보공개'→신용보증기금 「2026년 정보공개 고객 모니터링단」모집공고(진짜),
#      '채용'→74건 중 73건 진짜, '입찰'→26건 중 25건 진짜, '개인정보'→10건 전부 진짜.
#   3) 이중 안전장치 — 제목에 공고성 토큰(모집·공고·신청·접수·참가·선정·공모·지원사업)이
#      하나라도 있으면 목록에 있어도 절대 막지 않는다.
#   4) 스냅샷 9,406건 시뮬레이션에서 safe_to_block=true 로 확인된 문자열만 등재한다.
#      '정보공개'·'개인정보처리방침'·'지원사업공고'·'공지사항'은 진짜 공고 반례가 있어 제외.
#   5) 날짜 공란·URL 패턴은 판정 근거로 쓰지 않는다 — 양방향으로 실패한다(정크가 게시일을
#      갖고 있고, 반대로 날짜 없는 진짜 공고가 대량 존재).
#
# 끄기: 환경변수 MONITOR_NO_NONNOTICE_FILTER=1 (오차단 발견 시 즉시 무력화용)
NONNOTICE_FILTER_ENV = "MONITOR_NO_NONNOTICE_FILTER"

# 제목에 이 토큰이 하나라도 있으면 비공고 판정을 건너뛴다(이중 안전장치).
# ★'지원'·'설명회'는 적대적 반증에서 나온 보강 — 링크 도메인 룰만으로 막히던 경계 사례
#   ('중소기업 홍보영상 제작 지원(유튜브)' + youtube 링크)를 통과시킨다. 이 토큰들은 필터를
#   더 느슨하게만 만들어 recall 을 해칠 수 없고, 차단목록 중 '지원'을 품은 항목은
#   '지원/신청' 하나뿐이라 정크 차단력 손실도 없다.
NOTICE_SIGNAL_TOKENS = (
    "모집", "공고", "신청", "접수", "지원사업", "참가", "선정", "공모", "지원", "설명회",
)

# 제목 '완전일치' 차단 목록 — 각 항목이 그 정적 페이지의 명칭 '자체'인 경우만.
NON_NOTICE_TITLES = frozenset(_t.casefold() for _t in [
    # 정보공개 정적 페이지 (★사용자 O/X 피드백 실제 사례)
    "사전정보공표", "정보공개제도", "정보공개청구", "정보공개제도란",
    # 약관·방침
    "이용약관", "저작권정책", "영상정보처리기기방침", "고정형 영상정보처리기기운영관리 방침",
    # 기관 소개 메뉴
    "인사말", "연혁", "미션&비전", "기관소개", "조직구성", "조직 및 업무", "오시는길",
    # 사이트 공통 링크
    "회원가입", "로그인", "english", "사이트맵",
    # 고객지원 정적 페이지
    "faq", "ncs관련 faq", "고객의 소리", "홈페이지불편신고", "부패신고센터",
    # 경영공시 메뉴
    "통합공시", "자체공시", "사업실명제", "업무추진비", "징계현황", "주요계약현황",
    "기부금 수령 및 집행현황", "상품권 구매사용 현황", "공공데이터개방",
    # 게시판 목록 메뉴 (※부분포함 절대 금지 — '채용'·'입찰'은 대부분 진짜 공고다)
    "채용정보", "일자리정보", "입찰정보",
    # 자료실 메뉴
    "뉴스레터", "언론보도", "자료공간", "발간자료", "동향/분석자료", "kams now", "컨설팅 전문 정보",
    # 사업소개 메뉴 (공고성 토큰이 있는 '지원/신청'·'공모사업 안내'·'온라인 참가신청'은
    #   NOTICE_SIGNAL_TOKENS 가드에 먼저 걸려 실제로는 통과한다 — 의도된 recall 우선 동작)
    "사업안내", "지원/신청", "공모사업 안내", "온라인 참가신청",
    # 정부24 푸터 링크
    "누리집 안내지도", "복합인증관리", "보안센터", "인증등록/관리", "상담예약",
    "국민비서 구삐", "공공서비스 활용(open api)", "웹 접근성 품질인증 마크 획득",
    # 테이블 헤더·페이지네이션 오수집
    "번호", "새 카테고리", "날짜순", "[2]", "[ home ]",
    # 대표번호(링크가 tel: 이 아닌 경우 대비)
    "110", "1588-2188",
    # nav/배너 링크가 공고로 저장된 사례 (근본 해결은 해당 소스 셀렉터 수정)
    "oa", "직무 솔루션>", "k-스타트업", "단기수출보험(선적후)", "human rights watch",
    # 2026-08-04 실발송에서 확인된 게시판 카테고리 메뉴 (kovwa)
    "유관기관",
])

# 링크 스킴·도메인 기반 판정 (오탐 0 — 공고 상세가 tel:/SNS 일 수 없다)
NON_NOTICE_LINK_SCHEMES = ("tel:", "mailto:")
NON_NOTICE_LINK_DOMAINS = (
    "instagram.com", "x.com", "twitter.com", "facebook.com", "youtube.com",
)


def _normalize_title_key(title: Any) -> str:
    """제목 정규화 — 앞뒤 공백 제거 + 연속 공백 1칸 축약 + 대소문자 무시."""
    return " ".join(str(title or "").split()).casefold()


def non_notice_reason(item: dict) -> str:
    """공고가 아닌 정적/메뉴/외부링크 페이지면 근거 문자열, 아니면 "" 를 반환한다.

    제목(완전일치)과 링크(스킴·도메인)만 본다. 본문(description)은 절대 보지 않는다.
    """
    if os.environ.get(NONNOTICE_FILTER_ENV) == "1":
        return ""

    raw_title = str(item.get("title") or "")
    # ★이중 안전장치: 공고성 토큰이 하나라도 있으면 비공고로 판정하지 않는다.
    if any(tok in raw_title for tok in NOTICE_SIGNAL_TOKENS):
        return ""

    title_key = _normalize_title_key(raw_title)
    if title_key and title_key in NON_NOTICE_TITLES:
        return raw_title.strip()

    # 페이지네이션 링크를 공고로 오인한 경우 — 제목이 숫자뿐인 공고는 존재하지 않는다.
    # (2026-08-04 실발송: kovwa 목록의 페이지 번호 "1" 이 공고로 메일에 실렸다.)
    stripped_title = raw_title.strip()
    if stripped_title.isdigit() and len(stripped_title) <= 3:
        return f"페이지번호({stripped_title})"

    link = str(item.get("link") or "").strip()
    low = link.lower()
    if low.startswith(NON_NOTICE_LINK_SCHEMES):
        return low.split(":", 1)[0] + ":"
    host = urlsplit(low).netloc.split("@")[-1].split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    if host and host in NON_NOTICE_LINK_DOMAINS:
        return host
    # 사이트 대문(루트·index·main)은 공고 상세 페이지가 아니다.
    # 쿼리스트링이 있으면 상세일 수 있으므로 건드리지 않는다(recall 우선).
    parts = urlsplit(low)
    if host and not parts.query and not parts.fragment:
        path = parts.path.rstrip("/")
        if not path or re.fullmatch(r"/(?:index|main|home)(?:\.\w{2,5})?", path):
            return f"사이트 대문({host})"
    return ""


def ambiguous_notice_reason(item: dict) -> str:
    """hard 제외하기엔 반례가 있으나 본문 추천에 넣기엔 애매한 제목 → review 분리 근거.

    - 정보공개+모집/공고: 정적 메뉴 오수집·모니터링단류와 진짜 '환경정보공개 지원사업'이 섞임
      → 지원사업/바우처 등 명확 신호가 없으면 AMBIGUOUS_NOTICE.
    - 모니터링단: 기업 현금지원 확률 낮음 → review(완전 hard REPORT_JUNK 아님).
    """
    title = norm(item.get("title", ""))
    if not title:
        return ""
    if "모니터링단" in title:
        return "모니터링단"
    if "정보공개" in title and any(tok in title for tok in ("모집", "공고")):
        if not any(ok in title for ok in _AMBIGUOUS_GRANT_OK):
            return "정보공개"
    return ""

REGION_EXCLUDE_PHRASES = [
    "수도권 제외", "수도권 소재 기업 제외", "서울·경기·인천 제외", "서울 경기 인천 제외",
    "수도권 소재 기업 신청 불가", "인천 제외", "비수도권 기업 대상",
    "지역제조 중 수도권 제외", "인천 소재 기업 신청 불가",
]
OPEN_DEADLINE_TERMS = [
    "상시접수", "수시접수", "예산 소진 시까지", "예산소진 시까지", "예산 소진시까지", "상시모집", "수시모집", "수시 모집", "연중수시",
    # ★recall(round7): 한국 공고에 흔한 '마감 없는 모집' 표현 보강 — 이 신호를 놓치면
    #   과거 시작일('접수 2026.03.01부터 …')만 보고 closed 로 오판해, 아직 열려있는 공고를 누락한다.
    "선착순", "연중상시",
    # 접두어(예산/재원/물량/기금)·공백 무관하게 '소진 시'/'소진시' 로 '소진 시 마감/종료/까지' 를 포괄.
    # '소진으로 종료'(과거형 마감)는 '소진 시'·'소진시' 어디에도 안 걸려 closed 유지(precision).
    "소진 시", "소진시",
]

# 신청·모집 기간 라벨 (우선순위 순). 협약/사업기간과 구분한다.
APPLICATION_PERIOD_LABELS = (
    "신청기간", "모집기간", "접수기간", "지원신청기간", "참가신청기간",
    "신청 일정", "접수 일정", "모집 일정",
)
NON_APPLICATION_PERIOD_LABELS = (
    "협약기간", "사업기간", "수행기간", "지원기간", "운영기간", "서비스 완료",
    "사업 추진 기간", "지원 기간",
)
DETAIL_ENRICH_HOSTS = ("exportvoucher.com", "k-startup.go.kr", "nipa.kr", "bizinfo.go.kr")
MAX_DETAIL_ENRICH = 40
# --- 리스트-온리(상세 본문 미수집) 공고를 범용 추출기로 보강 ---
# 목적: 접수기간·지원금·성격이 상세페이지에만 있고 목록엔 없는 소스(144개)를 재크롤해 최대 복구.
GENERIC_DETAIL_ENRICH_ENABLED = os.environ.get("MONITOR_NO_GENERIC_ENRICH") != "1"
MAX_GENERIC_DETAIL_ENRICH = 1500      # 하루 신규분 커버(초과분은 다음 실행에서 처리)
DETAIL_ENRICH_WORKERS = 10            # 동시 상세 fetch 스레드 수

# 상세정보 추출 상태. 빈 문자열 하나로 "원문 미기재/파싱 실패/접근 실패"를 섞지 않는다.
EXTRACTION_SUCCESS = "SUCCESS"
NOT_SPECIFIED = "NOT_SPECIFIED"
PARSE_FAILED = "PARSE_FAILED"
DETAIL_FETCH_FAILED = "DETAIL_FETCH_FAILED"
_DETAIL_FAILURE_STATUSES = frozenset({PARSE_FAILED, DETAIL_FETCH_FAILED})
_GENERIC_ENRICH_SKIP_EXT = (
    ".pdf", ".hwp", ".hwpx", ".zip", ".xls", ".xlsx", ".doc", ".docx",
    ".jpg", ".jpeg", ".png", ".gif",
)
# 정부/기관 게시판 상세 본문 컨테이너 공통 후보(범용)
GENERIC_CONTENT_SELECTORS = (
    ".board_view, .bbs_view, .board-view, .bo_v_con, #bo_v_con, .view_con, .view_cont, "
    ".view_content, .viewcont, .cont_view, .board_txt, .board_cont, .bbs_content, "
    ".detail, .detail_view, .view, .view_area, .con_area, .sub_content, .contents_view, "
    "#content, #contents, article, main, .content, td.content"
)
_ENRICH_STORE_LOCK = threading.Lock()  # raw store 카운터 동시증가 보호(파일은 notice별 분리라 안전)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── 페이지네이션 계측 (P0 수집누락 탐지용) ────────────────────────────────────
# 각 fetcher 가 "몇 페이지를 돌았고 왜 멈췄는지"를 남긴다. 이 정보는 함수 밖에서는
# 관찰할 수 없다(모든 fetcher 가 list[dict] 만 반환하므로). 네트워크 요청을 1건도
# 늘리지 않고, items 를 읽지도 바꾸지도 않는 append-only 계측이다.
#   stop_reason: SINGLE_PAGE(페이지네이션 없음) / EMPTY_PAGE(빈 페이지로 정상 종료)
#                / MAX_PAGES_HIT(상한에 걸려 끊김 = 더 있을 수 있음)
# 킬스위치: MONITOR_NO_PAGE_STATS=1
_PAGE_STATS: dict[str, dict] = {}


def _page_stat(site_id: str, **fields: Any) -> None:
    """페이지 계측 기록. 실패해도 수집을 절대 막지 않는다(전부 무시)."""
    try:
        if os.environ.get("MONITOR_NO_PAGE_STATS") or not site_id:
            return
        cur = _PAGE_STATS.get(site_id) or {}
        cur.update(fields)
        _PAGE_STATS[site_id] = cur  # site_id 키 단위 대입만 (스레드 경합 회피)
    except Exception:
        pass


def page_stats_snapshot() -> dict[str, dict]:
    """현재까지 기록된 페이지 계측 스냅샷(얕은 복사)."""
    try:
        return {k: dict(v) for k, v in _PAGE_STATS.items()}
    except Exception:
        return {}


def reset_page_stats() -> None:
    """계측 초기화(실행 단위 분리용)."""
    try:
        _PAGE_STATS.clear()
    except Exception:
        pass


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
        return load_json_with_recovery(path, default)
    except Exception as e:
        log.warning("%s 로드 실패: %s", path, e)
        return default


def _pii_config(env_var: str, file_loader):
    """PII 격리(#96·#149): 환경변수(JSON 문자열)가 있으면 그걸 우선 쓰고, 없으면 파일에서 읽는다.

    실 수신자(groups.json)·기업 프로필(companies.json)을 Git 에 평문 커밋하는 대신 GitHub Secret
    등 환경변수로 주입할 수 있게 한다. 파싱 실패 시 파일로 폴백(운영 중단 방지).
    (워크플로에 secret 을 넘기고 실데이터 파일을 .gitignore 하는 배선은 Part B — monitor.yml/.gitignore.)
    """
    raw = os.environ.get(env_var, "").strip()
    if raw:
        try:
            data = json.loads(raw)
            log.info("%s 환경변수에서 로드(파일 대신 — PII 격리)", env_var)
            return data
        except Exception as e:  # noqa: BLE001
            log.error("%s 파싱 실패 — 파일로 폴백: %s", env_var, e)
    return file_loader()

def save_json(path: Path, data) -> None:
    try:
        atomic_write_json(path, data, indent=2, backup=True)
    except Exception as e:
        log.error("파일 저장 실패 %s: %s", path, e)
        raise


_NOTICE_VERSION_MATERIAL_FIELDS = frozenset({
    "title", "deadline", "application_period", "target", "support", "region",
})


def _notice_date_fields(item: dict) -> dict[str, str]:
    """게시일·등록일·수정일을 별도 표준 필드로 보존한다."""
    return {
        "published_at": str(item.get("published_at") or item.get("posted_date") or "").strip()[:10],
        "registered_at": str(item.get("registered_at") or item.get("registered_date") or item.get("reg_date") or "").strip()[:10],
        "updated_at": str(item.get("updated_at") or item.get("updated_date") or item.get("modified_at") or "").strip()[:10],
    }


def _notice_version_snapshot(item: dict) -> dict[str, str]:
    period = item.get("application_period") or {}
    return {
        "title": strip_title_badges(norm(item.get("title"))),
        "author": norm(item.get("author")),
        "deadline": resolve_item_deadline(item),
        "application_period": str(period.get("display") or "").strip(),
        "target": norm(item.get("target_field") or item.get("target_age_field")),
        "support": _mail_clean_text(item.get("support_field") or item.get("description") or "", limit=600),
        "region": norm(item.get("region_field")),
        **_notice_date_fields(item),
    }


def _notice_snapshot_hash(snapshot: dict[str, str]) -> str:
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _notice_list_hash(item: dict) -> str:
    return _notice_snapshot_hash({
        "title": strip_title_badges(norm(item.get("title"))),
        "author": norm(item.get("author")),
        "deadline": norm(item.get("deadline")),
        "link": norm(item.get("link")),
        **_notice_date_fields(item),
    })


def load_notice_versions() -> dict[str, dict]:
    raw = load_json(NOTICE_VERSIONS_PATH, {})
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def save_notice_versions(versions: dict[str, dict]) -> None:
    if not _ALLOW_PERSIST_SEEN or os.environ.get("MONITOR_NO_PERSIST_SEEN") == "1":
        log.info("notice_versions 저장 생략 (persist_seen=False)")
        return
    ordered = dict(sorted(
        versions.items(), key=lambda pair: str(pair[1].get("last_seen_at") or ""), reverse=True,
    )[:10000])
    save_json(NOTICE_VERSIONS_PATH, ordered)


def _delivery_notice_id(item: dict) -> str:
    return str(item.get("_delivery_id") or item.get("id") or "")


def _recent_recheck_dates(now: datetime, days_back: int) -> set:
    return {previous_business_day(now, offset) for offset in range(1, max(1, int(days_back or 1)) + 1)}


def _item_recent_for_recheck(item: dict, now: datetime, days_back: int) -> bool:
    targets = _recent_recheck_dates(now, days_back)
    oldest, today = min(targets), now.date()
    for value in _notice_date_fields(item).values():
        if not value:
            continue
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            continue
        if parsed in targets or (oldest < parsed < today and parsed.weekday() >= 5):
            return True
    return False


def select_notice_version_candidates(items: list[dict], seen_ids: set[str], versions: dict[str, dict], *, now: datetime, days_back: int) -> list[dict]:
    """신규·최근 N영업일·목록변경·미전달 변경만 상세보강 대상으로 고른다."""
    selected: list[dict] = []
    for item in items:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        if iid not in seen_ids:
            selected.append(item)
            continue
        previous = versions.get(iid)
        if previous is None:
            if _item_recent_for_recheck(item, now, days_back):
                selected.append({**item, "_version_seed_only": True})
            continue
        pending = bool(previous.get("observed_hash") and previous.get("observed_hash") != previous.get("delivered_hash"))
        if pending or _notice_list_hash(item) != previous.get("list_hash") or _item_recent_for_recheck(item, now, days_back):
            selected.append(item)
    return selected


def _snapshot_changed_fields(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def _latest_date_from_text(value: str):
    dates = [parsed for _pos, parsed in _parse_date_candidates(str(value or ""))]
    return max(dates) if dates else None


def _classify_notice_change(before: dict, after: dict) -> str:
    """P1-5: 공고 변경 유형을 세분화하여 판정한다.

    반환: DEADLINE_EXTENDED / TARGET_CHANGED / SUPPORT_AMOUNT_CHANGED /
          APPLICATION_URL_CHANGED / REANNOUNCEMENT / ADDITIONAL_RECRUITMENT /
          MINOR_TEXT_CHANGE / UPDATED
    """
    after_title = str(after.get("title") or "")
    before_title = str(before.get("title") or "")

    # 재공고 감지
    if "재공고" in after_title and "재공고" not in before_title:
        return "REANNOUNCEMENT"

    # 추가 모집 감지
    if any(term in after_title for term in ("추가모집", "추가 모집", "2차 모집", "2차모집")):
        if not any(term in before_title for term in ("추가모집", "추가 모집", "2차 모집", "2차모집")):
            return "ADDITIONAL_RECRUITMENT"

    # 마감 연장 감지
    old_deadline = _latest_date_from_text(str(before.get("application_period") or before.get("deadline") or ""))
    new_deadline = _latest_date_from_text(str(after.get("application_period") or after.get("deadline") or ""))
    if new_deadline and (old_deadline is None or new_deadline > old_deadline):
        return "DEADLINE_EXTENDED"

    # 지원대상 변경 감지
    old_target = str(before.get("target_field") or "")
    new_target = str(after.get("target_field") or "")
    if old_target and new_target and old_target != new_target:
        return "TARGET_CHANGED"

    # 신청 URL 변경 감지
    old_url = str(before.get("link") or "")
    new_url = str(after.get("link") or "")
    if old_url and new_url and old_url != new_url:
        return "APPLICATION_URL_CHANGED"

    # 기본: 텍스트 변경
    return "MINOR_TEXT_CHANGE"


def merge_notice_fields(canonical: dict, new_item: dict) -> dict:
    """P1-6: 여러 출처의 공고 정보를 병합한다.

    우선순위:
    - 대표 제목: 주관기관 공식 제목 (is_aggregator=False 우선)
    - 공식 공고문: 주관기관 URL
    - 신청 링크: 실제 공식 신청 URL
    - 지원대상: 최신·신뢰도 높은 구조화 필드
    - 접수기간: 최신 수정공고 기준
    - 추가 출처: 기업마당, K-Startup, 지역기관 등
    """
    result = {**canonical}

    # 출처 우선순위: 주관기관 > K-Startup > 기업마당 > 기타
    SOURCE_PRIORITY = {"kstartup": 1, "bizinfo": 2}

    canonical_priority = SOURCE_PRIORITY.get(canonical.get("source"), 99)
    new_priority = SOURCE_PRIORITY.get(new_item.get("source"), 99)

    # 대표 제목: 주관기관 우선
    if new_priority < canonical_priority:
        result["title"] = new_item.get("title", result.get("title", ""))

    # 신청 링크: 공식 신청 URL 우선
    new_link = new_item.get("link", "")
    if new_link and not result.get("link"):
        result["link"] = new_link

    # 지원대상: 최신 값 우선
    new_target = new_item.get("target_field", "")
    if new_target and len(new_target) > len(str(result.get("target_field", ""))):
        result["target_field"] = new_target

    # 접수기간: 최신 값 우선
    new_period = new_item.get("application_period", "")
    if new_period:
        result["application_period"] = new_period

    # 추가 출처 기록
    sources = result.get("_additional_sources", [])
    new_source = new_item.get("source", "")
    if new_source and new_source not in sources:
        sources.append(new_source)
        result["_additional_sources"] = sources

    return result


def _detail_extraction_unreliable(item: dict) -> bool:
    """상세 FETCH/PARSE 실패면 스냅샷이 불완전해 버전 재발송 근거로 쓰면 안 된다."""
    extraction = item.get("detail_extraction")
    if not isinstance(extraction, dict):
        return False
    status = str(extraction.get("status") or "").strip().upper()
    return status in {"DETAIL_FETCH_FAILED", "PARSE_FAILED"}


def classify_notice_versions(items: list[dict], seen_ids: set[str], versions: dict[str, dict]) -> tuple[list[dict], dict[str, dict]]:
    deliverable: list[dict] = []
    updates: dict[str, dict] = {}
    now_iso = datetime.now(KST).isoformat()
    for source in items:
        item = {**source, **_notice_date_fields(source)}
        iid = str(item.get("id") or "")
        if not iid:
            continue
        snapshot = _notice_version_snapshot(item)
        current_hash = _notice_snapshot_hash(snapshot)
        previous = versions.get(iid)
        base = {"snapshot": snapshot, "content_hash": current_hash, "list_hash": _notice_list_hash(item), "last_seen_at": now_iso}
        if iid not in seen_ids:
            version = max(1, int((previous or {}).get("version", 0) or 0))
            deliverable.append({**item, "_change_type": "NEW", "_notice_version": version, "_delivery_id": iid, "_changed_fields": list(snapshot)})
            updates[iid] = {**base, "version": version, "delivery_id": iid}
            continue
        # 상세 FETCH/PARSE 실패 스냅샷은 seed 경로에서도 전달 확정본으로 승격하면 안 된다.
        # (seed_only 가 빈 delivered_* 를 심으면, 다음 정상 enrich 가 전 필드 "변경"으로
        #  허위 @vN 재발송을 만든다 — delivered_hash 가 이미 있는 경로의 unreliable_observe
        #  가드와 같은 사고 유형.)
        if _detail_extraction_unreliable(item):
            updates[iid] = {
                **base,
                "version": max(1, int((previous or {}).get("version", 1) or 1)),
                "delivery_id": str((previous or {}).get("delivery_id") or iid),
                "unreliable_observe": True,
            }
            continue
        if previous is None or item.get("_version_seed_only"):
            updates[iid] = {**base, "version": 1, "delivery_id": iid, "seed_only": True}
            continue
        old_snapshot = previous.get("delivered_snapshot") or {}
        old_hash = str(previous.get("delivered_hash") or "")
        # 전달 확정 스냅샷이 없으면 빈 dict 와 비교해 전 필드가 "변경"으로 오인된다.
        # 이미 seen 이므로 시드만 하고 @vN 재발송하지 않는다.
        if not old_hash:
            updates[iid] = {
                **base,
                "version": max(1, int(previous.get("version", 1) or 1)),
                "delivery_id": str(previous.get("delivery_id") or iid),
                "seed_only": True,
            }
            continue
        changed = _snapshot_changed_fields(old_snapshot, snapshot)
        material = sorted(set(changed) & _NOTICE_VERSION_MATERIAL_FIELDS)
        if current_hash == old_hash or not material:
            updates[iid] = {**base, "version": int(previous.get("version", 1) or 1), "delivery_id": str(previous.get("delivery_id") or iid)}
            continue
        version = int(previous.get("version", 1) or 1) + 1
        change_type = _classify_notice_change(old_snapshot, snapshot)
        delivery_id = f"{iid}@v{version}"
        deliverable.append({**item, "_change_type": change_type, "_notice_version": version, "_delivery_id": delivery_id, "_changed_fields": material})
        updates[iid] = {**base, "version": version, "delivery_id": delivery_id, "change_type": change_type, "changed_fields": material}
    return deliverable, updates


def commit_notice_versions(versions: dict[str, dict], updates: dict[str, dict], seen_ids: set[str], *, now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now(KST)
    merged = {str(k): dict(v) for k, v in versions.items() if isinstance(v, dict)}
    for iid, update in updates.items():
        record = dict(merged.get(iid) or {})
        prior_pending_delivery_id = record.get("pending_delivery_id", "")
        record.update({
            "list_hash": update.get("list_hash", ""),
            "observed_hash": update.get("content_hash", ""),
            "observed_snapshot": update.get("snapshot", {}),
            "last_seen_at": update.get("last_seen_at") or now.isoformat(),
            "pending_delivery_id": update.get("delivery_id", ""),
        })
        if update.get("unreliable_observe"):
            # FETCH/PARSE 실패 스냅샷은 재조회 대상으로 관찰만 기록한다.
            # 이미 전달된 확정본과 기존 pending delivery는 절대 덮지 않는다.
            record["pending_delivery_id"] = prior_pending_delivery_id
            merged[iid] = record
            continue
        delivery_id = str(update.get("delivery_id") or iid)
        if update.get("seed_only") or delivery_id in seen_ids:
            record.update({
                "version": int(update.get("version", record.get("version", 1)) or 1),
                "delivery_id": delivery_id,
                "delivered_hash": update.get("content_hash", ""),
                "delivered_snapshot": update.get("snapshot", {}),
                "last_delivered_at": now.isoformat(),
                "change_type": update.get("change_type") or record.get("change_type") or "NEW",
                "pending_delivery_id": "",
            })
        merged[iid] = record
    save_notice_versions(merged)
    return merged


def normalize_title(title: str) -> str:
    """중복 판별용 제목 정규화: 소문자 + 특수문자/공백 제거"""
    t = unicodedata.normalize("NFKC", title.lower())
    return re.sub(r"[\s\W]+", "", t)


def safe_normalize_title(title: str) -> str:
    """P1-4: 의미 정보를 보존하는 안전한 제목 정규화.

    보존: 연도, 지역, 모집차수, 재공고, 추가모집, 수정공고
    제거: 중복 공백, 특수문자, 괄호, 구분기호, URL 파라미터
    """
    t = unicodedata.normalize("NFKC", title)
    # 소문자 변환 (한글은 영향 없음)
    t = t.lower()
    # 중복 공백 → 단일 공백
    t = re.sub(r"\s+", " ", t)
    # 괄호·구분기호 정규화
    t = re.sub(r"[()\[\]{}<>「」『』【】]", " ", t)
    # 중복 구분기호 제거
    t = re.sub(r"[·•∙‧]", "·", t)
    # URL 추적 파라미터 제거
    t = re.sub(r"[?&][\w=&]+", "", t)
    # 앞뒤 공백 제거
    return t.strip()


def generate_canonical_notice_id(item: dict) -> str:
    """P1-2: 크로스 소스 통합 ID 생성.

    동일 공고를 다른 소스에서 가져왔을 때 하나로 묶기 위한 ID.
    우선순위: 공고번호 > URL > 제목+기관+연도+마감
    """
    # 1. 공식 공고번호가 있으면 그것으로 통합
    notice_id = item.get("notice_id") or item.get("pbln_id") or ""
    if notice_id:
        return f"canon_{notice_id}"

    # 2. 공식 URL이 있으면 그것으로 통합
    link = item.get("link") or ""
    if link:
        # URL 정규화 (프로토콜, www, 트래커 제거)
        norm_link = re.sub(r"^https?://(www\.)?", "", link.lower())
        norm_link = re.sub(r"[?&][\w=&]+", "", norm_link)
        if norm_link:
            return f"canon_url_{hashlib.md5(norm_link.encode()).hexdigest()[:12]}"

    # 3. 제목+기관+연도+마감으로 해시
    title = safe_normalize_title(item.get("title", ""))
    org = (item.get("author") or item.get("organizer_field") or "").strip()
    deadline = (item.get("deadline") or "").strip()
    # 연도 추출
    year_match = re.search(r"(20\d{2})", title)
    year = year_match.group(1) if year_match else ""
    composite = f"{title}|{org}|{year}|{deadline}"
    return f"canon_{hashlib.md5(composite.encode()).hexdigest()[:12]}"


# 게시판 목록 제목 꼬리의 아이콘 대체텍스트 — 앵커 안에 첨부/새글 아이콘이 같이 들어있어
# '… 모집 공고 file'·'… 모집 안내 새로운게시글' 처럼 제목이 오염된 채 발송되던 문제.
_TITLE_BADGE_TAIL_RE = re.compile(
    r"(?:\s+(?:file|new|hot|첨부파일|파일있음|새로운게시글|새글|인기글))+\s*$",
    re.IGNORECASE,
)


def strip_title_badges(title: str) -> str:
    """목록 앵커에 딸려온 아이콘 텍스트(file·새로운게시글 등)를 제목 끝에서 제거."""
    t = re.sub(r"^\s*이미지\s*없음\s+", "", str(title or ""))
    return _TITLE_BADGE_TAIL_RE.sub("", t).strip()

def is_imminent(deadline: str) -> bool:
    """마감 문자열에 오늘~+7일 이내 날짜가 하나라도 있으면 임박(True).

    기존 구현은 공백 split 후 고정위치 'YYYY-MM-DD'(tok[4]·tok[7]=='-', len>=10)만 인식해
    '2026.6.30'(한자리 월/일)·'2026년 6월 30일'(한글)·'6.30까지'(연도 생략) 같은 실공고 빈출
    표기를 통째로 놓쳤다 → 마감이 7일 이내인데도 메일 최상단 '⚠️ 마감 임박' 알림에서 빠져
    고객이 신청기회를 놓치던 recall 갭. classify_deadline_status 등과 동일한 robust 파서
    _parse_date_candidates 를 재사용해 한자리·한글·점·범위 표기를 모두 인식하도록 통일한다."""
    if not deadline:
        return False
    today = datetime.now(KST).date()
    return any(0 <= (parsed - today).days <= 7 for _pos, parsed in _parse_date_candidates(deadline))

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
        (r"(?<![\d.])(\d{1,2})\s*[.]\s*(\d{1,2})\.?(?!\d)(?![%％배억만천원조점])", None),
    ]
    # 앞선(연도 포함) 패턴이 이미 차지한 원문 구간. 연도 생략 'M.D' 패턴이
    # '2025. 7. 22.' 의 꼬리(' 7. 22')를 재매칭해 실행연도(예: 2026)로 오인하면,
    # 작년 마감 공고의 마감일이 미래로 계산돼 '모집중'으로 오판된다(실사고 2026-07-24).
    claimed_spans: list[tuple[int, int]] = []
    for pattern, year_mode in patterns:
        pattern_spans: list[tuple[int, int]] = []
        for m in re.finditer(pattern, text):
            if any(s < m.end() and m.start() < e for s, e in claimed_spans):
                continue
            if year_mode is None:
                year, month, day = base_year, int(m.group(1)), int(m.group(2))
            elif year_mode == 2000:
                year, month, day = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            parsed = _valid_date(year, month, day)
            if parsed:
                candidates.append((m.start(), parsed))
                pattern_spans.append((m.start(), m.end()))
        claimed_spans.extend(pattern_spans)
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


def _posted_date(item: dict):
    """게시일(posted_date)을 date 로 파싱(연도 추론 기준). 없거나 불량이면 None."""
    pd = str(item.get("posted_date") or "").strip()[:10]
    if not pd:
        return None
    try:
        return datetime.strptime(pd, "%Y-%m-%d").date()
    except ValueError:
        return None


def _infer_deadline_year(month: int, day: int, posted):
    """축약 마감(월/일)의 연도 추론. ★마감 ≥ 게시일 규칙으로 false-past(오'마감'=누락) 차단.
    게시일 있으면 그 해로 두되 마감이 게시일보다 앞서면 +1년. 게시일 없으면 오늘 기준 반년 초과 과거면 +1년."""
    if posted:
        d = _valid_date(posted.year, month, day)
        if d and d < posted:
            d = _valid_date(posted.year + 1, month, day)
        return d
    today = datetime.now(KST).date()
    d = _valid_date(today.year, month, day)
    if d and (today - d).days > 200:
        d = _valid_date(today.year + 1, month, day)
    return d


def _deadline_shortform(text: str, posted=None) -> dict[str, str]:
    """라벨 없는 축약 마감표기 추출 — 제목/본문의 '~M/D', 'M/D~M/D', '~M월D일'.
    한국 공고 제목에 매우 흔한 '(~7/7)'·'(접수 6/24~7/7)' 형식. tilde(~)로 앵커해 보수적."""
    if not text:
        return {}

    def _single(e):
        # 단일 마감(~M/D): 시작=게시일(신청 개시)로 둬 'open' 판정(마감만으로 upcoming 오분류 방지).
        start = posted.isoformat() if (posted and posted <= e) else e.isoformat()
        return {"start": start, "end": e.isoformat(), "display": e.isoformat(), "label": "축약마감"}

    # 범위: M/D ~ M/D (슬래시·점). 뒤에 '18시' 등 다른 수가 와도 무방(일자 자체만 인접숫자 배제).
    m = re.search(r"(?<!\d)(\d{1,2})\s*[./]\s*(\d{1,2})(?![./]?\d)\s*~\s*(\d{1,2})\s*[./]\s*(\d{1,2})(?![./]?\d)", text)
    if m:
        s = _infer_deadline_year(int(m.group(1)), int(m.group(2)), posted)
        e = _infer_deadline_year(int(m.group(3)), int(m.group(4)), posted)
        if s and e and e >= s:
            return {"start": s.isoformat(), "end": e.isoformat(),
                    "display": f"{s.isoformat()} ~ {e.isoformat()}", "label": "축약범위"}
    # 단일 마감: ~ M/D  (tilde 필수)
    m = re.search(r"~\s*(?<!\d)(\d{1,2})\s*[./]\s*(\d{1,2})(?![./]?\d)", text)
    if m:
        e = _infer_deadline_year(int(m.group(1)), int(m.group(2)), posted)
        if e:
            return _single(e)
    # 단일 마감: ~ M월D일
    m = re.search(r"~\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if m:
        e = _infer_deadline_year(int(m.group(1)), int(m.group(2)), posted)
        if e:
            return _single(e)
    return {}


def extract_application_period(text: str, posted=None) -> dict[str, str]:
    """본문에서 신청·모집·접수 기간만 추출 (협약기간 등 제외).
    posted(게시일 date) 를 주면 연도 추론에 사용 — 라벨 없는 축약 마감(~M/D)도 안전 복구."""
    if not text:
        return {}
    normalized = text.replace("\xa0", " ")
    base_year = posted.year if posted else None
    for label in APPLICATION_PERIOD_LABELS:
        pattern = rf"{re.escape(label)}\s*[:：]?\s*([^\nㅇ]+)"
        m = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not m:
            continue
        segment = m.group(1).strip()
        if "까지" in segment:
            segment = segment[: segment.index("까지") + 2]
        dates = _parse_period_dates(segment, base_year)
        if not dates:
            # 라벨은 있으나 M월D일/연도형이 아닌 축약(6/24~7/7) — 축약 파서로 재시도
            sf = _deadline_shortform(segment, posted)
            if sf:
                return sf
            continue
        start, end = dates[0].isoformat(), dates[-1].isoformat()
        display = f"{start} ~ {end}" if start != end else end
        return {"start": start, "end": end, "display": display, "label": label}
    # 라벨 없이 제목/본문에 흔한 축약 마감표기 폴백
    return _deadline_shortform(normalized, posted)


def resolve_item_deadline(item: dict) -> str:
    """표시·필터용 마감일: 신청기간 우선, 없으면 기존 deadline."""
    period = extract_application_period(_notice_body_text(item), _posted_date(item))
    if period.get("display"):
        return period["display"]
    return (item.get("deadline") or "").strip()


def _applicant_target_text(item: dict) -> str:
    """지원대상(신청 가능 주체) 판정용 본문. 주관기관(author)은 지역 판정에 쓰지 않는다."""
    parts = [
        item.get("title", ""),
        item.get("description", ""),
        item.get("target_field", ""),
        item.get("target_age_field", ""),
    ]
    return norm(" ".join(p for p in parts if p))


def _region_field_short(region_field: str) -> str:
    rf = norm(region_field)
    for r in sorted(KNOWN_REGIONS, key=len, reverse=True):
        if r in rf:
            return r
    return rf


def _resolve_applicant_region_scope(item: dict) -> dict[str, Any]:
    """지원대상 기준 지역 범위. 주관·개최지가 아닌 '누가 신청할 수 있는지'만 본다.

    반환: {regions: [광역약칭...], nationwide: bool}
    - nationwide: 전국 어디서나 신청 가능
    - regions 비어있고 nationwide False: 지역 단서 없음
    - regions에 타 광역만: 해당 지역 소재 등 지원대상 한정
    """
    text = _applicant_target_text(item)
    det = _detect_target_regions(text) if text else {"regions": [], "nationwide": False}
    regions: list[str] = list(det.get("regions") or [])
    nationwide = bool(det.get("nationwide"))

    # 제목 다지역 태그 [서울ㆍ인천ㆍ경기ㆍ강원] — 그룹경로(classify_region_for_group)가 쓰는
    # 검증된 _title_region_tags 를 재사용해 지원대상 지역으로 합산한다. 기업경로(_region_signals)가
    # 이 스코프를 재사용하므로, own 이 태그에 명시됐는데 파서가 마지막 토큰만 잡아 '타지역 한정'으로
    # 오차단하던 비대칭 누락(titletag_own_blocked)을 막는다(대칭 원칙 · recall 보존).
    for r in _title_region_tags(item):
        if r not in regions:
            regions.append(r)

    if any(
        p in text
        for p in (
            "전국 소재", "전국 중소", "전국 기업", "전국 제조", "전국 소상공인",
            "전국 어디", "국내 전체", "국내전체", "지역 제한 없", "지역무관", "지역 무관",
        )
    ):
        nationwide = True

    has_applicant_local = bool(regions) or any(
        f"{r} 소재" in text or f"{r}특별시" in text or f"{r}광역시" in text
        for r in KNOWN_REGIONS
    )

    rf = norm(item.get("region_field") or "")
    rf_short = _region_field_short(rf) if rf else ""
    # 메타 region_field='전국'은 본문에 지원대상 지역 단서가 없을 때만 보조(recall).
    if rf == "전국" and not has_applicant_local:
        nationwide = True
    elif rf and rf != "전국" and rf_short and rf_short not in regions and not nationwide:
        if not has_applicant_local:
            regions.append(rf_short)

    # 드롭다운/제목 '전국'과 본문 '서울 소재' 등이 충돌하면 지원대상(본문) 우선(precision).
    if regions and nationwide and has_applicant_local:
        if any(
            f"{r} 소재" in text or f"신청일 기준 {r}" in text or f"{r}특별시 소재" in text
            for r in regions
        ):
            nationwide = False

    return {"regions": _unique(regions), "nationwide": nationwide}


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
        (r"서울특별시|서울\s*소재|서울\s", "서울"),
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
    # 공백 없는 지역 접미사 표기('충북지역'·'충북도내'·'충북관내') 보강(2026-06-25).
    # 기존 hint 는 '충북\\s'(뒤 공백)만 잡아 '충북지역 기업 대상'류 타지역 한정을 통째로 놓쳤다.
    # '소재'는 아래 KNOWN_REGIONS 패스(\\s*소재)가 이미 커버. '광주'는 경기 광주시 충돌로 제외.
    # '권'(광역권: 경기권·수도권 등)은 _other_region_block·수도권 family 면제가 따로 처리하므로 제외.
    for label in (
        "서울", "부산", "대구", "인천", "대전", "울산", "세종", "경기",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    ):
        if label not in regions and re.search(rf"{label}(?:지역|도내|시내|관내|내)", text):
            regions.append(label)
    _SOJI_EXCLUDE = frozenset({"수도권", "비수도권"})
    for label in KNOWN_REGIONS:
        if label in _SOJI_EXCLUDE:
            continue
        if re.search(rf"{re.escape(label)}\s*소재", text) and label not in regions:
            regions.append(label)
    # 인라인 다지역 나열(가운뎃점류로 이어진 광역 2개+) — 나열된 광역 전부를 지원대상으로.
    for m in _INLINE_REGION_LIST_RE.finditer(text):
        for r in _REGION_TOKEN_RE.findall(m.group(0)):
            val = _REGION_LONG_TO_SHORT.get(r, r)
            if val not in regions:
                regions.append(val)
    return {"regions": regions, "nationwide": nationwide}


def _hangul_len(text: str) -> int:
    """문자열 내 한글 음절 수(본문 블록 선택의 지표)."""
    return sum(1 for ch in text if "가" <= ch <= "힣")


def _nonlink_hangul_len(el: Any) -> int:
    """블록의 한글 수에서 링크(<a>) 안 한글 수를 뺀 값 — 본문다움 지표.
    nav/footer/사이트맵 블록은 텍스트가 거의 전부 링크라 이 값이 0에 가깝다."""
    total = _hangul_len(el.get_text())
    linked = sum(_hangul_len(a.get_text()) for a in el.find_all("a"))
    return total - linked


def _extract_main_content(soup: BeautifulSoup) -> str:
    """정부/기관 게시판 상세에서 본문 텍스트를 범용 추출.
    ① 흔한 본문 컨테이너 후보 → ② '링크 아닌 한글'이 가장 많은 블록 폴백.
    (호스트별 파서가 없는 144개 리스트-온리 소스를 위한 범용 경로)

    본문다움은 링크 밖 한글 수로 잰다. 전체 한글 수 기준이던 시절에는 메뉴·푸터
    링크 덩어리(수백 개 기관 링크)가 '가장 한글 많은 블록'으로 뽑혀, 지원내용이
    사이트 내비게이션 전문으로 채워진 메일이 나가던 실사고(2026-07-24)가 있었다."""
    for tag in soup.select(
        "script, style, nav, header, footer, aside, .lnb, .gnb, .snb, "
        ".paging, .btn_area, .search, .skip, .top_menu, .footer, .header"
    ):
        try:
            tag.decompose()
        except Exception:
            pass
    # 순수 링크 목록(ul/ol 의 한글이 사실상 전부 <a> 안) = 메뉴·패밀리사이트·푸터 링크.
    # 클래스명이 제각각인 사이트(nav 클래스 없음)에서도 내비게이션을 범용 제거한다.
    for lst in soup.find_all(("ul", "ol")):
        try:
            total = _hangul_len(lst.get_text())
            if (len(lst.find_all("li")) >= 5 and total >= 10
                    and _nonlink_hangul_len(lst) <= total * 0.1):
                lst.decompose()
        except Exception:
            pass
    for node in soup.select(GENERIC_CONTENT_SELECTORS):
        if _nonlink_hangul_len(node) >= 30:
            return node.get_text("\n", strip=True)
    # 폴백: 링크 아닌 한글이 가장 많은 블록(너무 큰 래퍼는 제외).
    # 동점(>=)은 나중(더 깊은) 블록이 이긴다 — find_all 은 부모가 먼저 오므로,
    # '메뉴(전부 링크)+본문'을 함께 감싼 래퍼 대신 본문만 담은 안쪽 블록이 선택된다.
    best, best_score = None, 0
    for el in soup.find_all(("div", "td", "section", "article")):
        txt = el.get_text("\n", strip=True)
        score = _nonlink_hangul_len(el)
        if score >= max(best_score, 1) and len(txt) < 20000:
            best, best_score = el, score
    return best.get_text("\n", strip=True) if best is not None and best_score >= 30 else ""


def _should_generic_enrich(item: dict, link: str) -> bool:
    """리스트-온리(본문 미수집) 공고를 범용 상세 보강 대상으로 볼지 판정."""
    if not link.lower().startswith(("http://", "https://")):
        return False
    path = link.lower().split("?")[0]
    if any(path.endswith(ext) for ext in _GENERIC_ENRICH_SKIP_EXT):
        return False
    # 이미 본문이 충분하면 재조회 불필요 — '리스트-온리'만 대상(120자 미만)
    desc = (item.get("description") or "").strip()
    if len(desc) >= 120:
        return False
    return True


_DETAIL_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("title",),
    "organizer": ("organizer_field", "author"),
    "url": ("link",),
    "description": ("description",),
    "application_period": ("application_period", "deadline"),
    "target": (
        "target_field", "business_age_text", "target_age_field",
        "exclude_target_field", "support_field",
    ),
    "region": ("region_field",),
}

_DETAIL_TABLE_MAX_TABLES = 20
_DETAIL_TABLE_MAX_ROWS = 100
_DETAIL_TABLE_MAX_CELLS = 20
_DETAIL_TABLE_MAX_CELL_CHARS = 500
_DETAIL_TABLE_MAX_CAPTION_CHARS = 200


def _positive_table_span(value: Any) -> int:
    """잘못된 rowspan/colspan은 기본값 1로 안전하게 정규화."""
    try:
        return max(1, int(str(value or "1").strip()))
    except (TypeError, ValueError):
        return 1


def _table_cell_text(cell: Any, table: Any) -> str:
    """중첩 표의 문자열을 바깥 셀 내용에 중복 합산하지 않는다."""
    parts = [
        str(node).strip()
        for node in cell.find_all(string=True)
        if str(node).strip() and node.find_parent("table") is table
    ]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _extract_detail_tables(soup: BeautifulSoup) -> dict[str, Any]:
    """상세 HTML 표의 행·셀·병합 관계를 크기 제한이 있는 JSON으로 보존."""
    source_tables = [
        table for table in soup.find_all("table")
        if table.find_parent("table") is None
    ]
    result: dict[str, Any] = {
        "truncated": len(source_tables) > _DETAIL_TABLE_MAX_TABLES,
        "tables": [],
    }
    for table in source_tables[:_DETAIL_TABLE_MAX_TABLES]:
        direct_rows = [
            row for row in table.find_all("tr")
            if row.find_parent("table") is table
        ]
        table_truncated = len(direct_rows) > _DETAIL_TABLE_MAX_ROWS
        rows: list[list[dict[str, Any]]] = []
        for row in direct_rows[:_DETAIL_TABLE_MAX_ROWS]:
            cells = row.find_all(("th", "td"), recursive=False)
            if len(cells) > _DETAIL_TABLE_MAX_CELLS:
                table_truncated = True
            structured_row: list[dict[str, Any]] = []
            for cell in cells[:_DETAIL_TABLE_MAX_CELLS]:
                full_text = _table_cell_text(cell, table)
                if len(full_text) > _DETAIL_TABLE_MAX_CELL_CHARS:
                    table_truncated = True
                structured_row.append({
                    "text": full_text[:_DETAIL_TABLE_MAX_CELL_CHARS],
                    "header": cell.name == "th",
                    "rowspan": _positive_table_span(cell.get("rowspan")),
                    "colspan": _positive_table_span(cell.get("colspan")),
                })
            if structured_row:
                rows.append(structured_row)
        if not rows:
            continue
        caption_node = table.find("caption", recursive=False)
        caption = re.sub(
            r"\s+", " ", caption_node.get_text(" ", strip=True)
        ).strip() if caption_node else ""
        if len(caption) > _DETAIL_TABLE_MAX_CAPTION_CHARS:
            table_truncated = True
        result["tables"].append({
            "caption": caption[:_DETAIL_TABLE_MAX_CAPTION_CHARS],
            "truncated": table_truncated,
            "rows": rows,
        })
    return result


def _extraction_evidence(value: Any) -> str:
    """메타에 남길 짧은 근거. 원문 전체나 오류/Secret은 기록하지 않는다."""
    if isinstance(value, dict):
        value = value.get("display") or value.get("end") or json.dumps(
            value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", str(value or "")).strip()[:160]


def _with_detail_extraction(
    item: dict,
    status: str,
    reason: str,
    *,
    detail_keys: set[str] | None = None,
) -> dict:
    """핵심 필드별 성공·미기재·파싱실패·접근실패와 출처·근거를 부착."""
    detail_keys = detail_keys or set()
    missing_status = NOT_SPECIFIED if status == EXTRACTION_SUCCESS else status
    field_statuses: dict[str, dict[str, str]] = {}
    for field_name, candidate_keys in _DETAIL_FIELD_KEYS.items():
        chosen_key = ""
        chosen_value: Any = ""
        for key in candidate_keys:
            value = item.get(key)
            present = bool(value) if isinstance(value, dict) else bool(
                str(value or "").strip())
            if present:
                chosen_key, chosen_value = key, value
                break
        if chosen_key:
            field_statuses[field_name] = {
                "status": EXTRACTION_SUCCESS,
                "source": "detail" if chosen_key in detail_keys else "list",
                "evidence": _extraction_evidence(chosen_value),
            }
        else:
            field_statuses[field_name] = {
                "status": missing_status,
                "source": "detail",
                "evidence": "",
            }
    return {
        **item,
        "detail_extraction": {
            "status": status,
            "reason": reason,
            "fields": field_statuses,
        },
    }


def _persist_detail_extraction_meta(item: dict) -> None:
    if _RAW_STORE is not None:
        with _ENRICH_STORE_LOCK:
            _RAW_STORE.update_meta_after_enrich(item)


def _parse_detail_from_page(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """상세 페이지에서 본문·지역·신청기간 추출."""
    result: dict[str, Any] = {}
    if "k-startup.go.kr" in url:
        for tit in soup.select("p.tit"):
            label = norm(tit.get_text())
            key = KSTARTUP_DETAIL_LABELS.get(label)
            if not key:
                continue
            nxt = tit.find_next("p", class_="txt")
            if not nxt:
                continue
            val = norm(nxt.get_text())
            if val and key not in result:   # 같은 라벨 중복 시 첫 값만
                result[key] = val
        body = soup.select_one(".view_cont, .content_view, #contents")
        if body:
            result["body"] = body.get_text("\n", strip=True)[:12000]
    elif "exportvoucher.com" in url:
        body = soup.select_one(".board_view, .view_cont, .bbs_view, article, #contents")
        if not body:
            body = soup
        result["body"] = body.get_text("\n", strip=True)[:12000]
    elif "nipa.kr" in url:
        body = soup.select_one(".detail") or soup.select_one(".tab3.bsnsWrap")
        if body:
            result["body"] = body.get_text("\n", strip=True)[:12000]
    elif "bizinfo.go.kr" in url:
        for span in soup.select("span.s_title"):
            label = norm(span.get_text())
            key = BIZINFO_DETAIL_LABELS.get(label)
            if not key:
                for lk, field_key in BIZINFO_DETAIL_LABELS.items():
                    if lk in label:
                        key = field_key
                        break
            if not key:
                continue
            txt_div = span.find_next_sibling("div", class_="txt")
            if not txt_div:
                continue
            val = norm(txt_div.get_text("\n", strip=True))
            if val and key not in result:
                result[key] = val[:12000] if key == "body" else val
        if "body" not in result:
            body = soup.select_one("article, .view_cont, #contents, main, .content")
            if body:
                result["body"] = body.get_text("\n", strip=True)[:12000]
    else:
        body = _extract_main_content(soup)
        if body:
            result["body"] = body[:12000]
    detail_tables = _extract_detail_tables(soup)
    if detail_tables["tables"]:
        result["tables"] = detail_tables
    return result


def enrich_item_from_detail(item: dict) -> dict:
    """상세 페이지를 조회해 description·deadline·지역 정보를 보강."""
    link = (item.get("link") or "").strip()
    if item.get("detail_enriched"):
        return item
    if not link:
        updated = _with_detail_extraction(
            item, DETAIL_FETCH_FAILED, "missing_detail_url")
        _persist_detail_extraction_meta(updated)
        return updated
    specialized = any(host in link for host in DETAIL_ENRICH_HOSTS)
    if not specialized:
        # 전용 호스트가 아니면, 리스트-온리(본문 미수집)일 때만 범용 보강
        if not GENERIC_DETAIL_ENRICH_ENABLED or not _should_generic_enrich(item, link):
            return item
    resp = _http_get(link, timeout=30)
    if resp is None:
        updated = _with_detail_extraction(
            item, DETAIL_FETCH_FAILED, "http_no_response")
        _persist_detail_extraction_meta(updated)
        return updated
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    if _RAW_STORE is not None:
        with _ENRICH_STORE_LOCK:
            _RAW_STORE.save_detail_html(item["id"], link, html_text)
    fields = _parse_detail_from_page(soup, link)
    if not any(str(value or "").strip() for value in fields.values()):
        updated = _with_detail_extraction(
            item, PARSE_FAILED, "no_extractable_detail")
        _persist_detail_extraction_meta(updated)
        return updated
    updated = {**item, "detail_enriched": True}
    detail_keys = set(fields)
    if fields.get("tables"):
        updated["detail_tables"] = fields["tables"]
    body = fields.get("body", "")
    if body:
        desc = (item.get("description") or "").strip()
        updated["description"] = f"{desc}\n{body}".strip() if desc else body
        detail_keys.add("description")
    if fields.get("region_field"):
        updated["region_field"] = fields["region_field"]
    # K-Startup 구조화 신호(업력/대상/주관기관 등) 전용 키로 보존 — 숫자 든 값은
    # description 에 합치지 않는다(매처가 멀티셀렉트를 오해석해 누락하는 것 방지).
    for k in ("business_age_text", "target_field", "target_age_field",
              "organizer_field", "exclude_target_field", "support_field"):
        if fields.get(k):
            updated[k] = fields[k]
    # 주관기관명은 author 가 비었을 때만 표시용으로 보강(지역 override 는 양쪽 다 본다).
    if fields.get("organizer_field") and not (updated.get("author") or "").strip():
        updated["author"] = fields["organizer_field"]
    period_src = fields.get("application_period_text") or updated.get("description", "")
    period: dict[str, str] = {}
    if fields.get("application_period_text"):
        # 기업마당 상세: 라벨 없이 "2026.06.18 ~ 2026.07.06" 만 오는 경우
        norm_period = re.sub(r"(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", fields["application_period_text"])
        dates = _parse_period_dates(norm_period)
        if dates:
            start, end = dates[0].isoformat(), dates[-1].isoformat()
            display = f"{start} ~ {end}" if start != end else end
            period = {"start": start, "end": end, "display": display, "label": "신청기간"}
    if not period.get("display"):
        if fields.get("application_period_text"):
            # 라벨 붙은 접수기간 텍스트 → 신뢰(전용/범용 공통)
            period_src = re.sub(
                r"(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", fields["application_period_text"],
            )
            period = extract_application_period(period_src)
        elif specialized:
            # 전용 호스트만 무라벨 본문에서도 마감 추정(검증된 경로)
            period = extract_application_period(period_src) or extract_application_period(body)
        else:
            # 범용: '신청/접수/모집기간' 라벨이 붙은 기간만 인정.
            # loose/축약 마감(label='축약마감')은 배제 — 과거 날짜 오추출로 open 공고를
            # closed 로 오판(누락)하는 것 방지(recall 우선). 검증된 extract_application_period 재사용.
            cand = extract_application_period(body)
            if cand.get("label") in APPLICATION_PERIOD_LABELS:
                period = cand
    if period.get("display"):
        updated["deadline"] = period["display"]
        updated["application_period"] = period
    elif specialized and not (updated.get("deadline") or "").strip():
        # 전용 호스트만: 상세만 있고 라벨이 없을 때 — 협약기간 등 비신청 라벨 구간은 제외
        # (범용은 무라벨 loose 추정 안 함 → 누락 방지)
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
    if period.get("display"):
        detail_keys.update({"deadline", "application_period"})
    updated = _with_detail_extraction(
        updated, EXTRACTION_SUCCESS, "detail_parsed", detail_keys=detail_keys)
    _persist_detail_extraction_meta(updated)
    return updated


def enrich_items(items: list[dict], limit: int = MAX_DETAIL_ENRICH) -> list[dict]:
    """신규 공고 중 상세 보강이 필요한 항목을 HTTP 상세 조회(동시 처리).
    ① 전용 호스트(구조화 파서) — 기업마당·K-Startup 은 별도 예산·최근게시 우선
    ② 리스트-온리(본문 미수집) 범용 보강 — 접수기간·지원금·성격 최대 복구."""
    try:
        from mail_core.matching.core_sources import (
            CORE_MAX_DETAIL_ENRICH,
            OTHER_SPECIALIZED_DETAIL_ENRICH,
            select_detail_enrich_targets,
        )
        specialized = select_detail_enrich_targets(
            items,
            specialized_hosts=DETAIL_ENRICH_HOSTS,
            core_limit=int(os.environ.get("MONITOR_CORE_DETAIL_ENRICH", CORE_MAX_DETAIL_ENRICH)),
            other_limit=min(int(limit), OTHER_SPECIALIZED_DETAIL_ENRICH),
            today=datetime.now(KST).date(),
        )
    except Exception:
        specialized = [
            it for it in items
            if any(h in (it.get("link") or "") for h in DETAIL_ENRICH_HOSTS)
            and not it.get("detail_enriched")
        ][:limit]
    generic: list[dict] = []
    if GENERIC_DETAIL_ENRICH_ENABLED:
        spec_ids = {it["id"] for it in specialized}
        for it in items:
            if it["id"] in spec_ids or it.get("detail_enriched"):
                continue
            link = (it.get("link") or "").strip()
            if any(h in link for h in DETAIL_ENRICH_HOSTS):
                continue  # 전용 호스트인데 limit 초과분 → 범용 대상 아님
            if _should_generic_enrich(it, link):
                generic.append(it)
        generic = generic[:MAX_GENERIC_DETAIL_ENRICH]
    targets = specialized + generic
    if not targets:
        return items
    log.info("상세 보강: 전용 %d + 범용 %d = %d건 (동시 %d)",
             len(specialized), len(generic), len(targets), DETAIL_ENRICH_WORKERS)
    from concurrent.futures import ThreadPoolExecutor

    def _one(it: dict) -> tuple[str, dict]:
        try:
            return it["id"], enrich_item_from_detail(it)
        except Exception as e:  # 한 건 실패가 전체 보강을 막지 않게 격리
            log.warning("상세 보강 실패 %s: %s", it.get("id"), e)
            failed = _with_detail_extraction(
                it, DETAIL_FETCH_FAILED, "detail_exception")
            _persist_detail_extraction_meta(failed)
            return it["id"], failed

    enriched_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=DETAIL_ENRICH_WORKERS) as pool:
        for iid, updated in pool.map(_one, targets):
            enriched_map[iid] = updated
    return [enriched_map.get(it["id"], it) for it in items]


def previous_business_day(from_dt: datetime | None = None, days_back: int = 1):
    """주말을 건너뛴 직전 영업일 계산."""
    day = (from_dt or datetime.now(KST)).date()
    remaining = max(1, days_back)
    while remaining:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


#: 오전/오후 발송 회차를 가르는 KST 시각. 예약(07:30·18:30 KST)보다 넉넉히 뒤에 둬서
#: GitHub Actions 예약 지연(실측 최대 ~1시간)에도 회차 판정이 흔들리지 않게 한다.
DELIVERY_PM_CUTOFF_HOUR = 14


def delivery_cycle_date(now: datetime | None = None) -> str:
    """발송 멱등 키의 기준 = 실행 당일(KST) + 발송 회차(`#am`/`#pm`).

    하루 2회 발송(07:30·18:30 KST, 2026-07-30 사용자 지정)에서 오후 실행이
    "오늘 이미 보냄"으로 스킵되지 않도록 회차를 키에 포함한다. 같은 회차의 재실행은
    계속 멱등으로 막힌다(크래시 후 재시도·중복 발송 방지).
    `days_back`·재조회창과는 무관하다.

    왜 실행 당일인가 (2026-07-28·29 실제 발송 누락 사고):
      기준일을 재조회창의 가장 오래된 날(`previous_business_day(now, days_back)`)로 쓰면
      `days_back` 을 늘리는 순간 기준일이 과거로 후퇴한다. 1→3 으로 바꾼 뒤(2026-07-25)
      기준일이 이미 발송 완료된 07-23·07-24 로 되돌아가, 멱등 게이트가 매일
      "이미 발송 완료"로 오판하고 수집·발송·커버리지 알림을 통째로 생략했다
      (07-28·07-29 run 이 2분 44초에 종료, 이틀치 digest 누락).
      실행 당일을 쓰면 하루에 정확히 한 세트가 되어 같은 날 재실행은 계속 멱등으로
      막히고(주말 재실행 2h+ 낭비 방지 의도 유지), 설정 변경이 미래 발송을 막지 못한다.
    날짜 필터·재조회 범위(`_recent_recheck_dates`)는 그대로 `days_back` 을 따른다.
    """
    dt = now or datetime.now(KST)
    slot = "am" if dt.hour < DELIVERY_PM_CUTOFF_HOUR else "pm"
    return f"{dt.date()}#{slot}"


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
    # 핵심 소스(PBLN/kstartup/…) 우선 보존 + 20xx 날짜키. 알파벳 꼬리 절단으로
    # 기업마당 id 가 통째로 사라지던 중복발송 사고를 막는다(seen_ids_prune).
    save_json(SEEN_IDS_PATH, prune_seen_ids(ids, max_keep=MAX_SEEN_IDS))

def load_sites() -> list[dict]:
    sites = load_json(SITES_PATH, [])
    active = [s for s in sites if s.get("enabled", True)]
    log.info("사이트: %d개 활성", len(active))
    return active

def load_groups() -> list[dict]:
    # 평문 groups.json 은 매칭 규칙만 가진다. 실제 수신자는 암호화된 private payload 로만 결합한다.
    # MAIL_GROUPS_JSON 은 이미 배포된 이전 Secret 형식과 테스트 호환을 위한 읽기 전용 이행 경로다.
    legacy_raw = os.environ.get("MAIL_GROUPS_JSON", "").strip()
    try:
        legacy_groups = bool(legacy_raw and isinstance(json.loads(legacy_raw), list))
    except json.JSONDecodeError:
        legacy_groups = False
    groups = _pii_config("MAIL_GROUPS_JSON", lambda: load_json(GROUPS_PATH, []))
    private_payload = private_config.load_private_payload()
    if private_payload:
        groups = private_config.merge_groups(groups, private_payload)
    else:
        groups = [
            {
                **dict(group),
                "tenant_id": private_config.normalize_tenant_id(group.get("tenant_id")),
                # 공개 파일에는 수신자를 신뢰하지 않는다. 배포 이전의 Secret 형식만 이행 허용.
                "recipients": list(group.get("recipients") or []) if legacy_groups else [],
            }
            for group in (groups or []) if isinstance(group, dict)
        ]
    active = [g for g in (groups or []) if g.get("active", True)]
    log.info("그룹: %d개 활성", len(active))
    return active

def load_settings() -> dict:
    default = {
        "date_filter_enabled": True,
        "days_back": 1,
        "raw_all_enabled": True,
        "raw_all_recipients": [],
        "claude_model": "claude-haiku-4-5-20251001",
        "claude_max_tokens": 4000,
        "fetch_max_workers": 10,
        # 기업 맞춤 정밀 매칭(2차 컷오프). 그룹에 company_id 연결 + 이 값 true 일 때만 적용.
        "company_match_enabled": False,
        # 게시일이 기준일(today)보다 이 일수 넘게 지난 공고를 '옛날 공고'로 강제 제외.
        # null(기본)이면 미적용 — 기존 '직전영업일 정확일치' 로직만 사용.
        "max_posted_age_days": None,
        # 날짜불명(게시일 못읽음) 공고 처리정책:
        #   strict=제외(검토대기) / recall=신청키워드·마감 살아있는 것만 포함 / all=전부 포함
        #   None이면 legacy include_date_unknown 으로 결정(True→all, False→strict).
        "date_unknown_policy": None,
        # 원문 저장(PC 로컬): docs/RAW_STORE.md
        "raw_store_enabled": False,
        "raw_store_retention_days": 30,
        "raw_store_max_detail_bytes": 800_000,
        "raw_store_gzip_detail": True,
    }
    settings = {**default, **load_json(SETTINGS_PATH, {})}
    private_payload = private_config.load_private_payload()
    if private_payload:
        settings = private_config.merge_settings(settings, private_payload)
    else:
        settings["tenant_id"] = private_config.normalize_tenant_id(settings.get("tenant_id"))
        settings["raw_all_recipients"] = []
    return settings


def _with_raw_store_stats(result: dict) -> dict:
    if _RAW_STORE is not None:
        result = {**result, **_RAW_STORE.summary()}
    return result


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


def _http_get(url: str, extra_headers: dict | None = None, timeout: int = 60, **kwargs) -> httpx.Response | None:
    """GET with 3-stage SSL fallback (bizinfo API·JSON 등 _soup 외 호출용)."""
    _ok, _why = net_guard.check_url(url)          # SSRF 가드(#20): 사설/내부 IP·비 http(s) 차단
    if not _ok:
        log.error("차단됨(SSRF 가드) %s: %s", url, _why)
        return None
    hdrs = {**HTTP_HEADERS, **(extra_headers or {})}
    last_err: Exception | None = None
    for stage in ("strict", "no_verify", "legacy"):
        verify: Any = True if stage == "strict" else (
            False if stage == "no_verify" else _legacy_ssl_ctx())
        try:
            with httpx.Client(timeout=timeout, headers=hdrs, follow_redirects=True,
                              verify=verify) as c:
                r = c.get(url, **kwargs)
                if not net_guard.is_safe(str(r.url)):  # 리다이렉트 최종 호스트 재검사
                    log.error("차단됨(SSRF 리다이렉트) %s → %s", url, r.url)
                    return None
                r.raise_for_status()
                return r
        except httpx.HTTPStatusError as e:
            log.error("접속 실패 %s: %s", url, e)
            return None
        except Exception as e:
            last_err = e
            continue
    log.error("접속 실패 %s: %s", url, last_err)
    return None


def _soup(url: str, extra_headers: dict | None = None, **kwargs):
    _ok, _why = net_guard.check_url(url)          # SSRF 가드(#20)
    if not _ok:
        log.error("차단됨(SSRF 가드) %s: %s", url, _why)
        return None
    hdrs = {**HTTP_HEADERS, **(extra_headers or {})}
    # 3단계 SSL 폴백: (1) 표준 검증 (2) 검증 해제 (3) legacy SSL ctx
    # 정상 사이트는 (1)에서 즉시 성공 → 기존 동작·속도 보존. SSL 실패만 폴백.
    # 네트워크/타임아웃 등 일시적 실패는 _HTTP_RETRIES 만큼 재시도한다 — 여러 소스가
    # 동시에 순간 실패(스케줄 실행 중 네트워크 블립)해 '0건 급락'/'수집실패' 알림이
    # 무더기로 뜨는 것을 줄인다. 4xx/5xx(HTTPStatusError)는 페이지 수준 오류라
    # 재시도가 무의미 → 즉시 None(폴백·재시도 안 함).
    last_err: Exception | None = None
    for attempt in range(_HTTP_RETRIES + 1):
        for stage in ("strict", "no_verify", "legacy"):
            verify: Any = True if stage == "strict" else (
                False if stage == "no_verify" else _legacy_ssl_ctx())
            try:
                with httpx.Client(timeout=30, headers=hdrs, follow_redirects=True,
                                  verify=verify) as c:
                    r = c.get(url, **kwargs)
                    if not net_guard.is_safe(str(r.url)):   # 리다이렉트 최종 호스트 재검사
                        log.error("차단됨(SSRF 리다이렉트) %s → %s", url, r.url); return None
                    r.raise_for_status()
                    return BeautifulSoup(r.text, "html.parser")
            except httpx.HTTPStatusError as e:
                log.error("접속 실패 %s: %s", url, e); return None  # 404 등은 폴백 무의미
            except Exception as e:
                last_err = e; continue
        if attempt < _HTTP_RETRIES:
            time.sleep(_HTTP_RETRY_BACKOFF * (attempt + 1))
    log.error("접속 실패 %s: %s", url, last_err); return None

def _item(id_, title, link, author, desc, deadline, source,
          posted_date="", is_aggregator=False) -> dict:
    # org=title 오염 차단(TASK-G05): 목록 파서가 제목을 주관기관 칸에 넣으면
    # 지역·키워드 판정이 제목 문자열에 오염된다 → 동일하면 author 를 비운다.
    title_n = norm(title)
    author_n = norm(author)
    if author_n and title_n and author_n == title_n:
        author_n = ""
    return {"id": id_, "title": title_n, "link": link, "author": author_n,
            "description": desc, "deadline": deadline, "source": source,
            "posted_date": posted_date, "is_aggregator": is_aggregator}


def _bizinfo_parse_item(it: dict, site_name: str, agg: bool) -> dict:
    """기업마당 API(직결·data.go.kr 공통) 원소 1건 → 표준 item. 필드명은 두 경로가 동일 계열."""
    iid = norm(it.get("pblancId", it.get("seq", "")))
    ttl = norm(it.get("pblancNm", it.get("title", "")))
    lnk = norm(it.get("pblancUrl", it.get("link", "")))
    if not iid:
        iid = f"bizinfo_{stable_id(ttl + lnk)}"
    posted = norm(it.get("regDt", it.get("pblancDt", it.get("creatPnttm", it.get("updtPnttm", "")))))
    if posted and len(posted) >= 10:
        posted = posted[:10]
    if not posted:
        posted = extract_date_from_text(norm(it.get("bsnsSumryCn", "")))
    item = _item(
        iid, ttl, lnk,
        norm(it.get("jrsdInsttNm", it.get("author", ""))),
        norm(it.get("bsnsSumryCn", it.get("description", ""))),
        norm(it.get("reqstBeginEndDe", it.get("reqstDt", ""))),
        site_name, posted, agg,
    )
    try:
        from mail_core.matching.core_sources import attach_bizinfo_structured
        return attach_bizinfo_structured(item, it)
    except Exception:
        item["core_source"] = "bizinfo"
        return item


def _fetch_bizinfo_direct(site: dict) -> list[dict]:
    """bizinfo.go.kr 직결 RSS-API 수집(워밍업 세션 + 빠른실패).

    ★ WAF 워밍업: 정부포털은 API 직타를 WAF 가 무응답 tarpit(→timeout) 시키는 경우가 있어,
      먼저 홈(referer)을 GET 해 쿠키를 받은 **같은 세션**으로 API 를 친다(TIPA WAF 우회와 동형).
    ★ 빠른실패: 정상 응답은 <2s 다. 차단이면 무한정 매달리지 말고 api_timeout(기본 30s)에 끊어
      과거 90s×재시도로 실행이 3~4시간 늘어지던 문제를 줄인다(닿으면 그대로 성공).
    실패 신호 규약은 종전과 동일 — 아무 것도 못 모으고 하드 실패면 RuntimeError.
    """
    page_unit = int(site.get("api_page_unit", 500))
    max_pages = int(site.get("api_max_pages", 4))
    retries = max(0, int(site.get("api_retries", 2)))
    timeout = int(site.get("api_timeout", 30))
    home = site.get("warmup_url", "https://www.bizinfo.go.kr/")
    items: list[dict] = []
    seen_ids: set[str] = set()
    agg = site.get("is_aggregator", True)
    params_base = {"crtfcKey": BIZINFO_API_KEY, "dataType": "json"}
    hdrs = {**HTTP_HEADERS, "Referer": home}

    def _warm(c: httpx.Client) -> None:
        try:  # best-effort — 실패해도 API 직타로 진행(쿠키 없이도 되면 그대로 됨)
            c.get(home, timeout=min(timeout, 15))
        except Exception as e:  # noqa: BLE001
            log.debug("기업마당 워밍업 생략(%s)", e)

    _pages_done, _stop_reason, _dup_pages = 0, "MAX_PAGES_HIT", 0
    for page in range(1, max_pages + 1):
        r = None
        for attempt in range(retries + 1):
            # 매 시도 새 세션(쿠키 초기화) + 워밍업 → API. SSL 폴백 3단계는 종전 유지.
            for stage in ("strict", "no_verify", "legacy"):
                verify: Any = True if stage == "strict" else (
                    False if stage == "no_verify" else _legacy_ssl_ctx())
                try:
                    with httpx.Client(timeout=timeout, headers=hdrs,
                                      follow_redirects=True, verify=verify) as c:
                        # 매 요청이 새 세션(쿠키 초기화)이라 워밍업도 매번 해야 한다 — page 1 에만
                        # 하면 page 2+·재시도 세션은 WAF 쿠키 없이 직타해 timeout 될 수 있다.
                        _warm(c)
                        resp = c.get(site["url"], params={
                            **params_base, "pageIndex": str(page), "pageUnit": str(page_unit)})
                        resp.raise_for_status()
                        r = resp
                        break
                except httpx.HTTPStatusError as e:
                    log.error("접속 실패 %s: %s", site["url"], e)
                    r = None
                    break
                except Exception:  # noqa: BLE001 — SSL/네트워크/타임아웃 → 다음 stage
                    r = None
                    continue
            if r is not None:
                break
            if attempt < retries:
                time.sleep(_HTTP_RETRY_BACKOFF * (attempt + 1))
        if r is None:
            if items:  # 부분 수집분은 보존
                log.error("기업마당 API 접속 실패(page %d) — 부분 수집 %d건 반환", page, len(items))
                break
            raise RuntimeError(f"기업마당 API 접속 실패 (page {page}, {retries + 1}회 시도)")
        try:
            data = r.json()
        except Exception as e:
            if items:
                log.error("기업마당 API JSON 파싱 실패(page %d): %s — 부분 수집 %d건 반환", page, e, len(items))
                break
            raise RuntimeError(f"기업마당 API JSON 파싱 실패 (page {page}): {e}") from e
        if err := data.get("reqErr"):
            if items:
                log.error("기업마당 API 오류(page %d): %s — 부분 수집 %d건 반환", page, err, len(items))
                break
            raise RuntimeError(f"기업마당 API 오류: {err}")
        raw = data.get("jsonArray", data.get("channel", {}).get("item", []))
        if isinstance(raw, dict):
            raw = [raw]
        _pages_done, _stop_reason = page, "MAX_PAGES_HIT"
        if not raw:
            _stop_reason = "EMPTY_PAGE"
            break
        _before = len(items)
        for it in raw:
            parsed = _bizinfo_parse_item(it, site["name"], agg)
            if parsed["id"] in seen_ids:
                continue
            seen_ids.add(parsed["id"])
            items.append(parsed)
        if len(items) == _before:
            _dup_pages += 1  # 이 페이지가 전부 기존 항목 = 같은 내용 반복 의심
        if len(raw) < page_unit:
            _stop_reason = "LAST_PAGE"
            break
    _page_stat(site.get("id", ""), stop_reason=_stop_reason, pages_fetched=_pages_done,
               duplicate_page=_dup_pages >= 2, items=len(items))
    return items


def _datagokr_rows(data: dict) -> list[dict]:
    """data.go.kr 응답 봉투에서 item 리스트를 꺼낸다(표준 response.body.items.item + 변형 허용)."""
    if not isinstance(data, dict):
        return []
    body = (data.get("response") or {}).get("body") if "response" in data else None
    rows = None
    if isinstance(body, dict):
        items = body.get("items")
        if isinstance(items, dict):
            rows = items.get("item")
        elif isinstance(items, list):
            rows = items
    if rows is None:  # 직결과 동일한 jsonArray 형태로 주는 오퍼레이션도 있음
        rows = data.get("jsonArray")
    if isinstance(rows, dict):
        rows = [rows]
    return rows or []


def _datagokr_error(data: dict) -> str:
    """data.go.kr 200-OK 에러 봉투에서 에러 메시지를 뽑는다(성공/무에러면 '').

    공공데이터포털은 인증키오류·트래픽초과 등을 HTTP 200 + header.resultCode 로 준다.
    이를 안 보면 빈 items 를 '정상 0건'으로 오인해(직결 reqErr 과 달리) 수집실패를 놓친다.
    성공 코드: '00'/'0000'(표준 header) · '00'(레거시 cmmMsgHeader).
    """
    if not isinstance(data, dict):
        return ""
    hdr = (data.get("response") or {}).get("header") if "response" in data else None
    if isinstance(hdr, dict):
        code = str(hdr.get("resultCode", "")).strip()
        if code and code not in ("00", "0000"):
            return f"{code} {hdr.get('resultMsg', '')}".strip()
    cmm = (data.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader")
    if isinstance(cmm, dict):
        code = str(cmm.get("returnReasonCode", "")).strip()
        if code and code not in ("00", "0000"):
            return f"{code} {cmm.get('errMsg', cmm.get('returnAuthMsg', ''))}".strip()
    return ""


def _fetch_bizinfo_datagokr(site: dict) -> list[dict]:
    """공공데이터포털(data.go.kr) 기업마당 지원사업정보 폴백 수집(영구 경로).

    bizinfo.go.kr 직결이 러너 IP 에서 차단될 때 사용. data.go.kr 은 API 전용 게이트웨이라
    WAF/지역차단이 없다. 엔드포인트·페이지 파라미터는 발급받은 오퍼레이션에 맞춰 sites.json 에서
    덮어쓸 수 있게 열어둔다(datagokr_url 등). 서비스키는 DATA_GO_KR_KEY 환경변수.
    """
    if not DATA_GO_KR_KEY:
        raise RuntimeError("DATA_GO_KR_KEY 미설정 — data.go.kr 폴백 비활성")
    # 실제 발급 엔드포인트(중기부 1421000/bizinfo). 요청변수 명세가 오퍼레이션마다 달라
    # 파라미터는 sites.json 의 datagokr_params 로 덮어쓸 수 있게 열어둔다(무코드 튜닝).
    url = site.get("datagokr_url", "https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService")
    rows_key = int(site.get("datagokr_num_rows", 500))
    max_pages = int(site.get("datagokr_max_pages", site.get("api_max_pages", 4)))
    timeout = int(site.get("api_timeout", 30))
    retries = max(0, int(site.get("api_retries", 2)))
    agg = site.get("is_aggregator", True)
    extra_params = site.get("datagokr_params", {})
    items: list[dict] = []
    seen_ids: set[str] = set()
    for page in range(1, max_pages + 1):
        # 직결과 동일하게 일시적 네트워크/5xx 블립은 api_retries 만큼 흡수(백오프).
        r = None
        for attempt in range(retries + 1):
            r = _http_get(url, timeout=timeout, params={
                "serviceKey": DATA_GO_KR_KEY, "returnType": "json", "dataType": "json",
                "numOfRows": str(rows_key), "pageNo": str(page), **extra_params})
            if r is not None:
                break
            if attempt < retries:
                time.sleep(_HTTP_RETRY_BACKOFF * (attempt + 1))
        if r is None:
            if items:
                log.error("기업마당 data.go.kr 접속 실패(page %d) — 부분 %d건", page, len(items))
                break
            raise RuntimeError(f"기업마당 data.go.kr 접속 실패 (page {page}, {retries + 1}회 시도)")
        try:
            data = r.json()
        except Exception as e:
            if items:
                break
            raise RuntimeError(f"기업마당 data.go.kr JSON 파싱 실패: {e}") from e
        # 직결 reqErr 과 동형: 200-OK 에러 봉투(인증키오류·트래픽초과)는 '진짜 0건'과 구분해 올린다.
        if err := _datagokr_error(data):
            if items:
                log.error("기업마당 data.go.kr 오류(page %d): %s — 부분 %d건", page, err, len(items))
                break
            raise RuntimeError(f"기업마당 data.go.kr 오류: {err}")
        rows = _datagokr_rows(data)
        if not rows:
            break
        for it in rows:
            parsed = _bizinfo_parse_item(it, site["name"], agg)
            if parsed["id"] in seen_ids:
                continue
            seen_ids.add(parsed["id"])
            items.append(parsed)
        if len(rows) < rows_key:
            break
    return items


def fetch_bizinfo(site: dict) -> list[dict]:
    # 기업마당 수집. 두 경로를 순서대로 시도한다:
    #   ① DATA_GO_KR_KEY 있으면 data.go.kr(공공데이터포털) 우선 — API 전용 게이트웨이라
    #      러너 IP WAF/지역차단이 없다(라이브 검증됨). bizinfo.go.kr 직결은 러너에서 거의 항상
    #      timeout 되므로, 직결을 먼저 시도하면 매 실행 ~90초를 헛되이 버린다 → data.go.kr 우선.
    #   ② 직결(bizinfo.go.kr RSS-API) — 키가 없거나 data.go.kr 이 하드 실패했을 때의 경로.
    #
    # ★ 실패 신호 규약 — 경로 하드 실패(접속/파싱/reqErr) 또는 fail-closed 0건이면
    #   다음 경로로 넘어가고, 전 경로 실패 시 예외를 올려 fetch_success=False 로 분류한다.
    #   정상 N건(>0)만 권위 응답으로 즉시 반환. 빈 목록 허용은 BIZINFO_ALLOW_EMPTY=1.
    if DATA_GO_KR_KEY:
        sources = [("data.go.kr", _fetch_bizinfo_datagokr), ("bizinfo 직결", _fetch_bizinfo_direct)]
    else:
        sources = [("bizinfo 직결", _fetch_bizinfo_direct)]

    hard_err: Exception | None = None
    # 앞선 경로가 죽고 뒤 경로가 살려낸 경우를 기록한다. 수집은 성공이라 로그가
    # INFO 로만 남아 조용히 묻히는데, 그 사이 안전망은 1개로 줄어 있다
    # (2026-08-02~ data.go.kr 이 매 실행 실패했지만 직결이 받쳐 아무도 몰랐다).
    failed_paths: list[str] = []
    _allow_empty = os.environ.get("BIZINFO_ALLOW_EMPTY", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    for label, fn in sources:
        try:
            got = fn(site)
            # ★ 기업마당 0건 fail-closed (TASK-03): 핵심소스 '진짜 0건'은 거의 없다.
            #   권위 응답이어도 0건이면 이 경로 실패로 보고 다음 경로를 시도한다.
            #   전 경로 0/실패면 아래 hard_err 로 올려 fetch_success=False 가 된다.
            #   BIZINFO_ALLOW_EMPTY=1 일 때만 빈 목록 반환을 허용.
            if not got and not _allow_empty:
                raise RuntimeError(
                    f"기업마당 {label} 0건 — fail-closed"
                    " (BIZINFO_ALLOW_EMPTY=1 로만 완화 가능)"
                )
        except Exception as e:  # noqa: BLE001 — 이 경로 하드 실패 → 다음 경로 시도
            log.error("기업마당 %s 실패: %s", label, e)
            failed_paths.append(f"{label}: {str(e)[:200]}")
            if hard_err is None:
                hard_err = e
            continue
        log.info("%s: %d건 (%s)", site["name"], len(got), label)
        if failed_paths:
            log.warning(
                "기업마당 경로 %d개 사망(%s) — '%s' 로 %d건 복구. "
                "남은 경로가 실패하면 즉시 0건이다.",
                len(failed_paths),
                ", ".join(p.split(":", 1)[0] for p in failed_paths),
                label, len(got),
            )
            _page_stat(site.get("id", ""), fallback_degraded=True,
                       fallback_failed_paths=failed_paths,
                       fallback_recovered_by=label)
        return got

    # 모든 경로가 하드 실패 → 수집실패 신호로 올린다.
    if hard_err is not None:
        raise hard_err
    log.info("%s: 0건", site["name"])
    return []


def fetch_myfair_legacy(site: dict) -> list[dict]:
    # 하위호환용 - fetch_myfair로 대체됨
    return fetch_myfair(site)


# K-Startup 목록 카드의 값 라벨 span 접두어 — 이 앞까지가 (분류·)주관기관 영역이다.
_KSTARTUP_SPAN_LABEL_PREFIXES = ("등록일자", "시작일자", "마감일자", "조회", "접수기간", "신청기간", "D-")


def _kstartup_cards_from_soup(soup: BeautifulSoup, clss: str, site: dict, seen_sn: set[str]) -> list[dict]:
    """K-Startup 목록 카드 파싱 — fetch_kstartup·다운로더 공통."""
    items: list[dict] = []
    agg = site.get("is_aggregator", False)
    base_url = site["url"]
    for card in soup.select(".notice"):
        a = card.select_one("a")
        title = strip_title_badges(norm(a.get_text() if a else ""))
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
        if sn and sn in seen_sn:
            continue
        if sn:
            seen_sn.add(sn)
        link = (f"{base_url}?pbancClssCd={clss}&schM=view&pbancSn={sn}") if sn else base_url
        spans = card.select("span.list")
        span_texts = [norm(sp.get_text()) for sp in spans]
        # 주관기관 = 날짜/조회 라벨 span 직전의 마지막 텍스트 span.
        # 카드에 따라 span.list[0] 이 사업분류('메이커 스페이스')나 제목 복제인 경우가
        # 있어(실측 2026-07-24), '첫 span=기관' 가정은 지원기관 오표기를 만들었다.
        org_cands: list[str] = []
        for st in span_texts:
            if any(st.startswith(p) for p in _KSTARTUP_SPAN_LABEL_PREFIXES):
                break
            if st and st != title:
                org_cands.append(st)
        org = org_cands[-1] if org_cands else (span_texts[0] if span_texts else "")
        dl = next((norm(sp.get_text().replace("마감일자", ""))
                   for sp in spans if "마감일자" in sp.get_text()), "")
        pm = re.search(r"등록일자\s*([\d.\-]{8,10})", card.get_text(" ", strip=True))
        posted = extract_date_from_text(pm.group(1)) if pm else ""
        flag = card.select_one(".flag:not(.day):not(.flag_agency)")
        flag_text = norm(flag.get_text()) if flag else ""
        iid = f"kstartup_{sn}" if sn else f"kstartup_{stable_id(title + org)}"
        item = _item(iid, title, link, org,
                     flag_text, dl,
                     site["name"], posted, agg)
        try:
            from mail_core.matching.core_sources import attach_kstartup_list_structured
            item = attach_kstartup_list_structured(
                item, flag_text=flag_text, clss=clss)
        except Exception:
            item["core_source"] = "kstartup"
        items.append(item)
    return items


def fetch_kstartup(site: dict) -> list[dict]:
    """K-Startup 진행중 공고 수집 — 공공 우선·민간 후순위·중복 안전.

    페이지 키는 반드시 `page` (pageIndex 무효, 실측 2026-07-26).
    종료는 '신규 0 연속 N회' + 분류별 max_pages 안전캡.
    """
    from mail_core.matching.kstartup_collect import (  # noqa: PLC0415
        build_list_params,
        class_plan,
        merge_unique_items,
        stop_reason_after_page,
    )

    plan = class_plan(site)
    items: list[dict] = []
    seen_sn: set[str] = set()
    seen_ids: set[str] = set()
    referer = site.get("referer") or site["url"]
    extra_hdr = {"Referer": referer}
    _pages_done = 0
    _stop_reason = "OK"
    _dup_pages = 0
    per_class: dict[str, int] = {}

    for step in plan:
        clss = step["clss"]
        label = step["label"]
        max_pages = int(step["max_pages"])
        view_count = int(step["view_count"])
        streak_limit = int(step["empty_new_streak"])
        empty_new_streak = 0
        class_new = 0

        for page in range(1, max_pages + 1):
            soup = _soup(
                site["url"],
                extra_headers=extra_hdr,
                params=build_list_params(page=page, clss=clss, view_count=view_count),
            )
            if not soup:
                _stop_reason = "PAGE_FETCH_FAILED"
                break

            # 카드 파싱(내부 seen_sn 으로 동일 sn 스킵) → 전역 id 병합
            page_items = _kstartup_cards_from_soup(soup, clss, site, seen_sn)
            raw_count = len(page_items)
            added, new_count = merge_unique_items(items, page_items, seen_ids)
            _pages_done += 1
            class_new += new_count

            if new_count == 0:
                empty_new_streak += 1
                if raw_count > 0:
                    _dup_pages += 1
            else:
                empty_new_streak = 0

            reason = stop_reason_after_page(
                page=page,
                max_pages=max_pages,
                raw_count=raw_count,
                new_count=new_count,
                empty_new_streak=empty_new_streak,
                streak_limit=streak_limit,
            )
            if reason:
                _stop_reason = f"{clss}:{reason}"
                break

        per_class[label] = class_new
        log.info("K-Startup %s: +%d건 (상한 %dp)", label, class_new, max_pages)

    try:
        _page_stat(
            site.get("id") or site.get("name") or "kstartup",
            pages_fetched=_pages_done,
            stop_reason=_stop_reason,
            duplicate_page=_dup_pages >= 2,
            items=len(items),
            public_items=per_class.get("공공", 0),
            private_items=per_class.get("민간", 0),
        )
    except Exception:
        pass
    log.info(
        "%s: %d건 (공공 %d + 민간 %d)",
        site["name"], len(items),
        per_class.get("공공", 0), per_class.get("민간", 0),
    )
    return items


# 페이지 링크 href 에서 흔히 쓰이는 페이지 파라미터(자동 탐지 보조용)
_PAGE_PARAM_RE = re.compile(
    r"[?&](?:page|pageIndex|pageNo|pageNum|pageNumber|currentPage|currentPageNo|"
    r"cpage|nPage|curPage|offset|start)="
    r"(\d+)", re.I)


def _next_page_url(soup: BeautifulSoup, base_url: str, next_no: int) -> str:
    """게시판 하단 페이지 링크에서 다음 페이지 URL 을 찾는다. 못 찾으면 빈 문자열.

    대부분의 정부·공공 게시판은 하단에 `1 2 3 4 5` 숫자 링크를 둔다. 그 중 다음 번호와
    텍스트가 일치하는 앵커를 고른다. `javascript:` 링크는 상세 URL 합성 규칙 없이는
    따라갈 수 없으므로 건너뛴다(무리하게 추측하지 않는다).
    """
    try:
        for a in soup.select("a[href]"):
            if a.get_text(strip=True) != str(next_no):
                continue
            href = a.get("href", "")
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue
            nxt = urljoin(base_url, href)
            if nxt.split("#")[0] == base_url.split("#")[0]:
                continue  # 같은 페이지로 돌아오는 링크
            page_match = _PAGE_PARAM_RE.search(nxt)
            if not page_match or int(page_match.group(1)) != next_no:
                continue  # 숫자 제목의 상세링크(id=2 등)를 페이지 링크로 오인하지 않는다.
            return nxt
    except Exception:
        pass
    return ""


def _generic_page_items(soup: BeautifulSoup, site: dict, page_url: str) -> list[dict]:
    """generic HTML 목록 한 페이지에서 공고 항목을 파싱한다.

    (fetch_html_generic 의 기존 행 파싱 로직 그대로 — 페이지네이션 지원을 위해
    함수로 분리만 했다. 동작 변경 없음.)
    """
    selectors = site.get("selectors", {})
    sel = selectors.get("row", "table tbody tr")
    date_selector = site.get("date_selector") or selectors.get("date", "")
    deadline_selector = site.get("deadline_selector") or selectors.get("deadline", "")
    items, agg = [], site.get("is_aggregator", False)
    for row in soup.select(sel):
        title_selector = selectors.get("title", "")
        link_selector = selectors.get("link", "a")
        a = row.select_one(link_selector) if link_selector else row.select_one("a")
        title = norm(a.get_text() if a else row.get_text())
        if title_selector:
            title = select_text(row, title_selector) or title
        title = strip_title_badges(title)
        if not title: continue
        href = a.get("href", "") if a else ""
        # 상대경로·중복링크 판정은 '지금 읽고 있는 페이지' 기준이어야 2페이지 이후도 정확하다.
        link = urljoin(page_url, href) if href else page_url
        bad_link = (not href or link.split("#")[0] == page_url.split("#")[0]
                    or href.startswith("javascript:"))
        if bad_link:
            # 목록 링크가 javascript:/#/onclick(글ID만) 인 사이트: selectors 의 합성 규칙으로 상세 URL 구성.
            # link_template + (link_id_attr=속성값 | link_arg_re=onclick/href 정규식 그룹). 미설정 사이트는 기존대로 skip(하위호환).
            tmpl = selectors.get("link_template")
            if tmpl and a is not None:
                idattr = selectors.get("link_id_attr")
                argre = selectors.get("link_arg_re")
                if idattr:
                    v = a.get(idattr, "")
                    grp = [v] if v else []
                elif argre:
                    m = re.search(argre, (a.get("onclick", "") or href))
                    grp = list(m.groups()) if m else []
                else:
                    grp = []
                if grp and all(grp):
                    link = urljoin(page_url, tmpl.format(*grp))
                else:
                    continue
            else:
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
    return items


def fetch_html_generic(site: dict) -> list[dict]:
    """generic HTML 목록 수집.

    기본은 **첫 페이지만**(max_pages 미설정 시 1) — 기존 동작을 그대로 보존한다.
    sites.json 에 `max_pages: N`(N>1) 을 준 소스만 다음 페이지를 따라간다(opt-in).
    다음 페이지 URL 은 하단 페이지 번호 링크에서 자동 탐지하며, 못 찾으면 즉시 멈춘다.
    """
    selectors = site.get("selectors", {})
    sel = selectors.get("row", "table tbody tr")
    try:
        max_pages = max(1, int(site.get("max_pages", 1)))
    except (TypeError, ValueError):
        max_pages = 1

    soup = _soup(site["url"])
    if not soup:
        # 접속/파싱 실패(soup=None)는 '진짜 0건'과 다르다 → 예외로 올려 상위가
        # fetch_success=False='수집실패'로 분류(커버리지 '0건 급락' 오탐·baseline 오염 방지).
        # 정상 응답인데 행이 0개면 soup 는 truthy → 아래에서 [] 반환(진짜 0건은 그대로).
        raise RuntimeError(f"{site.get('name', site.get('id', ''))} 접속 실패 (HTML 수집)")

    items = _generic_page_items(soup, site, site["url"])
    seen_ids = {it["id"] for it in items}
    page_url = site["url"]
    pages_fetched = 1
    stop_reason = "SINGLE_PAGE" if max_pages == 1 else "LAST_PAGE"
    dup_pages = 0

    for page_no in range(2, max_pages + 1):
        next_url = _next_page_url(soup, page_url, page_no)
        if not next_url:
            stop_reason = "NO_NEXT_LINK"
            break
        soup = _soup(next_url)
        if not soup:
            # 2페이지 이후 실패는 1페이지 수집분을 버릴 이유가 없다 — 부분 수집으로 계속.
            stop_reason = "PAGE_FETCH_FAILED"
            break
        page_url = next_url
        pages_fetched = page_no
        page_items = _generic_page_items(soup, site, next_url)
        fresh = [it for it in page_items if it["id"] not in seen_ids]
        if not fresh:
            # 다음 페이지가 이전과 같은 내용 = 페이지 파라미터가 안 먹는 사이트
            dup_pages += 1
            stop_reason = "DUPLICATE_PAGE"
            break
        seen_ids.update(it["id"] for it in fresh)
        items.extend(fresh)
        if page_no == max_pages:
            stop_reason = "MAX_PAGES_HIT"

    _page_stat(site.get("id", ""), stop_reason=stop_reason, pages_fetched=pages_fetched,
               duplicate_page=dup_pages > 0, row_candidates=len(soup.select(sel)) if soup else 0,
               items=len(items))
    log.info("%s: %d건%s", site["name"], len(items),
             f" ({pages_fetched}p)" if pages_fetched > 1 else "")
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
                    it = _item(
                        iid, title, site["url"], "소상공인시장진흥공단",
                        " / ".join(desc_parts), "", site["name"], posted, agg,
                    )
                    # 소진공 정책자금은 전국 소상공인 대상 → 지역 단서가 없어 '지역 미상'으로
                    #  하드컷 되어 발송 0건이던 문제 수정. region_field='전국'으로 명시(사실 정확)해
                    #  전국 공고로 인정 → 정책자금 키워드 보유 그룹에 정상 전달(누락 방지·recall).
                    it["region_field"] = "전국"
                    items.append(it)
    except Exception as e:
        log.error("소진공 정책자금 공지 API 실패: %s", e)
        return []

    log.info("%s: %d건", site["name"], len(items))
    return items


def _is_semas_policy_fund_notice(title: str, category: str) -> bool:
    if category == "대출정보":
        return True
    return any(keyword in title for keyword in ("정책자금", "자금", "대출", "상환", "융자"))


def fetch_smart_factory(site: dict) -> list[dict]:
    """스마트공장 사업관리시스템 '사업공고'(접수중) 수집.

    사이트가 React SPA + WAF(elevisor) 라 html_table 로는 0건(HTML 에 <table> 없음).
    실제 목록은 POST .../bsnsPbanc/selectBsnsPbancPage.do (JSON, key=list 필수).
    rcptStts=ING(접수중)만 받아 마감 누수를 줄인다. 상세는 SPA state 라우팅이라
    딥링크가 불가 → 링크는 목록 페이지로 둔다(클릭 시 공고 목록 화면).
    """
    list_url = site["url"].split("#")[0].rstrip("/")
    api_url = list_url + "/selectBsnsPbancPage.do"
    headers = {
        **HTTP_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": list_url,
        "Origin": "https://www.smart-factory.kr",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        max_pages = max(1, int(site.get("max_pages", 8)))
    except (TypeError, ValueError):
        max_pages = 8
    page_unit, agg = 10, site.get("is_aggregator", False)

    def _collect(verify: Any) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        with httpx.Client(timeout=30, headers=headers,
                          follow_redirects=True, verify=verify) as c:
            try:
                c.get("https://www.smart-factory.kr/")  # WAF/elevisor 세션 쿠키 선확보
            except httpx.HTTPError:
                pass
            for page_no in range(1, max_pages + 1):
                payload = {
                    "key": "list", "bizYr": "", "bizClsfYrNm": "", "dtlPbancNm": "",
                    "rcptStts": "ING", "ordrSe": "REG",
                    "currentPage": page_no, "pageUnit": page_unit,
                }
                r = c.post(api_url, content=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                r.raise_for_status()
                data = r.json()
                rows = data.get("pbancList") or []
                if not rows:
                    break
                for row in rows:
                    title = norm(row.get("dtlPbancNm", ""))
                    pbanc_id = norm(row.get("pbancId", ""))
                    if not title or not pbanc_id or pbanc_id in seen:
                        continue
                    seen.add(pbanc_id)
                    posted = norm(row.get("pbancYmd", ""))
                    rcpt = norm(row.get("rcptYmdDa2001", "")) or norm(row.get("rcptYmdDa2002", ""))
                    ymd = re.findall(r"\d{4}-\d{2}-\d{2}", rcpt)
                    deadline = " ~ ".join(ymd[:2]) if ymd else ""
                    biz = norm(row.get("bizClsfYrNm", ""))
                    pbanc_no = norm(row.get("pbancNo", ""))
                    desc = " / ".join(p for p in [
                        f"사업: {biz}" if biz else "",
                        f"공고번호: {pbanc_no}" if pbanc_no else "",
                    ] if p)
                    out.append(_item(f"{site['id']}_{pbanc_id}", title, list_url,
                                     "스마트제조혁신추진단", desc, deadline,
                                     site["name"], posted, agg))
                try:
                    total = int((data.get("paginationInfo") or {}).get("totalCount", 0))
                except (TypeError, ValueError):
                    total = 0
                if total and page_no * page_unit >= total:
                    break
        return out

    try:
        try:
            items = _collect(True)
        except httpx.ConnectError:
            items = _collect(False)   # 정부 사이트 SSL 체인 폴백
    except Exception as e:
        log.error("스마트공장 사업공고 API 실패: %s", e)
        return []
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_ripc(site: dict) -> list[dict]:
    """지역지식재산센터(RIPC PMS) 지원사업 공고 수집.

    목록 페이지(list.do)는 빈 테이블 껍데기 + AJAX 로딩이라 html_table 로는 0건.
    실제 목록은 POST .../notice/getNoticeList.do (JSON, 공개·로그인 불요). 최신순 정렬이라
    앞쪽 몇 페이지만 받아 신규 공고를 잡고, 날짜/마감 필터는 모니터가 처리한다. 상세는 신청자
    포털(로그인) 라우팅이라 딥링크 불가 → 링크는 목록 페이지. 제목의 [부산] 등 지역태그는
    그대로 둬 지역 매칭이 활용한다.
    """
    list_url = site["url"].split("#")[0].rstrip("/")
    api_url = list_url.rsplit("/", 1)[0] + "/getNoticeList.do"   # .../notice/getNoticeList.do
    headers = {
        **HTTP_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Referer": list_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        max_pages = max(1, int(site.get("max_pages", 5)))
    except (TypeError, ValueError):
        max_pages = 5
    agg = site.get("is_aggregator", False)

    def _collect(verify: Any) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        with httpx.Client(timeout=30, headers=headers,
                          follow_redirects=True, verify=verify) as c:
            try:
                c.get(list_url)   # 세션 쿠키 선확보
            except httpx.HTTPError:
                pass
            for page_no in range(1, max_pages + 1):
                # ★페이징 파라미터는 currentPageNo (currentPage/pageIndex 는 서버가 무시 → 1페이지 고정)
                r = c.post(api_url, data={"currentPageNo": str(page_no)})
                r.raise_for_status()
                result = (r.json() or {}).get("result") or {}
                rows = result.get("noticeList") or []
                if not rows:
                    break
                for row in rows:
                    title = norm(row.get("noticeTitle", ""))
                    seq = norm(str(row.get("noticeSeq", "")))
                    if not title or not seq or seq == "0" or seq in seen:
                        continue
                    seen.add(seq)
                    posted = norm(row.get("writeTimeStr", ""))
                    sd = re.findall(r"\d{4}-\d{2}-\d{2}", norm(row.get("startDateStr", "")))
                    ed = re.findall(r"\d{4}-\d{2}-\d{2}", norm(row.get("endDateStr", "")))
                    deadline = " ~ ".join([d for d in [sd[0] if sd else "", ed[0] if ed else ""] if d])
                    center = norm(row.get("centerName", ""))
                    cat = " ".join(p for p in [norm(row.get("bizCategory1Name", "")),
                                               norm(row.get("bizCategory2Name", ""))] if p)
                    notice_no = norm(row.get("noticeNo", ""))
                    desc = " / ".join(p for p in [
                        f"센터: {center}" if center else "",
                        f"분야: {cat}" if cat else "",
                        f"공고번호: {notice_no}" if notice_no else "",
                    ] if p)
                    out.append(_item(f"{site['id']}_{seq}", title, list_url,
                                     ("지역지식재산센터" + (f" {center}" if center else "")),
                                     desc, deadline, site["name"], posted, agg))
                try:
                    total_pages = int(result.get("totalPageCount", 0))
                except (TypeError, ValueError):
                    total_pages = 0
                if total_pages and page_no >= total_pages:
                    break
        return out

    try:
        try:
            items = _collect(True)
        except httpx.ConnectError:
            items = _collect(False)   # 정부 사이트 SSL 체인 폴백
    except Exception as e:
        log.error("RIPC 공고 API 실패: %s", e)
        return []
    log.info("%s: %d건", site["name"], len(items))
    return items


_KOTRA_LINK_RE = re.compile(r"\('([^']+selectBizMntInfoDetail\.do[^']+)'\)")


def fetch_kotra_biz(site: dict) -> list[dict]:
    """KOTRA 사업신청(subList/20000020753) 공고 수집.

    목록이 정적 <table> 이 아니라 POST-AJAX(selectBmBizAllListAjax.do)로 HTML 조각을
    렌더 → html_table 로는 0건. 세션쿠키 선확보 후 POST, div.card 파싱. 링크는
    javascript onclick 의 selectBizMntInfoDetail.do 상대경로를 합성(딥링크)."""
    base = "https://www.kotra.or.kr"
    list_url = site["url"].split("#")[0]
    api_url = base + "/module/subhome/bizAply/selectBmBizAllListAjax.do"
    headers = {**HTTP_HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": list_url,
               "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    try:
        max_pages = max(1, int(site.get("max_pages", 5)))
    except (TypeError, ValueError):
        max_pages = 5
    agg = site.get("is_aggregator", False)
    items: list[dict] = []
    seen: set[str] = set()
    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True, verify=False) as c:
            try:
                c.get(list_url)   # 세션쿠키 선확보
            except httpx.HTTPError:
                pass
            for page_no in range(1, max_pages + 1):
                r = c.post(api_url, data={"pageNo": str(page_no), "pageSize": "10",
                                          "collection": "business_application", "sch_nation_cd": "Y"})
                r.raise_for_status()
                soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")
                cards = soup.select("div.card")
                if not cards:
                    break
                for card in cards:
                    a = card.select_one("a.card-tit")
                    title = norm(a.get_text() if a else "")
                    href = a.get("href", "") if a else ""
                    mm = _KOTRA_LINK_RE.search(href)
                    if not title or not mm:
                        continue
                    rel = mm.group(1)
                    idm = re.search(r"dtlBizMntNo=([A-Za-z0-9]+)", rel)
                    bid = idm.group(1) if idm else stable_id(title)
                    if bid in seen:
                        continue
                    seen.add(bid)
                    deadline = ""
                    for dt in card.select("dl.card-meta-data dt"):
                        if "신청기간" in dt.get_text():
                            dd = dt.find_next("dd")
                            ymd = re.findall(r"\d{4}-\d{2}-\d{2}", norm(dd.get_text())) if dd else []
                            deadline = " ~ ".join(ymd[:2]) if ymd else ""
                            break
                    items.append(_item(f"{site['id']}_{bid}", title, urljoin(base, rel),
                                       "KOTRA", "", deadline, site["name"], "", agg))
    except Exception as e:
        log.error("KOTRA 사업신청 API 실패: %s", e)
        return []
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_kosme(site: dict) -> list[dict]:
    """중소벤처기업진흥공단(KOSME) 사업공고 수집.

    목록이 POST JSON(notice_list.json, activatedTab=01=사업공고 탭). 세션쿠키 선확보 후
    POST, ds_infoList 파싱. TITL_NM=제목/REG_DTM=게시일/VALI_DT=마감/SLNO=상세id."""
    base = "https://www.kosmes.or.kr"
    api_url = base + "/sh/nts/notice_list.json"
    headers = {**HTTP_HEADERS, "Referer": site["url"], "X-Requested-With": "XMLHttpRequest",
               "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
    agg = site.get("is_aggregator", False)
    try:
        row_count = max(10, int(site.get("row_count", 50)))
    except (TypeError, ValueError):
        row_count = 50
    items: list[dict] = []
    seen: set[str] = set()
    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True, verify=False) as c:
            try:
                c.get(site["url"])   # 세션쿠키 선확보
            except httpx.HTTPError:
                pass
            r = c.post(api_url, data={"nowPage": "1", "pageCount": "10", "rowCount": str(row_count),
                                      "param": "proc=List", "bKind": "popluar", "activatedTab": "01"})
            r.raise_for_status()
            for row in (r.json().get("ds_infoList") or []):
                title = norm(row.get("TITL_NM", ""))
                slno = norm(str(row.get("SLNO", "")))
                if not title or not slno or slno in seen:
                    continue
                seen.add(slno)
                posted = extract_date_from_text(norm(row.get("REG_DTM", "")) or norm(row.get("UPDT_DTM", "")))
                deadline = extract_date_from_text(norm(row.get("VALI_DT", "")))
                link = f"{base}/nsh/SH/NTS/SHNTS001F0.do?seqNo={slno}&tabPage=01"
                items.append(_item(f"{site['id']}_{slno}", title, link, "중소벤처기업진흥공단",
                                   "", deadline, site["name"], posted, agg))
    except Exception as e:
        log.error("KOSME 공고 API 실패: %s", e)
        return []
    log.info("%s: %d건", site["name"], len(items))
    return items


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


# ── TIPA (중소기업기술정보진흥원 · 기정원소식) ────────────────────────────────
def fetch_tipa(site: dict) -> list[dict]:
    """TIPA 알림마당 공고 목록 수집.

    tipa.or.kr(CodeIgniter)은 세션쿠키(ci_session)·Referer 없이 목록을 직접 GET 하면
    "The action you have requested is not allowed." 차단 페이지(HTTP 200, 테이블 0개)로
    응답하고 /eng 로 돌려보낸다. 그래서 세션·Referer 없는 html_table 로는 조용히 0건이
    되어 '진짜 0건'으로 오분류(수집 실패가 감지되지 않음)됐다.
    → 홈으로 세션쿠키를 선확보한 뒤 Referer 를 붙여 목록을 GET 한다.
    링크는 td.subject a 의 상대경로(/s040101/view/...)를 절대경로로 합성한다.
    """
    base = "https://www.tipa.or.kr"
    list_url = site["url"]
    headers = {**HTTP_HEADERS, "Referer": base + "/"}
    agg = site.get("is_aggregator", False)
    soup = None
    last_err: Exception | None = None
    for stage in ("strict", "no_verify", "legacy"):
        verify: Any = True if stage == "strict" else (
            False if stage == "no_verify" else _legacy_ssl_ctx())
        try:
            with httpx.Client(timeout=30, headers=headers, follow_redirects=True,
                              verify=verify) as c:
                c.get(base + "/")   # ci_session/csrf 쿠키 선확보(WAF 통과)
                r = c.get(list_url)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                break
        except httpx.HTTPStatusError as e:
            log.error("TIPA 접속 실패 %s: %s", list_url, e)
            raise RuntimeError(f"{site.get('name', 'TIPA')} 접속 실패 (HTML 수집)")
        except Exception as e:
            last_err = e
            continue
    if soup is None:
        raise RuntimeError(f"{site.get('name', 'TIPA')} 접속 실패: {last_err}")

    rows = soup.select("table tbody tr")
    if not rows:
        # 목록 테이블이 없다 = 차단 페이지(로/eng 리다이렉트)·구조 변경 → '진짜 0건'이 아니라
        # 수집 실패로 올려 커버리지 알림이 '수집실패'로 정확히 표기되게 한다(조용한 0건 방지).
        raise RuntimeError(f"{site.get('name', 'TIPA')} 목록 파싱 실패(행 0) — 차단/구조변경 의심")
    items: list[dict] = []
    for tr in rows:
        a = tr.select_one("td.subject a") or tr.select_one("a")
        if not a:
            continue
        title = norm(a.get("title") or a.get_text())
        if not title or len(title) < 5:
            continue
        href = a.get("href", "")
        link = urljoin(list_url, href) if href else list_url
        td_text = " ".join(td.get_text(" ", strip=True) for td in tr.select("td"))
        posted = extract_date_from_text(td_text)
        iid = f"{site['id']}_{stable_id(title + link)}"
        items.append(_item(iid, title, link, site["name"], "", "",
                           site["name"], posted, agg))
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
    """ITP 게시판: a[href='javascript:fncShow(seq)'] → 상세 URL 구성.
    PageNum 페이지네이션(fncBoardPage→frmSearch.PageNum)을 순회하되 최근 N페이지만 수집.
    (게시판이 수년치 아카이브 300건+ → 전량은 느리고 무의미. 모니터는 D-1 등록분만 발송하므로
     최근 페이지면 충분. 과거엔 1페이지만 받아 게시 많은 날 누락 위험이 있었음)
    tmid 파라미터로 게시판 구분 (13=사업공고, 15=공지, 36=마케팅센터 등)
    """
    BASE   = "https://www.itp.or.kr"
    DETAIL = BASE + "/intro.asp"
    base_url = site["url"]
    sep      = "&" if "?" in base_url else "?"

    # tmid 추출
    tmid_m = re.search(r"tmid=(\d+)", base_url)
    tmid   = tmid_m.group(1) if tmid_m else "15"

    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    max_pages = site.get("max_pages", 3)   # 최근 N페이지만(아카이브 전량 X). 필요시 site["max_pages"]로 상향
    for cp in range(1, max_pages + 1):
        soup = _soup(f"{base_url}{sep}PageNum={cp}", extra_headers={"Referer": BASE + "/"})
        if not soup: break
        page_new = 0
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
            if seq in seen: continue        # 고정 공지가 매 페이지 반복 → seq로 중복 제거
            seen.add(seq)
            page_new += 1
            link = f"{DETAIL}?tmid={tmid}&mode=view&seq={seq}"
            iid  = f"itp_{tmid}_{seq}"
            tds  = tr.select("td")
            td_text = " ".join(td.get_text(strip=True) for td in tds)
            dates   = re.findall(r"\d{4}[.\-]\d{2}[.\-]\d{2}", td_text)
            posted  = dates[0].replace(".", "-") if dates else ""
            items.append(_item(iid, title, link, "인천테크노파크(ITP)",
                               "", "", site["name"], posted, agg))
        if page_new == 0:  # 새 공고 없음(끝 도달 또는 전부 중복) → 종료
            break
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_nipa(site: dict) -> list[dict]:
    """a[href*='nttDetail'] 패턴, relative → absolute 변환.
    curPage 페이지네이션을 순회해 전체 수집(과거엔 1페이지 10건만 받아 대량 누락).
    참고: URL의 tab 파라미터는 서버가 무시하고 bbsNo 전체 목록을 반환 → 실측 ~207페이지/2067건.
    페이지에 새 공고가 0건이면(page_new==0) 끝에 도달한 것이라 자연 종료하므로,
    max_pages 는 무한루프 방지용 안전 상한일 뿐(전량 수집이 기본).
    """
    BASE = "https://www.nipa.kr/home/bsnsAll/0/"
    items, agg = [], site.get("is_aggregator", False)
    seen = set()
    base_url  = site["url"]
    sep       = "&" if "?" in base_url else "?"
    max_pages = site.get("max_pages", 300)  # 전량 수집 안전 상한(실측 ~207페이지) — site 설정으로 조정 가능
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
            it = _item(iid, title, link, "정보통신산업진흥원(NIPA)",
                       "", deadline, site["name"], posted, agg)
            # NIPA(정보통신산업진흥원)는 전국 대상 국가기관 ICT/SW/AI 사업 → 목록에 지역
            #  단서가 없어 지역 미상('확인 필요' 하단)으로 강등돼 AI 공고가 상단에 0건이던
            #  문제 수정. region_field='전국'으로 명시(사실 정확)해 전국 공고로 인정 →
            #  AI 키워드 보유 그룹(서울/전국 AI팀 등) 본문 상단에 정상 노출(누락 방지·recall).
            #  본문에 타지역 신청자-한정 단서가 있으면 _resolve_applicant_region_scope 가
            #  전국을 무시(precision) → 특정 지역 공고 오포함은 방지된다.
            it["region_field"] = "전국"
            items.append(it)
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
    if not soup:
        # 접속 실패는 '진짜 0건'과 다르다 → 예외로 올려 '수집실패'로 분류(0건 급락 오탐 방지).
        raise RuntimeError(f"{site['name']} 접속 실패 (중기부 HTML 수집)")
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
    """인천광역시 고시/공고(announce.incheon.go.kr citynet) 목록 수집.

    tr[onclick="viewData('sno','gbn')"] 행 = [번호, 제목, 부서, 게시일, 조회].
    ※기존에 긁던 www.incheon.go.kr/IC010205 는 2026-07 현재 '보도자료' 게시판이라
    음악축제 보도자료가 'AI' 키워드로 그룹 digest 에 오르던 오탐원이었다(실사고 2026-07-24).
    상세 URL 은 목록 페이지의 viewData() 스크립트가 조립하는 주소를 그대로 재현한다."""
    soup = _soup(site["url"])
    if not soup:
        return []
    items, agg = [], site.get("is_aggregator", False)
    seen: set[str] = set()
    for tr in soup.select("tr[onclick]"):
        m = re.search(r"viewData\('([^']+)'\s*,\s*'([^']*)'\)", tr.get("onclick", ""))
        if not m:
            continue
        sno, gbn = m.group(1), m.group(2)
        if sno in seen:
            continue
        seen.add(sno)
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        title = strip_title_badges(norm(tds[1].get_text()))
        if not title or len(title) < 4:
            continue
        author = norm(tds[2].get_text()) or "인천광역시"
        posted = extract_date_from_text(tds[3].get_text())
        link = (
            "http://announce.incheon.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do"
            f"?command=searchDetail&flag=gosiGL&svp=Y&sido=ic&sno={sno}&gosiGbn={gbn}"
        )
        items.append(_item(
            f"incheon_city_{sno}", title, link, author,
            "", "", site["name"], posted, agg,
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
        # 목록 td에 날짜가 등록일+마감일 2개 이상이면 마지막을 접수마감으로
        deadline = dates[-1].replace(".", "-") if len(dates) >= 2 else ""
        items.append(_item(iid, title, link, "중소기업혁신바우처(중소벤처기업부)",
                           "", deadline, site["name"], posted, agg))
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


# ── 한양대학교 창업지원단 신규사업공고 ────────────────────────────────────────
def fetch_hanyang_startup(site: dict) -> list[dict]:
    """한양대 창업지원단 게시판(Next.js SPA) 공고 수집.

    startup.hanyang.ac.kr 은 React/Next.js SPA 라 정적 HTML 에 목록이 없다(html_table
    로는 0건). 목록은 JSON API `/api/board/content?boardEnName={보드}&pageNo=N` 이
    {data:{list:[{contentId,title,regDate,categoryCodeName,...}]}} 로 응답한다(페이지는
    `page` 파라미터로 이동 — pageNo 는 서버가 무시하고 1페이지만 반환한다).
    상세(사용자용) 링크는 `/board/{보드}/view/{contentId}` 로 합성한다.
    보드명은 URL(/board/<name>/list)에서 추출하며 기본값은 startup_info(신규사업공고).
    """
    base = "https://startup.hanyang.ac.kr"
    m = re.search(r"/board/([a-zA-Z0-9_]+)", site.get("url", ""))
    board = m.group(1) if m else "startup_info"
    api = f"{base}/api/board/content"
    headers = {**HTTP_HEADERS, "Referer": site.get("url", base),
               "Accept": "application/json,*/*"}
    agg = site.get("is_aggregator", False)
    try:
        max_pages = max(1, int(site.get("max_pages", 3)))
    except (TypeError, ValueError):
        max_pages = 3
    items: list[dict] = []
    seen: set[str] = set()
    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True,
                          verify=False) as c:
            for page_no in range(1, max_pages + 1):
                r = c.get(api, params={"boardEnName": board, "page": page_no})
                r.raise_for_status()
                rows = (r.json().get("data") or {}).get("list") or []
                if not rows:
                    break
                for row in rows:
                    cid = row.get("contentId")
                    title = norm(row.get("title", ""))
                    if not cid or not title or cid in seen:
                        continue
                    seen.add(cid)
                    link = f"{base}/board/{board}/view/{cid}"
                    posted = (row.get("regDate") or "")[:10]
                    # 카테고리(교육/행사·네트워크/사업화/R&D/시설/기타)를 지원내용 힌트로 보존.
                    cat = norm(row.get("categoryCodeName", ""))
                    desc = f"[{cat}]" if cat else ""
                    items.append(_item(f"{site['id']}_{cid}", title, link,
                                       "한양대학교 창업지원단", desc, "",
                                       site["name"], posted, agg))
    except Exception as e:
        # 하드 실패(접속/JSON 파싱)는 '진짜 0건'과 구분해 예외로 올려 '수집실패'로 분류.
        log.error("%s API 실패: %s", site.get("name", "한양대 창업"), e)
        raise RuntimeError(f"{site.get('name', '한양대 창업')} 수집 실패 (API)")
    log.info("%s: %d건", site["name"], len(items))
    return items


FETCHERS = {
    "bizinfo_api":        fetch_bizinfo,
    "myfair_html":        fetch_myfair,
    "kstartup_html":      fetch_kstartup,
    "kita_html":          fetch_kita,
    "iris_api":           fetch_iris,
    "smtech_html":        fetch_smtech,
    "tipa_html":          fetch_tipa,
    "hanyang_startup_api": fetch_hanyang_startup,
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
    "smartfactory_api":   fetch_smart_factory,
    "ripc_api":           fetch_ripc,
    "kotra_biz_api":      fetch_kotra_biz,
    "kosme_api":          fetch_kosme,
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


_COVERAGE_ERROR_CONTENT_HINTS = (
    "captcha", "access denied", "forbidden", "login required", "log in required",
    "service unavailable", "under maintenance", "temporarily unavailable",
    "로그인 후", "로그인이 필요", "자동입력방지", "보안문자",
    "접근 권한", "접근이 제한", "서비스 점검", "시스템 점검",
    "오류가 발생", "페이지를 찾을 수 없",
)


def _coverage_item_quality(items: list[Any]) -> tuple[int, int]:
    """(필수필드 정상 건수, 오류 화면 의심 건수). 원문·개인정보는 저장하지 않는다."""
    valid_count = 0
    suspicious_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        required = (item.get("id"), item.get("title"), item.get("link"))
        if all(str(value or "").strip() for value in required):
            valid_count += 1
        text = " ".join(
            str(item.get(key) or "") for key in ("title", "description", "author")
        ).casefold()
        if any(hint in text for hint in _COVERAGE_ERROR_CONTENT_HINTS):
            suspicious_count += 1
    return valid_count, suspicious_count


def _coverage_risk_level(row: dict) -> str:
    if not row.get("enabled", True):
        return "낮음"
    if row.get("fetch_error") or not row.get("fetch_success"):
        return "높음"
    item_count = int(row.get("item_count", 0) or 0)
    if item_count > 0:
        if int(row.get("suspicious_content_count", 0) or 0) / item_count >= 0.5:
            return "높음"
        if int(row.get("valid_record_count", item_count) or 0) / item_count < 0.8:
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
            # P0 수집누락 탐지용 — 키는 항상 존재하게 두어 판정부가 분기하지 않게 한다
            "detail_link_ok_count": 0,
            "valid_record_count": 0,
            "suspicious_content_count": 0,
            "collect_status": "",
            "reason_codes": [],
            "risk_level": "",
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
            fetched = fn(site)
            if fetched is None:
                items = []
            elif isinstance(fetched, list):
                items = fetched
            elif isinstance(fetched, (dict, str, bytes)):
                items = [fetched]
            else:
                items = list(fetched)
            row["fetch_success"] = True
            row["item_count"] = len(items)
            valid_count, suspicious_count = _coverage_item_quality(items)
            row["valid_record_count"] = valid_count
            row["suspicious_content_count"] = suspicious_count
            dict_items = [
                {**it, "posted_date": str(it.get("posted_date") or "")}
                for it in items if isinstance(it, dict)
            ]
            matched, unknown, _excl = partition_posted_dates(dict_items, days_back)
            row["posted_parsed_count"] = len(matched)
            row["date_unknown_count"] = len(unknown)
            row["today_target_count"] = len(matched)
            # 중복제거 전·후 건수 — 같은 id 가 여러 번 잡히면 목록 파싱이 흔들린 신호
            unique_ids = {it.get("id") for it in dict_items if it.get("id")}
            row["dedup_removed_estimate"] = max(0, len(items) - len(unique_ids))
            row["final_mail_target_estimate"] = len(matched) + len(unknown)
            # 상세링크 추출률 — 링크가 목록 URL 그대로면 상세로 못 들어간 것
            site_url = (site.get("url") or "").split("#")[0]
            row["detail_link_ok_count"] = sum(
                1 for it in dict_items
                if str(it.get("link") or "")
                and str(it.get("link") or "").split("#")[0] != site_url
            )
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

    P1-2: canonical_notice_id 기반 크로스소스 중복 제거 추가.
    - 공고번호/URL/제목+기관으로 canonical ID 생성
    - 동일 canonical ID면 동일 공고로 판정

    P2-A: 첨부파일 해시 기반 중복 보조
    """
    kept: list[dict] = []
    norm_map: dict[str, dict] = {}  # normalized_title → kept item
    canonical_map: dict[str, dict] = {}  # canonical_notice_id → kept item
    attachment_map: dict[str, dict] = {}  # attachment_hash → kept item

    def similarity_key(title: str) -> str:
        return normalize_title(title)

    def is_duplicate(a_key: str, b_key: str) -> bool:
        if a_key == b_key:
            return True
        # 한 쪽이 다른 쪽의 부분문자열 (10자 이상)
        short, long = (a_key, b_key) if len(a_key) <= len(b_key) else (b_key, a_key)
        return len(short) >= 10 and short in long

    def attachment_hash(item: dict) -> str:
        """P2-A: 첨부파일 해시 생성 (URL+제목 기반)."""
        parts = [item.get("link", ""), item.get("title", ""), str(item.get("deadline", ""))]
        composite = "|".join(p for p in parts if p)
        return hashlib.md5(composite.encode()).hexdigest()[:16] if composite else ""

    for item in items:
        key = similarity_key(item["title"])
        if not key:
            kept.append(item)
            continue

        # P1-2: canonical ID 기반 중복 체크
        canonical_id = generate_canonical_notice_id(item)
        item["_canonical_notice_id"] = canonical_id

        # P2-A: 첨부파일 해시 기반 중복 체크
        att_hash = attachment_hash(item)
        item["_attachment_hash"] = att_hash

        dup_key = next((k for k in norm_map if is_duplicate(key, k)), None)

        if dup_key is None:
            # 신규 — canonical ID도 체크
            if canonical_id in canonical_map:
                existing = canonical_map[canonical_id]
                # 주관기관 우선
                if not item["is_aggregator"] and existing["is_aggregator"]:
                    kept.remove(existing)
                    kept.append(item)
                    del norm_map[similarity_key(existing["title"])]
                    norm_map[key] = item
                    canonical_map[canonical_id] = item
                    log.info("크로스소스중복: '%s' (%s) → '%s' (%s) 로 교체 (canonical: %s)",
                             existing["source"], existing["title"][:20],
                             item["source"], item["title"][:20], canonical_id)
                else:
                    log.info("크로스소스중복: '%s' 유지, '%s' 제거 (canonical: %s)",
                             existing["title"][:20], item["title"][:20], canonical_id)
            # P2-A: 첨부파일 해시로도 체크
            elif att_hash and att_hash in attachment_map:
                existing = attachment_map[att_hash]
                if not item["is_aggregator"] and existing["is_aggregator"]:
                    kept.remove(existing)
                    kept.append(item)
                    del norm_map[similarity_key(existing["title"])]
                    norm_map[key] = item
                    attachment_map[att_hash] = item
                    log.info("첨부중복: '%s' → '%s' 로 교체 (hash: %s)",
                             existing["title"][:20], item["title"][:20], att_hash)
                else:
                    log.info("첨부중복: '%s' 유지, '%s' 제거 (hash: %s)",
                             existing["title"][:20], item["title"][:20], att_hash)
            else:
                norm_map[key] = item
                canonical_map[canonical_id] = item
                if att_hash:
                    attachment_map[att_hash] = item
                kept.append(item)
        else:
            existing = norm_map[dup_key]
            # 현재 아이템이 주관기관이고 기존이 집계처이면 교체
            if not item["is_aggregator"] and existing["is_aggregator"]:
                kept.remove(existing)
                kept.append(item)
                del norm_map[dup_key]
                norm_map[key] = item
                # canonical map도 업데이트
                old_canonical = existing.get("_canonical_notice_id")
                if old_canonical and old_canonical in canonical_map:
                    del canonical_map[old_canonical]
                canonical_map[canonical_id] = item
                # attachment map도 업데이트
                old_att = existing.get("_attachment_hash")
                if old_att and old_att in attachment_map:
                    del attachment_map[old_att]
                if att_hash:
                    attachment_map[att_hash] = item
                log.info("중복제거: '%s' (%s) → '%s' (%s) 로 교체",
                         existing["source"], existing["title"][:20],
                         item["source"], item["title"][:20])
            else:
                log.info("중복제거: '%s' 유지, '%s' 제거 (%s)",
                         existing["title"][:20], item["title"][:20], item["source"])

    # P2-D: 소스별 고유 공고 기여도 통계 계산
    source_stats: dict[str, dict] = {}
    for item in kept:
        sid = str(item.get("source") or "unknown")
        if sid not in source_stats:
            source_stats[sid] = {"total": 0, "unique": 0}
        source_stats[sid]["total"] += 1
        # canonical ID가 이 소스에서 처음 나온 것만 unique로 카운트
        cid = item.get("_canonical_notice_id", "")
        if cid and canonical_map.get(cid, {}).get("source") == sid:
            source_stats[sid]["unique"] += 1

    log.info("중복제거: %d건 → %d건", len(items), len(kept))
    for sid, stats in sorted(source_stats.items()):
        log.info("  소스 %s: 총 %d건, 고유 %d건", sid, stats["total"], stats["unique"])

    return kept


# ══════════════════════════════════════════════════════════════════
# 날짜 필터 (D-1: 어제 올라온 공고)
# ══════════════════════════════════════════════════════════════════

def partition_posted_dates(
    items: list[dict], days_back: int = 3, max_age_days: int | None = None,
    now_dt: datetime | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """최근 N영업일과 그 사이 주말 게시물을 재조회한다."""
    now = now_dt or datetime.now(KST)
    target_dates = _recent_recheck_dates(now, days_back)
    oldest, newest, today = min(target_dates), max(target_dates), now.date()
    matched, unknown, excluded = [], [], []

    def _in_window(d) -> bool:
        return d in target_dates or (oldest < d < today and d.weekday() >= 5)

    for it in items:
        pd = str(it.get("published_at") or it.get("posted_date") or "").strip()
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
        elif _in_window(item_date):
            matched.append(it)
        else:
            excluded.append({**it, "_excluded_posted_date": pd[:10]})
    log.info("날짜분류(최근 %d영업일, %s~%s): 확정 %d / 날짜불명 %d / 제외 %d", days_back, oldest, newest, len(matched), len(unknown), len(excluded))
    return matched, unknown, excluded


def date_filter(items: list[dict], days_back: int = 1) -> tuple[list[dict], list[dict]]:
    """하위 호환: (확정, 날짜불명)만 반환."""
    matched, unknown, _excluded = partition_posted_dates(items, days_back)
    return matched, unknown


def assess_date_unknown_risk(item: dict) -> str:
    """날짜불명 공고의 오늘 누락 위험도: 낮음 / 중간 / 높음.

    W3 §11.2 G: 게시일/신청기간이 PARSE_FAILED·DETAIL_FETCH_FAILED 이면
    '원문 미기재'로 위장하지 않고 높음(recall include + review)으로 올린다.
    """
    try:
        from mail_core.operations import field_status as _fs  # noqa: PLC0415
        extraction = item.get("detail_extraction") or {}
        fields = extraction.get("fields") or {}
        for key in ("application_period", "title"):
            meta = fields.get(key) if isinstance(fields, dict) else None
            st = _fs.field_blank_kind(
                (meta or {}).get("status") if isinstance(meta, dict) else extraction.get("status"))
            if st in _fs.FAILURE_STATUSES:
                return "높음"
        if _fs.field_blank_kind(extraction.get("status")) in _fs.FAILURE_STATUSES:
            return "높음"
    except Exception:
        pass
    text = _notice_body_text(item)
    # APPLICATION_KEYWORDS 만 보면 '모집' 단독 제목이 낮음으로 떨어져 recall 누락이 난다.
    # evaluate_notice 의 application_like 와 같은 기준으로 중/고 위험을 판정한다.
    if _application_like(text):
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


def _item_body_recency_date(item: dict):
    """게시일 불명 공고의 '가장 최근 날짜 단서'(신청기간 종료/마감/본문 날짜) — recency 가드용.
    날짜 단서가 전혀 없으면 None(완전 무단서는 recall 위해 보존)."""
    dates = []
    period = item.get("application_period") or {}
    for key in ("end", "start"):
        v = period.get(key)
        if v:
            try:
                dates.append(datetime.strptime(v[:10], "%Y-%m-%d").date())
            except ValueError:
                pass
    body = _notice_body_text(item) + " " + (item.get("deadline") or "")
    dates += [parsed for _, parsed in _parse_date_candidates(body)]
    return max(dates) if dates else None


def _date_unknown_too_old(item: dict, max_age_days: int | None, now: datetime | None = None) -> bool:
    """게시일 불명이지만 본문 날짜 단서가 max_age_days 보다 오래됐으면 '옛날 공고'로 본다.
    단서가 전혀 없으면 False(보존). 4월 등 명백한 과거 공고가 recall 정책으로 새는 것을 차단."""
    if not max_age_days:
        return False
    recency = _item_body_recency_date(item)
    if recency is None:
        return False
    today = (now or datetime.now(KST)).date()
    return (today - recency).days > max_age_days


def split_unknown_by_policy(
    unknown_items: list[dict], policy: str,
    max_age_days: int | None = None, now: datetime | None = None,
) -> tuple[list[dict], list[dict]]:
    """재현(recall) 정책으로 날짜불명 공고를 (메일포함, 검토잔여)로 분리.
      - all   : 전부 메일 포함
      - recall: 위험도 '중간'·'높음'(신청키워드 있거나 마감 살아있음)만 포함, '낮음'은 검토대기
      - strict(기본): 전부 검토대기(메일 미포함)
    '안 놓치기' 목적 — 게시일을 못 읽어도 신청성 신호가 있으면 발송한다.
    max_age_days 지정 시: 본문 날짜 단서가 그보다 오래된 공고는 메일에서 제외(검토잔여로).
    날짜 단서가 전혀 없는 무단서 공고는 정책대로 유지(recall 보존)."""
    def _stale(it: dict) -> bool:
        return _date_unknown_too_old(it, max_age_days, now)

    if policy == "all":
        included = [it for it in unknown_items if not _stale(it)]
        remaining = [it for it in unknown_items if _stale(it)]
        return included, remaining
    if policy == "recall":
        included: list[dict] = []
        remaining: list[dict] = []
        for it in unknown_items:
            keep = assess_date_unknown_risk(it) in ("높음", "중간") and not _stale(it)
            (included if keep else remaining).append(it)
        return included, remaining
    return [], list(unknown_items)


# ══════════════════════════════════════════════════════════════════
# 그룹 필터
# ══════════════════════════════════════════════════════════════════

def classify_support_type(item: dict) -> list[str]:
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    matched = [t for t, kws in SUPPORT_TYPE_RULES.items() if any(_kw_in_text(text, k.lower()) for k in kws)]
    # K-Startup 상세 '지원분야'(권위 카테고리)가 있으면 정확 매핑을 합집합으로 보강 —
    # 키워드 추측이 놓친 '사업화/정책자금'을 지원금/바우처로, '멘토링ㆍ컨설팅ㆍ교육'을 컨설팅으로.
    sf = (item.get("support_field") or "").lower()
    if sf:
        had_keyword = bool(matched)
        for kw, bucket in KSTARTUP_FIELD_TO_TYPE.items():
            if kw in sf and bucket not in matched:
                matched.append(bucket)
        try:
            from mail_core.matching.core_sources import map_category_to_support_types
            for bucket in map_category_to_support_types(sf):
                if bucket not in matched:
                    matched.append(bucket)
        except Exception:
            pass
        # ★recall 1순위: support_field 만으로 기존 '그외'(미분류=관대 통과) 자격을 빼지 않는다.
        #   키워드 무매칭이던 공고는 '그외'를 유지 → goyang 등 그룹에서 부당 누락 방지.
        #   (지원분야 매핑은 표시 정확도용 — 매칭 게이트를 좁히지 않는다.)
        if not had_keyword and "그외" not in matched:
            matched.append("그외")
    return matched or ["그외"]


def _notice_body_text(item: dict) -> str:
    """마감(deadline) 필드 제외 본문 — 잘못된 기간 오염 방지."""
    return f"{item.get('title','')} {item.get('description','')} {item.get('author','')}".lower()


def _keyword_match_text(item: dict) -> str:
    """그룹 키워드(AI·SaaS 등) 매칭용 — 지원분야·대상·카테고리 포함, 주관기관명 제외."""
    parts = [
        item.get("title", ""),
        item.get("description", ""),
        item.get("support_field", ""),
        item.get("target_field", ""),
        item.get("category", ""),
    ]
    for key in ("hashtags", "tags", "hashTags"):
        val = item.get(key)
        if isinstance(val, (list, tuple)):
            parts.extend(str(x) for x in val if x)
        elif val:
            parts.append(str(val))
    try:
        from mail_core.matching.core_sources import keyword_extra_parts
        parts.extend(keyword_extra_parts(item))
    except Exception:
        pass
    return norm(" ".join(p for p in parts if p)).lower()


def _application_like(text: str) -> bool:
    """신청·모집 성격 공고인지(recall 우선 — 목록 stub에 기간 없어도 누락 방지)."""
    if any(kw in text for kw in APPLICATION_KEYWORDS):
        return True
    if any(kw in text for kw in GRANT_SIGNAL_KEYWORDS):
        return True
    return any(kw in text for kw in ("모집", "신청", "접수", "공모"))


_SUPPLIER_ROLE_TERMS = ("공급기업", "수행기관", "서비스 제공자")
_DEMAND_ROLE_TERMS = ("수요기업", "참여기업", "신청 기업", "지원기업", "제조기업", "중소기업")
_OPERATOR_ROLE_TERMS = ("운영기관", "운영기관 모집", "주관기관 모집", "수행기관 모집", "위탁기관")
_BENEFICIARY_ROLE_TERMS = ("수혜자", "수혜기업", "지원대상", "지원 받는")


def extract_target_roles(item: dict) -> dict[str, bool]:
    """P0-9: 공고에서 신청자/모집대상/수혜자/운영자 역할을 추출한다.

    반환: {is_applicant, is_recruitment_target, is_beneficiary, is_operator}
    """
    title = norm(item.get("title", "")).lower()
    target_field = norm(item.get("target_field", "")).lower()
    description = norm(item.get("description", "")).lower()
    text = f"{title} {target_field} {description}"

    # 운영자 모집 감지: "운영기관 모집", "수행기관 모집" 등
    is_operator = any(term in text for term in _OPERATOR_ROLE_TERMS)
    # 신청자가 운영자인지 확인: "운영기관 모집"이 제목에 있으면 운영자 모집
    operator_in_title = any(term in title for term in _OPERATOR_ROLE_TERMS)

    # 수요기업(신청자) 신호
    is_demand = any(term in text for term in _DEMAND_ROLE_TERMS)
    # 공급기업(수행자) 신호
    is_supplier = any(term in text for term in _SUPPLIER_ROLE_TERMS)

    # 최종 판정
    # "예비창업자를 지원할 운영기관 모집" → is_operator=True, is_applicant=False
    # "예비창업자 모집" → is_operator=False, is_applicant=True
    if operator_in_title and not is_demand:
        return {
            "is_applicant": False,
            "is_recruitment_target": False,
            "is_beneficiary": True,  # 수혜자는 예비창업자
            "is_operator": True,
        }
    if is_demand and not is_supplier:
        return {
            "is_applicant": True,
            "is_recruitment_target": True,
            "is_beneficiary": True,
            "is_operator": False,
        }
    if is_supplier and is_demand:
        return {
            "is_applicant": True,
            "is_recruitment_target": True,
            "is_beneficiary": True,
            "is_operator": False,
        }
    # 기본값: 신청자로 간주
    return {
        "is_applicant": True,
        "is_recruitment_target": True,
        "is_beneficiary": True,
        "is_operator": False,
    }


def _mixed_target_roles(item: dict) -> bool:
    """제목/구조화 대상에 수요·공급 모집이 함께 명시됐는지 판정한다."""
    role_text = norm(f"{item.get('title', '')} {item.get('target_field', '')}").lower()
    return (
        any(term in role_text for term in _SUPPLIER_ROLE_TERMS)
        and any(term in role_text for term in _DEMAND_ROLE_TERMS)
    )


def _active_application_title(title: str) -> bool:
    """제목이 결과·종료 안내가 아닌 현재 모집 공고인지 보수적으로 판정한다."""
    inactive_terms = (
        "모집 결과", "모집결과", "선정 결과", "선정결과", "최종 선정",
        "최종선정", "마감 안내", "접수 마감", "성료", "개최 결과", "개최결과",
    )
    if any(term in title for term in inactive_terms):
        return False
    active_terms = (
        "모집", "신청", "접수", "공모", "참가신청",
        "지원사업 공고", "지원 사업 공고", "지원계획 공고", "사업 공고",
    )
    return _application_like(title) and any(term in title for term in active_terms)


def _split_exclusion_hits(item: dict, code: str, hits: list[str]) -> tuple[list[str], list[str]]:
    """제외 단서를 자동 제외(hard)와 참고 문맥(soft)으로 나눈다.

    제외 단어가 제목에 있거나 제목이 모집 공고가 아니면 기존처럼 hard다.
    반대로 제목이 명백한 모집 공고인데 본문에만 교육·설명회·지침 등이 있으면
    부대 일정/유의사항일 수 있으므로 soft 근거로 남기고 공고 전체를 버리지 않는다.

    INFO_SESSION / EDUCATION_ONLY 특수: 제목에 설명회·교육일정이 있어도
    동시에 실모집 신호(모집/신청/공모 등)가 있으면 soft — '모집 및 설명회' 실공고 보존.
    단, 제목이 교육참여기업모집·교육생 모집처럼 교육 모집 자체면 hard 유지.
    설명회 참여기업 모집처럼 설명회가 모집 본체면 soft로 두되, evaluate_notice 가
    INFO_SESSION_REVIEW 로 본문 추천에서 분리한다(hard INFO_SESSION 아님).
    """
    if not hits:
        return [], []
    title = norm(item.get("title", "")).lower()
    if code == "SUPPLIER_ONLY" and _mixed_target_roles(item):
        return [], list(hits)
    title_hit = any(hit in title for hit in hits)
    if code in {"INFO_SESSION", "EDUCATION_ONLY"} and _active_application_title(title):
        # 교육 모집 전용 제목은 soft 완화 대상이 아니다.
        if code == "EDUCATION_ONLY" and _EDUCATION_RECRUIT_TITLE_RE.search(title):
            return list(hits), []
        # 제목·본문 모두 soft — 실모집 본체 + 부대 설명회/교육일정
        return [], list(hits)
    if title_hit:
        return list(hits), []
    if _active_application_title(title):
        return [], list(hits)
    return list(hits), []


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


def _kw_in_text(text_lower: str, kw_lower: str) -> bool:
    """키워드가 본문(이미 소문자)에 있는지 판정.
    ASCII 전용 키워드(AI/SaaS/MES/ERP/IP/VC 등)는 단어경계 매칭으로 'email'의 'ai',
    'enterprise'의 'erp', 'equipment'의 'ip' 같은 부분문자열 오매칭을 막는다(precision).
    한글 등 비ASCII 키워드는 띄어쓰기 없는 합성어가 흔하므로 부분문자열 매칭을 유지한다(recall).
    scoring._kw_hit 와 동일 정책 — 두 모듈의 키워드 매칭 일관성 유지."""
    if not kw_lower:
        return False
    if kw_lower.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(kw_lower) + r"(?![a-z0-9])", text_lower) is not None
    return kw_lower in text_lower


def _find_keyword_aliases(text: str, aliases: list[tuple[str, list[str]]]) -> list[str]:
    matches: list[str] = []
    for label, keys in aliases:
        if any(_kw_in_text(text, key.lower()) for key in keys):
            matches.append(label)
    return _unique(matches)


def _group_priority_hits(item: dict, group: dict | None) -> list[str]:
    """전역 PRIORITY_KEYWORD_ALIASES + 그룹 priority_keywords 합집합.

    - 전역: 사업화지원금·바우처·스마트공장 등 공통 최우선
    - 그룹: groups.json 업종별 우선어(예: bnco K-뷰티·디자인)
    메일 '우선 추천'과 점수/LLM이 같은 그룹 맥락을 쓰게 한다.
    """
    body = _notice_text(item)
    kw_text = _keyword_match_text(item)
    hits = _find_keyword_aliases(body, PRIORITY_KEYWORD_ALIASES)
    for kw in (group or {}).get("priority_keywords") or []:
        raw = str(kw or "").strip()
        if not raw:
            continue
        if _kw_in_text(kw_text, raw.lower()) or _kw_in_text(body, raw.lower()):
            hits.append(raw)
    return _unique(hits)


def classify_deadline_status(item: dict, today=None) -> str:
    today = today or datetime.now(KST).date()
    text = _notice_text(item)
    # P0-15: ALWAYS_OPEN / UNTIL_BUDGET_EXHAUSTED 세분화
    if any(term in text for term in ("상시접수", "수시접수", "상시모집", "수시모집", "수시 모집", "연중수시", "연중상시", "선착순")):
        return "always_open"
    if any(term in text for term in ("예산 소진 시까지", "예산소진 시까지", "예산 소진시까지", "소진 시", "소진시")):
        return "until_budget_exhausted"
    # 마감연장 감지
    if any(term in text for term in ("마감연장", "마감 연장", "연장공고", "연장 공고", "기한연장", "기한 연장")):
        return "extended"
    body_text = _notice_body_text(item)
    period = item.get("application_period") or extract_application_period(body_text, _posted_date(item))
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
    # 마감일 = 파싱된 날짜 중 '가장 늦은' 날짜(max). 이전엔 위치순 마지막(dates[-1])을 마감으로 봐서,
    # 본문 뒤쪽에 과거 참조일(문의일·작년 실적 등)이 있으면 살아있는 공고도 '마감됨'으로 오판했다.
    # max 로 바꿔 '모든 날짜가 과거일 때만' closed → 현재 모집중 공고의 과잉 마감거름 해소(recall).
    start_date, end_date = min(dates), max(dates)
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


_KSTARTUP_BIZ_BUCKET_RE = re.compile(r"(\d+)\s*년\s*(?:미만|이내|이하)")


def parse_kstartup_business_buckets(text: str, cfg: dict) -> str:
    """K-Startup '창업업력' 멀티셀렉트를 그룹 신청자 업력구간과 비교.
    값 예: '1년미만, 5년미만, 10년미만' / '전체' / '예비창업자'.
    각 'N년미만'은 '업력 N년 미만 기업 신청가능'(상한 N)을 뜻하고, 멀티셀렉트는
    그 합집합이라 사실상 '가장 큰 N 까지 허용'이다. 신청자 구간 (lo, hi] 와
    겹치려면 (lo < 업력 < N) 인 업력이 있어야 하므로 N > lo 가 필요충분.
    eligible / not_eligible / unknown(애매 → 통과, recall 우선)."""
    if not text:
        return "unknown"
    t = unicodedata.normalize("NFKC", text)
    if "전체" in t:
        return "eligible"
    lo_raw = cfg.get("min_exclusive")
    if lo_raw is None:
        lo_raw = cfg.get("min", 0)
    lo = float(lo_raw if lo_raw is not None else 0)
    ns = [int(mm.group(1)) for mm in _KSTARTUP_BIZ_BUCKET_RE.finditer(t)]
    if ns:
        return "eligible" if any(n > lo for n in ns) else "not_eligible"
    # 연수 버킷 없이 '예비창업자'만 → 창업 전·극초기 전용 → 신청자(업력 보유 기업) 불가
    if "예비창업자" in t:
        return "not_eligible"
    return "unknown"


def business_years_status(item: dict, group: dict) -> str:
    """그룹 신청자 업력 구간과 공고 업력 요건의 호환성. eligible/not_eligible/unknown/n/a."""
    cfg = group.get("business_years")
    if not cfg:
        return "n/a"
    # K-Startup 상세의 '창업업력' 전용 필드가 있으면 멀티셀렉트 전용 매퍼 우선
    # (generic 추출기는 '1년미만,…,10년미만'을 max=1 로 오접어 정당공고를 누락시킴).
    bucket_text = item.get("business_age_text")
    if bucket_text:
        return parse_kstartup_business_buckets(bucket_text, cfg)
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
    # ★조·천억 단위(대규모 출연·기금 공고) — '조원'/'천억원' 표기를 정확 추출.
    #   '제3조'(법 조항)·'3조2교대' 등 비금액 '조'를 금액으로 오추출하지 않도록 '원' 접미를 요구한다.
    #   기존엔 None→unknown(게이트 비제외)로 surface만 되고 표시 금액이 0/미상이었음 — 이제 정확 금액으로
    #   추출돼 표시 정확도↑ + 금액 게이트가 unknown 대신 eligible 로 확정(여전히 recall-safe).
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*조\s*원", t):
        amounts.append(int(float(m.group(1)) * 1_000_000_000_000))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*천억\s*원", t):
        amounts.append(int(float(m.group(1)) * 100_000_000_000))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*억", t):
        amounts.append(int(float(m.group(1)) * 100_000_000))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*천만", t):
        amounts.append(int(float(m.group(1)) * 10_000_000))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*백만", t):
        amounts.append(int(float(m.group(1)) * 1_000_000))
    # ★'원' 옵션 뒤 음수전방탐색 — '100만명/50만개/100만건' 등 비금액 '만'을 금액으로 오추출하지
    #   않는다(정당 공고를 AMOUNT_TOO_LOW 로 잘못 제외하던 recall 버그 차단). '500만원'=5,000,000 유지.
    for m in re.finditer(r"(?<![천백.\d])(\d{1,6})\s*만\s*원?(?![명개건회사세팀])", t):
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


# 제목 맨 앞에 잇따른 [ … ] 태그 1개를 pos 위치에서 매칭(반복 스캔용). 앞쪽 공백 허용.
_TITLE_TAG_LEAD_RE = re.compile(r"\s*\[([^\]\n]{1,40})\]")
_KNOWN_REGION_SHORT = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)


def _title_region_tags(item: dict) -> list[str]:
    """제목 맨 앞에 잇따른 [ … ] 태그(복수 가능)의 광역 약칭을 모두 반환(없으면 []).
    한국 정부공고에서 제목 앞 [지역] 은 '그 지역 기업 대상'의 강한 신호. 복수지역은
    한 대괄호 묶음(예: [서울ㆍ인천ㆍ경기])이든, 잇따른 분리 대괄호(예: [서울][인천])이든,
    또는 앞에 문서종류 태그가 붙은 형태(예: [모집공고][인천])이든 포함된 광역을 전부 잡아,
    그룹 지역이 그 목록에 있으면 통과시켜 표기형태 차이에 따른 recall 손실을 막는다.
    (기존엔 첫 대괄호만 읽어 own 광역이 둘째 이후 태그에 있으면 누락했음.)"""
    title = str(item.get("title", ""))
    tags: list[str] = []
    pos = 0
    while True:
        mt = _TITLE_TAG_LEAD_RE.match(title, pos)
        if not mt:
            break
        inner = mt.group(1)
        for r in _KNOWN_REGION_SHORT:
            if r in inner and r not in tags:
                tags.append(r)
        pos = mt.end()
    return tags


def _other_region_block(item: dict, own_meta: dict):
    """'지역=전국'으로 박혀도 명백한 타지역 한정이면 차단사유 반환(아니면 None) — recall-safe.
    own_meta={'label': 광역약칭(예 '경기'/'서울'/'인천'), 'districts': [자치구 풀네임...]}.
    own 신호(자치구 풀네임/광역명) 또는 사람이 쓴 제목·본문 '전국'이 있으면 None(미발동).
    (A) own family 가 아닌 광역권 토큰(제목), (B) 기초자치단체·지역재단 주관 + 비-own 지역명."""
    title = str(item.get("title", ""))
    raw_text = f"{title} {item.get('description','')} {item.get('author','')} {item.get('region_field','')}"
    text = _notice_text(item)
    org_text = f"{item.get('organizer_field','')} {item.get('author','')}"
    own_blob = f"{raw_text} {item.get('organizer_field','')}".lower()
    own_label = (own_meta.get("label") or "").strip().lower()
    districts = [d for d in own_meta.get("districts", []) if d]
    extra = {str(r).strip().lower() for r in own_meta.get("extra", []) if str(r).strip()}
    fam = {f.lower() for f in (_METRO_FAMILY if own_label in {x.lower() for x in _METRO_FAMILY} else {own_label})} | extra

    own_present = (
        any(d.lower() in text for d in districts)            # own 자치구 풀네임
        or (own_label and own_label in own_blob)             # own 광역명
        or any(e and e in own_blob for e in extra)           # 추가 적격 지역(수도권 묶음 등)
    )
    explicit_nationwide = ("전국" in title) or ("전국" in str(item.get("description", "")))
    if own_present or explicit_nationwide:
        return None
    # (A) 광역권 토큰 — own family 외 광역이면 차단
    for mch in _KWON_NAMED_RE.finditer(title):
        norm_r = "수도권" if mch.group("r") == "수도" else mch.group("r")
        if norm_r.lower() not in fam:
            return "타지역 권역"
    # (B) 기초자치단체/지역재단 주관 + 비-own 지역명 (전국운영기관 제외)
    if _LOCAL_GOV_ORG_RE.search(org_text) and not _NATIONAL_SCOPE_ORG_RE.search(org_text):
        own_loc = {own_label} | {d.lower() for d in districts} | extra
        other = [loc for loc in _ALL_LOCALITIES if loc in org_text and loc.lower() not in own_loc]
        if other:
            return other[:3]
    return None


def _metro_peer_districts(city: str, label: str) -> list[str]:
    """광역 내 구·군 목록. 신청자 구가 있을 때 '타 구 전용' 차단에 쓴다."""
    blob = f"{city or ''} {label or ''}".lower()
    if "인천" in blob:
        return list(INCHEON_DISTRICTS)
    return []


def classify_region_for_group(item: dict, group: dict) -> dict:
    """그룹 신청자 지역(광역+시·군) 기준 일반 지역 적합성 판정.
    인천 전용 classify_region 과 달리 임의 시·도/시·군을 지원한다."""
    text = _notice_text(item)
    raw_text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')} {item.get('region_field','')}"
    city = group.get("applicant_region_city", "")
    label = (group.get("applicant_region_label") or _short_region(city) or city).lower()
    district = group.get("applicant_region_district", "")
    districts = [d for d in ([district] + group.get("applicant_districts", [])) if d]
    # 추가 적격 지역(예: 서울 그룹에 인천·경기·수도권) — 신청자가 신청 가능한 다른 광역.
    extra_regions = [str(r).strip().lower() for r in group.get("extra_eligible_regions", []) if str(r).strip()]
    own_regions = [r for r in ([label] + extra_regions) if r]

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

    # 제목 [광역] 태그에 그룹 적격지역(own 광역 + extra_eligible_regions)이 하나도 없으면
    # nationwide 여도 차단(타지역 한정 신호). 복수지역 태그는 포함 광역을 전부 보고,
    # own_regions(label+extra) 중 하나라도 있으면 통과 — 본문 신호(2233행 own_present 의 extra)와
    # 기준을 맞춰 같은 적격지역이 제목태그/본문 표기위치에 따라 비대칭 누락되는 것을 막는다(recall 보존).
    # 단, 사람이 제목/설명에 '전국'을 명시했으면 _other_region_block 의 explicit_nationwide 면제와
    # 동일하게 태그 배제를 건너뛴다 — 타지역 태그가 앞에 와도 명시적 전국 공고는 누락 금지(recall).
    # 신청대상 지역을 먼저 정밀 판정. 제목 [지역]태그/신청한정 면제를 거친 "전국" substring
    # 대신 _resolve 의 nationwide(신청 전국 vs 개최지만 타지역 구분)로 판정 — '[대구] 전국
    # 박람회(대구 소재 한정)'가 '전국' 한 단어로 태그차단을 우회하던 빈틈 차단(recall 보존).
    app_scope = _resolve_applicant_region_scope(item)
    app_text = _applicant_target_text(item)
    detected = [r.lower() for r in (app_scope.get("regions") or [])]
    nationwide = bool(app_scope.get("nationwide"))

    tags = _title_region_tags(item)
    if tags and not nationwide and not any(r in tags for r in own_regions):
        return result("not_eligible", "not_eligible", [], tags)

    district_hits = []
    for d in districts:
        short_d = d.replace("시", "").replace("군", "").replace("구", "")
        if d.lower() in app_text or (short_d and short_d.lower() in app_text):
            district_hits.append(d)

    # 동일 광역 내 타 구·군만 명시(우리 구 미포함) → not_eligible.
    # classify_region(인천·남동구)의 '부평구 전용 차단'과 같은 정밀도 — for_group 경로에도 이식.
    peers = _metro_peer_districts(city, label)
    if districts and peers:
        mentioned_peers = [d for d in peers if d in app_text]
        other_districts = [d for d in mentioned_peers if d not in districts]
        if other_districts and not district_hits:
            return result("not_eligible", "not_eligible", [], other_districts)

    # ── recall-safe 타지역 override (공유헬퍼 _other_region_block; own-metro 파라미터화) ──
    # 권역(경상/호남/충청권 등) 멤버 적격 — own 광역이 명시 권역의 멤버면 적격(차단보다 우선=recall,
    # company_match 와 단일 정본 공유). 비멤버는 아래 차단 로직으로.
    from mail_core.matching.region_clusters import REGION_CLUSTER as _RC
    for _kwon, _members in _RC.items():
        if _kwon in app_text and ("비" + _kwon) not in app_text and any(r in _members for r in own_regions):
            return result("eligible", "eligible", [city or label], [])

    _ovr = _other_region_block(item, {"label": label, "districts": districts, "extra": extra_regions})
    if _ovr is not None:
        return result("not_eligible", "not_eligible", [],
                      [_ovr] if isinstance(_ovr, str) else list(_ovr))

    # ── 신청자 '지역 한정' 강신호 vs 문의·운영 보일러플레이트 (충북 누출 차단, 2026-06-25) ──
    # 타지역에 명시적 신청자-한정('충북지역 중소기업 대상')이 있고, own 광역은 문의·운영
    # 구간에만 등장(신청자 신호 아님)하면 not_eligible. own 이 신청자 문맥에 있으면 미발동(recall).
    restricted = _applicant_restricted_regions(app_text)
    if restricted:
        other_restricted = sorted(restricted - {r for r in own_regions})
        applicant_text = _strip_contact_spans(app_text)
        own_in_applicant = (
            any(r in restricted for r in own_regions)          # own 도 신청자-한정 신호
            or any(r in applicant_text for r in own_regions)   # own 이 신청자 문맥에 등장
            or any(d.lower() in applicant_text for d in districts)
        )
        if other_restricted and not own_in_applicant and not nationwide:
            return result("not_eligible", "not_eligible", [], other_restricted)

    other_only = [r for r in detected if r not in own_regions]
    own_in_app = any(r in app_text for r in own_regions) or any(r in detected for r in own_regions)
    if other_only and not own_in_app and not nationwide:
        return result("not_eligible", "not_eligible", [], other_only)

    if nationwide:
        return result("eligible", "eligible", [city or label], [])
    if district_hits:
        return result("eligible", "eligible", district_hits, [])

    # own 광역이 구조화 region_field('지역' 드롭다운)에만 있어도 own 신호로 인정(recall) —
    # _detect_target_regions 힌트는 '광역+공백'을 요구해 region_field='서울' 단독을 놓친다.
    region_field_norm = norm(item.get("region_field", "")).lower()
    region_hit = bool(own_regions) and any(
        (r in detected) or (r in app_text) or (r and r in region_field_norm) for r in own_regions)
    other_regions = [r for r in detected if r not in own_regions]
    if region_hit:
        # 우리 광역 언급 + 특정 타 시·군 한정 아님 → 적합(시·군 미상이나 포함 우선)
        return result("eligible", "eligible", [city or label], [])
    if other_regions:
        return result("not_eligible", "not_eligible", [], other_regions)
    # own 광역이 수도권 family(서울·인천·경기)이면 '수도권' 묶음공고는 신청 가능 — 수도권이 own
    # 광역을 포함하므로 KNOWN_REGIONS 폴백의 타지역 오인을 막는다(recall). '비수도권'은 가드로 배제.
    if ("수도권" in app_text and "비수도권" not in app_text
            and (set(own_regions) & {r.lower() for r in _METRO_FAMILY})):
        return result("eligible", "eligible", [city or label], [])
    if any(r.lower() in app_text for r in KNOWN_REGIONS):
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

    # 제목 [광역] 태그 우선 판정: 인천 포함이면(복수지역 [서울ㆍ인천ㆍ경기] 또는 잇따른
    # [서울][인천] 등) eligible 로 확정해 recall 보존. 인천 미포함이면 타지역 한정으로 보고
    # 차단하되, 사람이 제목/설명에 '전국'을 명시했으면 _other_region_block 의 explicit_nationwide
    # 면제와 동일하게 태그 차단을 건너뛴다 — 타지역 태그가 앞에 와도 명시적 전국 공고는 누락 금지(recall).
    tags = _title_region_tags(item)
    if tags and "인천" in tags:
        return {
            "region_status": "eligible",
            "district_status": "eligible",
            "eligible_regions": [APPLICANT_REGION_CITY],
            "excluded_regions": [],
        }
    app_scope = _resolve_applicant_region_scope(item)
    app_text = _applicant_target_text(item)
    explicit_regions = list(app_scope.get("regions") or [])
    nationwide = bool(app_scope.get("nationwide"))
    # 거친 "전국" substring 대신 정밀 nationwide 로 태그 면제 판정(빈틈 #13 차단, recall 보존).
    if tags and not nationwide:
        return {
            "region_status": "not_eligible",
            "district_status": "not_eligible",
            "eligible_regions": [],
            "excluded_regions": tags,
        }
    # 인천 그룹에도 동일 recall-safe 타지역 override 적용(own=인천, 수도권 family 상호제외).
    # own(인천/INCHEON_DISTRICTS) 또는 사람이 쓴 제목·본문 '전국'이 있으면 미발동(기존 분기 보존).
    _ovr = _other_region_block(item, {"label": "인천", "districts": INCHEON_DISTRICTS})
    if _ovr is not None:
        return {"region_status": "not_eligible", "district_status": "not_eligible",
                "eligible_regions": [],
                "excluded_regions": [_ovr] if isinstance(_ovr, str) else list(_ovr)}
    # 신청자 '지역 한정' 강신호 vs 문의·운영 보일러플레이트 (충북 누출 차단, 2026-06-25) —
    # classify_region_for_group 과 동일 규칙. 타지역 신청자-한정인데 '인천'은 문의/운영
    # 보일러플레이트에만 등장하면 not_eligible. 인천이 신청자 문맥에 있으면 미발동(recall).
    _restricted = _applicant_restricted_regions(app_text)
    if _restricted:
        _other_restricted = sorted(_restricted - {"인천"})
        _applicant_text = _strip_contact_spans(app_text)
        _own_in_applicant = (
            "인천" in _restricted
            or "인천" in _applicant_text
            or any(d.lower() in _applicant_text for d in INCHEON_DISTRICTS)
        )
        if _other_restricted and not _own_in_applicant and not nationwide:
            return {
                "region_status": "not_eligible",
                "district_status": "not_eligible",
                "eligible_regions": [],
                "excluded_regions": _other_restricted,
            }

    # own(인천) 광역명이 조사로 붙어('인천과') hint(\s 요구)에 안 잡혀도 본문 substring 으로 재확인 —
    # _other_region_block own_present(substring) 과 기준을 맞춰 표기위치 비대칭 누락 방지(recall).
    own_in_text = "인천" in app_text
    other_only = [r for r in explicit_regions if "인천" not in r]
    if other_only and not own_in_text and not nationwide:
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
    elif nationwide:
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif "인천광역시 소재" in app_text or "인천 소재" in app_text or "인천 지역" in app_text or "인천지역" in app_text:
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif "인천" in app_text or any("인천" in r for r in explicit_regions):
        # own 광역(인천)이 본문이 아니라 구조화 region_field('지역' 드롭다운)에만 있어도
        # own 신호로 인정 → eligible. 타지역은 이미 explicit_regions→other_only 로 배제하면서
        # own 만 region_field 를 무시하던 비대칭 누락 해소(recall). explicit_regions 는 2377행에서
        # region_field(norm)를 포함하므로 '인천'/'인천광역시' 단독 드롭다운을 모두 잡는다.
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif "수도권" in app_text and "비수도권" not in app_text:
        # 인천은 수도권(서울·인천·경기)에 포함 — '수도권 소재 기업' 공고는 인천 기업이 신청 가능.
        # (수도권 제외/소재기업 제외/신청불가·비수도권 …은 REGION_EXCLUDE_PHRASES·가드로 이미 배제됨.)
        # KNOWN_REGIONS 폴백이 '수도권'을 타지역으로 오인해 정당 공고를 누락시키던 갭 해소(recall).
        eligible_regions.append(APPLICANT_REGION_CITY)
        region_status = "eligible"
        district_status = "eligible"
    elif any(region.lower() in app_text for region in KNOWN_REGIONS):
        region_status = "not_eligible"
        district_status = "not_eligible"

    return {
        "region_status": region_status,
        "district_status": district_status,
        "eligible_regions": _unique(eligible_regions),
        "excluded_regions": _unique(excluded_regions),
    }


def region_match(item: dict, group_regions: list[str], region_info: dict | None = None) -> bool:
    """그룹 지역 조건 매칭. 남동구 신청 불가 공고는 인천 그룹에서 제외."""
    if not group_regions:
        return True
    info = region_info if region_info is not None else classify_region(item)
    if info["region_status"] == "not_eligible" or info["district_status"] == "not_eligible":
        return False
    text = _notice_text(item)
    g_regions = [r.lower() for r in group_regions]
    if any(r in text for r in g_regions):
        return True
    if "전국" in text:
        return True
    if info["region_status"] == "eligible":
        return True
    return False


def uses_incheon_region_engine(group: dict | None) -> bool:
    """인천(+남동구) 정밀 엔진을 쓸지. False면 classify_region_for_group."""
    if not group:
        return True
    city = group.get("applicant_region_city", APPLICANT_REGION_CITY)
    return city == APPLICANT_REGION_CITY


def resolve_region(item: dict, group: dict | None = None) -> dict:
    """지역 적격 단일 진입점.

    - 인천광역시 그룹(기본 포함): ``classify_region`` — 구 단위 배타(부평구 전용 등)
    - 그 외 시·도 그룹: ``classify_region_for_group`` — 임의 광역/시·군
    """
    g = group or {}
    if uses_incheon_region_engine(g if group is not None else None):
        return classify_region(item)
    return classify_region_for_group(item, g)


def keyword_match(item: dict, kw_cfg: dict) -> bool:
    kws = [k.lower() for k in kw_cfg.get("keywords", []) if k.strip()]
    if not kws:
        return True
    logic = kw_cfg.get("logic", "OR").upper()
    text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')}".lower()
    return all(_kw_in_text(text, k) for k in kws) if logic == "AND" else any(_kw_in_text(text, k) for k in kws)


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


def has_primary_support(item: dict) -> bool:
    """공고에 주된 지원(실질적 비용지원)이 있는지 판정한다.

    주된 지원: 지원금/바우처 (사업화자금, R&D, 시제품, 실증·PoC, 바우처 등)
    부가 지원만: 교육, 멘토링, 컨설팅, 투자, 입주공간 단독
    """
    types = classify_support_type(item)
    return "지원금/바우처" in types


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
    soft_excluded_keywords: list[str] = []
    target_type = "unknown"
    notice_type = "unknown"

    matched_keywords = _find_keyword_aliases(text, GENERAL_INCLUDE_KEYWORD_ALIASES)
    priority_keywords = _group_priority_hits(item, g)
    factory_keywords = _find_keyword_aliases(text, FACTORY_KEYWORD_ALIASES)
    matched_keywords = _unique(matched_keywords + factory_keywords)
    factory_required = any(term in text for term in FACTORY_REQUIRED_TERMS)
    factory_condition = bool(factory_keywords)
    service_hits = [kw for kw in GENERAL_SERVICE_EXCLUDE_KEYWORDS if kw in text]
    application_like = _application_like(text)
    smart_info = any(kw in priority_keywords for kw in ["스마트공장", "스마트팩토리", "제조DX", "공정개선", "공정자동화", "자동화", "제조혁신"])

    for code, rule_notice_type, rule_target_type, keywords in EXCLUSION_RULES:
        hits = [kw for kw in keywords if kw in text]
        hard_hits, soft_hits = _split_exclusion_hits(item, code, hits)
        soft_excluded_keywords.extend(soft_hits)
        if hard_hits:
            reason_codes.append(code)
            excluded_keywords.extend(hard_hits)
            if notice_type == "unknown":
                if code == "GUIDELINE_OR_MANUAL" and any("매뉴얼" in hit for hit in hard_hits):
                    notice_type = "manual"
                elif code == "GUIDELINE_OR_MANUAL" and any("부정수급" in hit for hit in hard_hits):
                    notice_type = "admin_notice"
                else:
                    notice_type = rule_notice_type
            if rule_target_type != "unknown":
                target_type = rule_target_type

    # 제목 앵커: 교육참여기업모집·교육생 모집 등 — EXCLUSION_RULES soft 완화와 무관하게 제외.
    edu_title = norm(item.get("title", ""))
    if _EDUCATION_RECRUIT_TITLE_RE.search(edu_title):
        reason_codes.append("EDUCATION_ONLY")
        excluded_keywords.append(_EDUCATION_RECRUIT_TITLE_RE.search(edu_title).group(0))
        if notice_type == "unknown":
            notice_type = "education"

    # 원본전체용 잡공고·행정고지 판정을 그룹 필터에도 적용(사유코드는 경로별로 분리).
    if is_report_junk(item):
        reason_codes.append("REPORT_JUNK")
        excluded_keywords.append("report_junk")
        if notice_type == "unknown":
            notice_type = "general_info"
    if is_admin_noise(item):
        reason_codes.append("ADMIN_NOISE")
        excluded_keywords.append("admin_noise")
        if notice_type == "unknown":
            notice_type = "admin_notice"

    # [제목 앵커] 비공고 정적 페이지(기관소개·정보공개·약관·nav 링크 등) 제외.
    # 제목 완전일치/링크 스킴만 보므로 본문 우연일치로 진짜 공고를 막지 않는다(위 상수 주석 참조).
    nonnotice_hit = non_notice_reason(item)
    if nonnotice_hit:
        reason_codes.append("NOT_GRANT_NOTICE")
        excluded_keywords.append(nonnotice_hit)
        if notice_type == "unknown":
            notice_type = "general_info"

    # 애매 비지원 — hard 금지(반례 있음: '환경정보공개 지원사업' 등 진짜 지원사업이 섞임)하되
    # 본문 추천에서 분리해 review 로 보낸다. 정보공개+모집/공고 조합은 정적 메뉴 오수집과
    # 진짜 지원사업이 혼재하므로, 지원사업/바우처 등 명확 신호가 없으면 AMBIGUOUS_NOTICE 로
    # review_needed=True 로 표시해 사람이 최종 판단한다.
    amb_hit = ambiguous_notice_reason(item)
    if amb_hit:
        reason_codes.append("AMBIGUOUS_NOTICE")
        excluded_keywords.append(amb_hit)
        if notice_type == "unknown":
            notice_type = "general_info"

    # [제목 앵커] 위원(개인 전문가) 위촉·모집 공고 — 기업 대상 지원사업이 아니므로 제외.
    committee_hit = _COMMITTEE_TITLE_RE.search(norm(item.get("title", "")))
    if committee_hit:
        reason_codes.append("COMMITTEE_RECRUITMENT")
        excluded_keywords.append(committee_hit.group(0))
        if notice_type == "unknown":
            notice_type = "general_info"

    hard_service_hits, soft_service_hits = _split_exclusion_hits(item, "INFO_SESSION", service_hits)
    soft_excluded_keywords.extend(soft_service_hits)
    if hard_service_hits:
        excluded_keywords.extend(hard_service_hits)
        if "설명회" in hard_service_hits or any("설명회" in h for h in hard_service_hits):
            reason_codes.append("INFO_SESSION")
            notice_type = "info_session"
        elif has_primary_support(item):
            # 주된 지원(사업화자금 등)이 있으면 서비스 키워드로 제외하지 않음 (P0-1)
            soft_excluded_keywords.extend(hard_service_hits)
        elif not application_like or ("단독" in text and not priority_keywords):
            reason_codes.append("LOW_PRIORITY_SERVICE_KEYWORD")
            notice_type = "general_info"

    # 설명회가 모집 본체(…설명회 참여기업 모집)이면 hard INFO_SESSION 대신 review 분리.
    # '모집 및 설명회' 등 부대 설명회는 soft 통과 유지.
    title_raw = norm(item.get("title", ""))
    if (
        "설명회" in title_raw
        and _INFO_SESSION_AS_RECRUIT_RE.search(title_raw)
        and not _INFO_SESSION_SECONDARY_RE.search(title_raw)
    ):
        reason_codes.append("INFO_SESSION_REVIEW")
        if "설명회" not in soft_excluded_keywords and "설명회" not in excluded_keywords:
            soft_excluded_keywords.append("설명회")
        if notice_type == "unknown":
            notice_type = "info_session"

    if smart_info and notice_type in {"education", "info_session", "general_info", "guideline", "manual"}:
        reason_codes.append("SMART_FACTORY_INFO_ONLY")

    if target_type == "unknown":
        supplier_signal = any(kw in text for kw in _SUPPLIER_ROLE_TERMS)
        demand_signal = any(
            kw in text for kw in ["수요기업", "참여기업", "중소기업", "소상공인", "제조기업", "신청 기업"]
        )
        if supplier_signal and demand_signal:
            target_type = "mixed"
        elif supplier_signal:
            target_type = "supplier"
        elif any(kw in text for kw in ["기선정", "선정기업 대상", "협약", "정산", "결과보고"]):
            target_type = "selected_company"
        elif demand_signal:
            target_type = "demand_company"

    if notice_type == "unknown" and application_like:
        notice_type = "application_notice"
    elif notice_type == "unknown" and any(kw in text for kw in ["일반 안내", "안내"]):
        notice_type = "general_info"

    deadline_status = classify_deadline_status(item, today)
    if deadline_status == "closed":
        reason_codes.append("CLOSED_DEADLINE")
    elif deadline_status == "unknown" and not application_like:
        reason_codes.append("MISSING_APPLICATION_PERIOD")

    applicant_district = g.get("applicant_region_district", APPLICANT_REGION_DISTRICT)
    incheon_engine = uses_incheon_region_engine(group)
    region_info = resolve_region(item, g if group is not None else None)
    if region_info["region_status"] == "not_eligible":
        reason_codes.append("REGION_NOT_ELIGIBLE")
    if region_info["district_status"] == "not_eligible":
        reason_codes.append("DISTRICT_NOT_ELIGIBLE")
    if region_info["region_status"] == "unknown" or region_info["district_status"] == "unknown":
        reason_codes.append("LOW_CONFIDENCE")
    if incheon_engine and "산업단지" in text and "입주기업" in text and applicant_district not in text:
        reason_codes.append("ONLY_SPECIFIC_INDUSTRIAL_COMPLEX")

    always_srcs = [s.lower() for s in g.get("source_always_include", [])]
    src = (item.get("source", "") + " " + item.get("author", "")).lower()
    source_bypass = always_srcs and any(s in src for s in always_srcs)
    req_regions = g.get("required_conditions", {}).get("regions", [])
    # 지역 미상(unknown)과 '확실한 타지역'(not_eligible)을 구분한다(사용자 정책 2026-06-19):
    #  확실한 타지역 → REGION_NOT_ELIGIBLE(제외). 지역 단서 전무 → REGION_UNKNOWN(버리지 말고 '지역 미상'으로 surface).
    region_positively_other = (
        region_info["region_status"] == "not_eligible"
        or region_info["district_status"] == "not_eligible"
    )
    if group is not None and not source_bypass:
        # 인천 엔진: required_conditions.regions + 구 배타를 region_match 로 결합.
        # 기타 광역: classify_region_for_group 의 region_status==eligible 만으로 통과.
        if incheon_engine:
            region_ok = region_match(item, req_regions, region_info=region_info)
        else:
            region_ok = region_info["region_status"] == "eligible"
        if not region_ok:
            reason_codes.append("REGION_NOT_ELIGIBLE" if region_positively_other else "REGION_UNKNOWN")

    excl_kws = [k.lower() for k in g.get("exclude_keywords", []) if k.strip()]
    group_excluded = [k for k in excl_kws if _kw_in_text(text, k)]
    mixed_supplier_hits = [
        hit for hit in group_excluded
        if _mixed_target_roles(item) and any(term in hit for term in _SUPPLIER_ROLE_TERMS)
    ]
    if mixed_supplier_hits:
        soft_excluded_keywords.extend(mixed_supplier_hits)
        group_excluded = [hit for hit in group_excluded if hit not in mixed_supplier_hits]
    hard_group_hits, soft_group_hits = _split_exclusion_hits(item, "GROUP_EXCLUSION", group_excluded)
    soft_excluded_keywords.extend(soft_group_hits)
    if hard_group_hits:
        reason_codes.append("GROUP_EXCLUSION")
        excluded_keywords.extend(hard_group_hits)

    kw_text = _keyword_match_text(item)
    or_kws = [k.lower() for k in g.get("or_keywords", []) if k.strip()]
    and_groups = [[k.lower() for k in ag if k.strip()] for ag in g.get("and_keyword_groups", []) if ag]
    group_keyword_pass = True
    if group is not None and not source_bypass and (or_kws or and_groups):
        group_keyword_pass = (
            any(_kw_in_text(kw_text, k) for k in or_kws)
            or any(all(_kw_in_text(kw_text, k) for k in ag) for ag in and_groups)
        )
        if not group_keyword_pass:
            reason_codes.append("INDUSTRY_NOT_MATCHED")

    if group is not None and not support_match(item, g.get("support_types", ALL_SUPPORT_TYPES)):
        reason_codes.append("INDUSTRY_NOT_MATCHED")

    # P0-4: 주된 지원/부가 지원 분리 — 단독 교육·멘토링·컨설팅·투자·입주 제외
    # 재정 지원 신호(지원금/바우처 키워드, 수출/판로/마케팅 등)가 있으면 부가 지원으로만 제외하지 않음
    if group is not None:
        support_types = classify_support_type(item)
        has_financial = "지원금/바우처" in support_types
        has_consulting = "컨설팅·교육·상담" in support_types
        has_investment = "투자" in support_types
        # 재정 지원 키워드가 본문에 있는지 추가 확인 (classify_support_type이 놓치는 경우 대비)
        _financial_signal_kws = [
            "수출", "해외", "판로", "마케팅", "전시회", "박람회", "바이어",
            "시제품", "사업화", "R&D", "실증", "PoC", "바우처", "보조금",
        ]
        has_financial_signal = has_financial or any(kw in text for kw in _financial_signal_kws)
        # 주된 지원 없이 부가 지원만 있는 경우 제외
        if not has_financial_signal and not has_investment:
            if has_consulting:
                # 교육·멘토링·컨설팅 단독 → 제외
                reason_codes.append("CONSULTING_ONLY")
        elif has_investment and not has_financial_signal and not has_consulting:
            # 투자 단독 → 제외
            reason_codes.append("INVESTMENT_ONLY")

    # NOT_APPLICATION_LIKE: 모집·공모 등 application 신호가 전혀 없는 공고.
    # NOT_GRANT_NOTICE(EXCLUSION_RULES 경로)와 조건이 같지만 경로를 분리한 것 —
    # 전자는 evaluate_notice 의 application 게이트, 후자는 제목 앵커 상수 매칭.
    if not application_like and not priority_keywords:
        reason_codes.append("NOT_APPLICATION_LIKE")

    biz_years_status = business_years_status(item, g) if group is not None else "n/a"
    amount_status = support_amount_status(item, g) if group is not None else "n/a"
    if biz_years_status == "not_eligible":
        reason_codes.append("BUSINESS_YEARS_NOT_ELIGIBLE")
    # 지원금 필터: 사용자 정책(2026-06-19) — 당분간 금액으로 거르지 않는다(recall 우선·'참가비' 오추출 위험 회피).
    # 금액은 표시용으로만 유지(support_amount_status). 재활성화: 그룹에 "enforce_amount_filter": true.
    if amount_status == "not_eligible" and g.get("enforce_amount_filter", False):
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
    soft_excluded_keywords = _unique(soft_excluded_keywords)
    region_status = region_info["region_status"]
    district_status = region_info["district_status"]
    hard_reasons = set(reason_codes) - {"FACTORY_REQUIRED_BUT_UNKNOWN"}
    # recall: 모집·신청 신호 있는데 기간 미파싱(목록 stub)이면 열린 공고로 간주 — 서울·AI 등 누락 방지
    # P0-15: always_open, until_budget_exhausted, extended도 열린 공고로 처리
    deadline_ok = deadline_status in {"open", "upcoming", "always_open", "until_budget_exhausted", "extended"} or (
        deadline_status == "unknown" and application_like
    )
    is_relevant = (
        not hard_reasons
        and deadline_ok
        and region_status == "eligible"
        and district_status == "eligible"
        and application_like
        and group_keyword_pass
    )
    # W3/P0-B: 빈 정보 3상태 — 추출 실패는 review 강제, NOT_SPECIFIED 는 unknown 금지.
    from mail_core.operations import field_status as _fs  # noqa: PLC0415
    detail_status = str(
        (item.get("detail_extraction") or {}).get("status") or "")
    detail_failure = detail_status in _DETAIL_FAILURE_STATUSES or _fs.should_force_review_for_extraction(item)
    detail_failure_blockers = {
        "GUIDELINE_OR_MANUAL", "EDUCATION_ONLY", "INFO_SESSION", "SUPPLIER_ONLY",
        "SELECTED_COMPANY_ONLY", "REGION_NOT_ELIGIBLE", "DISTRICT_NOT_ELIGIBLE",
        "CLOSED_DEADLINE", "SMART_FACTORY_INFO_ONLY", "COMMITTEE_RECRUITMENT",
        "ADMIN_NOISE", "REPORT_JUNK", "GROUP_EXCLUSION", "NOT_APPLICATION_LIKE",
        "NOT_GRANT_NOTICE", "BUSINESS_YEARS_NOT_ELIGIBLE", "AMOUNT_TOO_LOW",
    }
    detail_failure_review = (
        detail_failure
        and not (set(reason_codes) & detail_failure_blockers)
    )
    # 지역 필드 NOT_SPECIFIED(원문 미기재) → 전국/미지정 경로(eligible). unknown 버킷 금지.
    region_extract_status = _fs.region_field_status(item)
    if (
        region_extract_status == _fs.NOT_SPECIFIED
        and region_status == "unknown"
        and district_status != "not_eligible"
    ):
        region_status = "eligible"
        district_status = "eligible" if district_status == "unknown" else district_status
        region_info = {
            **region_info,
            "region_status": region_status,
            "district_status": district_status,
        }
        # REGION_UNKNOWN 사유가 있으면 제거(미기재≠미상).
        reason_codes = [c for c in reason_codes if c != "REGION_UNKNOWN"]
        hard_reasons = set(reason_codes) - {"FACTORY_REQUIRED_BUT_UNKNOWN"}
        # 재계산: 지역만 막혔던 경우 포함 후보 가능
        is_relevant = (
            not hard_reasons
            and deadline_ok
            and region_status == "eligible"
            and district_status == "eligible"
            and application_like
            and group_keyword_pass
        )
    # hard 제외 대신 본문 추천에서만 빼는 분리 코드(설명회 모집 본체·정보공개 애매건).
    _review_separate = {"INFO_SESSION_REVIEW", "AMBIGUOUS_NOTICE"}
    review_needed = (
        not is_relevant
        and (
            (
                bool(priority_keywords)
                and not (set(reason_codes) & detail_failure_blockers)
            )
            or detail_failure_review
            or bool(set(reason_codes) & _review_separate)
        )
    )
    # 지역 미상 surface(사용자 정책 2026-06-19): 지역만 모르고 그 외 조건은 적격이면
    #  버리지 말고 '지역 미상' 버킷으로 보내 보고 메일 하단에 함께 첨부한다(누락 방지).
    # W3: 추출 실패·NOT_SPECIFIED 는 이 버킷에 넣지 않는다(allow_region_unknown_bucket).
    region_unknown_review = (
        _fs.allow_region_unknown_bucket(item)
        and region_status == "unknown"
        and district_status != "not_eligible"
        and not is_relevant
        and deadline_ok
        and application_like
        and group_keyword_pass
        and not (hard_reasons - {"REGION_UNKNOWN", "LOW_CONFIDENCE"})
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
    if soft_excluded_keywords:
        notes.append(
            "본문 제외 단서 확인 필요 — 모집 본체와 함께 기재되어 자동 제외하지 않음: "
            + ", ".join(soft_excluded_keywords[:5])
        )
    if detail_failure_review:
        surf = _fs.surface_label_for_field(
            detail_status or region_extract_status, field="region")
        if surf:
            notes.append(f"{surf} — 원문 재확인 필요")
        else:
            notes.append("상세정보 추출 실패 — 원문 재확인 필요")
    elif region_extract_status == _fs.NOT_SPECIFIED:
        notes.append(_fs.surface_label_for_field(_fs.NOT_SPECIFIED, field="region"))

    result.update({
        "is_relevant": is_relevant,
        "target_type": target_type,
        "notice_type": notice_type,
        "deadline_status": deadline_status,
        "region_status": region_status,
        "industry_status": "matched" if group_keyword_pass or matched_keywords or priority_keywords else "not_matched",
        # 그룹 or/and 키워드 게이트 통과 여부(순수). INDUSTRY_NOT_MATCHED 는 키워드 미스(3682행)와
        # 지원유형 불일치(3685행) 둘 다에서 붙어 코드만으론 구분 불가 → 소비측(feedback_suggest)이
        # '진짜 키워드 미스 vs 지원유형 불일치'를 가르도록 게이트 결과 자체를 노출한다.
        "group_keyword_pass": group_keyword_pass,
        "matched_keywords": matched_keywords,
        "excluded_keywords": excluded_keywords,
        "soft_excluded_keywords": soft_excluded_keywords,
        "priority_keyword": bool(priority_keywords),
        "priority_keywords": priority_keywords,
        "relevance_score": relevance_score,
        "exclude_reason_codes": reason_codes,
        "filter_confidence": (
            "medium" if soft_excluded_keywords or detail_failure
            else ("high" if is_relevant or reason_codes else "medium")
        ),
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
        "detail_failure_review": detail_failure_review,
        "region_unknown_review": region_unknown_review,
        "business_years_status": biz_years_status,
        "support_amount_status": amount_status,
        # 표시용 — 구체 유형이 있으면 '그외'는 숨긴다(게이트는 classify_support_type 원본을 그대로 사용).
        "_types": ([t for t in classify_support_type(item) if t != "그외"] or ["그외"]),
    })
    return result


def _notice_sort_key(item: dict) -> tuple[int, int, int, int]:
    pri = item.get("priority_keywords") or []
    fund_first = 0 if any(p in FUND_PRIORITY_LABELS for p in pri) else 1
    return (
        fund_first,
        0 if item.get("priority_keyword") else 1,
        -int(item.get("relevance_score", 0) or item.get("_match_score", 0) or 0),
        0 if item.get("deadline_status") == "open" else 1,
    )


def filter_for_group_with_diagnostics(items: list[dict], group: dict, today=None) -> dict:
    included: list[dict] = []
    review: list[dict] = []
    region_unknown: list[dict] = []
    excluded: list[dict] = []
    for item in items:
        evaluated = evaluate_notice(item, group, today)
        if evaluated.get("is_relevant"):
            included.append(evaluated)
        elif evaluated.get("region_unknown_review"):
            region_unknown.append(evaluated)
        elif evaluated.get("review_needed"):
            review.append(evaluated)
        else:
            excluded.append(evaluated)
    included.sort(key=_notice_sort_key)
    review.sort(key=_notice_sort_key)
    region_unknown.sort(key=_notice_sort_key)
    excluded.sort(key=lambda it: (",".join(it.get("exclude_reason_codes", [])), it.get("title", "")))
    return {"included": included, "review": review, "region_unknown": region_unknown, "excluded": excluded}


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


def refine_included_by_score_llm(
    included: list[dict], group: dict,
) -> tuple[list[dict], list[dict]]:
    """evaluate_notice 통과분에 score_and_filter(점수+LLM 회색지대 컷)를 적용.

    group 에 score_threshold 가 없거나 llm_check_enabled 도 없으면 통과분 그대로.
    llm_check_enabled 만 켠 그룹은 score_threshold 기본 0(점수로는 거의 통과, LLM 밴드만 컷).
    API 키 없거나 anthropic 미설치 시 scoring.llm_relevance_check 가 보수적으로 통과시킨다.
    """
    if not _SCORE_OK:
        return included, []
    if "score_threshold" not in group and not group.get("llm_check_enabled"):
        return included, []
    g = group
    if "score_threshold" not in g:
        g = {**group, "score_threshold": 0}
    out = _score_and_filter(included, g)
    passed = list(out.get("passed") or [])
    rejected = []
    for it in out.get("rejected") or []:
        codes = list(it.get("exclude_reason_codes") or [])
        codes.append("SCORE_OR_LLM_REJECT")
        rejected.append({
            **it,
            "exclude_reason_codes": _unique(codes),
            "review_needed": True,
            "is_relevant": False,
            "filter_confidence": "medium",
            "notes": list(it.get("notes") or []) + ["점수/LLM 2차 컷오프"],
        })
    # 통과분에 점수 부착(정렬·표시용)
    audit_by_title = {
        str(a.get("title") or ""): a
        for a in (out.get("audit") or [])
        if a.get("decision") == "passed"
    }
    enriched = []
    for it in passed:
        title_key = str(it.get("title") or "")[:80]
        a = audit_by_title.get(title_key) or {}
        enriched.append({
            **it,
            "_match_score": a.get("score", it.get("_match_score")),
            "_score_reasons": a.get("reasons") or [],
            "_llm_check": a.get("llm"),
        })
    enriched.sort(key=_notice_sort_key)
    return enriched, rejected



# ══════════════════════════════════════════════════════════════════
# 렌더링 / Claude 요약
# ══════════════════════════════════════════════════════════════════

_REPORT_REGION_RANK = {"전국": 3, "서울": 4, "경기": 5, "인천": 6, "충청": 7}
_REPORT_BUCKET_LABEL = {1: "기업마당", 2: "K-스타트업", 3: "전국 대상", 4: "서울",
                        5: "경기", 6: "인천", 7: "충청", 8: "기타"}


def _report_region(item: dict) -> str:
    """[원본전체] 정렬용 지역 판정. 지역 미표기는 '전국' 기본 + 주관기관명으로 지역 보강."""
    tags = _title_region_tags(item)
    text = f"{item.get('title','')} {item.get('description','')} {item.get('region_field','')}"
    src = f"{item.get('author','')} {item.get('source','')}"
    det = _detect_target_regions(text)
    regions = set(tags) | set(det.get("regions", []))
    for r in ("서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
              "강원", "전북", "전남", "경북", "경남", "제주"):
        if r in src:
            regions.add(r)
    if any(x in src or x in text for x in ("충남", "충북", "충청")):
        regions.add("충청")
    if det.get("nationwide") or "전국" in text:
        return "전국"
    for r in ("서울", "경기", "인천"):
        if r in regions:
            return r
    if regions & {"충북", "충남", "충청"}:
        return "충청"
    if regions:
        return "기타지역"
    return "전국"


def _report_rank(item: dict) -> int:
    """[원본전체] 정렬 순서: 1기업마당 2K스타트업 3전국 4서울 5경기 6인천 7충청 8기타."""
    src = (str(item.get("source", "")) + " " + str(item.get("author", ""))).lower()
    if "기업마당" in src or "bizinfo" in src:
        return 1
    if "startup" in src or "k스타트업" in src or "케이스타트업" in src:
        return 2
    return _REPORT_REGION_RANK.get(_report_region(item), 8)


def render_all(items: list[dict], dedup_count: int, date_unknown: int, include_unknown: bool = True) -> str:
    # 출처·지역 순으로 묶어 정렬: 기업마당 > K스타트업 > 전국 > 서울 > 경기 > 인천 > 충청 > 기타.
    buckets: dict[int, list] = {}
    for it in items:
        buckets.setdefault(_report_rank(it), []).append(it)
    unknown_note = f" / 날짜불명 {date_unknown}건 포함" if include_unknown and date_unknown else (f" / 날짜불명 {date_unknown}건 제외됨" if not include_unknown and date_unknown else "")
    lines = [f"전체 수집 — {len(items)}건 (중복제거 후){unknown_note}\n"]
    for rank in sorted(buckets):
        src_items = buckets[rank]
        label = _REPORT_BUCKET_LABEL.get(rank, "기타")
        lines += [f"\n━━━ {label} — {len(src_items)}건 ━━━"]
        for it in src_items:
            dl = resolve_item_deadline(it)
            # 다이제스트와 같은 정제를 태운다 — 예전엔 원본을 그대로 찍어
            # "&amp;" 같은 HTML 엔티티와 "새로운게시글" 배지가 그대로 메일에 나갔다.
            title = strip_title_badges(_mail_clean_text(it.get("title") or "(제목없음)", limit=160))
            author = _mail_clean_text(it.get("author") or "", limit=80) or "미기재"
            lines += [f"▸ {title}",
                      f"  기관: {author} | 마감: {dl or '미기재'}"
                      f" | 등록: {it.get('posted_date') or '날짜불명'}"]
            if it.get("link"):
                lines.append(f"  링크: {it['link']}")
            lines.append("")
    return "\n".join(lines).strip()


def mail_topic(items: list[dict]) -> str:
    if items and all(it.get("source") == SEMAS_LOAN_SOURCE for it in items):
        return SEMAS_LOAN_TITLE
    # 내용 기반 제목 — 기존엔 무조건 '수출·해외진출 공고' 고정이라 AI 공고도 그 제목으로 오발송됨.
    # 우선키워드 빈도 top 2 로 라벨링, 없으면 중립 '지원사업 공고'.
    counts: dict[str, int] = {}
    for it in items:
        for k in (it.get("priority_keywords") or []):
            counts[k] = counts.get(k, 0) + 1
    if counts:
        top = sorted(counts, key=lambda k: (-counts[k], k))[:2]
        return "·".join(top) + " 공고"
    return "지원사업 공고"


def _plain_text(s: str, limit: int = 1500) -> str:
    """HTML 태그·엔티티 제거 → 사용자용 평문. 길면 자른다."""
    if not s:
        return ""
    if "<" in s:
        s = BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:limit].rstrip() + " …") if len(s) > limit else s


MAIL_SUPPORT_BLURB_LIMIT = 160
REGION_UNKNOWN_MAIL_LIMIT = 10

_MAIL_FOOTER_MARKERS = (
    "개인정보처리방침", "영상정보처리기기", "이메일무단수집거부", "Copyright",
    "이 페이지에서 제공하는 정보", "패밀리 사이트", "목록으로 바로가기",
)
_MAIL_NAV_TOKENS = (
    "메인", "회원가입", "로그인", "고객센터", "재단소개", "인사말", "연 혁", "조직도",
    "업무안내", "알림마당", "공지사항", "채용정보", "자료실", "홍보마당", "정보공개",
    # 게시판 목록/메뉴를 통째로 긁었을 때만 나오는 토큰(공고 본문에는 거의 없다).
    "전체메뉴", "전체보기", "카테고리", "회원서비스", "주요소식", "입주공고", "유관기관",
    "사업고시", "센터뉴스", "뉴스레터", "글쓴이", "작성시간", "조회수", "좋아요", "검색하기",
)

# 게시판 목록·상세 페이지의 표 머리글/메타값 — 공고 내용이 아니라 화면 부속물이다.
# (실측: 메일 '지원내용'에 "주관기관 : 이종석 2026-08-03 777" 처럼 담당자·작성일·조회수가 그대로 노출됨)
_MAIL_LIST_NOISE_RE = (
    re.compile(r"제목\s+글쓴이\s+작성시간\s+조회수\s+좋아요"),
    re.compile(r"구분\s+제목\s+작성일\s+조회\s+접수기간\s+상태"),
    re.compile(r"전체메뉴\s*닫기"),
    re.compile(r"총\s*\d[\d,]*\s*건\s*검색하기"),
    re.compile(r"주관기관\s*[:：]\s*[가-힣]{2,4}(?=\s|$)"),   # 담당자 이름
    re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}\s+\d{1,7}(?=\s|$)"),  # 작성일 + 조회수
    re.compile(r"\(\s*D-\d+\s*\)"),                            # 남은 날짜 카운트다운
    re.compile(r"(?:^|\s)[가-힣]{2,6}\s*[:：]\s*(?=[가-힣]{2,6}\s*[:：])"),  # 값 없는 빈 라벨
)


def _mail_clean_text(value: object, *, limit: int = MAIL_SUPPORT_BLURB_LIMIT) -> str:
    """메일 표시용 텍스트 정제: HTML·Markdown·연락처·메뉴/푸터·긴 URL 제거."""
    raw = str(value or "")
    raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", raw)
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    text = _plain_text(raw, limit=6000)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", text)
    text = re.sub(r"(?:\+?82[-. ]?)?0\d{1,2}[-. )]\d{3,4}[-. ]\d{4}", " ", text)
    text = re.sub(r"(?:담당자|연락처|전화|이메일|팩스|fax|tel)\s*[:：]?\s*[^|·•]{0,45}", " ", text, flags=re.I)
    for marker in _MAIL_FOOTER_MARKERS:
        pos = text.find(marker)
        if pos >= 80:
            text = text[:pos]
    # 목록성 판정은 노이즈를 지우기 '전'에 한다 — 지우고 나면 판정 근거가 함께 사라진다.
    # (실측: IDSC 케이스는 "전체메뉴 닫기"·"총 273 건 검색하기" 를 먼저 지우자 토큰이 4개로 줄어 빠져나갔다.)
    nav_hits = sum(1 for token in _MAIL_NAV_TOKENS if token in text[:500])
    nav_hits += sum(1 for noise_re in _MAIL_LIST_NOISE_RE if noise_re.search(text[:1000]))
    for noise_re in _MAIL_LIST_NOISE_RE:
        text = noise_re.sub(" ", text)
    if nav_hits >= 5:
        anchors = [text.find(token) for token in ("지원대상", "사업내용", "지원내용", "모집개요", "신청자격", "☞")]
        anchors = [pos for pos in anchors if pos >= 0]
        if not anchors:
            # 메뉴·게시판 목록만 긁혔고 공고 본문이 없다. 쓰레기를 보여주느니 비운다
            # (호출부가 다음 후보 필드나 "상세 공고문 확인" 으로 넘어간다).
            return ""
        text = text[min(anchors):]
    text = re.sub(r"\s+", " ", text).strip(" -·•|/")
    return (text[:limit].rstrip() + " …") if len(text) > limit else text


def _mail_target_text(item: dict) -> str:
    for key in ("target_field", "target_age_field", "business_age_text"):
        value = _mail_clean_text(item.get(key), limit=180)
        if value:
            return value
    return "공고문 확인"


def _mail_support_blurb(item: dict, limit: int = MAIL_SUPPORT_BLURB_LIMIT) -> str:
    """구조화 지원내용을 우선하고, 모바일 한 화면 기준 160자로 제한한다."""
    structured = _mail_clean_text(item.get("support_field"), limit=limit)
    description = _mail_clean_text(item.get("description"), limit=limit)
    candidate = structured if len(structured) >= 25 else description or structured
    title = _mail_clean_text(item.get("title"), limit=200)
    if title and candidate.startswith(title):
        candidate = candidate[len(title):].lstrip(" :-·•")
    # 정제 후 남은 게 라벨 부스러기 수준이면 보여주지 않는다(엉뚱한 글자보다 '확인'이 낫다).
    if len(candidate.strip()) < 12:
        return "상세 공고문 확인"
    return candidate or "상세 공고문 확인"


def _mail_fit_reason(item: dict) -> str:
    for key in ("fit_reason", "match_reason", "company_match_reason"):
        value = _mail_clean_text(item.get(key), limit=160)
        if value:
            return value
    types = [str(v) for v in (item.get("_types") or []) if str(v).strip()]
    region = _region_label(item)
    parts = []
    if item.get("priority_keyword"):
        parts.append("우선 검토 대상")
    if types:
        parts.append("·".join(types[:2]))
    if region != "확인 필요" and not region.endswith("전체"):
        parts.append(region)
    return " / ".join(parts) or "그룹 조건과 일치"


def fallback_body(items: list[dict]) -> str:
    """모바일 메일용 8줄 카드. 내부판정값·원문전체·연락처는 표시하지 않는다."""
    lines: list[str] = []
    items = sorted(items, key=_notice_sort_key)
    imminent = [it for it in items if is_imminent(it.get("deadline", ""))]
    if imminent:
        lines.append("⚠️ 7일 이내 마감: " + ", ".join(
            _mail_clean_text(it.get("title"), limit=45) for it in imminent[:5]
        ))
        lines.append("")
    sections = [
        ("우선 추천", [it for it in items if it.get("priority_keyword")]),
        ("일반 추천", [it for it in items if not it.get("priority_keyword")]),
    ]
    # 번호는 '실제로 표시되는' 섹션에만 순서대로 붙인다.
    # (예전엔 번호가 제목에 박혀 있어, 우선 추천이 비면 본문이 "2. 일반 추천" 부터 시작했다.)
    visible = [(title, its) for title, its in sections if its]
    for idx, (section_title, section_items) in enumerate(visible, start=1):
        lines.append(f"{idx}. {section_title}" if len(visible) > 1 else section_title)
        for it in section_items:
            title = strip_title_badges(_mail_clean_text(it.get("title") or "(제목없음)", limit=160))
            _badge = {"EXTENDED": "[마감연장] ", "REANNOUNCED": "[재공고] ", "UPDATED": "[수정] "}.get(it.get("_change_type"), "")
            title = _badge + title
            # 기관명이 비면 수집 출처라도 보여준다("미기재"보다 어디서 온 공고인지가 낫다).
            author = _mail_clean_text(it.get("author") or it.get("source") or "미기재", limit=80)
            types = " · ".join(str(v) for v in (it.get("_types") or ["미분류"])[:2])
            region = _region_label(it)
            display_region = "제한 없음" if region.endswith("전체") else region
            # 신청기간(시작~종료)이 잡힌 공고는 '마감' 이 아니라 '접수기간' 으로 적는다.
            deadline_text = resolve_item_deadline(it) or "미기재"
            deadline_label = "접수기간" if "~" in deadline_text else "마감"
            lines.extend([
                "──────────────────",
                f"📌 {title}",
                f"• 기관: {author} | 유형: {types}",
                f"• 대상: {_mail_target_text(it)}",
                f"• 지원내용: {_mail_support_blurb(it)}",
                f"• {deadline_label}: {deadline_text} | 지역: {display_region}",
                f"• 적합사유: {_mail_fit_reason(it)}",
                f"• 원문: {it.get('link') or '미기재'}",
            ])
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
        # 표 깨짐 방지(|)뿐 아니라 HTML 엔티티·배지도 걷어낸다(render_all 과 동일 기준).
        title = strip_title_badges(_mail_clean_text(it.get("title") or "", limit=160)).replace("|", "/")
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


def select_region_unknown_for_mail(items: list[dict], limit: int = REGION_UNKNOWN_MAIL_LIMIT) -> list[dict]:
    """지원사업성이 확인된 지역미상만 우선순위순으로 최대 limit건 표시한다."""
    clean = [it for it in items if not is_admin_noise(it) and not is_report_junk(it)]
    clean = sorted(clean, key=lambda it: (
        0 if it.get("priority_keyword") else 1,
        _notice_sort_key(it),
    ))
    return clean[:max(0, int(limit))]


def write_region_unknown_report(items: list[dict], group_name: str, *, run_at: datetime | None = None) -> Path | None:
    """메일에서 생략된 지역미상 전체 목록을 관리자 로그로 저장한다."""
    if not items:
        return None
    run_at = run_at or datetime.now(KST)
    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(group_name or "group")).strip("_")[:50] or "group"
    path = LOGS_DIR / f"region_unknown_{run_at:%Y%m%d}_{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 지역 미상 관리자 리포트 — {group_name}", "",
        f"- 생성: {run_at.strftime('%Y-%m-%d %H:%M KST')}",
        f"- 전체: {len(items)}건", "",
    ]
    for it in items:
        lines.append(
            f"- {it.get('title') or '(제목없음)'} | {it.get('author') or '미기재'} | "
            f"마감 {resolve_item_deadline(it) or '미기재'} | {it.get('link') or ''}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_region_unknown(items: list[dict], limit: int = REGION_UNKNOWN_MAIL_LIMIT, *, total_count: int | None = None) -> str:
    """메일에는 최대 10건만 표시하고 나머지는 관리자 리포트로 분리한다."""
    if not items:
        return ""
    shown = select_region_unknown_for_mail(items, limit=limit)
    total = len(items) if total_count is None else int(total_count)
    if not shown:
        return ""
    lines = [
        "\n\n────────────────────────────────",
        f"📍 지역 확인 필요 (메일 표시 {len(shown)}건 / 전체 {total}건)",
    ]
    for it in shown:
        try:
            from mail_core.operations.field_status import (
                region_field_status,
                surface_label_for_field,
            )
            surf = surface_label_for_field(region_field_status(it), field="region")
        except Exception:
            surf = ""
        title_line = f"\n▸ {_mail_clean_text(it.get('title') or '(제목없음)', limit=120)}"
        if surf:
            title_line += f" [{surf}]"
        lines.append(title_line)
        lines.append(
            f"  기관: {_mail_clean_text(it.get('author') or '미기재', limit=70)}"
            f" | 마감: {resolve_item_deadline(it) or '미기재'}"
        )
        if it.get("link"):
            lines.append(f"  원문: {it['link']}")
    if total > len(shown):
        lines.append(f"\n나머지 {total - len(shown)}건은 관리자 지역미상 리포트에 저장했습니다.")
    return "\n".join(lines)

def claude_summarize(items: list[dict], group: dict) -> str:
    """메일 본문 렌더. 기본은 수집 필드만 사용(금액·날짜를 LLM이 지어내지 않게).

    MONITOR_DIGEST_LLM=1 이면 맨 위에 '한 줄 적합성' 코멘트만 LLM으로 붙인다.
    공고별 금액·마감·링크는 여전히 fallback_body(원문 필드)만 쓴다.
    """
    if not items:
        return ""
    body = fallback_body(sorted(items, key=_notice_sort_key)[:MAX_FOR_CLAUDE])
    if os.environ.get("MONITOR_DIGEST_LLM", "") not in ("1", "true", "True"):
        return body
    try:
        from mail_core.matching.scoring import llm_relevance_check
    except Exception:
        return body
    # 상위 3건만 짧은 코멘트 — 비용·환각 최소화
    notes = []
    for it in sorted(items, key=_notice_sort_key)[:3]:
        r = llm_relevance_check(it, group)
        reason = str(r.get("reason") or "").strip()
        if reason and r.get("is_relevant", True):
            title = strip_title_badges(_mail_clean_text(it.get("title"), limit=40))
            notes.append(f"- {title}: {reason[:80]}")
    if not notes:
        return body
    return "AI 한줄 메모(참고·원문 수치 아님):\n" + "\n".join(notes) + "\n\n" + body


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

# 테스트 실발송 안전장치: 값이 있으면 모든 발송 수신자를 이 주소 하나로 강제한다.
# (그룹·raw_all·watchlist 등 모든 발송 경로가 send_email/send_to_list 를 거치므로 여기서 일괄 차단)
_ONLY_TO: str = ""

# 사용자 ⭕/❌ 피드백 루프(Tier C 골든 축적) — 모듈이 없어도 발송은 그대로(표시 전용).
try:
    from mail_core.delivery import feedback as _feedback_mod
    _FEEDBACK_OK = True
except Exception:  # noqa: BLE001
    _feedback_mod = None
    _FEEDBACK_OK = False


def _feedback_links_enabled() -> bool:
    """서명키가 있는 경우에만 O/X 링크를 표시한다.

    미서명 피드백은 누구나 제목을 위조할 수 있어 P0 학습 입력으로 쓰지 않는다. 키가 없으면
    피드백 기능만 비활성화하고 공고 발송은 정상 진행한다.
    """
    return (
        _FEEDBACK_OK
        and bool(getattr(_feedback_mod, "feedback_token", None))
        and _feedback_mod.feedback_token.enabled()
        and os.getenv("MONITOR_NO_FEEDBACK_LINKS", "") not in ("1", "true", "True")
    )


# 본문(plain)의 링크를 HTML 파트에서 실제 클릭 가능한 앵커로 바꾼다.
# (기존엔 escape 만 해 mailto 피드백 링크가 눌리지 않았다 — 공고 🔗 링크도 함께 클릭 가능해짐)
_LINK_RE = re.compile(r"""(https?://[^\s<>"']+|mailto:[^\s<>"']+)""")


def _linkify_html(text: str) -> str:
    """escape + URL→<a> + 줄바꿈→<br>. 피드백 mailto 는 '⭕ 맞아요/❌ 아니에요' 라벨로 표시."""
    text = text or ""
    out: list[str] = []
    pos = 0
    for m in _LINK_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        raw = m.group(0)
        url = raw.rstrip(".,;)")            # 문장부호는 링크에서 제외
        tail = raw[len(url):]
        label = ""
        if _FEEDBACK_OK:
            try:
                label = _feedback_mod.feedback_link_label(url)
            except Exception:  # noqa: BLE001
                label = ""
        out.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(label or url)}</a>')
        out.append(html.escape(tail))
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


def _render_feedback_block(items: list[dict]) -> str:
    """digest 하단 '이 추천 맞았나요?' ⭕/❌ 섹션. 실패해도 발송은 계속(표시 전용)."""
    if not (items and _feedback_links_enabled()):
        return ""
    try:
        return _feedback_mod.render_feedback_block(items, GMAIL_ADDRESS)
    except Exception as e:  # noqa: BLE001
        log.warning("피드백 링크 생성 실패(무시): %s", e)
        return ""


def _build_mime_message(subject: str, body: str, to: str) -> MIMEMultipart:
    """발송·초안 공용 MIME 구성(plain + html). send_email/save_draft_to_gmail 가 공유한다."""
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, GMAIL_ADDRESS, to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(
        f"<html><body style='font-family:Arial;line-height:1.7'>"
        f"<pre style='white-space:pre-wrap;font-family:inherit'>{_linkify_html(body)}</pre>"
        f"</body></html>", "html", "utf-8"))
    return msg


def send_email(subject: str, body: str, to: str) -> None:
    # 초안 모드: 실제 발송(SMTP) 대신 Gmail Drafts 에 초안만 생성한다(safe-by-default).
    # (send_to_list 를 거치지 않는 직접 호출 경로도 초안 모드에선 발송이 아닌 초안으로 우회)
    if _DRAFT_MODE:
        save_draft_to_gmail(subject, body, to)
        return
    # safe-by-default: _ALLOW_SMTP_SEND 가 False면 직접 호출이라도 SMTP 연결 없이 즉시 종료한다.
    # (send_to_list 를 거치지 않는 워치리스트 등 직접 호출 경로의 실발송 사고를 원천 차단)
    if not _ALLOW_SMTP_SEND:
        log.info(
            "send_email 생략 (allow_send=False): subject=%s to=%s",
            subject[:60], _mask_email(to or _ONLY_TO or ""),
        )
        return
    if _ONLY_TO:
        to = _ONLY_TO
    msg = _build_mime_message(subject, body, to)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        srv.sendmail(GMAIL_ADDRESS, to, msg.as_string())
    log.info("발송 완료 → %s", _mask_email(to))


def _find_drafts_folder(imap: imaplib.IMAP4) -> str:
    """Gmail Drafts 특수폴더명을 로케일 무관하게 탐색한다.

    LIST 응답에서 폴더 속성에 `\\Drafts` 플래그가 붙은 폴더를 찾아 그(인코딩된) 폴더명을
    돌려준다. 한국어 계정(`[Gmail]/임시보관함` 등)은 modified-UTF-7 로 인코딩돼 오지만,
    APPEND 에는 그 원문(wire) 폴더명을 그대로 써야 하므로 디코딩하지 않는다.
    탐색 실패 시 표준 폴백 `[Gmail]/Drafts`.
    """
    try:
        typ, data = imap.list('""', "*")
        if typ == "OK":
            for raw in data or []:
                line = (
                    raw.decode("utf-8", "ignore")
                    if isinstance(raw, (bytes, bytearray))
                    else str(raw)
                )
                if "\\Drafts" not in line:
                    continue
                # 예: (\HasNoChildren \Drafts) "/" "[Gmail]/&vPSw3ITW...-"
                m = re.search(r'"([^"]*)"\s*$', line)
                if m:
                    return m.group(1)
                return line.rsplit(" ", 1)[-1].strip().strip('"')
    except Exception as e:  # 탐색 실패는 폴백으로 흡수(본 작업 비차단)
        log.warning("Drafts 폴더 탐색 실패 — 폴백([Gmail]/Drafts) 사용: %s", e)
    return "[Gmail]/Drafts"


def save_draft_to_gmail(subject: str, body: str, to: str) -> bool:
    """Gmail Drafts 특수폴더에 RFC822 메시지를 IMAP APPEND 해 '초안'으로 저장한다(발송 아님).

    safe-by-default: SMTP 발송을 전혀 하지 않고, 사람이 Gmail 초안함에서 확인 후 직접
    보내도록 초안만 만든다. 자격증명(GMAIL_ADDRESS/GMAIL_APP_PASSWORD)이 없으면 예외 없이
    False 를 돌려준다(본 작업 비차단). 성공 시 True.
    """
    target = _ONLY_TO or to
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD):
        log.info("GMAIL 미설정 — 초안 생성 생략: to=%s", _mask_email(target))
        return False
    msg = _build_mime_message(subject, body, target)
    raw = msg.as_bytes()
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        folder = _find_drafts_folder(imap)
        typ, resp = imap.append(
            folder, r"(\Draft)", imaplib.Time2Internaldate(time.time()), raw,
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP APPEND 실패({folder}): {typ} {resp!r}")
        log.info("초안 생성 완료 → %s (folder=%s)", _mask_email(target), folder)
        return True
    finally:
        try:
            imap.logout()
        except Exception:  # 로그아웃 실패는 무시(초안은 이미 저장됨)
            pass


def draft_to_list(subject: str, body: str, recipients: list[str]) -> None:
    """다수 수신자용 초안 생성 — 유효 수신자별로 Gmail 초안 1건씩 APPEND(발송의 초안 버전).

    _DRAFT_OK/_DRAFT_FAIL 카운트. 개별 실패는 전체를 막지 않고 로깅만 한다(RULES 8: 자동
    재발송 금지 — 여기선 애초에 발송이 아니라 초안이라 무관).
    """
    global _DRAFT_OK, _DRAFT_FAIL, _LAST_DRAFT_ERR
    targets = [_ONLY_TO] if _ONLY_TO else validate_recipients(recipients)["valid"]
    if not targets:
        log.info("초안 생성 대상 없음: subject=%s", subject[:60])
        return
    for to in targets:
        try:
            if save_draft_to_gmail(subject, body, to):
                _DRAFT_OK += 1
            else:
                _DRAFT_FAIL += 1
        except Exception as e:
            _DRAFT_FAIL += 1
            _LAST_DRAFT_ERR = str(e)
            log.error("초안 생성 실패 (%s): %s", _mask_email(to), e)


def send_to_list(subject: str, body: str, recipients: list[str], *, idem: dict | None = None) -> set[str]:
    """수신자별 개별 발송(To/Cc 상호노출 없음).

    idem 이 주어지면 (기준일·그룹·수신자) 단위 멱등 발송을 한다:
      idem = {"date": 기준일자, "group": 그룹키, "path": 상태파일경로}
    - 이미 성공 기록된 (일자·그룹·수신자)는 건너뛴다 → 크래시/부분실패 후 재실행이 성공
      수신자에게 중복 발송하지 않음(진단서 #113·#114).
    - 발송 성공 즉시 체크포인트 저장 → 루프 도중 중단돼도 이미 보낸 수신자는 보존(#144).
    idem 이 없으면 종전 동작(멱등 없이 전량 발송) — watchlist·원본전체 등 기존 호출 하위호환.
    """
    if _ONLY_TO:
        recipients = [_ONLY_TO]
    # 초안 모드: 발송 대신 각 수신자별 Gmail 초안 생성(allow_send 게이트와 무관하게 초안만).
    if _DRAFT_MODE:
        draft_to_list(subject, body, recipients)
        return set()
    if not _ALLOW_SMTP_SEND:
        checked = validate_recipients(recipients)
        log.info(
            "발송 생략 (allow_send=False): subject=%s recipients=%s",
            subject[:60], ", ".join(checked["masked"]) or "(없음)",
        )
        return set()
    global _SEND_OK, _SEND_FAIL, _LAST_SEND_ERR
    delivered: set[str] = delivery_state.load(idem["path"]) if idem else set()
    delivered_recipients: set[str] = set()
    for to in validate_recipients(recipients)["valid"]:
        dkey = delivery_state.key(
            idem["date"], idem["group"], to, tenant=idem.get("tenant", "default"),
        ) if idem else None
        if dkey is not None and (
            dkey in delivered or delivery_state.legacy_key(idem["date"], idem["group"], to) in delivered
        ):
            log.info("멱등 skip (이미 발송됨): %s [%s]", _mask_email(to), idem["group"])
            delivered_recipients.add(to.strip().lower())
            continue
        try:
            send_email(subject, body, to)
            _SEND_OK += 1
            delivered_recipients.add(to.strip().lower())
            if idem and dkey is not None:
                # 성공 즉시 체크포인트 — 중단 시에도 이 수신자는 재발송 안 됨.
                delivery_state.mark(idem["path"], dkey, _cache=delivered)
        except Exception as e:
            _SEND_FAIL += 1
            _LAST_SEND_ERR = str(e)
            log.error("발송 실패 (%s): %s", _mask_email(to), e)
    return delivered_recipients


def guard_group_recipients(
    recipients: list[str], settings: dict, group_name: str, *, group: dict | None = None,
) -> list[str]:
    """#120: settings['recipient_allowlist'] 설정 시 화이트리스트 밖 수신자를 제외·경보.

    groups.json 오설정(A그룹 recipients 에 B고객 유입)으로 타 그룹 다이제스트가 잘못 나가는 것을
    방지한다. allowlist 미설정이면 종전 그대로(동작 불변, opt-in).
    """
    scoped = list(recipients)
    # 새 private payload 경로에서는 그룹 ID와 tenant ID 모두 일치한 수신자만 통과한다.
    # payload 가 없을 때는 이미 평문 public config 가 recipients=[] 이므로 자연스럽게 fail-closed 된다.
    if group is not None and private_config.load_private_payload():
        scoped = private_config.allowed_recipients(group, scoped)
        if len(scoped) != len(recipients):
            log.error("tenant 수신자 경계 위반(그룹 '%s') — 발송 제외 %d명",
                      group_name, len(recipients) - len(scoped))
            alert_ntfy("recipient_tenant_guard",
                       f"[{group_name}] tenant 경계 밖 수신자 발송 차단",
                       priority="high", tags="warning")
    allow = settings.get("recipient_allowlist") or []
    if not allow:
        return scoped
    allow_set = {str(a).strip().lower() for a in allow}
    kept = [r for r in scoped if str(r).strip().lower() in allow_set]
    dropped = [r for r in scoped if str(r).strip().lower() not in allow_set]
    if dropped:
        log.error("수신자 화이트리스트 위반(그룹 '%s') — 발송 제외 %d명: %s",
                  group_name, len(dropped), ", ".join(_mask_email(d) for d in dropped))
        alert_ntfy("recipient_guard",
                   f"[{group_name}] 화이트리스트 밖 수신자 {len(dropped)}명 발송 차단(그룹 설정 확인)",
                   priority="high", tags="warning")
    return kept


def _outbox_targets(recipients: list[str]) -> list[str]:
    targets = [_ONLY_TO] if _ONLY_TO else recipients
    return validate_recipients(targets)["valid"]


def deliver_with_outbox(
    subject: str,
    body: str,
    recipients: list[str],
    *,
    date: str,
    tenant: str,
    group: str,
    notice_ids: list[str],
) -> None:
    """Persist a PII-encrypted delivery plan before SMTP, then checkpoint each recipient.

    ``seen_ids`` is deliberately updated later, after every planned delivery has either
    completed or been retained in this encrypted queue. That ordering prevents both lost
    notices and duplicate messages across crash/partial-recipient reruns (#113–#115).
    """
    targets = _outbox_targets(recipients)
    if not targets:
        log.warning("발송 대기열 생성 생략(유효 수신자 없음): group=%s", group)
        return
    entry = delivery_outbox.upsert(
        date=date,
        tenant=tenant,
        group=group,
        subject=subject,
        body=body,
        recipients=targets,
        notice_ids=notice_ids,
    )
    delivered = send_to_list(
        subject,
        body,
        targets,
        idem={"date": date, "tenant": tenant, "group": group, "path": str(DELIVERY_STATE_PATH)},
    )
    delivery_outbox.settle(entry["id"], delivered)


def retry_pending_outbox() -> None:
    """Finish only the recipients that remain after an interrupted send run."""
    for entry in delivery_outbox.pending():
        recipients = [str(value) for value in entry.get("recipients", [])]
        if not recipients:
            continue
        delivered = send_to_list(
            str(entry.get("subject") or ""),
            str(entry.get("body") or ""),
            recipients,
            idem={
                "date": str(entry.get("date") or ""),
                "tenant": str(entry.get("tenant") or "default"),
                "group": str(entry.get("group") or "outbox"),
                "path": str(DELIVERY_STATE_PATH),
            },
        )
        delivery_outbox.settle(str(entry.get("id") or ""), delivered)


def persist_completed_outbox(seen_ids: set[str]) -> set[str]:
    """Commit completed deliveries to seen_ids, then acknowledge their encrypted records."""
    completed = delivery_outbox.completed()
    if not completed:
        return seen_ids
    notice_ids = {
        str(notice_id) for entry in completed
        for notice_id in (entry.get("notice_ids") or []) if str(notice_id)
    }
    if notice_ids:
        seen_ids.update(notice_ids)
        save_seen_ids(seen_ids)
    delivery_outbox.acknowledge_completed({str(entry.get("id") or "") for entry in completed})
    return seen_ids


VOUCHER_KEYWORDS = ("수출바우처", "혁신바우처")


def _is_voucher(it: dict) -> bool:
    """수출바우처·혁신바우처 공고인지(제목·우선키워드 기준). 별도 강조·푸시 대상."""
    text = str(it.get("title", "")) + " " + " ".join(it.get("priority_keywords", []) or [])
    return any(v in text for v in VOUCHER_KEYWORDS)


def alert_email(subject: str, body: str) -> None:
    """PC용 알림 이메일 — 커버리지 이상 등 '헬스 알림'을 메일로 발송(PC에서 확인).
    announcement 발송 게이트(_ALLOW_SMTP_SEND)와 무관하게 항상 시도한다(alert_ntfy 와
    동일 정책 — dry-run 스케줄에서도 헬스 알림은 나가야 함). 수신=자기 자신(GMAIL_ADDRESS,
    안전 수신자 규칙). 실패해도 본 작업엔 영향 없음."""
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD):
        log.info("GMAIL 미설정 — PC 알림 이메일 생략")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[mail-monitor] {subject}"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = GMAIL_ADDRESS
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(
            f"<html><body style='font-family:Arial;line-height:1.7'>"
            f"<pre style='white-space:pre-wrap;font-family:inherit'>{html_pre(body)}</pre>"
            f"</body></html>", "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            srv.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        log.info("PC 알림 이메일 발송: %s", subject)
    except Exception as e:  # 알림 실패는 본 작업을 막지 않는다
        log.warning("PC 알림 이메일 실패(무시): %s", e)


def alert_ntfy(title: str, message: str, priority: str = "high", tags: str = "warning") -> None:
    """폰 푸시(ntfy) 발송. NTFY_TOPIC 환경변수가 있을 때만. 실패해도 본 작업엔 영향 없음."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        log.info("NTFY_TOPIC 미설정 — 폰 알림 생략")
        return
    try:
        ascii_title = title.encode("ascii", "ignore").decode().strip() or "mail-monitor"
        httpx.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": ascii_title, "Priority": priority, "Tags": tags},
            timeout=15,
        )
        log.info("ntfy 폰 알림 발송 완료")
    except Exception as e:
        log.warning("ntfy 알림 실패(무시): %s", e)


# ── 집중 모니터링 워치리스트 ──────────────────────────────────────────────────
# 사용자가 준 키워드/제목 또는 URL 에 걸리는 공고는 날짜·그룹 필터를 우회해 강제 포함하고
# 전용 메일 + 폰 푸시로 강조한다. '놓치면 안 되는 공고'를 절대 안 놓치기 위한 장치.
WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"


def load_watchlist() -> dict:
    """watchlist.json 로드(키워드·URL·수신자). 없거나 형식오류면 빈 워치리스트."""
    raw = load_json(WATCHLIST_PATH, {})
    if not isinstance(raw, dict):
        return {"keywords": [], "urls": [], "recipients": []}
    private_payload = private_config.load_private_payload()
    # 테스트/진단이 임시 watchlist 경로를 주입할 때는 운영 수신자 payload 를 섞지 않는다.
    if private_payload and WATCHLIST_PATH.resolve() == (CONFIG_DIR / "watchlist.json").resolve():
        raw = private_config.merge_watchlist(raw, private_payload)
    elif WATCHLIST_PATH.resolve() == (CONFIG_DIR / "watchlist.json").resolve():
        # 공개 운영 파일의 수신자는 무시한다. 암호화 payload 가 없는 상태에서는 발송하지 않는다.
        raw = {**raw, "recipients": []}
    normalized = {
        "keywords": [str(k).strip() for k in (raw.get("keywords") or []) if str(k).strip()],
        "urls": [str(u).strip() for u in (raw.get("urls") or []) if str(u).strip()],
        "recipients": [str(r).strip() for r in (raw.get("recipients") or []) if str(r).strip()],
    }
    for key in ("max_items", "url_max_age_days", "url_unknown_cap"):
        if key in raw:
            try:
                normalized[key] = int(raw[key])
            except (TypeError, ValueError):
                pass
    if raw.get("tenant_id"):
        normalized["tenant_id"] = private_config.normalize_tenant_id(raw.get("tenant_id"))
    return normalized


def _norm_url(u: str) -> str:
    """비교용 URL 정규화: 스킴·www·쿼리·앵커·끝슬래시 제거 + 소문자."""
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("?")[0].split("#")[0].rstrip("/")


def is_watchlisted(item: dict, watchlist: dict) -> bool:
    """공고가 워치리스트(키워드/제목 또는 URL)에 걸리는지. 걸리면 강제포함·강조 대상.
    ASCII 키워드(IP 등)는 단어경계 매칭으로 'equipment' 같은 오매칭 방지(_kw_in_text).

    키워드는 '제목·주관기관'만 본다(워치리스트 설명 문구의 '키워드/제목' 그대로).
    상세 보강된 본문(description)은 보지 않는다 — 6KB 본문·nav 잔여물에는 '지식재산'
    같은 단어가 우연히 들어가('한국지식재산보호원' 등), 1년 지난 마감 공고까지
    날짜필터를 우회해 그룹 digest 상단에 오르던 실사고(2026-07-24)의 원인이었다."""
    return bool(watchlist_match_kind(item, watchlist))


def watchlist_match_kind(item: dict, watchlist: dict) -> str:
    """'' | 'keyword' | 'url' — 키워드가 URL보다 우선."""
    kws = watchlist.get("keywords") or []
    if kws:
        text = f"{item.get('title','')} {item.get('author','')}".lower()
        if any(_kw_in_text(text, k.lower()) for k in kws):
            return "keyword"
    nurls = [n for n in (_norm_url(u) for u in (watchlist.get("urls") or [])) if n]
    if nurls:
        link = _norm_url(item.get("link") or item.get("url") or "")
        if link and any(link.startswith(n) or n in link for n in nurls):
            return "url"
    return ""


def _post_run_alert(result: dict) -> None:
    """클라우드 자동발송(main) 직후 실패/0통이면 폰 알림. 크래시는 워크플로 if:failure가 담당."""
    if not isinstance(result, dict) or not result.get("ok"):
        return
    stat = (
        f"수집 {result.get('collected', 0)}→신규 {result.get('new_items', 0)}"
        f"→대상 {result.get('filtered_items', 0)}건"
    )
    if _DRAFT_MODE:
        # 초안 모드: 실발송 없음 — 초안 생성 실패 시에만 폰 알림, 정상은 로깅만(0통 노이즈 방지).
        d_ok = result.get("drafts_created", _DRAFT_OK)
        d_fail = result.get("draft_failed", _DRAFT_FAIL)
        if d_fail > 0:
            alert_ntfy(
                "draft FAILED",
                f"⚠️ Gmail 초안 생성 실패 {d_fail}건 (성공 {d_ok}건).\n"
                f"마지막 오류: {_LAST_DRAFT_ERR[:200]}\n{stat}",
                priority="high", tags="rotating_light",
            )
        else:
            log.info("초안 생성 완료: %d건 — 폰 알림 생략", d_ok)
        return
    if _SEND_FAIL > 0:
        # PC(이메일)로 알림 — 자동발송이 실패로 조용히 멈추는 사고를 즉시 확인(사용자 PC 선호).
        alert_email(
            "공고 메일 발송 실패 — 확인 필요",
            f"⚠️ 공고 메일 발송 실패 {_SEND_FAIL}건 (성공 {_SEND_OK}건).\n"
            f"마지막 오류: {_LAST_SEND_ERR[:200]}\n{stat}",
        )
    elif _SEND_OK == 0 and os.environ.get("ALERT_ON_ZERO", "1") == "1":
        alert_ntfy(
            "mail 0 sent",
            f"ℹ️ 오늘 공고 메일 0통 (조건 매칭/신규 없음).\n{stat}",
            priority="default", tags="information_source",
        )
    else:
        log.info("발송 정상: 성공 %d건 — 폰 알림 생략", _SEND_OK)


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def execute_monitor(
    *,
    allow_send: bool = False,
    include_raw_all: bool = False,
    persist_seen: bool = False,
    draft_mode: bool = False,
    group_id: str = "",
    collection_gate: dict | None = None,
) -> dict:
    global _ALLOW_SMTP_SEND, _ALLOW_PERSIST_SEEN, _SEND_OK, _SEND_FAIL, _LAST_SEND_ERR, _RAW_STORE
    global _DRAFT_MODE, _DRAFT_OK, _DRAFT_FAIL, _LAST_DRAFT_ERR

    gate = collection_gate if isinstance(collection_gate, dict) else {}
    send_hold = bool(gate.get("send_hold"))
    try:
        from mail_core.operations.miss_remediation import effective_allow_send
        effective_send, hold_reason = effective_allow_send(
            allow_send, send_hold=send_hold)
    except Exception:
        effective_send, hold_reason = allow_send, "gate_import_error"
    if allow_send and not effective_send:
        log.warning(
            "RUN FAILED send_hold — 실발송 보류 (reason=%s, run_status=%s)",
            hold_reason, gate.get("run_status"),
        )
    elif allow_send and send_hold and effective_send:
        log.warning(
            "send_hold 이지만 발송 허용 (reason=%s) — shadow/override",
            hold_reason,
        )

    _ALLOW_SMTP_SEND = effective_send
    _ALLOW_PERSIST_SEEN = persist_seen
    _DRAFT_MODE = draft_mode
    _DRAFT_OK = 0
    _DRAFT_FAIL = 0
    _LAST_DRAFT_ERR = ""
    _SEND_OK = 0
    _SEND_FAIL = 0
    _LAST_SEND_ERR = ""
    _RAW_STORE = None

    # deliver: 실제 발송(effective_send) 또는 초안 생성(draft_mode)
    deliver = effective_send or draft_mode
    now = datetime.now(KST)
    mode = "send" if effective_send else ("draft" if draft_mode else "preview")
    log.info("=== 모니터링 시작 v6 (%s) / mode=%s ===", now.strftime("%Y-%m-%d %H:%M KST"), mode)

    sites    = load_sites()
    groups   = load_groups()
    settings = load_settings()
    seen_ids = load_seen_ids()
    if group_id:
        groups = [g for g in groups if g.get("id") == group_id]
        if not groups:
            log.error("그룹 '%s' 을(를) 찾을 수 없습니다", group_id)
            raise SystemExit(1)
        log.info("단일 그룹 모드: %s", groups[0].get("name", group_id))
    days_back = max(1, int(settings.get("days_back", 3) or 3))

    # 실제 자동발송은 암호화된 대기열 없이는 시작하지 않는다. 이전 중단 run 의 미완료
    # 수신자부터 재시도하고, 이미 완료된 건은 seen_ids 에 반영한 뒤 대기열에서 제거한다.
    if effective_send and persist_seen:
        if not delivery_outbox.is_ready():
            raise RuntimeError("실발송에는 MAIL_PRIVATE_CONFIG_KEY 또는 로컬 암호화 키가 필요합니다")
        retry_pending_outbox()
        seen_ids = persist_completed_outbox(seen_ids)

    if not sites:
        log.info("활성 사이트 없음. 종료.")
        return _with_raw_store_stats({"ok": True, "mode": mode, "reason": "no_active_sites"})
    if not groups:
        log.info("활성 그룹 없음. 종료.")
        return _with_raw_store_stats({"ok": True, "mode": mode, "reason": "no_active_groups"})

    target_date_early = delivery_cycle_date(now)
    # 기준일 전 수신자 멱등 완료면 수집 생략(주말 재실행 낭비 방지)
    if effective_send and persist_seen:
        try:
            from mail_core.delivery.skip_gate import should_skip_fetch_already_delivered
            _wl_early = load_watchlist()
            _skip = should_skip_fetch_already_delivered(
                target_date=str(target_date_early),
                groups=groups,
                settings=settings,
                watchlist=_wl_early,
                include_raw_all=include_raw_all,
                delivery_path=DELIVERY_STATE_PATH,
            )
            if _skip.get("skip"):
                log.info(
                    "기준일 %s 발송 단위 %s개 멱등 완료 — 수집·발송 생략 (%s)",
                    _skip.get("target_date"), _skip.get("units"), _skip.get("reason"),
                )
                return _with_raw_store_stats({
                    "ok": True,
                    "mode": mode,
                    "reason": "already_delivered",
                    "skipped_fetch": True,
                    "target_date": str(target_date_early),
                    "mail_sent": 0,
                    "collected": 0,
                    "new_items": 0,
                    "filtered_items": 0,
                })
        except Exception as e:
            log.warning("발송완료 스킵 게이트 실패(무시·수집 계속): %s", e)

    if _RawStore is not None:
        _RAW_STORE = _RawStore.from_settings(settings, run_day=now.date())

    # ① 전체 수집
    all_items = fetch_all(sites)
    if not all_items:
        log.info("수집 0건. 종료.")
        return _with_raw_store_stats({"ok": True, "mode": mode, "reason": "no_items"})
    log.info("수집 완료: %d건", len(all_items))

    # P1-17: 소스 상태관리 — 수집 결과를 source_health에 반영
    try:
        from mail_core.operations.source_health import (
            classify_source_status,
            update_source_health,
            should_alert,
            mark_alerted,
        )
        from mail_core.operations.source_health import TIER1_SOURCES

        # 소스별 수집 건수 집계
        items_by_source: dict[str, int] = {}
        for it in all_items:
            sid = str(it.get("source") or it.get("site_id") or "unknown")
            items_by_source[sid] = items_by_source.get(sid, 0) + 1

        # Tier 1 소스 상태 업데이트
        for site in sites:
            sid = str(site.get("id") or site.get("name") or "")
            if sid not in TIER1_SOURCES:
                continue
            count = items_by_source.get(sid, 0)
            status = classify_source_status(sid, item_count=count, parse_rate=1.0)
            update_source_health(sid, status, item_count=count, parse_rate=1.0)
            # 알림 확인
            if should_alert(sid):
                log.warning("소스 %s 장애 알림 필요", sid)
                mark_alerted(sid)
    except Exception as e:
        log.warning("소스 상태관리 실패(무시): %s", e)

    # ② 중복 제거
    deduped = dedup_items(all_items)
    dedup_removed = len(all_items) - len(deduped)

    # ③ 신규 + 최근 N영업일 재검사 + 수정/연장/재공고 버전 판정
    # 상세 enrich → 추출 재시도 → 버전 분류 순서 고정.
    # classify 를 retry 앞에 두면 FETCH 실패 스냅샷으로 허위 UPDATED(@vN) 재발송이 난다.
    notice_versions = load_notice_versions()
    version_candidates = select_notice_version_candidates(
        deduped, seen_ids, notice_versions, now=now, days_back=days_back,
    )
    enriched_candidates = enrich_items(version_candidates)

    extraction_rates_by_site: dict = {}
    extraction_retry_plan: list = []
    extraction_retry_stats: dict = {}
    try:
        from mail_core.operations.field_status import (
            compute_extraction_rates,
            plan_extraction_retries,
            run_extraction_retries,
            write_extraction_rates_report,
        )
        from mail_core.operations.miss_remediation import enqueue_extraction_failures

        _sleep_raw = os.environ.get("MONITOR_EXTRACTION_RETRY_SLEEP", "")
        if _sleep_raw == "0":
            _backoff = (0, 0)
            _sleep_fn = lambda _s: None  # noqa: E731
        else:
            _backoff = (60, 180)
            _sleep_fn = None
        enriched_candidates, extraction_retry_stats = run_extraction_retries(
            enriched_candidates,
            enrich_item_from_detail,
            backoff_sec=_backoff,
            sleep_fn=_sleep_fn,
        )
        if extraction_retry_stats.get("attempted"):
            log.info(
                "추출 재시도: planned=%s attempted=%s recovered=%s still_failed=%s",
                extraction_retry_stats.get("planned"),
                extraction_retry_stats.get("attempted"),
                extraction_retry_stats.get("recovered"),
                extraction_retry_stats.get("still_failed"),
            )
    except Exception as e:
        log.warning("extraction retry 실패(무시·분류 계속): %s", e)

    new_items, notice_version_updates = classify_notice_versions(
        enriched_candidates, seen_ids, notice_versions,
    )
    brand_new_count = sum(1 for it in new_items if it.get("_change_type") == "NEW")
    changed_count = len(new_items) - brand_new_count
    log.info("처리대상: 신규 %d / 중요변경 %d / 버전검사 %d", brand_new_count, changed_count, len(version_candidates))

    if _RAW_STORE is not None:
        _RAW_STORE.begin_run(collected=len(all_items), deduped=len(deduped), new_items=len(new_items))
        for it in new_items:
            _RAW_STORE.save_item_meta(it)

    try:
        from mail_core.operations.field_status import (
            compute_extraction_rates,
            plan_extraction_retries,
            write_extraction_rates_report,
        )
        from mail_core.operations.miss_remediation import enqueue_extraction_failures

        by_site: dict[str, list] = {}
        for it in new_items:
            sid = str(it.get("site_id") or it.get("source") or "unknown")
            by_site.setdefault(sid, []).append(it)
        extraction_rates_by_site = {
            sid: compute_extraction_rates(rows) for sid, rows in by_site.items()
        }
        enqueue_extraction_failures(new_items)
        extraction_retry_plan = plan_extraction_retries(new_items)
        write_extraction_rates_report(
            extraction_rates_by_site, run_at=now)
    except Exception as e:
        log.warning("extraction_rates/queue 실패(무시): %s", e)

    # W2: DEGRADED/P0 소스 공고는 발송 후보에서 제외 (정상 소스만 발송)
    p0_dropped: list = []
    gate_reports = gate.get("source_reports") or gate.get("p0_sources") or []
    if gate_reports:
        try:
            from mail_core.operations.miss_remediation import drop_items_from_p0_sources
            new_items, p0_dropped = drop_items_from_p0_sources(new_items, gate_reports)
            if p0_dropped:
                log.warning(
                    "P0 소스 공고 %d건 발송 후보에서 제외 (site P0 필터)",
                    len(p0_dropped),
                )
        except Exception as e:
            log.warning("P0 소스 필터 실패(무시): %s", e)
            p0_dropped = []

    # 집중 모니터링: 사용자 워치리스트(키워드/제목·URL) 매칭분 — 필터 우회 강제포함·강조 대상
    # 게시판 URL 전량 매칭 폭발 방지: 날짜창·max_items 선별(2026-07-26 74건 사고)
    watchlist = load_watchlist()
    watch_hits: list = []
    if watchlist["keywords"] or watchlist["urls"]:
        try:
            from mail_core.matching.watchlist_select import (
                select_watchlist_hits,
                watchlist_limits_from_config,
            )
            limits = watchlist_limits_from_config(watchlist)
            watch_hits = select_watchlist_hits(
                new_items,
                match_kind=lambda it: watchlist_match_kind(it, watchlist),
                today=now.date(),
                **limits,
            )
        except Exception as e:
            log.warning("워치리스트 선별 실패 — 전체 매칭으로 폴백: %s", e)
            watch_hits = [it for it in new_items if is_watchlisted(it, watchlist)]
    if watch_hits:
        log.info("🎯 집중 모니터링 매칭: %d건", len(watch_hits))

    # ④ 날짜 필터 (직전 영업일)
    recheck_dates = sorted(_recent_recheck_dates(now, days_back))
    # 발송 멱등 키는 재조회창의 끝(가장 오래된 날)이 아니라 실행 당일을 쓴다.
    # (days_back 을 늘리면 기준일이 과거로 후퇴해 발송이 조용히 멈춘다 — delivery_cycle_date 참조)
    target_date = delivery_cycle_date(now)
    window_label = f"{recheck_dates[0]} ~ {recheck_dates[-1]}"
    # 하루 2회 발송(07:30·18:30 KST)이라 제목에 회차를 붙여 오전분·저녁분을 구분한다.
    # 회차 경계는 발송 멱등 키와 같은 DELIVERY_PM_CUTOFF_HOUR 를 쓴다(표기·멱등 불일치 방지).
    _slot_label = "오전" if now.hour < DELIVERY_PM_CUTOFF_HOUR else "저녁"
    date_str    = f"{now.strftime('%m/%d')} {_slot_label}"

    include_unknown = settings.get("include_date_unknown", False)
    # 날짜불명 처리정책: 명시값 우선, 없으면 legacy include_date_unknown 로 결정
    unknown_policy = settings.get("date_unknown_policy") or ("all" if include_unknown else "strict")
    date_matched: list = []
    date_unknown: list = []
    date_excluded: list = []
    date_review_queue: list = []
    if settings.get("date_filter_enabled", True):
        date_matched, date_unknown, date_excluded = partition_posted_dates(
            new_items, days_back, max_age_days=settings.get("max_posted_age_days"),
        )
        included_unknown, remaining_unknown = split_unknown_by_policy(
            date_unknown, unknown_policy,
            max_age_days=settings.get("max_posted_age_days") or settings.get("date_unknown_max_age_days"),
            now=now,
        )
        date_review_queue = build_date_review_queue(remaining_unknown)
        filtered_new = date_matched + included_unknown
        log.info(
            "날짜필터 후 메일대상 %d건 (확정 %d + 날짜불명포함 %d/%d, 정책=%s) / 검토대기 %d / 제외 %d",
            len(filtered_new), len(date_matched), len(included_unknown), len(date_unknown),
            unknown_policy, len(date_review_queue), len(date_excluded),
        )
    else:
        filtered_new = new_items
        date_unknown = []
        date_excluded = []

    # 같은 ID의 중요 변경은 게시일이 과거여도 재처리한다. 여전히 마감된 단순수정은 제외.
    # P1-5: 새로운 변경 유형 (DEADLINE_EXTENDED, TARGET_CHANGED, REANNOUNCEMENT 등)도 포함
    _IMPORTANT_CHANGE_TYPES = {
        "EXTENDED", "REANNOUNCED", "UPDATED",
        "DEADLINE_EXTENDED", "TARGET_CHANGED", "SUPPORT_AMOUNT_CHANGED",
        "APPLICATION_URL_CHANGED", "REANNOUNCEMENT", "ADDITIONAL_RECRUITMENT",
    }
    _filtered_ids = {_delivery_notice_id(it) for it in filtered_new}
    for it in new_items:
        if it.get("_change_type") not in _IMPORTANT_CHANGE_TYPES:
            continue
        if classify_deadline_status(it, now.date()) == "closed":
            continue
        did = _delivery_notice_id(it)
        if did and did not in _filtered_ids:
            filtered_new.append({**it, "_forced_change_reprocess": True})
            _filtered_ids.add(did)

    # 워치리스트 매칭분 강제포함 — 날짜필터로 빠졌어도 '절대 안 놓침'
    if watch_hits:
        _wl_seen = {it["id"] for it in filtered_new}
        for it in watch_hits:
            if it.get("id") and it["id"] not in _wl_seen:
                filtered_new.append(it)
                _wl_seen.add(it["id"])
        # 집중 모니터링 전용 메일 + 폰 푸시 (raw_all 설정과 무관하게 보장)
        if deliver:
            wl_recipients = watchlist["recipients"] or settings.get("raw_all_recipients") or []
            if wl_recipients:
                wl_body = "🎯 집중 모니터링 — 지정 키워드/주소에 매칭된 공고입니다.\n\n" + "".join(
                    f"[{i}] {it.get('title', '(제목없음)')}\n"
                    f"  마감: {resolve_item_deadline(it) or '미기재'}\n"
                    f"  링크: {it.get('link') or it.get('url') or '미기재'}\n\n"
                    for i, it in enumerate(watch_hits, 1)
                )
                wl_subject = f"🎯 [집중 모니터링] {len(watch_hits)}건 ({date_str})"
                if effective_send and persist_seen:
                    deliver_with_outbox(
                        wl_subject, wl_body, wl_recipients,
                        date=str(target_date),
                        tenant=str(watchlist.get("tenant_id") or settings.get("tenant_id") or "default"),
                        group="watchlist",
                        notice_ids=[_delivery_notice_id(it) for it in watch_hits],
                    )
                else:
                    send_to_list(wl_subject, wl_body, wl_recipients)
            alert_ntfy(
                "watchlist",
                f"집중 모니터링 공고 {len(watch_hits)}건!\n"
                + "\n".join(f"- {it.get('title', '')[:50]}" for it in watch_hits[:5]),
                priority="high", tags="dart",
            )

    # ⑤ 원본전체 메일 — 행정고지(주민등록·CCTV·입찰)+잡공고(공지·결과·채용·총회 등) 제외 후 출처·지역순 정렬
    raw_items = [it for it in filtered_new if not is_admin_noise(it) and not is_report_junk(it)]
    raw_dropped = len(filtered_new) - len(raw_items)
    if raw_dropped:
        log.info("원본전체 행정고지·잡공고 제외: %d건", raw_dropped)
    if (
        deliver
        and include_raw_all
        and settings.get("raw_all_enabled", True)
        and settings.get("raw_all_recipients")
    ):
        raw_topic = mail_topic(raw_items)
        body_raw = (
            f"수집일시: {now.strftime('%Y-%m-%d %H:%M KST')}\n"
            f"재조회범위: {window_label} (최근 {days_back}영업일)\n"
            f"전체수집: {len(all_items)}건 → 중복제거: {dedup_removed}건 → 신규: {len(new_items)}건\n"
            f"날짜필터 후 발송대상: {len(raw_items)}건 (행정고지·잡공고 {raw_dropped}건 제외)\n\n"
        ) + render_all(raw_items, dedup_removed, len(date_unknown), include_unknown)
        raw_subject = f"[원본전체] {raw_topic} ({date_str}) — {len(raw_items)}건"
        if effective_send and persist_seen:
            deliver_with_outbox(
                raw_subject, body_raw, settings["raw_all_recipients"],
                date=str(target_date),
                tenant=str(settings.get("tenant_id") or "default"),
                group="raw_all",
                notice_ids=[_delivery_notice_id(it) for it in raw_items],
            )
        else:
            send_to_list(raw_subject, body_raw, settings["raw_all_recipients"])

    if not filtered_new:
        if persist_seen and _ALLOW_PERSIST_SEEN:
            commit_notice_versions(notice_versions, notice_version_updates, seen_ids, now=now)
        log.info("처리 대상 없음. 종료.")
        return _with_raw_store_stats({
            "ok": True,
            "mode": mode,
            "collected": len(all_items),
            "deduped": len(deduped),
            "new_items": len(new_items),
            "brand_new_items": brand_new_count,
            "changed_items": changed_count,
            "filtered_items": 0,
            "date_unknown_items": len(date_unknown),
            "date_review_queue": date_review_queue,
            "date_excluded_count": len(date_excluded),
            "mail_sent": False,
            "drafts_created": _DRAFT_OK,
            "draft_failed": _DRAFT_FAIL,
            "seen_ids_persisted": bool(persist_seen and _ALLOW_PERSIST_SEEN),
            "sent_groups": [],
            "preview_groups": [],
        })

    # ⑥ 그룹별 필터 + 발송
    # 기업 맞춤 정밀 매칭(2차 컷오프)용 기업 프로필 로드 (활성화 시에만)
    companies_by_id: dict = {}
    if settings.get("company_match_enabled") and _CM_OK:
        try:
            # PII 격리(#96): 기업 프로필을 환경변수(MAIL_COMPANIES_JSON)로 주입 가능(없으면 파일).
            _companies = _pii_config("MAIL_COMPANIES_JSON", _load_companies)
            companies_by_id = {c["id"]: c for c in (_companies or [])}
            log.info("기업 프로필 로드: %d개 (정밀 매칭 활성)", len(companies_by_id))
        except Exception as e:
            log.warning("기업 프로필 로드 실패 — 정밀 매칭 건너뜀: %s", e)

    sent_groups: list[dict] = []
    preview_groups: list[dict] = []
    for group in groups:
        diagnostics = filter_for_group_with_diagnostics(filtered_new, group)
        g_items = diagnostics["included"]
        review_items = diagnostics["review"]
        ru_items = diagnostics["region_unknown"]
        ru_limit = int(settings.get("region_unknown_mail_limit", REGION_UNKNOWN_MAIL_LIMIT))
        ru_mail_items = select_region_unknown_for_mail(ru_items, limit=ru_limit)
        if ru_items:
            write_region_unknown_report(ru_items, str(group.get("name") or "group"), run_at=now)
        excluded_items = diagnostics["excluded"]
        # 점수+LLM 2차 컷(그룹 score_threshold / llm_check_enabled)
        g_items, _score_demoted = refine_included_by_score_llm(g_items, group)
        if _score_demoted:
            review_items = review_items + _score_demoted
            log.info("그룹 '%s' 점수/LLM 컷오프: %d건 → 검토 강등", group.get("name"), len(_score_demoted))
        # 2차 정밀 컷오프: 그룹에 연결된 기업 프로필 점수 미달은 검토로 강등
        g_items, _demoted = refine_included_by_company(g_items, group, settings, companies_by_id)
        if _demoted:
            review_items = review_items + _demoted
            log.info("그룹 '%s' 기업매칭 컷오프: %d건 → 검토 강등", group.get("name"), len(_demoted))
        if not deliver:
            preview_groups.append({
                "name": group.get("name"),
                "priority_items": sum(1 for it in g_items if it.get("priority_keyword")),
                "matched_items": len(g_items),
                "review_items": len(review_items),
                "region_unknown_items": len(ru_mail_items),
            "region_unknown_total_items": len(ru_items),
                "region_unknown_mail_items": len(ru_mail_items),
                "excluded_items": len(excluded_items),
                "sample_titles": [it.get("title") for it in g_items[:5]],
                "review_titles": [it.get("title") for it in review_items[:5]],
                "region_unknown_titles": [it.get("title") for it in ru_items[:5]],
                "excluded_summary": render_excluded_summary(excluded_items),
            })
        if not g_items and not ru_mail_items:
            log.info("그룹 '%s': 조건 매칭 공고 없음", group.get("name"))
            continue
        sent_groups.append({
            "name": group.get("name"),
            "matched_items": len(g_items),
            "priority_items": sum(1 for it in g_items if it.get("priority_keyword")),
            "review_items": len(review_items),
            "region_unknown_items": len(ru_items),
            "excluded_items": len(excluded_items) if not deliver else 0,
        })
        if deliver:
            summary    = claude_summarize(g_items, group) if g_items else "오늘 기준 조건 매칭 공고는 없습니다.\n"
            g_norm     = _normalize_group(group)
            req_rgns   = g_norm.get("required_conditions", {}).get("regions", [])
            _or_kws    = g_norm.get("or_keywords", [])
            _and_grps  = g_norm.get("and_keyword_groups", [])
            _kw_parts  = ([f"OR({', '.join(_or_kws[:3])})"] if _or_kws else []) + \
                         [f"AND({', '.join(ag)})" for ag in _and_grps[:2]]
            kw_str     = " | ".join(_kw_parts) or "전체"
            # 수출·혁신 바우처 공고는 별도 강조(메일 상단 블록 + 폰 푸시 ntfy)
            voucher_items = [it for it in g_items if _is_voucher(it)]
            voucher_block = ""
            if voucher_items:
                voucher_block = (
                    f"🔔🔔 [수출·혁신 바우처 공고 {len(voucher_items)}건 — 우선 확인!] 🔔🔔\n"
                    + "".join(
                        f"  • {it['title']} (마감 {resolve_item_deadline(it) or '미기재'})\n"
                        for it in voucher_items
                    )
                    + "\n"
                )
            header  = (
                f"수집일시: {now.strftime('%Y-%m-%d %H:%M KST')}\n"
                f"재조회범위: {window_label} (최근 {days_back}영업일)\n"
                f"그룹: {group.get('name')}\n"
                f"지역: {', '.join(req_rgns) or '전국'}\n"
                f"지원유형: {', '.join(g_norm.get('support_types', ALL_SUPPORT_TYPES))}\n"
                f"전체 {len(filtered_new)}건 → 그룹 매칭 {len(g_items)}건\n\n"
            )
            # 키워드는 제목/상단에서 빼고 본문 최하단에 참고용으로만(숨김처리)
            kw_footer = (
                "\n\n────────────────────────────────\n"
                f"ⓘ 검색조건(참고): 키워드 {kw_str}\n"
            )
            # 지역 미상 공고 — 보고 메일 하단에 '확인 필요' 섹션으로 함께 첨부(누락 방지, 사용자 정책 2026-06-19)
            region_unknown_block = render_region_unknown(
                ru_mail_items, limit=ru_limit, total_count=len(ru_items),
            )
            # 사용자 ⭕/❌ 피드백 링크 — 실제 나간 메일이 맞았는지 사람 정답(Tier C)을 모은다.
            feedback_block = _render_feedback_block(g_items)
            subj_count = f"{len(g_items)}건" + (
                f"+지역확인 {len(ru_mail_items)}건" if ru_mail_items else ""
            )
            # (기준일·그룹·수신자) 단위 멱등 발송 — 재실행/부분실패 시 성공 수신자 중복 방지(#113·#114·#144).
            _gid = str(group.get("id") or group.get("name") or "grp")
            _recips = guard_group_recipients(
                group.get("recipients", []), settings, group.get("name"), group=group,
            )
            _subject = f"[{group.get('name')}] {subj_count} ({date_str})"
            _body = header + voucher_block + summary + region_unknown_block + feedback_block + kw_footer
            if effective_send and persist_seen:
                deliver_with_outbox(
                    _subject, _body, _recips,
                    date=str(target_date),
                    tenant=str(group.get("tenant_id") or "default"),
                    group=_gid,
                    notice_ids=[_delivery_notice_id(it) for it in (g_items + ru_mail_items)],
                )
            else:
                send_to_list(_subject, _body, _recips)
            if voucher_items:
                alert_ntfy(
                    f"voucher {len(voucher_items)}",
                    f"🔔 [{group.get('name')}] 수출·혁신 바우처 공고 {len(voucher_items)}건!\n"
                    + "\n".join(f"- {it['title'][:50]}" for it in voucher_items[:5]),
                    priority="high", tags="loudspeaker",
                )
    # ⑦ 모든 그룹의 delivery plan 이 끝난 뒤에만 seen_ids 를 갱신한다. 중간 크래시 때는
    # outbox + recipient checkpoint 가 남으므로 다음 run 이 중복 없이 미완료분을 이어 보낸다.
    if effective_send and persist_seen:
        seen_ids = persist_completed_outbox(seen_ids)
        commit_notice_versions(notice_versions, notice_version_updates, seen_ids, now=now)
    log.info("=== 완료 ===")
    # 실제 발송분(기업 정밀 컷오프 반영)과 일치하도록 sent_groups 집계 사용
    final_mail_count = sum(g.get("matched_items", 0) for g in sent_groups)
    return _with_raw_store_stats({
        "ok": True,
        "mode": mode,
        "collected": len(all_items),
        "deduped": len(deduped),
        "dedup_removed": dedup_removed,
        "new_items": len(new_items),
        "brand_new_items": brand_new_count,
        "changed_items": changed_count,
        "date_window": window_label,
        "filtered_items": len(filtered_new),
        "p0_source_items_dropped": len(p0_dropped),
        "send_hold": bool(send_hold),
        "send_hold_reason": hold_reason if send_hold else "",
        "run_status": gate.get("run_status") or "",
        "date_matched_count": len(date_matched) if settings.get("date_filter_enabled", True) else len(filtered_new),
        "date_unknown_items": len(date_unknown),
        "date_review_queue": date_review_queue,
        "date_review_queue_count": len(date_review_queue),
        "date_excluded_count": len(date_excluded),
        "final_mail_target_count": final_mail_count,
        "mail_sent": bool(effective_send and _ALLOW_SMTP_SEND),
        "drafts_created": _DRAFT_OK,
        "draft_failed": _DRAFT_FAIL,
        "seen_ids_persisted": bool(persist_seen and _ALLOW_PERSIST_SEEN),
        "sent_groups": sent_groups,
        "preview_groups": preview_groups,
        "extraction_rates_by_site": extraction_rates_by_site,
        "extraction_retry_plan_count": len(extraction_retry_plan),
        "extraction_retry_stats": extraction_retry_stats,
    })


def main(
    allow_send: bool = False,
    include_raw_all: bool = False,
    persist_seen: bool = False,
    collection_gate: dict | None = None,
    group_id: str = "",
) -> dict:
    # safe-by-default: 인자를 명시적으로 True 로 주지 않으면 발송·원본전체·seen_ids 저장을
    # 모두 하지 않는다(preview-only). 실발송은 호출자가 allow_send=True 를 명시할 때만.
    result = execute_monitor(
        allow_send=allow_send,
        include_raw_all=include_raw_all,
        persist_seen=persist_seen,
        collection_gate=collection_gate,
        group_id=group_id,
    )
    _post_run_alert(result)
    return result


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
    path = path or (LOGS_DIR / "site_collection_coverage_report.md")
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
    path = path or (LOGS_DIR / "today_notice_missing_risk_report.md")
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
    path = path or (LOGS_DIR / f"review_queue_{stamp}.md")
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
                f"{it.get('source', '')} | {it.get('link', '')}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_coverage_anomaly_report(
    anomalies: list[dict],
    path: Path | None = None,
    *,
    run_at: datetime | None = None,
) -> Path:
    """수집 이상탐지 결과를 별도 마크다운으로 저장(dry-run 보고서)."""
    run_at = run_at or datetime.now(KST)
    path = path or (LOGS_DIR / "coverage_anomaly_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 수집 이상탐지",
        "",
        f"- 생성: {run_at.strftime('%Y-%m-%d %H:%M KST')}",
        f"- 감지: {len(anomalies)}건 "
        f"(high {sum(1 for a in anomalies if a.get('severity') == 'high')} / "
        f"medium {sum(1 for a in anomalies if a.get('severity') == 'medium')})",
        "",
    ]
    if not anomalies:
        lines.append("(이상 없음 — baseline 대비 0건 급락·수집실패·급감 없음)")
    else:
        order = {"high": 0, "medium": 1, "low": 2}
        for a in sorted(anomalies, key=lambda x: order.get(x.get("severity", "low"), 3)):
            lines.append(
                f"- **{a.get('severity', '')}** | {a.get('site_name', '')} | "
                f"{a.get('reason', '')} | 평소 {a.get('baseline', 0)}→오늘 {a.get('current', 0)}건 | "
                f"{(a.get('url', '') or '')[:80]}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_source_coverage_json(
    payload: dict, path: Path | None = None, *, run_at: datetime | None = None,
) -> Path:
    """기계 판독용 실행대장. logs/source_coverage_YYYYMMDD.json"""
    run_at = run_at or datetime.now(KST)
    path = path or (LOGS_DIR / f"source_coverage_{run_at:%Y%m%d}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_source_coverage_md(
    payload: dict, path: Path | None = None, *, run_at: datetime | None = None,
) -> Path:
    """관리자 확인용 실행대장 보고서. logs/source_coverage_YYYYMMDD.md"""
    from mail_core.operations import coverage_alert as _ca  # noqa: PLC0415

    run_at = run_at or datetime.now(KST)
    path = path or (LOGS_DIR / f"source_coverage_{run_at:%Y%m%d}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_ca.render_coverage_markdown(payload), encoding="utf-8")
    return path


def write_p0_collection_alert(
    payload: dict, path: Path | None = None, *, run_at: datetime | None = None,
) -> Path:
    """P0 누락위험 알림 사본. logs/p0_collection_alert_YYYYMMDD.md"""
    from mail_core.operations import coverage_alert as _ca  # noqa: PLC0415

    run_at = run_at or datetime.now(KST)
    path = path or (LOGS_DIR / f"p0_collection_alert_{run_at:%Y%m%d}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_ca.render_p0_alert_markdown(payload), encoding="utf-8")
    return path


def run_source_coverage_audit(
    rows: list[dict],
    sites: list[dict] | None = None,
    *,
    allow_alert: bool = True,
    run_at: datetime | None = None,
    write_files: bool = True,
) -> dict:
    """활성 소스 실행 완전성·수집 품질을 P0/P1 로 판정하고 산출물·알림을 남긴다.

    운영 게이트이지만 **소스 P0(DEGRADED)만으로는 발송을 막지 않는다**.
    런 FAILED(send_hold) 실보류 배선은 W1. 전체를 try/except 로 감싸 이 감사 자체의
    실패가 본 작업(수집·발송)에 절대 전파되지 않게 한다.

    반환: summarize_run_status() 결과 + {"payload", "files"} (실패 시 status="SUCCESS").
    """
    try:
        from mail_core.operations import coverage_alert as _ca  # noqa: PLC0415

        run_at = run_at or datetime.now(KST)
        baseline = _ca.load_coverage_baseline()
        page_stats = page_stats_snapshot()
        try:
            from mail_core.operations import detector_config as _dc  # noqa: PLC0415
            detector_cfg = _dc.load_detector_config()
        except Exception:
            detector_cfg = None
        reports = _ca.classify_sources(
            rows, baseline, page_stats=page_stats, detector_cfg=detector_cfg)
        exec_check = _ca.verify_source_execution(sites, rows)
        summary = _ca.summarize_run_status(reports, exec_check)
        payload = _ca.build_coverage_payload(
            rows, reports, summary, exec_check=exec_check,
            generated_at=run_at.strftime("%Y-%m-%d %H:%M KST"),
        )
        # W1: 실행 판정 ledger append (실패해도 본작업 무영향)
        try:
            from mail_core.operations import source_run_ledger as _led  # noqa: PLC0415
            run_id = _led.new_run_id()
            recs = [
                _led.build_ledger_record(
                    run_id=run_id,
                    source_report=rep,
                    page_stat=(page_stats or {}).get(rep.get("site_id", "")),
                )
                for rep in reports
            ]
            _led.append_source_runs(recs)
        except Exception:
            pass
        files: dict[str, str] = {}
        if write_files:
            files["json"] = str(write_source_coverage_json(payload, run_at=run_at))
            files["md"] = str(write_source_coverage_md(payload, run_at=run_at))
            if summary.get("p0_count"):
                files["p0_alert"] = str(write_p0_collection_alert(payload, run_at=run_at))
        if summary.get("p0_count") and allow_alert:
            hold_tag = "[FAILED][send_hold] " if summary.get("send_hold") else ""
            alert_email(
                f"{hold_tag}[P0 수집 누락 위험] {summary['p0_count']}개 소스 — 확인 필요",
                _ca.format_p0_alert_message(payload),
            )
        return {**summary, "payload": payload, "files": files}
    except Exception as e:  # 감사 실패는 절대 수집·발송을 막지 않는다
        log.warning("소스 커버리지 감사 실패(무시): %s", e)
        return {"status": "SUCCESS", "send_hold": False, "p0_count": 0, "p1_count": 0,
                "p0_sources": [], "p1_sources": [], "payload": {}, "files": {},
                "audit_error": str(e)[:200]}


def run_coverage_anomaly_check(rows: list[dict], *, allow_alert: bool = True) -> list[dict]:
    """커버리지 이상탐지: baseline 대비 0건 급락·수집실패·급감을 찾아 (보수적으로) 폰 알림.

    안전 설계: 전체를 try/except 로 감싸 이상탐지 실패가 본 작업(메일)에 영향 0.
    baseline 이력이 있는 사이트만 비교(첫 실행/신규 사이트 오탐 방지). high 가 있을 때만,
    그리고 allow_alert 일 때만 ntfy 1회 발송. 그 후 성공한 사이트로 baseline 갱신·저장.
    반환: 감지된 anomaly dict 리스트(없으면 빈 리스트).
    """
    try:
        from mail_core.operations import coverage_alert as _ca  # noqa: PLC0415

        baseline = _ca.load_coverage_baseline()
        anomalies = _ca.detect_coverage_anomalies(rows, baseline)
        highs = [a for a in anomalies if a.get("severity") == "high"]
        if highs and allow_alert:
            # PC(이메일)로 알림 — 평소 수집되던 사이트가 0건/급감/실패 시 확인 요청.
            alert_email(
                "커버리지 이상(수집 0건/급감/실패) — 확인 필요",
                _ca.format_anomaly_message(anomalies)
                + "\n\n(평소 수집되던 사이트가 조용히 바뀌어 공고를 놓치는 사고 감지 — "
                  "GitHub Actions 로그/사이트를 확인하세요.)",
            )
        new_baseline = _ca.update_coverage_baseline(baseline, rows)
        _ca.save_coverage_baseline(new_baseline)
        return anomalies
    except Exception as e:  # 이상탐지 실패는 절대 본 작업을 막지 않는다
        log.warning("커버리지 이상탐지 실패(무시): %s", e)
        return []


# ══════════════════════════════════════════════════════════════════
# 디제스트 품질 측정 — "빠짐없이(recall)·적합만(precision)" 자동 계측
# ══════════════════════════════════════════════════════════════════
# 새 수집·새 분류를 만들지 않고, run_dry_run/execute_monitor 가 이미 산출한
# 신호(date_review_queue·coverage_anomalies·coverage·sent/preview_groups)를
# 재사용해 매일 digest(초안)가 적합공고를 놓쳤는지/무관공고를 섞었는지만 통합 계측한다.
# 임계는 보수적: 근거 있는 위험이 0 이면 OK.

_DIGEST_RECALL_RISK_LEVELS = ("중간", "높음")
_DIGEST_WEEKEND_EDGE_DAYS = 3  # too_old 제외됐어도 최근 며칠 내 주말 게시면 '주말 엣지'로 본다


def _digest_delivered_groups(run_result: dict) -> list[dict]:
    """digest 로 실제 전달된 그룹 목록. 실발송이면 sent_groups, 아니면(초안/미리보기)
    preview_groups 를 쓴다. 둘 다 그룹당 region_unknown_items 카운트를 담는다
    (execute_monitor 반환 계약)."""
    sent = run_result.get("sent_groups") or []
    if sent:
        return sent
    return run_result.get("preview_groups") or []


def _digest_delivered_count(run_result: dict) -> int:
    """digest 에 실제 전달된(발송/초안) 공고 수 K. 반환 계약의 집계값 우선."""
    for key in ("final_mail_target_count", "filtered_items"):
        v = run_result.get(key)
        if isinstance(v, int) and v >= 0:
            return v
    return sum(int(g.get("matched_items", 0) or 0) for g in _digest_delivered_groups(run_result))


def _measure_recall_risk(run_result: dict, now: datetime | None = None) -> tuple[int, dict]:
    """빠질 뻔한 적합공고 계측 — 세 신호의 (건수, 근거)."""
    now = now or datetime.now(KST)
    today = now.date()

    # ① date_unknown 인데 신청신호가 있어 검토큐로 남은 것(메일 미포함) = 빠질 뻔
    queue = run_result.get("date_review_queue") or []
    risky = [it for it in queue if it.get("date_unknown_risk") in _DIGEST_RECALL_RISK_LEVELS]

    # ② too_old 로 제외됐지만 최근·주말 게시(주말 recall 엣지). run_result 에 항목 리스트
    #    date_excluded 가 있을 때만 계측(계약상 count 만 있을 수 있음 → 그땐 근거부족).
    excluded_items = run_result.get("date_excluded")
    excluded_available = isinstance(excluded_items, list)
    weekend_edge: list[dict] = []
    if excluded_available:
        for it in excluded_items:
            if it.get("_excluded_reason") != "too_old":
                continue
            pd = (it.get("_excluded_posted_date") or it.get("posted_date") or "")[:10]
            try:
                d = datetime.strptime(pd, "%Y-%m-%d").date()
            except ValueError:
                continue
            if 0 <= (today - d).days <= _DIGEST_WEEKEND_EDGE_DAYS and d.weekday() >= 5:
                weekend_edge.append(it)

    # ③ 커버리지 이상(0건 급락·수집실패·급감) 소스 수 + baseline 이력 없이도 수집 실패한 소스.
    #    date parsing 실패(high missing_risk)는 ①의 review queue 로 이미 잡히므로 중복 제외.
    anomalies = run_result.get("coverage_anomalies") or []
    alert_sites: set[str] = {
        (a.get("site_id") or a.get("site_name") or "")
        for a in anomalies if a.get("severity") in ("high", "medium")
    }
    for row in run_result.get("coverage") or []:
        if not row.get("enabled", True):
            continue
        if not row.get("fetch_success") or row.get("fetch_error"):
            alert_sites.add(row.get("site_id") or row.get("site_name") or "")
    alert_sites.discard("")

    total = len(risky) + len(weekend_edge) + len(alert_sites)
    detail = {
        "date_unknown_risky": {
            "count": len(risky),
            "titles": [it.get("title", "")[:80] for it in risky[:10]],
            "note": "게시일 불명이나 신청 신호가 있어 검토큐에 남은 공고(메일 미포함)",
        },
        "excluded_recent_weekend": {
            "count": len(weekend_edge),
            "titles": [it.get("title", "")[:80] for it in weekend_edge[:10]],
            "note": ("too_old 로 제외됐지만 최근 주말 게시 — 주말 누락 엣지"
                     if excluded_available
                     else "측정 근거 부족 — run_result 에 date_excluded 항목 리스트 없음(count 만 존재)"),
        },
        "coverage_alert_sources": {
            "count": len(alert_sites),
            "sources": sorted(alert_sites)[:20],
            "note": "평소 수집되던 소스가 0건/급감/수집실패 — 조용한 누락 위험",
        },
    }
    return total, detail


def _measure_precision_risk(run_result: dict) -> tuple[int, dict]:
    """digest 에 섞인 무관공고 계측 — 근거 있는 것만, 없으면 0+근거부족 note."""
    groups = _digest_delivered_groups(run_result)
    region_unknown = 0
    breakdown: list[dict] = []
    for g in groups:
        n = int(g.get("region_unknown_items", 0) or 0)
        if n:
            region_unknown += n
            breakdown.append({"group": g.get("name"), "region_unknown_items": n})
    detail = {
        # 지역 미확정으로 그룹 지역과 불일치할 수 있는데 digest '확인 필요' 섹션에 첨부된 건
        "region_unknown_in_digest": {
            "count": region_unknown,
            "groups": breakdown,
            "note": "지역 미확정이라 그룹 지역과 불일치 가능 — digest 에 확인필요로 포함됨",
        },
        # 항목별 매칭점수/지역판정은 run_result 집계에 없어 약한매칭은 계측 불가
        "weak_match": {
            "count": 0,
            "note": "측정 근거 부족 — run_result 집계에 항목별 매칭점수·지역판정 없음",
        },
    }
    if not groups:
        detail["note"] = "측정 근거 부족 — 전달 그룹 정보 없음"
    return region_unknown, detail


def measure_digest_quality(run_result: dict, *, now: datetime | None = None) -> dict:
    """매일 digest(초안)가 '빠짐없이·적합만' 왔는지 계측한다(읽기 전용·재사용).

    입력: run_dry_run/execute_monitor 가 반환한 dict(그리고 run_dry_run 이 덧붙인
          coverage·coverage_anomalies). 새 수집/분류 없이 기존 신호만 통합한다.
    반환 verdict:
      {"recall_ok":bool,"precision_ok":bool,"recall_risk":N,"precision_risk":M,
       "delivered":K,"detail":{...},"generated_at":iso}
    임계 보수적: 근거 있는 위험이 0 이면 OK.
    """
    now = now or datetime.now(KST)
    recall_risk, recall_detail = _measure_recall_risk(run_result, now=now)
    precision_risk, precision_detail = _measure_precision_risk(run_result)
    delivered = _digest_delivered_count(run_result)
    return {
        "recall_ok": recall_risk == 0,
        "precision_ok": precision_risk == 0,
        "recall_risk": recall_risk,
        "precision_risk": precision_risk,
        "delivered": delivered,
        "detail": {
            "recall": recall_detail,
            "precision": precision_detail,
            "mode": run_result.get("mode", ""),
            "drafts_created": run_result.get("drafts_created", 0),
        },
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
    }


def format_digest_quality_line(verdict: dict) -> str:
    """사람용 1줄 요약."""
    recall = "OK" if verdict.get("recall_ok") else "위험!"
    precision = "OK" if verdict.get("precision_ok") else "위험!"
    return (
        f"📊 오늘 품질: 빠짐없이 {recall}(위험 {verdict.get('recall_risk', 0)})"
        f"·적합만 {precision}(위험 {verdict.get('precision_risk', 0)})"
        f"·전달 {verdict.get('delivered', 0)}건"
    )


def write_digest_quality_report(
    verdict: dict,
    path: Path | None = None,
    *,
    run_at: datetime | None = None,
) -> Path:
    """계측 결과를 workspace/digest_quality_YYYYMMDD.json 으로 저장(gitignore 관례)."""
    run_at = run_at or datetime.now(KST)
    stamp = run_at.strftime("%Y%m%d")
    path = path or (BASE_DIR / "workspace" / f"digest_quality_{stamp}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_dry_run(
    *,
    write_reports: bool = True,
    fetch_coverage: bool = True,
    allow_coverage_alert: bool = False,
    draft_mode: bool = False,
    group_id: str = "",
) -> dict:
    """실제 발송·seen_ids 저장 없이 전체 파이프라인 검증.

    allow_coverage_alert: 커버리지 이상탐지에서 high 발견 시 실제 ntfy 알림 발송 여부.
    기본 False(수동 dry-run 노이즈 방지). 스케줄에서 활성화하려면 True 로 호출.
    draft_mode: True 면 실발송(SMTP) 없이 공고 digest 를 Gmail 초안(Drafts)으로 생성한다.
    seen_ids 는 여전히 저장하지 않으며, 커버리지 등 dry-run 검증 산출물은 그대로 유지한다.
    """
    os.environ["MONITOR_NO_PERSIST_SEEN"] = "1"
    seen_before = SEEN_IDS_PATH.stat().st_mtime if SEEN_IDS_PATH.exists() else None

    coverage_rows: list[dict] = []
    coverage_anomalies: list[dict] = []
    coverage_audit: dict = {}
    collection_gate: dict = {}
    if fetch_coverage:
        all_sites = load_json(SITES_PATH, [])
        reset_page_stats()
        coverage_rows = fetch_site_coverage(all_sites)
        # 활성 소스 실행 완전성·품질 감사(P0/P1). 알림은 anomaly_check 와 중복되지 않게
        # P0 가 있을 때만 별도 1회. 실패해도 내부에서 흡수되어 dry-run 을 막지 않는다.
        coverage_audit = run_source_coverage_audit(
            coverage_rows, all_sites, allow_alert=allow_coverage_alert,
        )
        try:
            from mail_core.operations.miss_remediation import (
                enqueue_p0_from_reports,
                plan_retries,
            )
            reports = (coverage_audit.get("payload") or {}).get("sources") or (
                coverage_audit.get("p0_sources") or [])
            enqueue_p0_from_reports(reports)
            coverage_audit["retry_plan"] = plan_retries(
                coverage_audit.get("p0_sources") or [])
        except Exception as e:
            log.warning("manual_queue/retry_plan 실패(무시): %s", e)
        coverage_anomalies = run_coverage_anomaly_check(
            coverage_rows, allow_alert=allow_coverage_alert,
        )
        collection_gate = {
            "send_hold": bool(coverage_audit.get("send_hold")),
            "run_status": coverage_audit.get("status") or "",
            "source_reports": (coverage_audit.get("payload") or {}).get("sources") or [],
            "p0_sources": coverage_audit.get("p0_sources") or [],
        }

    result = execute_monitor(
        allow_send=False, include_raw_all=False, persist_seen=False,
        draft_mode=draft_mode, collection_gate=collection_gate,
        group_id=group_id,
    )
    result["coverage"] = coverage_rows
    result["coverage_anomalies"] = coverage_anomalies
    result["source_coverage_summary"] = {
        k: v for k, v in coverage_audit.items() if k not in ("payload",)
    }
    # 최상위 스칼라로 승격 — API 응답 요약(_result_summary)이 스칼라만 통과시키기 때문
    result["run_status"] = coverage_audit.get("status") or result.get("run_status") or "SUCCESS"
    result["collection_p0_count"] = int(coverage_audit.get("p0_count", 0) or 0)
    result["collection_p1_count"] = int(coverage_audit.get("p1_count", 0) or 0)
    result["send_hold"] = bool(collection_gate.get("send_hold"))
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

    # 디제스트 품질 측정 (빠짐없이·적합만) — 매일 자동. 실패해도 본 파이프라인엔 영향 0.
    quality_line = ""
    try:
        verdict = measure_digest_quality(result)
        result["digest_quality"] = verdict
        quality_line = format_digest_quality_line(verdict)
        log.info(quality_line)
        if write_reports:
            write_digest_quality_report(verdict)
    except Exception as e:
        log.warning("digest 품질 측정 실패(무시): %s", e)

    if write_reports:
        write_coverage_report(coverage_rows)
        anomaly_path = write_coverage_anomaly_report(coverage_anomalies)
        write_today_missing_risk_report(result)
        write_review_queue_report(result.get("date_review_queue") or [])
        # 사람용 품질 1줄을 커버리지 이상탐지 리포트 말미에 첨부
        if quality_line:
            try:
                with anomaly_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"\n{quality_line}\n")
            except OSError:
                pass

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="수출·지원사업 모니터")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="발송·seen_ids 저장 없이 preview 및 var/logs/ 보고서 생성",
    )
    parser.add_argument(
        "--skip-coverage-fetch",
        action="store_true",
        help="dry-run 시 사이트별 순차 수집 생략(네트워크 절약)",
    )
    parser.add_argument(
        "--coverage-alert",
        action="store_true",
        help="dry-run 커버리지 이상탐지에서 high 발견 시 실제 폰 알림(ntfy) 발송",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="실발송(SMTP) 대신 공고 digest 를 Gmail 초안(Drafts)으로 생성한다(safe-by-default). "
             "dry-run 파이프라인(커버리지·보고서)을 그대로 돌리되 preview 대신 초안을 만든다. "
             "--dry-run 과 함께 줘도 동일하게 동작(미리보기 산출물 + 초안 생성).",
    )
    parser.add_argument(
        "--only-to",
        default="",
        metavar="EMAIL",
        help="모든 발송 수신자를 이 주소 하나로 강제(테스트 실발송용 안전장치). "
             "그룹·raw_all·watchlist 어떤 경로든 이 주소로만 나간다.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="실제 이메일을 발송한다. 기본(미지정)은 발송하지 않는 preview-only. "
             "이 플래그가 있어야만 SMTP 전송이 일어난다.",
    )
    parser.add_argument(
        "--persist-seen",
        action="store_true",
        help="이번 run 의 신규 공고 id 를 seen_ids.json 에 저장한다(기본은 저장 안 함).",
    )
    parser.add_argument(
        "--include-raw-all",
        action="store_true",
        help="원본전체(raw_all) 보고 메일도 함께 발송 대상에 포함한다(기본은 미포함).",
    )
    parser.add_argument(
        "--group",
        default="",
        metavar="GROUP_ID",
        help="지정한 그룹만 실행한다(예: grp_prestartup_ai). 미지정 시 모든 활성 그룹.",
    )
    args = parser.parse_args()
    if args.only_to:
        _ONLY_TO = args.only_to
        log.info("only-to 모드: 모든 발송 수신자를 %s 로 강제합니다(테스트)", _mask_email(args.only_to))
    if args.send and not args.persist_seen:
        parser.error("--send 는 --persist-seen 과 함께 사용해야 합니다(중복·누락 방지 대기열 필수)")
    _run_guard = None
    if args.send:
        _run_guard = run_lock.MonitorRunLock()
        if not _run_guard.acquire():
            log.warning("다른 실발송 run 이 진행 중입니다 — 이번 실행은 중복 방지를 위해 종료합니다")
            raise SystemExit(0)
    try:
        if args.draft:
            # 초안 모드: 실발송 없이 공고 digest 를 Gmail 초안으로 생성.
            # dry-run 파이프라인을 재사용해 커버리지 이상탐지·보고서를 그대로 유지하고,
            # preview 대신 초안을 만든다(--dry-run 동시 지정도 동일 동작).
            summary = run_dry_run(
                fetch_coverage=not args.skip_coverage_fetch,
                allow_coverage_alert=args.coverage_alert,
                draft_mode=True,
                group_id=args.group,
            )
            _post_run_alert(summary)
            log.info(
                "draft 완료: 수집=%s 신규=%s 초안생성=%s 초안실패=%s mail_sent=%s",
                summary.get("collected"),
                summary.get("new_items"),
                summary.get("drafts_created"),
                summary.get("draft_failed"),
                summary.get("mail_sent"),
            )
        elif args.dry_run:
            summary = run_dry_run(
                fetch_coverage=not args.skip_coverage_fetch,
                allow_coverage_alert=args.coverage_alert,
                group_id=args.group,
            )
            log.info(
                "dry-run 완료: 수집=%s 신규=%s review_queue=%s mail_sent=%s seen_changed=%s",
                summary.get("collected"),
                summary.get("new_items"),
                summary.get("date_review_queue_count"),
                summary.get("mail_sent"),
                summary.get("seen_ids_file_changed"),
            )
        else:
            # 실발송 경로: 커버리지 감사로 send_hold·P0 필터·manual_queue 를 연결한다.
            # allow_alert 는 --coverage-alert 일 때만(알림 노이즈 분리).
            #
            # ★ skip 이어도 SystemExit(0) 금지 (2026-07-30 TASK-G01):
            #   과거 early-exit 가 coverage/P0/artifact 를 통째로 건너뛰어
            #   "2분대 초록불 + 수집이상 침묵" 사고가 났다. 발송만 생략하고
            #   coverage·이상탐지·아티팩트는 반드시 돌린다.
            _t0 = time.monotonic()
            _skip_fetch = False
            _skip_meta: dict = {}
            if args.send and args.persist_seen:
                try:
                    from mail_core.delivery.skip_gate import (
                        should_skip_fetch_already_delivered,
                    )
                    _settings_ee = load_settings()
                    _groups_ee = load_groups()
                    _wl_ee = load_watchlist()
                    _td = delivery_cycle_date(datetime.now(KST))
                    _skip_ee = should_skip_fetch_already_delivered(
                        target_date=str(_td),
                        groups=_groups_ee,
                        settings=_settings_ee,
                        watchlist=_wl_ee,
                        include_raw_all=args.include_raw_all,
                        delivery_path=DELIVERY_STATE_PATH,
                    )
                    if _skip_ee.get("skip"):
                        _skip_fetch = True
                        _skip_meta = dict(_skip_ee)
                        log.info(
                            "기준일 %s 발송 단위 %s개 멱등 완료 — 수집·발송 생략"
                            "(coverage/P0/artifact 는 계속)",
                            _skip_ee.get("target_date"), _skip_ee.get("units"),
                        )
                except Exception as e:
                    log.warning("발송완료 skip 판정 실패(무시·수집 계속): %s", e)
            if args.send and not DATA_GO_KR_KEY:
                # DATA_GO_KR_KEY 정책(TASK-G03): 실발송에서 키 없으면 기업마당이
                # bizinfo 직결(WAF timeout)에만 의존 → 경고를 남긴다(발송은 막지 않음).
                log.warning(
                    "DATA_GO_KR_KEY 미설정 — 기업마당 data.go.kr 폴백 비활성"
                    "(GHA Secret 등록 권장)"
                )
            _gate: dict = {}
            if not args.skip_coverage_fetch:
                try:
                    _all_sites = load_json(SITES_PATH, [])
                    reset_page_stats()
                    _cov_rows = fetch_site_coverage(_all_sites)
                    _audit = run_source_coverage_audit(
                        _cov_rows, _all_sites, allow_alert=bool(args.coverage_alert),
                    )
                    _status = _audit.get("status") or ""
                    if _status == "FAILED" or _audit.get("send_hold"):
                        log.warning(
                            "수집 상태 FAILED — send_hold (P0 %s / P1 %s)",
                            _audit.get("p0_count"), _audit.get("p1_count"),
                        )
                    elif _status == "DEGRADED":
                        log.warning(
                            "수집 상태 DEGRADED — P0 %s건/P1 %s건 (정상 소스만 발송)",
                            _audit.get("p0_count"), _audit.get("p1_count"),
                        )
                    try:
                        from mail_core.operations.miss_remediation import (
                            enqueue_p0_from_reports,
                            plan_retries,
                        )
                        _reports = (_audit.get("payload") or {}).get("sources") or (
                            _audit.get("p0_sources") or [])
                        enqueue_p0_from_reports(_reports)
                        _audit["retry_plan"] = plan_retries(_audit.get("p0_sources") or [])
                    except Exception as e:
                        log.warning("manual_queue 갱신 실패(무시): %s", e)
                    if args.coverage_alert:
                        run_coverage_anomaly_check(_cov_rows, allow_alert=True)
                    _gate = {
                        "send_hold": bool(_audit.get("send_hold")),
                        "run_status": _status,
                        "source_reports": (_audit.get("payload") or {}).get("sources") or [],
                        "p0_sources": _audit.get("p0_sources") or [],
                    }
                except Exception as e:
                    log.warning("커버리지 점검 실패(무시): %s", e)
            if _skip_fetch:
                _dur = time.monotonic() - _t0
                log.info(
                    "skipped_fetch=true duration_sec=%.1f target_date=%s reason=%s"
                    " units=%s (coverage done, send skipped)",
                    _dur,
                    _skip_meta.get("target_date"),
                    _skip_meta.get("reason"),
                    _skip_meta.get("units"),
                )
                # 이상치 경보(TASK-G04): skip 인데도 coverage 가 비정상적으로 짧으면 경고.
                # coverage 를 돌렸다면 보통 수분 이상; 30초 미만이면 artifact/수집 의심.
                if _dur < 30 and not args.skip_coverage_fetch:
                    log.warning(
                        "SHORT_RUN_ANOMALY skipped_fetch=true duration_sec=%.1f"
                        " — coverage artifact/수집 누락 의",
                        _dur,
                    )
            else:
                main(
                    allow_send=args.send,
                    include_raw_all=args.include_raw_all,
                    persist_seen=args.persist_seen,
                    collection_gate=_gate,
                    group_id=args.group,
                )
    except Exception as e:
        log.exception("치명적 오류: %s", e)
        raise
    finally:
        if _run_guard is not None:
            _run_guard.release()

"""수출·지원사업 모니터링 에이전트 v6
기능: 수집 → 중복제거(주관기관 우선) → 날짜필터(D-1) → 그룹별 조건필터 → Claude요약 → 발송
설정: sites.json / groups.json / settings.json / seen_ids.json
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

import delivery_state  # 발송 멱등 상태((기준일·그룹·수신자) 단위 체크포인트)
import net_guard       # 아웃바운드 SSRF 가드(사설/내부 IP·비 http(s) 차단)
import llm_safety      # Claude 요약 인젝션 격리·사실성 검증(#99·#101·#102·#104)

BASE_DIR = Path(__file__).resolve().parent

try:
    from raw_store import RawStore as _RawStore
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
SITES_PATH    = BASE_DIR / "sites.json"
GROUPS_PATH   = BASE_DIR / "groups.json"
SETTINGS_PATH = BASE_DIR / "settings.json"
SEEN_IDS_PATH = BASE_DIR / "seen_ids.json"
# (기준일·그룹·수신자) 단위 발송 멱등 상태 — 크래시/부분실패 후 재실행 시 중복발송 방지.
DELIVERY_STATE_PATH = BASE_DIR / "delivery_state.json"

# ── 상수 ─────────────────────────────────────────────────────────────────────
KST            = timezone(timedelta(hours=9))
MAX_SEEN_IDS   = 5000
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
    "공모", "참가신청",
]

GENERAL_SERVICE_EXCLUDE_KEYWORDS = ["설명회", "컨설팅지원", "멘토링"]

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
    "컨설팅", "멘토링", "인증지원", "시제품", "입주기업", "투자유치",
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
    "회원 모집", "모니터링단", "평가위원", "심사위원", "멘토 모집", "운영위원", "강사 모집",
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

    link = str(item.get("link") or "").strip()
    low = link.lower()
    if low.startswith(NON_NOTICE_LINK_SCHEMES):
        return low.split(":", 1)[0] + ":"
    host = urlsplit(low).netloc.split("@")[-1].split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    if host and host in NON_NOTICE_LINK_DOMAINS:
        return host
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
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
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


def _extract_main_content(soup: BeautifulSoup) -> str:
    """정부/기관 게시판 상세에서 본문 텍스트를 범용 추출.
    ① 흔한 본문 컨테이너 후보 → ② 한글 텍스트가 가장 많은 블록 폴백.
    (호스트별 파서가 없는 144개 리스트-온리 소스를 위한 범용 경로)"""
    for tag in soup.select(
        "script, style, nav, header, footer, aside, .lnb, .gnb, .snb, "
        ".paging, .btn_area, .search, .skip, .top_menu, .footer, .header"
    ):
        try:
            tag.decompose()
        except Exception:
            pass
    node = soup.select_one(GENERIC_CONTENT_SELECTORS)
    if node:
        txt = node.get_text("\n", strip=True)
        if _hangul_len(txt) >= 30:
            return txt
    # 폴백: 한글 텍스트가 가장 많은 블록(너무 큰 래퍼는 제외)
    best, best_len = "", 0
    for el in soup.find_all(("div", "td", "section", "article")):
        txt = el.get_text("\n", strip=True)
        hl = _hangul_len(txt)
        if hl > best_len and len(txt) < 20000:
            best, best_len = txt, hl
    return best if best_len >= 30 else ""


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


def _parse_detail_from_page(soup: BeautifulSoup, url: str) -> dict[str, str]:
    """상세 페이지에서 본문·지역·신청기간 추출."""
    result: dict[str, str] = {}
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
    return result


def enrich_item_from_detail(item: dict) -> dict:
    """상세 페이지를 조회해 description·deadline·지역 정보를 보강."""
    link = (item.get("link") or "").strip()
    if not link or item.get("detail_enriched"):
        return item
    specialized = any(host in link for host in DETAIL_ENRICH_HOSTS)
    if not specialized:
        # 전용 호스트가 아니면, 리스트-온리(본문 미수집)일 때만 범용 보강
        if not GENERIC_DETAIL_ENRICH_ENABLED or not _should_generic_enrich(item, link):
            return item
    resp = _http_get(link, timeout=30)
    if resp is None:
        return item
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    if _RAW_STORE is not None:
        with _ENRICH_STORE_LOCK:
            _RAW_STORE.save_detail_html(item["id"], link, html_text)
    fields = _parse_detail_from_page(soup, link)
    updated = {**item, "detail_enriched": True}
    body = fields.get("body", "")
    if body:
        desc = (item.get("description") or "").strip()
        updated["description"] = f"{desc}\n{body}".strip() if desc else body
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
    if _RAW_STORE is not None:
        with _ENRICH_STORE_LOCK:
            _RAW_STORE.update_meta_after_enrich(updated)
    return updated


def enrich_items(items: list[dict], limit: int = MAX_DETAIL_ENRICH) -> list[dict]:
    """신규 공고 중 상세 보강이 필요한 항목을 HTTP 상세 조회(동시 처리).
    ① 전용 호스트(구조화 파서) ② 리스트-온리(본문 미수집) 범용 보강 — 접수기간·지원금·성격 최대 복구."""
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
            return it["id"], it

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
    # PII 격리(#149): 실 수신자가 담긴 그룹 설정을 환경변수(MAIL_GROUPS_JSON)로 주입 가능.
    groups = _pii_config("MAIL_GROUPS_JSON", lambda: load_json(GROUPS_PATH, []))
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
    return {**default, **load_json(SETTINGS_PATH, {})}


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
    return {"id": id_, "title": title, "link": link, "author": author,
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
    return _item(
        iid, ttl, lnk,
        norm(it.get("jrsdInsttNm", it.get("author", ""))),
        norm(it.get("bsnsSumryCn", it.get("description", ""))),
        norm(it.get("reqstBeginEndDe", it.get("reqstDt", ""))),
        site_name, posted, agg,
    )


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
    # ★ 실패 신호 규약(커버리지 오탐 방지) — 한 경로가 '예외 없이' 완료하면(0건이어도) 그 응답을
    #   권위 있는 것으로 신뢰해 그대로 반환한다(정상 0건 = '진짜 0건' → [] 반환, 다음 경로로 안 넘어감).
    #   경로가 하드 실패(HTTP 접속실패·JSON 파싱실패·reqErr/resultCode 오류)하면 다음 경로로 넘어가고,
    #   모든 경로가 하드 실패하면 첫 예외를 올린다 → 상위(fetch_all)가 fetch_success=False='수집실패'로
    #   분류(커버리지 알림 정확 표기 + baseline 오염 방지).
    if DATA_GO_KR_KEY:
        sources = [("data.go.kr", _fetch_bizinfo_datagokr), ("bizinfo 직결", _fetch_bizinfo_direct)]
    else:
        sources = [("bizinfo 직결", _fetch_bizinfo_direct)]

    hard_err: Exception | None = None
    for label, fn in sources:
        try:
            got = fn(site)
        except Exception as e:  # noqa: BLE001 — 이 경로 하드 실패 → 다음 경로 시도
            log.error("기업마당 %s 실패: %s", label, e)
            if hard_err is None:
                hard_err = e
            continue
        # 예외 없이 완료 = 권위 있는 응답(0건이어도 신뢰) → 그대로 반환.
        log.info("%s: %d건 (%s)", site["name"], len(got), label)
        return got

    # 모든 경로가 하드 실패 → 수집실패 신호로 올린다.
    if hard_err is not None:
        raise hard_err
    log.info("%s: 0건", site["name"])
    return []


def fetch_myfair_legacy(site: dict) -> list[dict]:
    # 하위호환용 - fetch_myfair로 대체됨
    return fetch_myfair(site)


def _kstartup_cards_from_soup(soup: BeautifulSoup, clss: str, site: dict, seen_sn: set[str]) -> list[dict]:
    """K-Startup 목록 카드 파싱 — fetch_kstartup·다운로더 공통."""
    items: list[dict] = []
    agg = site.get("is_aggregator", False)
    base_url = site["url"]
    for card in soup.select(".notice"):
        a = card.select_one("a")
        title = norm(a.get_text() if a else "")
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
        org = norm(spans[0].get_text()) if spans else ""
        dl = next((norm(sp.get_text().replace("마감일자", ""))
                   for sp in spans if "마감일자" in sp.get_text()), "")
        pm = re.search(r"등록일자\s*([\d.\-]{8,10})", card.get_text(" ", strip=True))
        posted = extract_date_from_text(pm.group(1)) if pm else ""
        flag = card.select_one(".flag:not(.day):not(.flag_agency)")
        iid = f"kstartup_{sn}" if sn else f"kstartup_{stable_id(title + org)}"
        items.append(_item(iid, title, link, org,
                           norm(flag.get_text()) if flag else "", dl,
                           site["name"], posted, agg))
    return items


def fetch_kstartup(site: dict) -> list[dict]:
    # 공공(PBC010)·민간(PBC020) + 다페이지(기본 5) — 1페이지만 보면 page2+ 공고 누락.
    max_pages = int(site.get("max_pages", 5))
    items: list[dict] = []
    seen_sn: set[str] = set()
    referer = site.get("referer") or site["url"]
    extra_hdr = {"Referer": referer}

    for clss in ("PBC010", "PBC020"):
        empty_streak = 0
        for page in range(1, max_pages + 1):
            soup = _soup(site["url"], extra_headers=extra_hdr, params={
                "schMenuId": "10090", "pageIndex": str(page), "viewCount": "100",
                "pbancSttus": "ing", "pbancClssCd": clss,
            })
            if not soup:
                break
            page_items = _kstartup_cards_from_soup(soup, clss, site, seen_sn)
            if not page_items:
                empty_streak += 1
            else:
                empty_streak = 0
                items.extend(page_items)
            if empty_streak >= 2:
                break
    log.info("%s: %d건", site["name"], len(items))
    return items


def fetch_html_generic(site: dict) -> list[dict]:
    selectors = site.get("selectors", {})
    sel    = selectors.get("row", "table tbody tr")
    date_selector = site.get("date_selector") or selectors.get("date", "")
    deadline_selector = site.get("deadline_selector") or selectors.get("deadline", "")
    soup   = _soup(site["url"])
    if not soup:
        # 접속/파싱 실패(soup=None)는 '진짜 0건'과 다르다 → 예외로 올려 상위가
        # fetch_success=False='수집실패'로 분류(커버리지 '0건 급락' 오탐·baseline 오염 방지).
        # 정상 응답인데 행이 0개면 soup 는 truthy → 아래에서 [] 반환(진짜 0건은 그대로).
        raise RuntimeError(f"{site.get('name', site.get('id', ''))} 접속 실패 (HTML 수집)")
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
        bad_link = (not href or link.split("#")[0] == site["url"].split("#")[0]
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
                    link = urljoin(site["url"], tmpl.format(*grp))
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
    # 이 수집기는 페이지네이션을 하지 않는다(첫 페이지만). 목록 행 수와 실제 추출 수를
    # 함께 남겨, 페이지가 꽉 찬 채 끝났는지(=뒤에 더 있을 가능성)를 사후 판단할 수 있게 한다.
    _page_stat(site.get("id", ""), stop_reason="SINGLE_PAGE", pages_fetched=1,
               row_candidates=len(soup.select(sel)), items=len(items))
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
            # P0 수집누락 탐지용 — 키는 항상 존재하게 두어 판정부가 분기하지 않게 한다
            "detail_link_ok_count": 0,
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
            items = fn(site)
            row["fetch_success"] = True
            row["item_count"] = len(items)
            matched, unknown, _excl = partition_posted_dates(items, days_back)
            row["posted_parsed_count"] = len(matched)
            row["date_unknown_count"] = len(unknown)
            row["today_target_count"] = len(matched)
            # 중복제거 전·후 건수 — 같은 id 가 여러 번 잡히면 목록 파싱이 흔들린 신호
            unique_ids = {it.get("id") for it in items if it.get("id")}
            row["dedup_removed_estimate"] = max(0, len(items) - len(unique_ids))
            row["final_mail_target_estimate"] = len(matched) + len(unknown)
            # 상세링크 추출률 — 링크가 목록 URL 그대로면 상세로 못 들어간 것
            site_url = (site.get("url") or "").split("#")[0]
            row["detail_link_ok_count"] = sum(
                1 for it in items
                if (it.get("link") or "") and (it.get("link") or "").split("#")[0] != site_url
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
    now_dt: datetime | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    posted_date 기준 분류.
    반환: (대상기간 확정, 날짜불명, 그 외 날짜·파싱실패 제외)

    대상기간 = 직전영업일(target) + 그 직후 ~ 오늘 사이의 주말(토/일).
    매일 도는 cron 이 '직전영업일' 하루만 잡으면, 토·일에 게시된 공고는 어떤
    실행일의 직전영업일과도 일치하지 않아 영구 누락된다(주말 recall 손실). 그래서
    직전영업일 직후의 토·일 게시물도 함께 포함한다(평일 실행은 단일일=기존 동작 동일).

    max_age_days 가 지정되면, 게시일이 오늘 기준 그 일수보다 오래된 공고는
    '옛날 공고'로 간주해 강제 제외(_excluded_reason="too_old"). None 이면 미적용.
    """
    now = now_dt or datetime.now(KST)
    target = previous_business_day(now, days_back)
    today = now.date()
    matched, unknown, excluded = [], [], []

    def _in_window(d) -> bool:
        if d == target:
            return True
        # 직전영업일 직후 ~ 오늘 이전의 주말(토/일) 게시물도 포함 (주말 누락 방지)
        return target < d < today and d.weekday() >= 5

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
        if _in_window(item_date):
            matched.append(it)
        else:
            excluded.append({**it, "_excluded_posted_date": pd[:10]})
    log.info(
        "날짜분류(직전영업일-%d, target=%s, today=%s): 확정 %d / 날짜불명 %d / 제외 %d",
        days_back, target, today, len(matched), len(unknown), len(excluded),
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
    """그룹 키워드(AI·SaaS 등) 매칭용 — 지원분야·대상 필드 포함, 주관기관명 제외."""
    parts = [
        item.get("title", ""),
        item.get("description", ""),
        item.get("support_field", ""),
        item.get("target_field", ""),
    ]
    return norm(" ".join(p for p in parts if p)).lower()


def _application_like(text: str) -> bool:
    """신청·모집 성격 공고인지(recall 우선 — 목록 stub에 기간 없어도 누락 방지)."""
    if any(kw in text for kw in APPLICATION_KEYWORDS):
        return True
    if any(kw in text for kw in GRANT_SIGNAL_KEYWORDS):
        return True
    return any(kw in text for kw in ("모집", "신청", "접수", "공모"))


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


def classify_deadline_status(item: dict, today=None) -> str:
    today = today or datetime.now(KST).date()
    text = _notice_text(item)
    if any(term in text for term in OPEN_DEADLINE_TERMS):
        return "open"
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

    # ── recall-safe 타지역 override (공유헬퍼 _other_region_block; own-metro 파라미터화) ──
    # 권역(경상/호남/충청권 등) 멤버 적격 — own 광역이 명시 권역의 멤버면 적격(차단보다 우선=recall,
    # company_match 와 단일 정본 공유). 비멤버는 아래 차단 로직으로.
    from region_clusters import REGION_CLUSTER as _RC
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
    application_like = _application_like(text)
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

    # [제목 앵커] 비공고 정적 페이지(기관소개·정보공개·약관·nav 링크 등) 제외.
    # 제목 완전일치/링크 스킴만 보므로 본문 우연일치로 진짜 공고를 막지 않는다(위 상수 주석 참조).
    nonnotice_hit = non_notice_reason(item)
    if nonnotice_hit:
        reason_codes.append("NOT_GRANT_NOTICE")
        excluded_keywords.append(nonnotice_hit)
        if notice_type == "unknown":
            notice_type = "general_info"

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
    elif deadline_status == "unknown" and not application_like:
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
    # 지역 미상(unknown)과 '확실한 타지역'(not_eligible)을 구분한다(사용자 정책 2026-06-19):
    #  확실한 타지역 → REGION_NOT_ELIGIBLE(제외). 지역 단서 전무 → REGION_UNKNOWN(버리지 말고 '지역 미상'으로 surface).
    region_positively_other = (
        region_info["region_status"] == "not_eligible"
        or region_info["district_status"] == "not_eligible"
    )
    if group is not None and not source_bypass:
        region_ok = (region_info["region_status"] == "eligible") if use_generic_region else region_match(item, req_regions)
        if not region_ok:
            reason_codes.append("REGION_NOT_ELIGIBLE" if region_positively_other else "REGION_UNKNOWN")

    excl_kws = [k.lower() for k in g.get("exclude_keywords", []) if k.strip()]
    group_excluded = [k for k in excl_kws if _kw_in_text(text, k)]
    if group_excluded:
        reason_codes.append("NOT_GRANT_NOTICE")
        excluded_keywords.extend(group_excluded)

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

    if not application_like and not priority_keywords:
        reason_codes.append("NOT_GRANT_NOTICE")

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
    region_status = region_info["region_status"]
    district_status = region_info["district_status"]
    hard_reasons = set(reason_codes) - {"FACTORY_REQUIRED_BUT_UNKNOWN"}
    # recall: 모집·신청 신호 있는데 기간 미파싱(목록 stub)이면 열린 공고로 간주 — 서울·AI 등 누락 방지
    deadline_ok = deadline_status in {"open", "upcoming"} or (
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
    review_needed = (
        not is_relevant
        and bool(priority_keywords)
        and not (set(reason_codes) & {
            "GUIDELINE_OR_MANUAL", "EDUCATION_ONLY", "INFO_SESSION", "SUPPLIER_ONLY",
            "SELECTED_COMPANY_ONLY", "REGION_NOT_ELIGIBLE", "DISTRICT_NOT_ELIGIBLE",
            "CLOSED_DEADLINE", "SMART_FACTORY_INFO_ONLY",
        })
    )
    # 지역 미상 surface(사용자 정책 2026-06-19): 지역만 모르고 그 외 조건은 적격이면
    #  버리지 말고 '지역 미상' 버킷으로 보내 보고 메일 하단에 함께 첨부한다(누락 방지).
    region_unknown_review = (
        region_status == "unknown"
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
        "region_unknown_review": region_unknown_review,
        "business_years_status": biz_years_status,
        "support_amount_status": amount_status,
        # 표시용 — 구체 유형이 있으면 '그외'는 숨긴다(게이트는 classify_support_type 원본을 그대로 사용).
        "_types": ([t for t in classify_support_type(item) if t != "그외"] or ["그외"]),
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
            lines += [f"▸ {it['title']}",
                      f"  기관: {it.get('author') or '미기재'} | 마감: {dl or '미기재'}"
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
    """HTML 태그·엔티티 제거 → 사용자용 평문(메일 본문에 코드/태그 노출 방지). 길면 자른다.
    한도(limit)는 지원내용 본문이 조기에 잘리지 않도록 넉넉히 둔다."""
    if not s:
        return ""
    if "<" in s:
        s = BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:limit].rstrip() + " …") if len(s) > limit else s


def fallback_body(items: list[dict]) -> str:
    # 표시 정책: 사용자에게 필요한 정보만. HTML/내부코드·매칭키워드·스마트공장 등은 숨김.
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
            desc = _plain_text(it.get("description", ""))
            block = [
                "━━━━━━━━━━━━━━━━━━",
                f"📌 {it.get('title') or '(제목없음)'}",
                f"• 지원기관: {it.get('author') or '미기재'}",
                f"• 지원유형: {' · '.join(it.get('_types', ['미분류']))}",
            ]
            if desc:
                block.append(f"• 지원내용: {desc}")
            block.append(f"• 신청마감: {resolve_item_deadline(it) or '미기재'}")
            region_label = _region_label(it)
            if not region_label.endswith("전체"):     # 비제약('…전체')은 생략, 제약/확인필요만 표시
                block.append(f"• 지역: {region_label}")
            if it.get("factory_required") is True:
                block.append("• 공장보유 필요")
            notes = [n for n in (it.get("notes") or []) if n]
            if notes:
                block.append(f"• 확인: {' / '.join(notes)}")
            block += [
                f"• 등록일: {it.get('posted_date') or '날짜불명'}",
                f"• 출처: {it.get('source') or '미기재'}",
                f"• 🔗 {it.get('link') or '미기재'}",
                "━━━━━━━━━━━━━━━━━━",
            ]
            lines += block
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


def render_region_unknown(items: list[dict], limit: int = 30) -> str:
    """지역 단서가 없어 자동분류 못 한 공고를 보고 메일 하단에 '확인 필요'로 첨부(누락 방지)."""
    if not items:
        return ""
    lines = [
        "\n\n────────────────────────────────",
        f"📍 지역 미상 — 확인 필요 ({len(items)}건)",
        "  (지역 단서가 없어 우리 지역인지 자동 판단 못 함 — 놓치지 않도록 함께 첨부)",
    ]
    for it in items[:limit]:
        lines.append(f"\n▸ {it.get('title') or '(제목없음)'}")
        lines.append(
            f"  기관: {it.get('author') or '미기재'}"
            f" | 마감: {resolve_item_deadline(it) or '미기재'}"
            f" | 등록: {it.get('posted_date') or '날짜불명'}"
        )
        if it.get("link"):
            lines.append(f"  🔗 {it['link']}")
    if len(items) > limit:
        lines.append(f"\n외 {len(items) - limit}건")
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
    # 인젝션 관측(로깅) — 차단이 아니라 격리+사후검증이 주 방어.
    _inj = llm_safety.detect_injection(items_txt)
    if _inj:
        log.warning("공고 원문에 인젝션 의심 문구 %d건(격리·검증으로 방어): %s", len(_inj), _inj[:3])
    prompt = f"""{llm_safety.guard_preamble()}

아래는 [{region_ctx} / {kw_ctx} / {type_ctx}] 조건으로 선별된 공고입니다.
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
{llm_safety.wrap_untrusted(items_txt)}"""
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=8000,
            messages=[{"role": "user", "content": prompt}])
        # 출력 토큰 상한(max_tokens)에 걸려 응답이 중간에 끊기면 뒤쪽 공고 본문이 통째로
        # 사라진다(메일 '본문 잘림'). 이때는 요약본 대신 전 공고를 빠짐없이 담는
        # fallback_body 로 대체해 누락을 막는다.
        if getattr(resp, "stop_reason", None) == "max_tokens":
            log.warning("Claude 요약이 토큰 상한에 걸려 잘림 — fallback_body 로 대체(본문 보존)")
            return fallback_body(limited)
        text = resp.content[0].text.strip()
        if not text:
            return fallback_body(limited)
        # 사실성 사후검증(#99·#101·#104): 미승인 링크 호스트·다수 누락이면 결정론적 DB 렌더로 대체.
        _ok, _why = llm_safety.verify_summary(text, limited)
        if not _ok:
            log.warning("Claude 요약 사실성 검증 실패 — fallback_body(DB값)로 대체: %s", _why)
            return fallback_body(limited)
        return text
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

# 테스트 실발송 안전장치: 값이 있으면 모든 발송 수신자를 이 주소 하나로 강제한다.
# (그룹·raw_all·watchlist 등 모든 발송 경로가 send_email/send_to_list 를 거치므로 여기서 일괄 차단)
_ONLY_TO: str = ""

# 사용자 ⭕/❌ 피드백 루프(Tier C 골든 축적) — 모듈이 없어도 발송은 그대로(표시 전용).
try:
    import feedback as _feedback_mod
    _FEEDBACK_OK = True
except Exception:  # noqa: BLE001
    _feedback_mod = None
    _FEEDBACK_OK = False


def _feedback_links_enabled() -> bool:
    """MONITOR_NO_FEEDBACK_LINKS=1 이면 digest 피드백 링크를 끈다(표시 전용 스위치)."""
    return _FEEDBACK_OK and os.getenv("MONITOR_NO_FEEDBACK_LINKS", "") not in ("1", "true", "True")


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


def send_to_list(subject: str, body: str, recipients: list[str], *, idem: dict | None = None) -> None:
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
        return
    if not _ALLOW_SMTP_SEND:
        checked = validate_recipients(recipients)
        log.info(
            "발송 생략 (allow_send=False): subject=%s recipients=%s",
            subject[:60], ", ".join(checked["masked"]) or "(없음)",
        )
        return
    global _SEND_OK, _SEND_FAIL, _LAST_SEND_ERR
    delivered: set[str] = delivery_state.load(idem["path"]) if idem else set()
    for to in validate_recipients(recipients)["valid"]:
        dkey = delivery_state.key(idem["date"], idem["group"], to) if idem else None
        if dkey is not None and dkey in delivered:
            log.info("멱등 skip (이미 발송됨): %s [%s]", _mask_email(to), idem["group"])
            continue
        try:
            send_email(subject, body, to)
            _SEND_OK += 1
            if idem and dkey is not None:
                # 성공 즉시 체크포인트 — 중단 시에도 이 수신자는 재발송 안 됨.
                delivery_state.mark(idem["path"], dkey, _cache=delivered)
        except Exception as e:
            _SEND_FAIL += 1
            _LAST_SEND_ERR = str(e)
            log.error("발송 실패 (%s): %s", _mask_email(to), e)


def guard_group_recipients(recipients: list[str], settings: dict, group_name: str) -> list[str]:
    """#120: settings['recipient_allowlist'] 설정 시 화이트리스트 밖 수신자를 제외·경보.

    groups.json 오설정(A그룹 recipients 에 B고객 유입)으로 타 그룹 다이제스트가 잘못 나가는 것을
    방지한다. allowlist 미설정이면 종전 그대로(동작 불변, opt-in).
    """
    allow = settings.get("recipient_allowlist") or []
    if not allow:
        return recipients
    allow_set = {str(a).strip().lower() for a in allow}
    kept = [r for r in recipients if str(r).strip().lower() in allow_set]
    dropped = [r for r in recipients if str(r).strip().lower() not in allow_set]
    if dropped:
        log.error("수신자 화이트리스트 위반(그룹 '%s') — 발송 제외 %d명: %s",
                  group_name, len(dropped), ", ".join(_mask_email(d) for d in dropped))
        alert_ntfy("recipient_guard",
                   f"[{group_name}] 화이트리스트 밖 수신자 {len(dropped)}명 발송 차단(그룹 설정 확인)",
                   priority="high", tags="warning")
    return kept


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
WATCHLIST_PATH = BASE_DIR / "watchlist.json"


def load_watchlist() -> dict:
    """watchlist.json 로드(키워드·URL·수신자). 없거나 형식오류면 빈 워치리스트."""
    raw = load_json(WATCHLIST_PATH, {})
    if not isinstance(raw, dict):
        return {"keywords": [], "urls": [], "recipients": []}
    return {
        "keywords": [str(k).strip() for k in (raw.get("keywords") or []) if str(k).strip()],
        "urls": [str(u).strip() for u in (raw.get("urls") or []) if str(u).strip()],
        "recipients": [str(r).strip() for r in (raw.get("recipients") or []) if str(r).strip()],
    }


def _norm_url(u: str) -> str:
    """비교용 URL 정규화: 스킴·www·쿼리·앵커·끝슬래시 제거 + 소문자."""
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("?")[0].split("#")[0].rstrip("/")


def is_watchlisted(item: dict, watchlist: dict) -> bool:
    """공고가 워치리스트(키워드/제목 또는 URL)에 걸리는지. 걸리면 강제포함·강조 대상.
    ASCII 키워드(IP 등)는 단어경계 매칭으로 'equipment' 같은 오매칭 방지(_kw_in_text)."""
    kws = watchlist.get("keywords") or []
    if kws:
        text = f"{item.get('title','')} {item.get('description','')} {item.get('author','')}".lower()
        if any(_kw_in_text(text, k.lower()) for k in kws):
            return True
    nurls = [n for n in (_norm_url(u) for u in (watchlist.get("urls") or [])) if n]
    if nurls:
        link = _norm_url(item.get("link") or item.get("url") or "")
        if link and any(link.startswith(n) or n in link for n in nurls):
            return True
    return False


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
) -> dict:
    global _ALLOW_SMTP_SEND, _ALLOW_PERSIST_SEEN, _SEND_OK, _SEND_FAIL, _LAST_SEND_ERR, _RAW_STORE
    global _DRAFT_MODE, _DRAFT_OK, _DRAFT_FAIL, _LAST_DRAFT_ERR
    _ALLOW_SMTP_SEND = allow_send
    _ALLOW_PERSIST_SEEN = persist_seen
    _DRAFT_MODE = draft_mode
    _DRAFT_OK = 0
    _DRAFT_FAIL = 0
    _LAST_DRAFT_ERR = ""
    _SEND_OK = 0
    _SEND_FAIL = 0
    _LAST_SEND_ERR = ""
    _RAW_STORE = None

    # deliver: 실제 발송(allow_send) 또는 초안 생성(draft_mode)이면 디제스트 본문을 실제로
    # 만들어 전달한다. draft_mode 는 _DRAFT_MODE 를 통해 send_to_list 가 초안으로 우회한다.
    deliver = allow_send or draft_mode
    now = datetime.now(KST)
    mode = "send" if allow_send else ("draft" if draft_mode else "preview")
    log.info("=== 모니터링 시작 v6 (%s) / mode=%s ===", now.strftime("%Y-%m-%d %H:%M KST"), mode)

    sites    = load_sites()
    groups   = load_groups()
    settings = load_settings()
    seen_ids = load_seen_ids()
    days_back = settings.get("days_back", 1)

    if not sites:
        log.info("활성 사이트 없음. 종료.")
        return _with_raw_store_stats({"ok": True, "mode": mode, "reason": "no_active_sites"})
    if not groups:
        log.info("활성 그룹 없음. 종료.")
        return _with_raw_store_stats({"ok": True, "mode": mode, "reason": "no_active_groups"})

    if _RawStore is not None:
        _RAW_STORE = _RawStore.from_settings(settings, run_day=now.date())

    # ① 전체 수집
    all_items = fetch_all(sites)
    if not all_items:
        log.info("수집 0건. 종료.")
        return _with_raw_store_stats({"ok": True, "mode": mode, "reason": "no_items"})
    log.info("수집 완료: %d건", len(all_items))

    # ② 중복 제거
    deduped = dedup_items(all_items)
    dedup_removed = len(all_items) - len(deduped)

    # ③ 신규 필터 (seen_ids)
    new_items = [it for it in deduped if it["id"] and it["id"] not in seen_ids]
    log.info("신규(미발송): %d건 / 전체: %d건", len(new_items), len(deduped))

    if _RAW_STORE is not None:
        _RAW_STORE.begin_run(
            collected=len(all_items), deduped=len(deduped), new_items=len(new_items),
        )
        for it in new_items:
            _RAW_STORE.save_item_meta(it)

    new_items = enrich_items(new_items)

    # 집중 모니터링: 사용자 워치리스트(키워드/제목·URL) 매칭분 — 필터 우회 강제포함·강조 대상
    watchlist = load_watchlist()
    watch_hits = (
        [it for it in new_items if is_watchlisted(it, watchlist)]
        if (watchlist["keywords"] or watchlist["urls"]) else []
    )
    if watch_hits:
        log.info("🎯 집중 모니터링 매칭: %d건", len(watch_hits))

    # ④ 날짜 필터 (직전 영업일)
    target_date = previous_business_day(now, days_back)
    date_str    = now.strftime("%m/%d")

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
                send_to_list(f"🎯 [집중 모니터링] {len(watch_hits)}건 ({date_str})", wl_body, wl_recipients)
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
            f"기준일자: {target_date} (직전영업일) 공고\n"
            f"전체수집: {len(all_items)}건 → 중복제거: {dedup_removed}건 → 신규: {len(new_items)}건\n"
            f"날짜필터 후 발송대상: {len(raw_items)}건 (행정고지·잡공고 {raw_dropped}건 제외)\n\n"
        ) + render_all(raw_items, dedup_removed, len(date_unknown), include_unknown)
        send_to_list(
            f"[원본전체] {raw_topic} ({date_str}) — {len(raw_items)}건",
            body_raw, settings["raw_all_recipients"],
        )

    if not filtered_new:
        log.info("처리 대상 없음. 종료.")
        if persist_seen:
            seen_ids.update(it["id"] for it in deduped)
            save_seen_ids(seen_ids)
        return _with_raw_store_stats({
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
                "region_unknown_items": len(ru_items),
                "excluded_items": len(excluded_items),
                "sample_titles": [it.get("title") for it in g_items[:5]],
                "review_titles": [it.get("title") for it in review_items[:5]],
                "region_unknown_titles": [it.get("title") for it in ru_items[:5]],
                "excluded_summary": render_excluded_summary(excluded_items),
            })
        if not g_items and not ru_items:
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
                f"기준일자: {target_date} (직전영업일) 공고\n"
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
            region_unknown_block = render_region_unknown(ru_items)
            # 사용자 ⭕/❌ 피드백 링크 — 실제 나간 메일이 맞았는지 사람 정답(Tier C)을 모은다.
            feedback_block = _render_feedback_block(g_items)
            subj_count = f"{len(g_items)}건" + (f"+지역미상 {len(ru_items)}건" if ru_items else "")
            # (기준일·그룹·수신자) 단위 멱등 발송 — 재실행/부분실패 시 성공 수신자 중복 방지(#113·#114·#144).
            _send_kw: dict = {}
            if persist_seen:
                _gid = str(group.get("id") or group.get("name") or "grp")
                _send_kw["idem"] = {"date": str(target_date), "group": _gid, "path": str(DELIVERY_STATE_PATH)}
            _recips = guard_group_recipients(group.get("recipients", []), settings, group.get("name"))
            send_to_list(
                f"[{group.get('name')}] {subj_count} ({date_str})",
                header + voucher_block + summary + region_unknown_block + feedback_block + kw_footer,
                _recips,
                **_send_kw,
            )
            if voucher_items:
                alert_ntfy(
                    f"voucher {len(voucher_items)}",
                    f"🔔 [{group.get('name')}] 수출·혁신 바우처 공고 {len(voucher_items)}건!\n"
                    + "\n".join(f"- {it['title'][:50]}" for it in voucher_items[:5]),
                    priority="high", tags="loudspeaker",
                )
            # 체크포인트(#144): 이 그룹 발송분을 즉시 seen 기록·저장 → 이후 그룹에서 크래시해도
            # 이미 보낸 건은 다음 실행에서 재발송되지 않는다(종전엔 루프 끝에서만 저장).
            if persist_seen:
                seen_ids.update(it["id"] for it in g_items if it.get("id"))
                seen_ids.update(it["id"] for it in ru_items if it.get("id"))
                save_seen_ids(seen_ids)

    # ⑦ seen_ids 업데이트 (date_unknown도 포함 — 날짜불명 공고 재발송 방지)
    if persist_seen:
        seen_ids.update(it["id"] for it in deduped)
        seen_ids.update(it["id"] for it in date_unknown if it.get("id"))
        save_seen_ids(seen_ids)
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
        "filtered_items": len(filtered_new),
        "date_matched_count": len(date_matched) if settings.get("date_filter_enabled", True) else len(filtered_new),
        "date_unknown_items": len(date_unknown),
        "date_review_queue": date_review_queue,
        "date_review_queue_count": len(date_review_queue),
        "date_excluded_count": len(date_excluded),
        "final_mail_target_count": final_mail_count,
        "mail_sent": bool(allow_send and _ALLOW_SMTP_SEND),
        "drafts_created": _DRAFT_OK,
        "draft_failed": _DRAFT_FAIL,
        "seen_ids_persisted": bool(persist_seen and _ALLOW_PERSIST_SEEN),
        "sent_groups": sent_groups,
        "preview_groups": preview_groups,
    })


def main(
    allow_send: bool = False,
    include_raw_all: bool = False,
    persist_seen: bool = False,
) -> dict:
    # safe-by-default: 인자를 명시적으로 True 로 주지 않으면 발송·원본전체·seen_ids 저장을
    # 모두 하지 않는다(preview-only). 실발송은 호출자가 allow_send=True 를 명시할 때만.
    result = execute_monitor(
        allow_send=allow_send,
        include_raw_all=include_raw_all,
        persist_seen=persist_seen,
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
    path = path or (BASE_DIR / "logs" / "coverage_anomaly_report.md")
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
    path = path or (BASE_DIR / "logs" / f"source_coverage_{run_at:%Y%m%d}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_source_coverage_md(
    payload: dict, path: Path | None = None, *, run_at: datetime | None = None,
) -> Path:
    """관리자 확인용 실행대장 보고서. logs/source_coverage_YYYYMMDD.md"""
    import coverage_alert as _ca  # noqa: PLC0415

    run_at = run_at or datetime.now(KST)
    path = path or (BASE_DIR / "logs" / f"source_coverage_{run_at:%Y%m%d}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_ca.render_coverage_markdown(payload), encoding="utf-8")
    return path


def write_p0_collection_alert(
    payload: dict, path: Path | None = None, *, run_at: datetime | None = None,
) -> Path:
    """P0 누락위험 알림 사본. logs/p0_collection_alert_YYYYMMDD.md"""
    import coverage_alert as _ca  # noqa: PLC0415

    run_at = run_at or datetime.now(KST)
    path = path or (BASE_DIR / "logs" / f"p0_collection_alert_{run_at:%Y%m%d}.md")
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

    운영 게이트이지만 **발송을 막지 않는다** — P0 가 나와도 상태만 DEGRADED 로 표시하고
    정상 수집분의 판정·발송은 그대로 계속된다. 전체를 try/except 로 감싸 이 감사 자체의
    실패가 본 작업(수집·발송)에 절대 전파되지 않게 한다.

    반환: summarize_run_status() 결과 + {"payload", "files"} (실패 시 status="OK").
    """
    try:
        import coverage_alert as _ca  # noqa: PLC0415

        run_at = run_at or datetime.now(KST)
        baseline = _ca.load_coverage_baseline()
        page_stats = page_stats_snapshot()
        reports = _ca.classify_sources(rows, baseline, page_stats=page_stats)
        exec_check = _ca.verify_source_execution(sites, rows)
        summary = _ca.summarize_run_status(reports, exec_check)
        payload = _ca.build_coverage_payload(
            rows, reports, summary, exec_check=exec_check,
            generated_at=run_at.strftime("%Y-%m-%d %H:%M KST"),
        )
        files: dict[str, str] = {}
        if write_files:
            files["json"] = str(write_source_coverage_json(payload, run_at=run_at))
            files["md"] = str(write_source_coverage_md(payload, run_at=run_at))
            if summary.get("p0_count"):
                files["p0_alert"] = str(write_p0_collection_alert(payload, run_at=run_at))
        if summary.get("p0_count") and allow_alert:
            alert_email(
                f"[P0 수집 누락 위험] {summary['p0_count']}개 소스 — 확인 필요",
                _ca.format_p0_alert_message(payload),
            )
        return {**summary, "payload": payload, "files": files}
    except Exception as e:  # 감사 실패는 절대 수집·발송을 막지 않는다
        log.warning("소스 커버리지 감사 실패(무시): %s", e)
        return {"status": "OK", "p0_count": 0, "p1_count": 0, "p0_sources": [],
                "p1_sources": [], "payload": {}, "files": {}, "audit_error": str(e)[:200]}


def run_coverage_anomaly_check(rows: list[dict], *, allow_alert: bool = True) -> list[dict]:
    """커버리지 이상탐지: baseline 대비 0건 급락·수집실패·급감을 찾아 (보수적으로) 폰 알림.

    안전 설계: 전체를 try/except 로 감싸 이상탐지 실패가 본 작업(메일)에 영향 0.
    baseline 이력이 있는 사이트만 비교(첫 실행/신규 사이트 오탐 방지). high 가 있을 때만,
    그리고 allow_alert 일 때만 ntfy 1회 발송. 그 후 성공한 사이트로 baseline 갱신·저장.
    반환: 감지된 anomaly dict 리스트(없으면 빈 리스트).
    """
    try:
        import coverage_alert as _ca  # noqa: PLC0415

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
    if fetch_coverage:
        all_sites = load_json(SITES_PATH, [])
        reset_page_stats()
        coverage_rows = fetch_site_coverage(all_sites)
        # 활성 소스 실행 완전성·품질 감사(P0/P1). 알림은 anomaly_check 와 중복되지 않게
        # P0 가 있을 때만 별도 1회. 실패해도 내부에서 흡수되어 dry-run 을 막지 않는다.
        coverage_audit = run_source_coverage_audit(
            coverage_rows, all_sites, allow_alert=allow_coverage_alert,
        )
        coverage_anomalies = run_coverage_anomaly_check(
            coverage_rows, allow_alert=allow_coverage_alert,
        )

    result = execute_monitor(
        allow_send=False, include_raw_all=False, persist_seen=False, draft_mode=draft_mode,
    )
    result["coverage"] = coverage_rows
    result["coverage_anomalies"] = coverage_anomalies
    result["source_coverage_summary"] = {
        k: v for k, v in coverage_audit.items() if k not in ("payload",)
    }
    # 최상위 스칼라로 승격 — API 응답 요약(_result_summary)이 스칼라만 통과시키기 때문
    result["run_status"] = coverage_audit.get("status", "OK")
    result["collection_p0_count"] = int(coverage_audit.get("p0_count", 0) or 0)
    result["collection_p1_count"] = int(coverage_audit.get("p1_count", 0) or 0)
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
        help="발송·seen_ids 저장 없이 preview 및 logs/ 보고서 생성",
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
    args = parser.parse_args()
    if args.only_to:
        _ONLY_TO = args.only_to
        log.info("only-to 모드: 모든 발송 수신자를 %s 로 강제합니다(테스트)", _mask_email(args.only_to))
    try:
        if args.draft:
            # 초안 모드: 실발송 없이 공고 digest 를 Gmail 초안으로 생성.
            # dry-run 파이프라인을 재사용해 커버리지 이상탐지·보고서를 그대로 유지하고,
            # preview 대신 초안을 만든다(--dry-run 동시 지정도 동일 동작).
            summary = run_dry_run(
                fetch_coverage=not args.skip_coverage_fetch,
                allow_coverage_alert=args.coverage_alert,
                draft_mode=True,
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
            # 실발송 경로에서도 커버리지 이상탐지(모니터링) 유지 — 평소 수집되던 사이트가
            # 0건/급감/실패 시 PC 이메일 알림(누락 방지, PR #123). --coverage-alert 일 때만.
            if args.coverage_alert and not args.skip_coverage_fetch:
                try:
                    _all_sites = load_json(SITES_PATH, [])
                    reset_page_stats()
                    _cov_rows = fetch_site_coverage(_all_sites)
                    # P0 감사 — 활성 소스 미실행·수집실패·급감을 즉시 알린다.
                    # 발송을 막지 않는다: 아래 main() 은 결과와 무관하게 그대로 실행된다.
                    _audit = run_source_coverage_audit(_cov_rows, _all_sites, allow_alert=True)
                    if _audit.get("status") == "DEGRADED":
                        log.warning(
                            "수집 상태 DEGRADED — P0 %s건/P1 %s건 (발송은 계속 진행)",
                            _audit.get("p0_count"), _audit.get("p1_count"),
                        )
                    run_coverage_anomaly_check(_cov_rows, allow_alert=True)
                except Exception as e:
                    log.warning("커버리지 점검 실패(무시): %s", e)
            main(
                allow_send=args.send,
                include_raw_all=args.include_raw_all,
                persist_seen=args.persist_seen,
            )
    except Exception as e:
        log.exception("치명적 오류: %s", e)
        raise

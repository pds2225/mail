"""grp_goyang(경기 고양·업력3~7년·300만원초과) 정확도+누락방지 회귀 테스트.

근본원인(실데이터 재현): ① K-Startup 상세 '지역'이 대부분 '전국' → classify_region_for_group
가 nationwide=True 면 무조건 region eligible → 강원권 행사·서울 청년공간도 경기 그룹 통과.
② 상세 본문 셀렉터가 죽어 업력/대상/주관 신호가 통째로 누락 → 모든 K-Startup 공고가 unknown.
③ 상세 p.tit/p.txt 의 [창업업력][대상][주관기관명] 등 신호를 버림.

수정: 구조화필드 전용키 복원 + 업력 버킷 매퍼 + recall-safe 타지역 override.
★불변(recall 1순위): 정당한 경기/전국 공고는 절대 누락 금지(애매하면 통과).
"""
import json
import os
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402

GROUPS = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
GOYANG = GROUPS["grp_goyang"]
CFG = GOYANG["business_years"]


def _region(item):
    return m.classify_region_for_group(item, m._normalize_group(GOYANG))["region_status"]


# ══════════════════════════════════════════════════════════════════
# 업력 버킷 매퍼 (K-Startup '창업업력' 멀티셀렉트 → 그룹 (3,7] 호환성)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("text,expected", [
    ("1년미만, 2년미만, 3년미만, 5년미만, 7년미만, 10년미만", "eligible"),  # 표준 멀티셀렉트
    ("전체", "eligible"),
    ("예비창업자", "not_eligible"),                    # 예비 단독 → 신청불가
    ("3년미만", "not_eligible"),                       # N=3, N>3 거짓(strict 경계)
    ("5년미만", "eligible"),                           # N=5>3, 4년차 신청가능
    ("예비창업자, 1년미만, 2년미만, 3년미만, 5년미만", "eligible"),
    ("", "unknown"),
])
def test_business_buckets(text, expected):
    assert m.parse_kstartup_business_buckets(text, CFG) == expected


def test_recall_standard_multiselect_not_dropped():
    """★최대 recall 앵커: K-Startup 최빈 멀티셀렉트가 generic 경로(max=1)로 접혀
    not_eligible 로 누락되던 것을 버킷 매퍼가 eligible 로 정확히 살린다."""
    it = {"title": "전국 지원사업", "description": "신청접수", "deadline": "2099-12-31",
          "business_age_text": "1년미만, 2년미만, 3년미만, 5년미만, 7년미만, 10년미만"}
    assert m.business_years_status(it, GOYANG) == "eligible"


def test_business_years_uses_bucket_when_present():
    it = {"title": "x", "description": "", "deadline": "", "business_age_text": "3년미만"}
    assert m.business_years_status(it, GOYANG) == "not_eligible"


def test_business_years_falls_back_without_bucket():
    """business_age_text 없으면 기존 generic 경로 그대로(회귀 0)."""
    it = {"title": "x", "description": "업력 명시 없는 공고문", "deadline": ""}
    assert m.business_years_status(it, GOYANG) == "unknown"


# ══════════════════════════════════════════════════════════════════
# 지역 override — must_exclude (안 맞는 공고 거름)
# ══════════════════════════════════════════════════════════════════
def test_region_kwon_excludes_gangwon():
    """제목 '강원권' 권역 토큰 + own-region 전무 → not_eligible (사용자 신고 #1)."""
    assert _region({"title": "2026 강원권 LIPS INVESTOR DAY",
                    "author": "재단법인 강원창조경제혁신센터", "region_field": "전국"}) == "not_eligible"


def test_region_localgov_excludes_seongbuk():
    """주관 '성북문화재단'(문화재단+성북) + 전국 → not_eligible (사용자 신고 #2: 길음)."""
    assert _region({"title": "[길음청년희망스토어] 청년창업실험공간",
                    "author": "재단법인 성북문화재단", "region_field": "전국"}) == "not_eligible"


def test_region_localgov_excludes_dongdaemun():
    assert _region({"title": "2026 청년창업 레벨UP",
                    "author": "동대문구청", "region_field": "전국"}) == "not_eligible"


# ══════════════════════════════════════════════════════════════════
# 지역 override — must_include (recall 앵커: 절대 누락 금지)
# ══════════════════════════════════════════════════════════════════
def test_region_spares_national_ccei():
    """서울창조경제혁신센터 주관 전국공고(KAMCO형) — CCEI 는 local-gov 제외 → eligible 유지."""
    assert _region({"title": "2026 KAMCO Startup TechBlaze 모집 공고",
                    "author": "서울창조경제혁신센터", "region_field": "전국"}) == "eligible"


def test_region_spares_own_region_signal():
    """경기도경제과학진흥원(C4IR) — own-region '경기' 신호 → override 최우선 미발동."""
    assert _region({"title": "2026 C4IR Korea 멤버십",
                    "author": "(재)경기도경제과학진흥원", "region_field": "전국"}) == "eligible"


def test_region_spares_private_org():
    assert _region({"title": "[TBC 6월 웨비나] Why Georgia 미국 진출",
                    "author": "주식회사 코발트", "region_field": "전국"}) == "eligible"


def test_region_spares_english_seoul():
    """영문 'Seoul' 은 한글 광역약칭 매칭 대상 아님 — false positive 방지."""
    assert _region({"title": "Pre-IVS2026 in Seoul 참가자 모집",
                    "author": "(주)플린토파트너스", "region_field": "전국"}) == "eligible"


def test_region_spares_gyeonggi_company():
    assert _region({"title": "경기 제조기업 성장지원",
                    "author": "경기테크노파크", "region_field": "전국"}) == "eligible"


def test_region_kwon_not_fired_when_own_region_present():
    """권역 토큰이 있어도 own-region(경기) 신호가 있으면 미발동(보수적·recall 우선)."""
    assert _region({"title": "강원권·경기 공동 지원사업",
                    "author": "경기도", "region_field": "경기"}) == "eligible"


def test_region_kwon_spared_when_explicit_nationwide_title():
    """★recall: 제목에 명시적 '전국'이 있으면 권역 토큰이 있어도 진짜 전국공고로 보고 통과.
    (K-Startup region_field='전국' 드롭다운이 아니라 사람이 쓴 제목/본문의 '전국'을 신뢰.)"""
    assert _region({"title": "2026 충청권 스타트업 IR 전국 모집",
                    "author": "창업진흥원", "region_field": "전국"}) == "eligible"


def test_region_localgov_spared_when_explicit_nationwide_desc():
    """본문에 '전국 기업 누구나' 명시 → local-gov override 미발동(recall 보존)."""
    assert _region({"title": "강원권 데모데이", "description": "전국 기업 누구나 신청 가능",
                    "author": "원주시청", "region_field": "전국"}) == "eligible"


def test_region_gangwon_lips_still_excluded_no_explicit_nationwide():
    """대조: 명시적 '전국' 텍스트 없는 강원권 행사는 여전히 제외(사용자 신고 #1 유지)."""
    assert _region({"title": "2026 강원권 LIPS INVESTOR DAY 참여기업 모집",
                    "author": "재단법인 강원창조경제혁신센터", "region_field": "전국"}) == "not_eligible"


# ══════════════════════════════════════════════════════════════════
# K-Startup 상세 구조화필드 파서 복원
# ══════════════════════════════════════════════════════════════════
def test_kstartup_parser_extracts_structured_fields():
    html = (
        '<div>'
        '<p class="tit">지역</p><p class="txt">전국</p>'
        '<p class="tit">창업업력</p><p class="txt">5년미만, 7년미만</p>'
        '<p class="tit">대상</p><p class="txt">대학생, 일반기업</p>'
        '<p class="tit">대상연령</p><p class="txt">만 20세 이상 ~ 만 39세 이하</p>'
        '<p class="tit">주관기관명</p><p class="txt">재단법인 성북문화재단</p>'
        '</div>'
    )
    soup = BeautifulSoup(html, "html.parser")
    fields = m._parse_detail_from_page(soup, "https://www.k-startup.go.kr/x")
    assert fields["region_field"] == "전국"
    assert fields["business_age_text"] == "5년미만, 7년미만"
    assert "성북문화재단" in fields["organizer_field"]
    assert fields["target_age_field"].startswith("만 20")
    # 숫자 든 값이 전용 키로만 보존(본문 오염 방지) — body 키엔 안 들어감
    assert "10년미만" not in fields.get("body", "")

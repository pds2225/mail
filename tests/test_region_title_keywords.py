# -*- coding: utf-8 -*-
"""region_title_keywords — 제목 지역 키워드 규칙 회귀 테스트.

케이스는 전부 실제 공고 제목 코퍼스(4,551건)에서 확인된 것이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from region_title_keywords import resolve_title_region  # noqa: E402


def rf(title: str):
    return resolve_title_region(title).region_field


def reason(title: str):
    return resolve_title_region(title).reason


# ── 대괄호 안에 광역명이 없어도 지역을 인식한다(이번 확장의 핵심) ──

def test_sigungu_tag_resolves_to_sido():
    assert rf("[미추홀구] 2026년 소상공인 지원사업 모집") == "인천광역시"
    assert rf("[김포시] 관내기업 채용 지원") == "경기도"
    assert rf("[장수군] 2026년 시군구연고산업육성사업 지원기업 모집") == "전북특별자치도"


def test_org_tag_resolves_to_sido():
    assert rf("[인천테크노파크] 수출기업 애로상담 창구 운영") == "인천광역시"
    assert rf("[서울시여성가족재단] 2026 일·생활균형 기본 컨설팅") == "서울특별시"
    assert rf("[전북바이오융합산업진흥원] 고용혁신 프로젝트") == "전북특별자치도"


def test_body_region_without_tag():
    assert rf("2026년 하남시 기업지원시책 안내") == "경기도"
    assert rf("홍천군 고향사랑기부제 기금사업 아이디어 공모") == "강원특별자치도"
    assert rf("2026년 대구콘텐츠코리아랩 콘텐츠 스타트업 부스트업 모집") == "대구광역시"


# ── 권역(복수 광역) ──

def test_area_tag_multi_region():
    assert rf("[전남광주] 2026년 수출 중소기업 통번역비 지원") == "광주광역시,전라남도"
    assert rf("[대구ㆍ경북] 2026년 기업지원 프로그램") == "대구광역시,경상북도"


def test_area_narrowed_by_body_sigungu():
    # 권역 태그 + 본문에 특정 시군구 → 그 광역으로 좁힌다
    assert rf("[전남광주] 목포시 2026년 골목형상점가 모집 공고") == "전라남도"


# ── 오탐 방지(코퍼스 실측 반례) ──

def test_daejeon_exhibition_is_not_region():
    # '혁신대전'·'반도체대전'의 대전 = 大展
    assert rf("[재공고]「2026 중소기업 기술·경영 혁신대전」행사대행 용역 입찰공고") is None
    assert rf("2026년 대한민국 에너지대전 공동부스 참여기업 모집") is None


def test_busan_byproduct_is_not_region():
    v = resolve_title_region("2026년 수산부산물 재활용 규제자유특구 책임보험 지원기업 모집")
    assert v.region_field is None or "부산광역시" not in v.region_field


def test_university_name_is_not_region_signal():
    # 경북대=대구, 충남대=대전 — 대학 소재지와 이름이 어긋나므로 지역신호에서 제외
    assert rf("2026년 경북대학교 첨단정보통신융합산업기술원 연수연구원 선발") is None


def test_gwangju_alone_is_ambiguous():
    # 광주광역시 / 경기 광주시 모호 → 라벨 금지, 사람확인 큐
    assert rf("광주 사회적경제 가치마켓 개최") is None
    assert reason("광주 사회적경제 가치마켓 개최") == "ambiguous_region_name"


def test_duplicate_gu_name_is_ambiguous():
    assert rf("[남구일자리종합센터] 제12회 일자리 매칭데이") is None


# ── 전국·충돌 ──

def test_nationwide_explicit():
    assert rf("2027년 전국단위 신청사업 공모 안내") == "전국"


def test_region_plus_nationwide_goes_review():
    v = resolve_title_region("[부산] 전국단위 창업 공모전 참가기업 모집")
    assert v.region_field is None and v.reason == "nationwide_conflict"


def test_conflicting_regions_go_review():
    v = resolve_title_region("서울시 및 부산시 공동 주최 설명회")
    assert v.region_field is None and v.reason == "region_conflict"


def test_no_region_signal():
    v = resolve_title_region("2026년 창업지원사업 통합공고")
    assert v.region_field is None and v.reason is None

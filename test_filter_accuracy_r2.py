"""라운드2: 전 필터 정확성↑ + 누락방지↑ 회귀 테스트 (네트워크/SMTP 없음 — 게시일만 respx).

대상 요구사항: 지역(전 4그룹·인천 포함)·지원사업성격(K-Startup 지원분야 권위 매핑)·게시일(등록일자).
★불변(recall 1순위): own-region/명시적'전국' 신호가 있으면 절대 누락하지 않는다.
"""
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
import respx

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

G = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}


def _gen(item, gid):
    return m.classify_region_for_group(item, m._normalize_group(G[gid]))["region_status"]


def _inc(item):
    return m.classify_region(item)["region_status"]


# ══════════════════════════════════════════════════════════════════
# 지역 — must_exclude (안 맞는 공고 거름), 전 4그룹
# ══════════════════════════════════════════════════════════════════
def test_incheon_blocks_gangwon_kwon():
    assert _inc({"title": "2026 강원권 화장품 수출 데모데이",
                 "author": "강원창조경제혁신센터", "region_field": "전국"}) == "not_eligible"


def test_incheon_blocks_dongdaemun_gu_office():
    assert _inc({"title": "청년창업 발레용품 지원",
                 "author": "동대문구청", "region_field": "전국"}) == "not_eligible"


def test_seoul_group_blocks_busan_kwon():
    assert _gen({"title": "부산권 AI 스타트업 IR", "author": "x", "region_field": "전국"},
                "grp_ai_saas") == "not_eligible"


def test_goyang_blocks_gangwon_lips_preserved():
    """라운드1 신고#1 — 헬퍼 일반화 후에도 보존."""
    assert _gen({"title": "2026 강원권 LIPS INVESTOR DAY",
                 "author": "강원창조경제혁신센터", "region_field": "전국"}, "grp_goyang") == "not_eligible"


def test_busan_kwon_blocked_for_all_metro_groups():
    item = {"title": "부산권 제조 지원", "author": "x", "region_field": "전국"}
    assert _inc(item) == "not_eligible"                       # 인천
    assert _gen(item, "grp_goyang") == "not_eligible"          # 경기
    assert _gen(item, "grp_ai_saas") == "not_eligible"         # 서울


# ══════════════════════════════════════════════════════════════════
# 지역 — must_include (recall 앵커, 누락 금지)
# ══════════════════════════════════════════════════════════════════
def test_incheon_spares_explicit_nationwide():
    assert _inc({"title": "전국 화장품 수출지원 참여기업 모집",
                 "description": "전국 화장품 제조기업 수출"}) == "eligible"


def test_incheon_spares_own_incheon():
    assert _inc({"title": "인천 소재 발레용품 수출바우처", "description": "인천 기업 신청"}) == "eligible"


def test_seoul_group_spares_metro_family_kwon():
    """수도권 family(경기권)는 서울 그룹에서 차단 안 함 — 수도권 상호 누락 0."""
    assert _gen({"title": "경기권 제조 지원", "author": "x", "region_field": "전국"},
                "grp_ai_saas") != "not_eligible"


def test_goyang_seongbuk_localgov_still_blocked():
    """헬퍼 일반화 후에도 경기 그룹의 서울자치구(성북) 기초자치 차단 유지."""
    assert _gen({"title": "길음 청년창업", "author": "재단법인 성북문화재단",
                 "region_field": "전국"}, "grp_goyang") == "not_eligible"


def test_incheon_short_district_no_swallow():
    """인천 own '중구'→short '중'이 서울 '중랑'을 삼키지 않음(풀네임 정확매칭)."""
    assert _inc({"title": "중랑 청년 지원", "author": "중랑구청", "region_field": "전국"}) == "not_eligible"


def test_national_org_ccei_spared_all_groups():
    """창조경제혁신센터 주관 전국공고 — (B) 차단 제외(전국 정당공고 보호)."""
    item = {"title": "2026 KAMCO TechBlaze 모집 공고", "author": "서울창조경제혁신센터",
            "region_field": "전국"}
    assert _gen(item, "grp_goyang") == "eligible"


# ══════════════════════════════════════════════════════════════════
# 지원사업성격 — K-Startup '지원분야' 권위 매핑
# ══════════════════════════════════════════════════════════════════
def test_support_type_field_사업화_to_grant():
    assert "지원금/바우처" in m.classify_support_type(
        {"title": "서천군 지역기업 성장지원사업", "support_field": "사업화"})


def test_support_type_field_정책자금_to_grant():
    assert "지원금/바우처" in m.classify_support_type(
        {"title": "정책자금 안내", "support_field": "정책자금"})


def test_support_type_field_멘토링_to_consulting():
    assert "컨설팅·교육·상담" in m.classify_support_type(
        {"title": "x", "support_field": "멘토링ㆍ컨설팅ㆍ교육"})


def test_support_type_field_행사_stays_etc():
    assert m.classify_support_type({"title": "x", "support_field": "행사ㆍ네트워크"}) == ["그외"]


def test_support_type_no_field_unchanged():
    """support_field 없으면 기존 키워드 분류 그대로(회귀 0)."""
    assert m.classify_support_type({"title": "수출바우처 지원", "description": ""}) == ["지원금/바우처"]


def test_support_field_consulting_only_preserves_etc_gate():
    """★recall 회귀 방지: 키워드 없는 공고가 support_field=멘토링이어도 게이트엔 '그외' 유지
    (지원유형 매핑이 매칭 게이트를 좁혀 goyang 등에서 부당 누락하면 안 됨)."""
    types = m.classify_support_type({"title": "고양시 창업도약 참여기업 모집", "support_field": "멘토링"})
    assert "그외" in types and "컨설팅·교육·상담" in types


def test_support_field_grant_only_preserves_etc_gate():
    types = m.classify_support_type({"title": "성장지원사업", "support_field": "사업화"})
    assert "그외" in types and "지원금/바우처" in types


def test_goyang_consulting_only_notice_not_dropped():
    """end-to-end: 키워드 없는 정당 공고가 support_field=멘토링이어도 goyang에서 누락 안 됨."""
    item = {"title": "고양시 창업도약 참여기업 모집 신청접수", "description": "신청",
            "deadline": "2099-12-31", "support_field": "멘토링",
            "region_field": "전국", "business_age_text": "전체"}
    ev = m.evaluate_notice(item, G["grp_goyang"])
    assert ev["is_relevant"] is True
    assert "그외" not in ev["_types"]   # 표시는 컨설팅·교육으로 정확(그외 숨김)


# ══════════════════════════════════════════════════════════════════
# 게시일 — K-Startup 목록 카드 '등록일자' 추출
# ══════════════════════════════════════════════════════════════════
KSTARTUP_URL = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"

_CARD = """<div class="notice">
  <a href="?pbancSn=9001">테스트 게시일 공고</a>
  <button onclick="goView('9001')">상세</button>
  <span class="list">테스트기관</span>
  <span class="list">마감일자 2026-12-31</span>
  <span class="list">등록일자 2026-06-19</span>
  <p class="flag">공공기관</p>
</div>"""


@respx.mock
def test_kstartup_posted_date_extracted_from_card():
    respx.get(KSTARTUP_URL, params__contains={"pbancClssCd": "PBC010"}).mock(
        return_value=httpx.Response(200, html=f"<html><body>{_CARD}</body></html>"))
    respx.get(KSTARTUP_URL, params__contains={"pbancClssCd": "PBC020"}).mock(
        return_value=httpx.Response(200, html="<html><body></body></html>"))
    items = m.fetch_kstartup({"id": "kstartup", "name": "K-Startup",
                              "url": KSTARTUP_URL, "is_aggregator": False})
    assert len(items) == 1
    assert items[0]["posted_date"] == "2026-06-19"   # 등록일자 추출(기존엔 빈값)
    assert items[0]["deadline"] == "2026-12-31"

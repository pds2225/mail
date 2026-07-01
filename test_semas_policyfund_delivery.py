"""소상공인 정책자금(SEMAS) 발송 회귀 테스트 — 감사에서 '발송 0건' 발견분 수정 고정.

근본원인: 소진공 정책자금은 전국 소상공인 대상이라 지역 단서가 없어 region=unknown →
is_relevant(region=='eligible' 하드요구)에 걸려 전 그룹 발송 0건이었다.
수정: ① fetch_semas_loan_ols 가 region_field='전국' 설정(사실 정확) ② grp_bnco.source_always_include
에 '소진공 정책자금' 추가 → 정책자금 원하는 그룹에 전량 전달. recall 1순위.
"""
import json
import os
import sys
from pathlib import Path

import httpx
import respx

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor as m  # noqa: E402

ROOT = Path(__file__).resolve().parent
GROUPS = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
SEARCH = "https://ols.semas.or.kr/ols/man/SMAN051M/search.do"


def _semas_item(title):
    """실제 fetch 형태의 소진공 정책자금 item(수정 반영: region_field='전국')."""
    return {"id": "semas_loan_ols_1_x", "title": title, "link": "https://ols.semas.or.kr/x",
            "author": "소상공인시장진흥공단", "description": "구분: 대출정보",
            "deadline": "", "source": m.SEMAS_LOAN_SOURCE, "posted_date": "2026-06-30",
            "is_aggregator": False, "region_field": "전국"}


def _bucket(item, gid):
    d = m.filter_for_group_with_diagnostics([item], GROUPS[gid])
    for b in ("included", "review", "excluded"):
        if d[b]:
            return b


# ── 발송(전달) 회귀 ────────────────────────────────────────────────
def test_semas_policyfund_delivered_to_bnco():
    """소상공인 관련 정책자금 → grp_bnco 전달(과거 발송 0건 회귀 방지)."""
    assert _bucket(_semas_item("2026년 6월 신용취약소상공인자금 신청안내"), "grp_bnco") != "excluded"


def test_semas_generic_fund_delivered_via_source_bypass():
    """키워드 없는 일반 정책자금(상생성장/혁신성장 등)도 source_always_include 로 전달."""
    assert _bucket(_semas_item("2026년 2분기 혁신성장촉진자금 신청안내"), "grp_bnco") != "excluded"


def test_semas_nationwide_region_eligible():
    """region_field='전국' → 인천 그룹에서도 region eligible(지역 하드컷 해제)."""
    it = _semas_item("2026년 재도전특별자금 신청안내")
    assert m.classify_region(it)["region_status"] == "eligible"


def test_source_always_include_no_leak_to_other_sources():
    """부작용 방지: source_always_include('소진공 정책자금')는 다른 소스를 통과시키지 않는다."""
    other = {"id": "x", "title": "재도전특별자금 관련 세미나", "author": "무관기관",
             "description": "", "deadline": "", "source": "K-Startup",
             "posted_date": "2026-06-30", "is_aggregator": False}
    ev = m.evaluate_notice(other, GROUPS["grp_bnco"])
    # 소스가 소진공이 아니므로 source_bypass 미발동 → 인천/키워드 필터가 정상 적용
    assert ev.get("is_relevant") is not True or "인천" in other.get("title", "")


def test_grp_bnco_has_source_always_include():
    assert "소진공 정책자금" in GROUPS["grp_bnco"].get("source_always_include", [])


# ── fetcher 가 region_field='전국' 세팅 (respx 오프라인) ────────────────
@respx.mock
def test_fetch_semas_sets_nationwide_region():
    rows = {"result": [
        {"loanSeCdNm": "직접대출", "bltwtrClcd": "대출정보",
         "bltwtrTitNm": "2026년 6월 신용취약소상공인자금 신청안내",
         "bltwtrSeq": "1001", "bbsTypeCd": "01", "frstRegDt": "2026-06-30"},
    ]}
    respx.post(SEARCH).mock(side_effect=lambda req: httpx.Response(
        200, json=rows if b"pageNo=1" in req.content else {"result": []}))
    site = {"id": "semas_loan_ols", "name": m.SEMAS_LOAN_SOURCE,
            "url": "https://ols.semas.or.kr/ols/man/SMAN051M/page.do",
            "is_aggregator": False, "max_pages": 1}
    items = monitor_fetch(site)
    assert items and all(it.get("region_field") == "전국" for it in items)


def monitor_fetch(site):
    return m.fetch_semas_loan_ols(site)

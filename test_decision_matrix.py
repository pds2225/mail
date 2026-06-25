"""5필드 전수 진리표 회귀 테스트 (네트워크/SMTP 없음) — 평생목표 [[mail-lifelong-accuracy-goal]].

지역·지원금·지원사업성격·게시일·접수기간의 모든 경우의 수에서 매칭 판정이 정합한지,
filter_for_group_with_diagnostics 의 세 버킷(included/review/excluded)을 bucket_of 로 검증.
2계층: Tier-1(recall) bucket != 'excluded'; Tier-2(precision) bucket=='excluded' + 구체 hard reason.
★기대값은 empirical pre-check 관측을 권위로 박았다(가정 금지). recall 1순위.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

G = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
ACTIVE = [gid for gid in G if G[gid].get("active")]
TODAY = date(2026, 6, 18)
PERIOD = {"start": "2026-06-01", "end": "2026-12-31", "display": "2026-06-01 ~ 2026-12-31"}


def base(gid):
    common = {"id": "x", "deadline": "2026-12-31", "application_period": dict(PERIOD),
              "is_aggregator": False, "posted_date": "2026-06-18"}
    return {**common, **{
        "grp_default": {"title": "인천광역시 스마트공장 구축 지원사업 신청접수",
                        "description": "인천 소재 중소기업 대상 신청접수", "author": "기관"},
        "grp_ai_saas": {"title": "서울특별시 AI 솔루션 도입 지원 신청접수",
                        "description": "서울 소재 기업 신청접수", "author": "기관"},
        "grp_prestartup_ai": {"title": "서울 AI 솔루션 도입 지원사업 신청접수",
                              "description": "서울 소재 기업 AI 솔루션 신청접수", "author": "기관"},
        "grp_bnco": {"title": "인천광역시 화장품 수출지원 신청접수",
                     "description": "인천 소재 화장품 기업 신청접수", "author": "기관"},
    }[gid]}


def bucket_of(item, gid):
    d = m.filter_for_group_with_diagnostics([item], G[gid], TODAY)
    for b in ("included", "region_unknown", "review", "excluded"):
        if d[b]:
            return b, d[b][0]
    return "none", {}


def mk(gid, **mut):
    it = base(gid)
    it.update(mut)
    return it


# 커버리지 게이트용 — 검증한 (axis, category, group) 기록
COVERED = set()


def record(axis, cat, gid):
    COVERED.add((axis, cat, gid))


# ══════════════════════════════════════════════════════════════════
# baseline — 4그룹 전부 통과(included) + 게이트 invariant
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("gid", ACTIVE)
def test_baseline_included(gid):
    b, ev = bucket_of(base(gid), gid)
    record("baseline", "neutral", gid)
    assert b == "included", (gid, b, ev.get("exclude_reason_codes"))
    assert ev["is_relevant"] is True
    assert "NOT_GRANT_NOTICE" not in ev["exclude_reason_codes"]
    assert "INDUSTRY_NOT_MATCHED" not in ev["exclude_reason_codes"]


# ══════════════════════════════════════════════════════════════════
# [지역] 4그룹 × {전국명시, 타지역권역, 타지역기초단체, unknown}
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("gid", ACTIVE)
def test_region_explicit_nationwide_passes(gid):
    """전국 명시(title) → Tier-1 통과(recall)."""
    b, ev = bucket_of(mk(gid, title="전국 " + base(gid)["title"].split(" ", 1)[1],
                         region_field="전국"), gid)
    record("region", "explicit_nationwide", gid)
    assert b != "excluded", (gid, b, ev.get("exclude_reason_codes"))


@pytest.mark.parametrize("gid", ACTIVE)
def test_region_other_kwon_excluded(gid):
    """타지역 광역권(부산) → Tier-2 excluded + REGION_NOT_ELIGIBLE."""
    b, ev = bucket_of(mk(gid, title="부산권 " + base(gid)["title"].split(" ", 1)[1],
                         description="신청접수", region_field="전국"), gid)
    record("region", "other_kwon", gid)
    assert b == "excluded" and "REGION_NOT_ELIGIBLE" in ev["exclude_reason_codes"]


@pytest.mark.parametrize("gid", ACTIVE)
def test_region_other_localgov_excluded(gid):
    """타지역 기초단체 주관(동대문구청) → Tier-2 excluded + REGION_NOT_ELIGIBLE."""
    b, ev = bucket_of(mk(gid, author="동대문구청",
                         title=base(gid)["title"].split(" ", 1)[1],
                         description="신청접수", region_field="전국"), gid)
    record("region", "other_localgov", gid)
    assert b == "excluded" and "REGION_NOT_ELIGIBLE" in ev["exclude_reason_codes"]


@pytest.mark.parametrize("gid", ACTIVE)
def test_region_unknown_surfaced_not_excluded(gid):
    """★정책변경(2026-06-19): 지역 단서 전무 → 버리지 말고 '지역 미상' 버킷으로 surface(recall).
    '확실한 타지역'(not_eligible)과 달리 REGION_NOT_ELIGIBLE 를 붙이지 않는다."""
    b, ev = bucket_of(mk(gid, title=base(gid)["title"].split(" ", 1)[1],
                         description="중소기업 신청접수"), gid)
    record("region", "unknown", gid)
    assert b == "region_unknown", (gid, b, ev.get("exclude_reason_codes"))
    assert "REGION_NOT_ELIGIBLE" not in ev["exclude_reason_codes"]
    assert ev.get("region_unknown_review") is True


# ══════════════════════════════════════════════════════════════════
# [지원금] 합성 임계 그룹 × {초과, 이하, 미상, 비금액}
#   현재 active 그룹엔 min_support_amount 임계가 없으므로(grp_goyang 제거됨),
#   grp_prestartup_ai 를 복제해 임계 3,000,000(exclusive)을 주입한 합성 그룹으로
#   금액 추출/임계 비교 로직(support_amount_status·AMOUNT_TOO_LOW)을 계속 검증한다.
# ══════════════════════════════════════════════════════════════════
def _amount_group():
    g = dict(G["grp_prestartup_ai"])
    g["min_support_amount"] = 3_000_000
    g["min_support_amount_inclusive"] = False
    return g


def _amount_item(**mut):
    """합성 그룹 키워드 게이트(AI/서울/신청접수)를 통과하는 기준 아이템."""
    it = {"id": "x", "deadline": "2026-12-31", "application_period": dict(PERIOD),
          "is_aggregator": False, "posted_date": "2026-06-18",
          "title": "서울 AI 솔루션 지원 신청접수", "description": "서울 AI 솔루션 신청접수",
          "author": "기관"}
    it.update(mut)
    return it


def _amount_bucket(item):
    g = _amount_group()
    d = m.filter_for_group_with_diagnostics([item], g, TODAY)
    for b in ("included", "review", "excluded"):
        if d[b]:
            return b, d[b][0]
    return "none", {}


def test_amount_over_threshold_included():
    b, ev = _amount_bucket(_amount_item(description="서울 AI 솔루션 신청접수 지원금 500만원"))
    record("amount", "over", "grp_prestartup_ai")
    assert b == "included" and ev["support_amount_status"] == "eligible"


def test_amount_under_threshold_not_filtered():
    """★정책변경(2026-06-19): 지원금 필터 비활성 — 금액 미달이어도 제외하지 않는다(recall).
    합성 임계 그룹(min_support_amount=3,000,000)이라도 enforce_amount_filter 없으면 게이트 미적용.
    표시값(support_amount_status)은 여전히 'not_eligible'로 산출되지만 제외엔 영향 없음."""
    b, ev = _amount_bucket(_amount_item(description="서울 AI 솔루션 신청접수 지원금 200만원"))
    record("amount", "under", "grp_prestartup_ai")
    assert b == "included" and "AMOUNT_TOO_LOW" not in ev["exclude_reason_codes"]
    assert ev["support_amount_status"] == "not_eligible"


def test_amount_filter_reenabled_by_group_flag_excludes():
    """역호환: 그룹에 enforce_amount_filter=true 면 금액 필터가 다시 작동(미달→excluded)."""
    g = _amount_group(); g["enforce_amount_filter"] = True
    item = _amount_item(description="서울 AI 솔루션 신청접수 지원금 200만원")
    d = m.filter_for_group_with_diagnostics([item], g, TODAY)
    assert d["excluded"] and "AMOUNT_TOO_LOW" in d["excluded"][0]["exclude_reason_codes"]


def test_amount_unknown_included():
    """미상 → 통과(recall: unknown→pass)."""
    b, ev = _amount_bucket(_amount_item())
    record("amount", "unknown", "grp_prestartup_ai")
    assert b == "included" and ev["support_amount_status"] == "unknown"


def test_amount_nonmoney_man_not_excluded():
    """★RED 회귀: '100만명' 비금액이 정당 공고를 AMOUNT_TOO_LOW 로 제외하면 안 됨."""
    b, ev = _amount_bucket(_amount_item(
        title="서울 AI 솔루션 지원 신청접수 참여 100만명 돌파"))
    record("amount", "nonmoney", "grp_prestartup_ai")
    assert b != "excluded" and ev["support_amount_status"] == "unknown"


@pytest.mark.parametrize("gid", ["grp_ai_saas", "grp_prestartup_ai", "grp_bnco"])
def test_amount_na_for_groups_without_threshold(gid):
    """임계 없는 그룹은 amount n/a — 이 축 미적용(통과)."""
    b, ev = bucket_of(base(gid), gid)
    record("amount", "n/a", gid)
    assert ev["support_amount_status"] == "n/a" and b == "included"


# ── RED 단위 + 양방향 대칭쌍(차단 과잉/누수 방지) ──
@pytest.mark.parametrize("text,expected", [
    ("100만명 돌파", None), ("100만건 접수", None), ("50만개 보급", None),
    ("지원금 500만원", 5_000_000), ("최대 300만원 지원", 3_000_000),
    ("3000만원", 30_000_000), ("20억원 규모", 2_000_000_000), ("만 20세 이상", None),
])
def test_extract_support_amount_unit(text, expected):
    assert m.extract_support_amount(text) == expected


# ══════════════════════════════════════════════════════════════════
# [접수기간] 4그룹 × {open, closed, 상시, 미상}
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("gid", ACTIVE)
def test_deadline_open_included(gid):
    b, ev = bucket_of(base(gid), gid)
    record("deadline", "open", gid)
    assert b == "included" and ev["deadline_status"] == "open"


@pytest.mark.parametrize("gid", ACTIVE)
def test_deadline_closed_excluded(gid):
    b, ev = bucket_of(mk(gid, application_period={"start": "2026-05-01", "end": "2026-06-10",
                                                  "display": "~2026-06-10"}, deadline="2026-06-10"), gid)
    record("deadline", "closed", gid)
    assert b == "excluded" and "CLOSED_DEADLINE" in ev["exclude_reason_codes"]


@pytest.mark.parametrize("gid", ACTIVE)
def test_deadline_always_open_included(gid):
    """상시모집(OPEN_DEADLINE_TERMS) → open 통과."""
    b, ev = bucket_of(mk(gid, application_period=None, deadline="",
                         title=base(gid)["title"] + " 상시모집"), gid)
    record("deadline", "always", gid)
    assert b != "excluded" and ev["deadline_status"] == "open"


@pytest.mark.parametrize("gid", ACTIVE)
def test_deadline_missing_observed(gid):
    """기간 미상 + 신청·모집 신호 없음 → MISSING_APPLICATION_PERIOD."""
    b, ev = bucket_of(mk(
        gid, application_period=None, deadline="",
        title="제도 안내", description="유의사항 참고",
    ), gid)
    record("deadline", "missing", gid)
    assert "MISSING_APPLICATION_PERIOD" in ev["exclude_reason_codes"]
    assert b == "excluded"


@pytest.mark.parametrize("gid", ACTIVE)
def test_deadline_missing_but_application_signal_recall(gid):
    """recall: 모집·신청 키워드 있는데 기간 미파싱 → 누락하지 않음(서울·AI 목록 stub)."""
    b, ev = bucket_of(mk(gid, application_period=None, deadline=""), gid)
    record("deadline", "missing_recall", gid)
    assert "MISSING_APPLICATION_PERIOD" not in ev["exclude_reason_codes"]
    assert b in ("included", "region_unknown", "review")


# ══════════════════════════════════════════════════════════════════
# [지원사업성격] K-Startup 지원분야 권위매핑 + '그외' 게이트 보존
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sf,expect_in", [
    ("사업화", "지원금/바우처"), ("정책자금", "지원금/바우처"),
    ("멘토링ㆍ컨설팅ㆍ교육", "컨설팅·교육·상담"),
])
def test_support_type_field_mapping(sf, expect_in):
    record("support_type", sf, "any")
    assert expect_in in m.classify_support_type({"title": "x", "support_field": sf})


def test_support_type_etc_gate_preserved():
    """★recall: 키워드 무매칭 + support_field=멘토링이어도 게이트엔 '그외' 유지."""
    record("support_type", "etc_preserved", "any")
    assert "그외" in m.classify_support_type({"title": "x", "support_field": "멘토링"})


def test_support_type_no_field_unchanged():
    record("support_type", "keyword_only", "any")
    assert m.classify_support_type({"title": "수출바우처 지원"}) == ["지원금/바우처"]


# ══════════════════════════════════════════════════════════════════
# [게시일] 등록일자 추출 + 직전영업일/주말 윈도
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("text,expected", [
    ("등록일자 2026-06-19", "2026-06-19"), ("신청기간 2026.06.13 까지", "2026-06-13"),
    ("2.5% 할인", ""), ("3.4억원", ""),
])
def test_posted_date_extract(text, expected):
    record("posted", "extract", "any")
    assert m.extract_date_from_text(text) == expected


def test_posted_weekend_window_monday():
    """월요일 실행: 금/토/일 게시물 모두 포함(직전영업일 윈도, recall)."""
    record("posted", "weekend", "any")
    from datetime import datetime
    monday = datetime(2026, 6, 15, 8, 0, tzinfo=m.KST)
    items = [{"id": x, "title": x, "posted_date": d, "is_aggregator": False}
             for x, d in [("fri", "2026-06-12"), ("sat", "2026-06-13"),
                          ("sun", "2026-06-14"), ("thu", "2026-06-11")]]
    matched, unknown, excluded = m.partition_posted_dates(items, days_back=1, now_dt=monday)
    assert {i["id"] for i in matched} == {"fri", "sat", "sun"}


# ══════════════════════════════════════════════════════════════════
# 교차조합(축독립 보강) — 전부 Tier-1 통과(recall-위험 조합)
# ══════════════════════════════════════════════════════════════════
def test_cross_own_region_x_unknown_amount():
    b, _ = bucket_of(base("grp_prestartup_ai"), "grp_prestartup_ai")  # 서울 own + 금액 임계 무(n/a)
    record("cross", "own_x_unknown_amount", "grp_prestartup_ai")
    assert b == "included"


def test_cross_always_open_x_unknown_amount():
    b, _ = bucket_of(mk("grp_prestartup_ai", application_period=None, deadline="",
                        title="서울 AI 솔루션 도입 지원사업 신청접수 상시모집"), "grp_prestartup_ai")
    record("cross", "always_x_unknown_amount", "grp_prestartup_ai")
    assert b != "excluded"


def test_cross_own_region_x_unknown_date():
    """서울 own + 게시일 불명(dict 마감 살아있음) → 통과."""
    b, _ = bucket_of(mk("grp_prestartup_ai", posted_date=""), "grp_prestartup_ai")
    record("cross", "own_x_unknown_date", "grp_prestartup_ai")
    assert b == "included"


# ══════════════════════════════════════════════════════════════════
# 커버리지 게이트 — 모든 (axis, category) 적용 셀이 ≥1 케이스에 매핑
# ══════════════════════════════════════════════════════════════════
def test_coverage_complete():
    """falsifiable: 핵심 축×카테고리가 전부 검증됐는지 머신 체크."""
    region_cats = {"explicit_nationwide", "other_kwon", "other_localgov", "unknown"}
    deadline_cats = {"open", "closed", "always", "missing"}
    required = set()
    for c in region_cats:
        required |= {("region", c, g) for g in ACTIVE}
    for c in deadline_cats:
        required |= {("deadline", c, g) for g in ACTIVE}
    required |= {("amount", c, "grp_prestartup_ai") for c in {"over", "under", "unknown", "nonmoney"}}
    required |= {("baseline", "neutral", g) for g in ACTIVE}
    missing = required - COVERED
    assert not missing, f"미검증 셀: {sorted(missing)}"

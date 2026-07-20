"""지역 미상 surface + 지원금 필터 비활성 정책 회귀 테스트 (네트워크/SMTP 없음).

사용자 정책(2026-06-19): 평생목표 [[mail-lifelong-accuracy-goal]] / recall 1순위.
- 지역 단서가 전혀 없는 공고는 버리지 말고 '지역 미상' 버킷으로 surface → 보고 메일 하단에 함께 첨부.
- '확실한 타지역'(부산권 등)은 그대로 제외(REGION_NOT_ELIGIBLE) — 잘못 surface 하지 않는다.
- 지원금(금액)으로는 당분간 거르지 않는다(필터 비활성, 표시값은 유지).
"""
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

TODAY = date(2026, 6, 18)
PERIOD = {"start": "2026-06-01", "end": "2026-12-31", "display": "2026-06-01 ~ 2026-12-31"}

# groups.json 설정 변경에 독립된 단위 테스트용 경기 지역 픽스처.
# grp_goyang(경기 고양시) 그룹과 동일한 region 속성을 갖고 키워드 필터는 없음.
_TEST_GROUP_GYEONGGI = {
    "id": "test_gyeonggi",
    "name": "테스트 경기 그룹",
    "applicant_region_city": "경기도 고양시",
    "applicant_region_label": "경기",
    "or_keywords": [],
    "and_keyword_groups": [],
    "exclude_keywords": [],
    "required_conditions": {},
    "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
    "score_threshold": 1,
}


def _item(**mut):
    it = {"id": "x", "title": "제조기업 성장지원 사업 신청접수",
          "description": "중소기업 신청접수", "author": "기관",
          "deadline": "2026-12-31", "application_period": dict(PERIOD),
          "is_aggregator": False, "posted_date": "2026-06-18"}
    it.update(mut)
    return it


def _diag(item, group=None):
    return m.filter_for_group_with_diagnostics([item], group or _TEST_GROUP_GYEONGGI, TODAY)


# ── 지역 미상 surface ───────────────────────────────────────────────
def test_region_unknown_goes_to_region_unknown_bucket():
    d = _diag(_item())
    assert d["region_unknown"], d
    ev = d["region_unknown"][0]
    assert ev["region_status"] == "unknown"
    assert "REGION_NOT_ELIGIBLE" not in ev["exclude_reason_codes"]
    assert ev["is_relevant"] is False  # 자동 포함은 아님(확인 필요)


def test_diagnostics_has_region_unknown_key():
    d = _diag(_item())
    assert set(d.keys()) == {"included", "review", "region_unknown", "excluded"}


def test_positively_other_region_still_excluded_not_surfaced():
    """확실한 타지역(부산권)은 surface 하지 않고 그대로 제외한다(과잉 surface 방지)."""
    d = _diag(_item(title="부산권 제조기업 성장지원 사업 신청접수"))
    assert not d["region_unknown"], d["region_unknown"]
    assert d["excluded"] and "REGION_NOT_ELIGIBLE" in d["excluded"][0]["exclude_reason_codes"]


def test_own_region_still_included():
    """우리 지역(경기)은 그대로 included — 정책 변경이 정상 동작을 깨지 않는다."""
    d = _diag(_item(title="경기도 제조기업 성장지원 사업 신청접수",
                    description="경기 소재 중소기업 신청접수"))
    assert d["included"] and d["included"][0]["is_relevant"] is True


def test_closed_deadline_region_unknown_not_surfaced():
    """지역 미상이라도 마감 종료 등 다른 하드 사유가 있으면 surface 안 함(노이즈 방지)."""
    d = _diag(_item(deadline="2026-01-01 ~ 2026-01-10",
                    application_period={"start": "2026-01-01", "end": "2026-01-10",
                                        "display": "2026-01-01 ~ 2026-01-10"}))
    assert not d["region_unknown"], d["region_unknown"]


# ── 보고 메일 하단 '지역 미상' 섹션 렌더 ─────────────────────────────
def test_render_region_unknown_section():
    items = [{"title": "지역없는 지원사업 공고", "author": "어떤기관",
              "deadline": "2026-12-31", "posted_date": "2026-06-18",
              "link": "https://example.com/a"}]
    out = m.render_region_unknown(items)
    assert "지역 미상" in out and "확인 필요" in out
    assert "지역없는 지원사업 공고" in out
    assert "https://example.com/a" in out


def test_render_region_unknown_empty_is_blank():
    assert m.render_region_unknown([]) == ""

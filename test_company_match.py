"""Unit tests for company_match.py — 기업 맞춤 매칭 레이어.

Run: python -m pytest test_company_match.py -v
네트워크/환경변수 불필요 (self-contained).
"""
from __future__ import annotations

import json
from pathlib import Path

import company_match


# ── 픽스처 ────────────────────────────────────────────────────────────────────

def _incheon_company(**ov):
    c = {
        "id": "cmp_incheon",
        "name": "인천 제조수출 기업",
        "email": company_match.TEST_RECIPIENT,
        "active": True,
        "region": {"city": "인천", "district": "남동구"},
        "industry_keywords": ["화장품", "뷰티", "제조", "제조업"],
        "interest_keywords": ["수출", "해외전시회", "스마트공장", "공정자동화"],
        "exclude_keywords": ["설명회", "교육일정", "공급기업"],
        "has_factory": True,
        "export_focus": True,
        "support_type_prefs": ["지원금/바우처"],
        "match_threshold": 50,
    }
    c.update(ov)
    return company_match._normalize_company(c)


def _seoul_company(**ov):
    c = {
        "id": "cmp_seoul",
        "name": "서울 AI 스타트업",
        "email": company_match.TEST_RECIPIENT,
        "active": True,
        "region": {"city": "서울", "district": ""},
        "industry_keywords": ["AI", "인공지능", "데이터", "SaaS"],
        "interest_keywords": ["사업화", "스타트업"],
        "exclude_keywords": ["설명회"],
        "has_factory": False,
        "export_focus": False,
        "support_type_prefs": ["지원금/바우처"],
        "match_threshold": 50,
    }
    c.update(ov)
    return company_match._normalize_company(c)


def _item(title="", description="", **ov):
    it = {"title": title, "description": description}
    it.update(ov)
    return it


# 기업 맞춤 격리 검증용 공통 공고 셋
def _sample_items():
    return [
        _item("인천 남동구 제조기업 스마트공장 지원 신청접수",
              "인천 남동구 소재 제조업 영위 기업. 공장보유 우대.",
              _types=["지원금/바우처"]),
        _item("서울 AI 데이터 SaaS 스타트업 사업화 지원",
              "서울 소재 인공지능 데이터 SaaS 기업 사업화 자금.",
              _types=["지원금/바우처"]),
        _item("부산 전용 물류비 지원사업",
              "부산광역시 소재 기업만 신청 가능. 부산 외 지역 제외.",
              _types=["지원금/바우처"]),
    ]


# ── US-001: 로더 ──────────────────────────────────────────────────────────────

def test_load_companies_missing_file_returns_empty():
    out = company_match.load_companies(Path("___nope_companies___.json"))
    assert out == []


def test_load_companies_filters_active_and_fills_defaults(tmp_path):
    data = {"companies": [
        {"id": "a", "email": company_match.TEST_RECIPIENT, "active": True},
        {"id": "b", "email": company_match.TEST_RECIPIENT, "active": False},
    ]}
    p = tmp_path / "companies.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = company_match.load_companies(p)
    assert len(out) == 1
    assert out[0]["id"] == "a"
    # 누락 필드 기본값 보정
    assert out[0]["match_threshold"] == company_match.DEFAULT_THRESHOLD
    assert out[0]["region"] == {"city": "", "district": ""}
    assert out[0]["industry_keywords"] == []


def test_real_companies_json_loads():
    out = company_match.load_companies()  # 프로젝트 companies.json
    assert len(out) >= 1
    assert all(c["email"] == company_match.TEST_RECIPIENT for c in out)


# ── US-002: 점수 ──────────────────────────────────────────────────────────────

def test_score_region_district_boost():
    s = company_match.compute_match_score(
        _item("인천 남동구 제조 지원", "남동구 소재 제조업"), _incheon_company())
    assert s["breakdown"]["region_status"] == "district"
    assert s["score"] >= 50


def test_score_other_region_only_is_mismatch():
    s = company_match.compute_match_score(
        _item("부산 전용 지원", "부산광역시 소재 기업만"), _incheon_company())
    assert s["breakdown"]["region_status"] == "other_only"
    assert any("타지역" in m for m in s["mismatches"])
    assert s["score"] < 50


def test_score_exclude_keyword_drops_below_threshold():
    s = company_match.compute_match_score(
        _item("스마트공장 설명회 안내", "설명회 일정"), _incheon_company())
    assert s["breakdown"]["exclude_hits"] >= 1
    assert s["score"] < 50


def test_score_factory_condition_met_for_factory_company():
    s = company_match.compute_match_score(
        _item("인천 제조 지원", "남동구 공장보유 기업 제조업"), _incheon_company())
    assert s["breakdown"]["factory_required"] is True
    assert any("공장" in r for r in s["reasons"])


def test_score_factory_required_but_company_has_none():
    s = company_match.compute_match_score(
        _item("서울 제조시설 보유 기업 지원", "서울 공장보유 제조시설 필수"), _seoul_company())
    assert any("공장" in m for m in s["mismatches"])


def test_score_empty_item_zero():
    s = company_match.compute_match_score(_item(), _incheon_company())
    assert s["score"] == 0


def test_score_bounded_0_100():
    s = company_match.compute_match_score(
        _item("인천 남동구 화장품 제조 수출 해외전시회 스마트공장 공정자동화",
              "남동구 화장품 뷰티 제조업 수출 해외전시회 스마트공장 공장보유 베트남"),
        _incheon_company())
    assert 0 <= s["score"] <= 100


# ── US-003: 매칭/랭킹/하드제외/격리 ───────────────────────────────────────────

def test_match_for_company_threshold_splits():
    out = company_match.match_for_company(_sample_items(), _incheon_company())
    assert len(out["matched"]) >= 1
    titles = " ".join(it.get("title", "") for it in out["matched"])
    assert "인천" in titles
    # 부산 전용은 제외
    assert all("부산" not in it.get("title", "") for it in out["matched"])


def test_match_ranked_descending():
    out = company_match.match_for_company(_sample_items(), _incheon_company())
    scores = [it["_match_score"] for it in out["matched"]]
    assert scores == sorted(scores, reverse=True)


def test_hard_exclude_closed_deadline():
    items = [_item("인천 남동구 제조 스마트공장 지원", "남동구 제조업",
                   deadline_status="closed", _types=["지원금/바우처"])]
    out = company_match.match_for_company(items, _incheon_company())
    assert len(out["matched"]) == 0
    assert out["audit"][0]["decision"] == "rejected_hard"


def test_hard_exclude_region_code():
    items = [_item("인천 남동구 제조 스마트공장 지원", "남동구 제조업",
                   exclude_reason_codes=["REGION_NOT_ELIGIBLE"])]
    out = company_match.match_for_company(items, _incheon_company())
    assert len(out["matched"]) == 0


def test_company_tailoring_isolation():
    """동일 입력 → 두 기업이 서로 다른 결과 (기업 맞춤 핵심)."""
    items = _sample_items()
    incheon = company_match.match_for_company(items, _incheon_company())
    seoul = company_match.match_for_company(items, _seoul_company())

    incheon_titles = {it["title"] for it in incheon["matched"]}
    seoul_titles = {it["title"] for it in seoul["matched"]}

    assert incheon_titles != seoul_titles
    assert any("인천" in t for t in incheon_titles)
    assert any("서울" in t for t in seoul_titles)
    # 교차 미스매치: 인천 기업은 서울 전용 공고를 받지 않는다
    assert not any("서울" in t for t in incheon_titles)
    assert not any("인천" in t for t in seoul_titles)


def test_match_backward_compat_missing_threshold():
    raw = {"id": "x", "email": company_match.TEST_RECIPIENT,
           "region": {"city": "인천", "district": "남동구"},
           "industry_keywords": ["제조"]}
    out = company_match.match_for_company(
        [_item("인천 남동구 제조 지원", "남동구 제조업")], raw)
    assert "matched" in out and "rejected" in out


# ── US-004: 초안/마스킹/안전 ──────────────────────────────────────────────────

def test_digest_has_banner_and_masked_email():
    company = _incheon_company()
    matched = [_item("인천 남동구 제조 지원", "남동구 제조업", _match_score=80,
                     _match_reasons=["산업적합"], author="인천TP",
                     deadline="2026-06-30", link="http://x")]
    digest = company_match.build_company_digest(company, matched)
    assert "발송 금지" in digest
    # 원본 이메일 평문 미포함, 마스킹 표기 포함
    assert company_match.TEST_RECIPIENT not in digest
    assert company_match.mask_email(company_match.TEST_RECIPIENT) in digest


def test_digest_empty_matched():
    digest = company_match.build_company_digest(_incheon_company(), [])
    assert "없습니다" in digest
    assert "발송 금지" in digest


def test_assert_test_recipient_only():
    ok, viol = company_match.assert_test_recipient_only(
        [{"email": company_match.TEST_RECIPIENT}])
    assert ok and viol == []
    ok2, viol2 = company_match.assert_test_recipient_only(
        [{"email": "stranger@example.com"}])
    assert not ok2 and viol2 == ["stranger@example.com"]


def test_module_does_not_import_smtplib():
    """실제 발송 경로 부재: company_match 는 smtplib 을 import/호출하지 않는다.

    docstring 설명에는 단어가 등장할 수 있으므로 실제 import/호출 패턴만 검사한다.
    """
    src = Path(company_match.__file__).read_text(encoding="utf-8")
    assert "import smtplib" not in src
    assert "smtplib." not in src       # 모듈 속성 호출 없음
    assert "SMTP" not in src           # smtplib.SMTP / SMTP_SSL 등 미사용


def test_determinism():
    items = _sample_items()
    a = company_match.match_for_company(items, _incheon_company())
    b = company_match.match_for_company(items, _incheon_company())
    assert [it["_match_score"] for it in a["matched"]] == [it["_match_score"] for it in b["matched"]]

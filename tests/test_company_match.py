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
    # 추적 JSON에는 이메일이 없어야 하며, 운영 Secret 이 있을 때만 로더가 결합한다.
    public_text = company_match.COMPANIES_PATH.read_text(encoding="utf-8")
    assert "@" not in public_text
    assert all("email" in c for c in out)


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


def test_score_nationwide_with_other_region_not_boosted():
    """'전국' 표기가 있어도 타지역(대구)이 명시되면 전국 보너스를 주지 않고 감점·확인필요로 surface.

    회귀: 비앤코(인천)에 '[대구] 식품박람회'가 '전국' 한 단어로 +16점(적합도 76·1위)
    매칭되던 버그. 타지역 명시를 '전국' 키워드보다 우선 평가해야 한다.
    """
    boosted = company_match.compute_match_score(
        _item("전국 식품제조 박람회 참가 지원",
              "전국 식품제조업소 대상. 대구 EXCO 개최. 판로 개척 수출."),
        _incheon_company())
    assert boosted["breakdown"]["region_status"] == "nationwide_other_region"
    assert any("확인 필요" in mm for mm in boosted["mismatches"])
    # 같은 본문에서 '대구'만 뺀(순수 전국) 공고보다 점수가 낮아야 한다
    pure = company_match.compute_match_score(
        _item("전국 식품제조 박람회 참가 지원",
              "전국 식품제조업소 대상. 판로 개척 수출."),
        _incheon_company())
    assert boosted["score"] < pure["score"]


def test_score_pure_nationwide_still_boosted():
    """타지역 명시 없는 순수 '전국' 공고는 종전대로 전국 보너스 유지(recall 보존)."""
    s = company_match.compute_match_score(
        _item("전국 중소제조기업 수출바우처 지원", "전국 중소기업 대상 수출 지원. 제조업."),
        _incheon_company())
    assert s["breakdown"]["region_status"] == "nationwide"
    assert s["breakdown"]["region_score"] > 0


def test_score_other_region_with_nationwide_excluded_from_match():
    """전국+타지역 동시 공고는 match_for_company 상위 매칭에서 밀려난다(점수 하락)."""
    item = _item("전국 식품박람회", "전국 식품제조 대상. 대구 개최. 판로 수출 박람회.")
    out = company_match.match_for_company([item], _incheon_company())
    # 전국 보너스 대신 감점 → threshold(50) 미만으로 매칭 제외
    assert all("대구" not in it.get("description", "") for it in out["matched"])


def test_score_other_region_with_operator_in_own_region():
    """★Workflow 확정 빈틈: '대구 전용' 공고에 운영사 주소로 우리 시(인천)가 끼어도
    신청자격 강신호(대구 소재 기업만)를 보고 타지역 한정으로 제외한다.
    (city in text 가 운영사/문의처 주소까지 +시일치로 잡던 '거울상' 버그 차단)"""
    s = company_match.compute_match_score(
        _item("대구 전용 식품박람회 참가지원",
              "대구광역시 소재 기업만 신청 가능. 운영사: 인천 소재 OO센터. 박람회 수출."),
        _incheon_company())
    assert s["breakdown"]["region_status"] == "other_only"
    assert any("타지역" in m for m in s["mismatches"])


def test_score_region_token_word_boundary_no_false_positive():
    """광역명 부분매칭 오탐 방지: '서울대 교수'의 '서울'을 지역으로 오인하지 않는다.
    → 전국 청년 공고는 인천 기업에 nationwide 로 유지(타지역 오탐 감점 없음)."""
    s = company_match.compute_match_score(
        _item("청년 창업 지원", "전국 청년 대상. 멘토 서울대 교수 참여."),
        _incheon_company())
    assert s["breakdown"]["region_status"] == "nationwide"


def test_score_non_metropolitan_only_excludes_incheon():
    """'비수도권 한정' 공고는 수도권인 인천을 제외한다."""
    s = company_match.compute_match_score(
        _item("비수도권 제조기업 지원", "비수도권 소재 중소제조기업 대상."),
        _incheon_company())
    assert s["breakdown"]["region_status"] == "other_only"


def test_score_sudogwon_family_eligible():
    """'수도권' 공고는 수도권 family 인 인천 기업에 적격(소재 단서 없어도)."""
    s = company_match.compute_match_score(
        _item("수도권 제조기업 수출지원", "수도권 소재 제조기업 대상. 박람회."),
        _incheon_company())
    assert s["breakdown"]["region_status"] == "city"
    assert s["breakdown"]["region_score"] > 0


def test_score_fullname_province_other_region_excluded():
    """광역 풀네임(경상남도) 타지역 한정도 약칭으로 정규화해 제외한다."""
    s = company_match.compute_match_score(
        _item("경남 수출", "경상남도 소재 수출기업 대상."),
        _incheon_company())
    assert s["breakdown"]["region_status"] == "other_only"


def test_count_hits_ascii_word_boundary():
    """영어약어(AI·MES·SaaS)는 단어경계 — email·training 의 substring 오매칭을 차단하고,
    진짜 영어약어·한글 키워드는 그대로 매칭한다(2026-06-29 채점엔진 비대칭 수정)."""
    # email·training 안에 ai/mes 가 substring 으로 들어가도 오매칭 안 함
    assert company_match._count_hits("이메일 email 안내 training maintenance", ["AI", "MES"]) == (0, [])
    # 진짜 영어약어는 단어경계로 매칭
    assert company_match._count_hits("ai 인공지능 saas 사업화 dx", ["AI", "SaaS", "DX"])[0] == 3
    # 한글 키워드는 substring 유지
    assert company_match._count_hits("제조업 화장품 뷰티 대상", ["제조", "화장품"])[0] == 2


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

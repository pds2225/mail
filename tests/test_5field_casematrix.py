"""5필드 전수 진리표 (라운드3) — 각 판정 함수의 '모든 경우의 수'를 함수 단위로 고정.

목적: 공고 매칭 5필드(지역·지원금·지원사업성격·게시일·접수기간)의 경우의 수마다
'올바른 기대값'을 단언해, 현재 동작이 진리표와 일치하는지 전수 검증한다.

기존 테스트와의 분담(중복 단언 금지):
  - test_decision_matrix.py : evaluate_notice/filter 의 '버킷(included/review/excluded)' end-to-end 진리표.
  - 이 파일(라운드3)    : 그 하위의 '개별 판정 함수' 진리표 + 기존이 빠뜨린 경계·희귀 셀
                          (is_imminent[기존 테스트 전무], 임계 경계값, '접수예정' 단일 upcoming 경로,
                           own지역 직접신호, region_field 단독 '전국', 지역신호 전무,
                           KSTARTUP 지원분야 매핑 확장, support_match 게이트, 명시적 교차조합).

판정 규칙(★불변): 누락 제로(recall) > 정확도(precision). 애매하면 '포함' 쪽.
  - 현재 동작 == 기대값 → 통과 테스트(올바른 현재 동작을 회귀 고정).
  - 현재 동작 != 기대값(특히 정당 공고 누락=recall 손실) → @pytest.mark.xfail 로 갭 명시(로직은 불변).
  - 기대값을 확신 못 하는 애매 케이스 → 단언하지 않고 NIGHT_REPORT '사람 판단 필요'에 기록.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

# env 부트스트랩 — 빈 문자열로 export 된 키(일부 격리 셸)도 보정(멱등, 정상환경 무영향).
for _k, _v in {
    "BIZINFO_API_KEY": "test_key", "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com", "GMAIL_APP_PASSWORD": "test_pass",
    "MONITOR_NO_PERSIST_SEEN": "1",
}.items():
    if not os.environ.get(_k, "").strip():
        os.environ[_k] = _v

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

G = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
ACTIVE = [gid for gid in G if G[gid].get("active")]
TODAY = date(2026, 6, 18)  # 고정 기준일(요일=목)


# 지역 판정 헬퍼 — 그룹 유형에 맞는 분류기를 자동 선택(인천=classify_region, 그 외=for_group).
def region_status(item, gid):
    g = G[gid]
    city = g.get("applicant_region_city", m.APPLICANT_REGION_CITY)
    if city == m.APPLICANT_REGION_CITY:  # 인천 기본 그룹
        return m.classify_region(item)["region_status"]
    return m.classify_region_for_group(item, m._normalize_group(g))["region_status"]


# 인천 그룹(classify_region) / 일반 그룹(classify_region_for_group) 대표 id
INCHEON_GIDS = [gid for gid in ACTIVE
                if G[gid].get("applicant_region_city", m.APPLICANT_REGION_CITY) == m.APPLICANT_REGION_CITY]
GENERIC_GIDS = [gid for gid in ACTIVE if gid not in INCHEON_GIDS]


# ── 합성 경기·임계·업력 그룹 (★production groups.json 불변 · 테스트 픽스처일 뿐) ──
# 상류 sync 6cd6a99 가 grp_goyang(경기·업력(3,7]·임계 300만 초과·exclusive) 그룹을 제거했다.
# 임계·업력·경기-own 축은 현재 active 그룹에 전혀 없으므로, sync 가 갱신한 test_decision_matrix.py
# 와 동일 패턴으로 '합성 그룹'을 만들어 개별 판정 함수의 계약을 전수 고정한다(git 복원 = 옛 goyang 등가).
# or_keywords=[] → 키워드 게이트 미적용(옛 goyang 과 동일·permissive)이라 5필드 축만 격리 검증된다.
def gyeonggi_group(inclusive=False, enforce=False, business_years=None):
    g = {
        "id": "grp_gyeonggi_synth", "active": True,
        "applicant_region_city": "경기도", "applicant_region_label": "경기",
        "required_conditions": {"regions": ["경기"]},
        "min_support_amount": 3_000_000, "min_support_amount_inclusive": inclusive,
        "support_types": ["지원금/바우처", "투자", "그외"], "or_keywords": [],
    }
    if enforce:
        g["enforce_amount_filter"] = True
    if business_years:
        g["business_years"] = business_years
    return g


# ══════════════════════════════════════════════════════════════════
# G001 지역 — own지역 직접신호 / region_field 단독'전국' / 지역신호 전무
#   (타지역 권역·기초단체·전국명시·short-form 삼킴은 test_filter_accuracy_r2 / test_goyang_precision 가 커버)
# ══════════════════════════════════════════════════════════════════
def test_G001_own_signal_incheon_eligible():
    """인천 그룹: '인천 소재' own 직접신호 → eligible(전국 아님)."""
    assert region_status({"title": "인천 소재 기업 수출지원", "description": "인천 소재 중소기업"},
                         "grp_bnco") == "eligible"


def test_G001_own_signal_seoul_eligible():
    assert region_status({"title": "서울 소재 AI기업 지원", "description": "서울 소재 기업"},
                         "grp_ai_saas") == "eligible"


def test_G001_own_signal_gyeonggi_eligible():
    """경기 합성 그룹: own 광역 '경기 소재' 직접신호 → eligible."""
    assert m.classify_region_for_group(
        {"title": "경기도 소재 제조기업 지원", "description": "경기 소재 중소기업"},
        m._normalize_group(gyeonggi_group()))["region_status"] == "eligible"


@pytest.mark.parametrize("region_text", ["인천 소재 중소기업", "경기 소재 중소기업", "수도권 소재 기업"])
def test_G001_extra_eligible_regions_prestartup(region_text):
    """★sync 신규(extra_eligible_regions): grp_prestartup_ai 는 own(서울) 외에 인천·경기·수도권도
    적격 광역으로 본다 → 해당 지역 신호는 eligible(전국공고 외 인접 수도권 누락 방지·recall)."""
    rs = m.classify_region_for_group(
        {"title": f"{region_text} AI 솔루션 지원", "description": region_text},
        m._normalize_group(G["grp_prestartup_ai"]))["region_status"]
    assert rs == "eligible"


@pytest.mark.parametrize("gid", ACTIVE)
def test_G001_region_field_only_nationwide_eligible(gid):
    """★recall: 제목·본문엔 지역신호 없고 region_field 드롭다운만 '전국' → eligible(누락 금지)."""
    item = {"title": "중소기업 수출 지원사업", "description": "중소기업 대상 신청", "region_field": "전국"}
    assert region_status(item, gid) == "eligible"


@pytest.mark.parametrize("gid", ACTIVE)
def test_G001_no_region_signal_unknown(gid):
    """지역신호 전혀 없음 → unknown(eligible/not_eligible 어느 쪽도 단정 안 함)."""
    item = {"title": "중소기업 지원사업 신청", "description": "중소기업 대상 모집"}
    assert region_status(item, gid) == "unknown"


def test_G001_incheon_other_district_not_eligible():
    """인천 그룹(남동구 기업): 같은 인천이라도 '부평구 소재 기업' 전용 → 남동구 신청 불가(not_eligible).
    precision 동작(남동구 기업 대상). recall 손실 아님 — 남동구 기업은 부평구 전용에 신청 못 함."""
    assert m.classify_region({"title": "부평구 소재 기업 지원", "description": "인천 부평구 소재 기업 대상"}
                             )["region_status"] == "not_eligible"


# ── G001 4그룹 횡단 대칭(★recall): '전국'·'타지역 권역'을 모든 활성 그룹에서 동일 판정 ──
#   태스크 요구 "4그룹(인천계열·서울·경기 고양) 모두"를 명시 충족. 두 분류기를 한 번에 횡단:
#     인천계열(grp_default·grp_bnco)=classify_region / 서울·경기(grp_ai_saas·grp_goyang)=classify_region_for_group.
#   (own지역 직접신호·지역신호 전무는 위 함수단위 테스트가 이미 커버 — 중복 단언 추가 안 함.)
@pytest.mark.parametrize("gid", ACTIVE)
def test_G001_explicit_nationwide_eligible_all_groups(gid):
    """본문 '전국' 명시 → 모든 그룹에서 eligible(전국 공고를 어느 그룹도 누락하면 안 됨)."""
    item = {"title": "전국 중소기업 수출바우처 지원사업",
            "description": "전국 소재 중소기업 대상 신청접수"}
    assert region_status(item, gid) == "eligible"


@pytest.mark.parametrize("gid", ACTIVE)
def test_G001_other_metro_region_not_eligible_all_groups(gid):
    """순수 타지역 권역(부산권, own·전국 신호 없음) → 모든 그룹에서 not_eligible.
    부산권은 수도권 family(서울·인천·경기) 밖이라 4그룹 전부에 '타지역' → recall-safe 배제(누락 아님)."""
    item = {"title": "부산권 제조기업 성장지원 공고",
            "description": "제조 중소기업 신청접수"}
    assert region_status(item, gid) == "not_eligible"


def test_G001_other_gyeonggi_city_observed():
    """★관측앵커(사람 판단 필요): 경기 그룹에서 '수원시 전용'(경기 광역·전국·권역·기초단체 신호 전무)은
    현재 unknown 을 반환한다 — 인천 그룹이 '부평구 전용'을 not_eligible 로 처리하는 것과 비대칭.
    (인천=자치구 풀네임 매칭 / 경기=개별 시 식별 경로 없음.) 함수 레벨 unknown 은 하드 배제가 아니라
    recall-안전(게이트에선 region_unknown 버킷으로 surface)이지만, '경기 기업이 수원 전용에 신청
    가능한가'는 precision 도메인 판단이라 단정하지 않고 현재 동작만 고정한다. (NIGHT_REPORT 참조.)"""
    rs = m.classify_region_for_group(
        {"title": "수원시 소재 제조기업 전용 지원", "description": "수원시 소재 중소기업 대상 신청접수"},
        m._normalize_group(gyeonggi_group()))["region_status"]
    assert rs == "unknown"


# ── 라운드3 보강(2026-06-22 sync cc844f2 점검): 제목 '[광역]' 태그 경로 + extra_eligible_regions 갭 ──
def test_G001_title_tag_own_incheon_eligible():
    """제목 '[인천]' 광역 태그 = own 강한 신호 → eligible(태그 경로는 기존 region 테스트 미커버·2334행)."""
    assert m.classify_region({"title": "[인천] 제조기업 수출지원"})["region_status"] == "eligible"


def test_G001_title_tag_other_region_not_eligible():
    """제목 '[부산]' 타지역 광역 태그(own·전국 신호 없음) → not_eligible(명백한 타지역 한정, recall-safe·2343행)."""
    assert m.classify_region({"title": "[부산] 제조기업 성장지원"})["region_status"] == "not_eligible"


# [수정완료 2026-06-23] 위 갭을 monitor.py 2280행 title-tag 분기가 own_regions(label+extra)를
# 보도록 고쳐 해소 — extra 적격광역(인천)의 제목 '[인천]' 태그도 본문 신호와 동일하게 eligible.
# 표기위치(제목태그 vs 본문) 비대칭 누락 제거. 이제 정상 통과 테스트로 회귀 고정.
def test_G001_title_tag_extra_eligible_region_should_pass():
    """기대=현재: extra 적격광역(인천)의 제목 태그도 eligible(2280행 own_regions 반영 수정 후)."""
    rs = m.classify_region_for_group(
        {"title": "[인천] AI 솔루션 지원사업"},
        m._normalize_group(G["grp_prestartup_ai"]))["region_status"]
    assert rs == "eligible"


# ══════════════════════════════════════════════════════════════════
# G002 지원금 — extract_support_amount 단위 + 임계 경계값 + status n/a
#   (over/under/unknown/nonmoney 버킷은 test_decision_matrix 가 커버 — 여기선 경계/단위 보강)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("text,expected", [
    ("5천만원 지원", 50_000_000),          # 천만 단위
    ("1억원 지원", 100_000_000),           # 억 단위
    ("최대 5억원 규모", 500_000_000),
    ("300만원 지원", 3_000_000),           # 만원 단위 경계금액
    ("최대 7천만원", 70_000_000),
    ("100만건 접수", None),                # 비금액 '만'(건) → None (recall: 오추출 금지)
    ("참여 50만명", None),                 # 비금액 '만'(명)
    ("지원 규모 미정", None),              # 금액 미상
    # ── 라운드3 보강(2026-06-22): 범위·복합단위·raw원 경계·공백 (실공고 빈출 패턴, 기존 미커버) ──
    ("3천만원~5천만원 지원", 50_000_000),  # 범위표기 → max(상한) 채택(recall-safe)
    ("1억5천만원 지원", 100_000_000),      # 억+천만 혼합 → 합산 아닌 최대 단일성분(1억)
    ("2억3천5백만원 규모", 200_000_000),   # 복합단위 → 2억(최대), '백만'룰과 상호작용
    ("1000000원", 1_000_000),             # raw '원' 7자리 경계 → 추출(\d{7,})
    ("999999원", None),                    # raw '원' 6자리 → 미추출(\d{7,} 경계)
    ("5 000 만원 지원", 50_000_000),       # 숫자 내부 공백 → NFKC 후 제거하고 인식
])
def test_G002_extract_support_amount(text, expected):
    assert m.extract_support_amount(text) == expected


def test_G002_threshold_boundary_strict_exclusive():
    """합성 임계그룹: min_support_amount=3,000,000, inclusive=false → 정확히 300만원은 not_eligible(초과만 인정)."""
    item = {"title": "경기 제조기업 지원", "description": "지원금 300만원", "author": "기관", "deadline": ""}
    assert m.support_amount_status(item, gyeonggi_group()) == "not_eligible"


def test_G002_threshold_just_over_eligible():
    item = {"title": "경기 제조기업 지원", "description": "지원금 500만원", "author": "기관", "deadline": ""}
    assert m.support_amount_status(item, gyeonggi_group()) == "eligible"


def test_G002_threshold_inclusive_boundary_eligible():
    """가상 그룹(inclusive=true)로 경계 포함 동작 확인: 임계와 '같은 값'은 eligible."""
    grp = {"min_support_amount": 3_000_000, "min_support_amount_inclusive": True}
    item = {"title": "x", "description": "지원금 300만원", "author": "", "deadline": ""}
    assert m.support_amount_status(item, grp) == "eligible"


def test_G002_amount_unknown_is_recall_pass():
    """금액 미상(None) → unknown. (게이트에서 unknown 은 제외하지 않음=recall)."""
    item = {"title": "경기 제조기업 지원", "description": "지원금 규모 추후 공지", "author": "", "deadline": ""}
    assert m.support_amount_status(item, gyeonggi_group()) == "unknown"


def test_G002_amount_filter_disabled_by_default_no_exclude():
    """★sync 정책변경(2026-06-19): 임계 미달이어도 enforce_amount_filter 없으면 게이트가 제외하지
    않는다(금액 표시용·recall 우선·'참가비' 오추출 회피). enforce=True 면 다시 AMOUNT_TOO_LOW.
    (end-to-end under/enforce 4그룹 커버는 test_decision_matrix — 여기선 함수↔플래그 계약만 고정.)"""
    item = {"title": "경기 제조기업 신청접수", "description": "경기 소재 신청접수 지원금 200만원",
            "author": "기관", "deadline": "2026-12-31",
            "application_period": {"start": "2026-06-01", "end": "2026-12-31", "display": "2026-06-01 ~ 2026-12-31"},
            "posted_date": "2026-06-18", "is_aggregator": False}
    off = m.evaluate_notice(item, gyeonggi_group(enforce=False), TODAY)
    on = m.evaluate_notice(item, gyeonggi_group(enforce=True), TODAY)
    assert off["support_amount_status"] == "not_eligible"            # 표시값은 미달로 산출
    assert "AMOUNT_TOO_LOW" not in off["exclude_reason_codes"]       # 그러나 제외 안 함(기본)
    assert "AMOUNT_TOO_LOW" in on["exclude_reason_codes"]            # 플래그 켜면 제외


@pytest.mark.parametrize("gid", ["grp_ai_saas", "grp_bnco"])
def test_G002_status_na_without_threshold(gid):
    """임계(min_support_amount) 없는 그룹 → n/a(이 축 미적용)."""
    item = {"title": "지원사업", "description": "지원금 100만원", "author": "", "deadline": ""}
    assert m.support_amount_status(item, G[gid]) == "n/a"


def test_G002_nonsupport_fee_amount_observed():
    """★관측앵커(사람 판단 필요): '참가비 3만원' 같은 부담금도 '금액'으로 추출된다(현재 동작=30,000).
    extract_support_amount 는 지원금/부담금을 구분하지 않으므로, 임계 그룹(goyang)에서 비-지원금
    소액이 AMOUNT_TOO_LOW 오제외(recall 손실)를 유발할 수 있다 — 단정 대신 현재 동작만 고정한다.
    (NIGHT_REPORT '사람 판단 필요' 참조. 로직 변경은 아침 사람검토 사안.)"""
    assert m.extract_support_amount("해외전시회 참가비 3만원") == 30_000


def test_G002_burden_fee_amount_observed():
    """★관측앵커(사람 판단 필요): '자부담금' 같은 부담금도 참가비와 동형으로 지원금과 구분 없이 추출된다.
    extract_support_amount 는 지원금/부담금 미구분 — enforce_amount_filter 재활성화 시 소액 부담금이
    AMOUNT_TOO_LOW 오제외(recall 손실)를 유발할 수 있다. 현재 동작만 고정(단정 X). NIGHT_REPORT 참조."""
    assert m.extract_support_amount("자부담금 50만원") == 500_000


# ══════════════════════════════════════════════════════════════════
# G003 지원사업성격 — KSTARTUP 지원분야 권위매핑 확장 + '그외' 게이트 보존 + support_match 게이트
#   (지원금/투자/컨설팅/그외 본문 키워드 분류는 test_monitor 가 커버)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sf,expected_bucket", [
    ("융자", "지원금/바우처"),
    ("보증", "지원금/바우처"),
    ("기술개발", "지원금/바우처"),
    ("R&D", "지원금/바우처"),
    ("컨설팅", "컨설팅·교육·상담"),
    ("교육", "컨설팅·교육·상담"),
])
def test_G003_kstartup_field_mapping(sf, expected_bucket):
    """K-Startup 권위 '지원분야' → 우리 버킷 정확 매핑(키워드 추측 보강)."""
    assert expected_bucket in m.classify_support_type({"title": "공고", "support_field": sf})


def test_G003_field_etc_stays_etc():
    """매핑 안 되는 분야(시설·행사 등)는 '그외' 유지(잡음 방지)."""
    assert m.classify_support_type({"title": "공고", "support_field": "시설ㆍ공간ㆍ보육"}) == ["그외"]


def test_G003_etc_gate_preserved_with_field():
    """★recall: 키워드 무매칭 + support_field 매핑이 있어도 게이트엔 '그외' 자격 유지(부당 누락 방지)."""
    types = m.classify_support_type({"title": "고양시 창업도약 참여기업 모집", "support_field": "융자"})
    assert "그외" in types and "지원금/바우처" in types


def test_G003_multi_label_when_multiple_keywords():
    """본문에 여러 유형 키워드 → 복수 라벨(합집합)."""
    types = m.classify_support_type({"title": "투자유치 및 컨설팅 지원", "description": "엔젤투자 멘토링"})
    assert "투자" in types and "컨설팅·교육·상담" in types


def test_G003_support_match_all_types_passes():
    """enabled_types 가 전체(ALL_SUPPORT_TYPES)면 무조건 통과(early return)."""
    assert m.support_match({"title": "행사 네트워크"}, m.ALL_SUPPORT_TYPES) is True


def test_G003_support_match_empty_passes():
    """enabled_types 가 비면 통과(미설정=제한 없음)."""
    assert m.support_match({"title": "행사 네트워크"}, []) is True


def test_G003_support_match_etc_included_when_enabled():
    """'그외'가 enabled_types 에 포함된 그룹(grp_bnco)에서 그외 공고는 통과(recall 보존)."""
    enabled = G["grp_bnco"]["support_types"]
    assert "그외" in enabled
    assert m.support_match({"title": "해외진출 네트워크 행사"}, enabled) is True


def test_G003_support_match_investment_only_excludes_consulting():
    """precision: '투자'만 enabled 인 그룹에서 컨설팅 전용 공고는 매칭 안 됨(False)."""
    assert m.support_match({"title": "컨설팅 멘토링 교육 과정"}, ["투자"]) is False


# ── 라운드3 보강(2026-06-22): support_field substring 경로 + 본문 키워드경계 + 게이트 '그외' recall ──
def test_G003_field_substring_partial_match():
    """support_field 는 substring 비교(1953행 'kw in sf') — 'AI기술개발' 안의 '기술개발'도 지원금 인정.
    (본문은 _kw_in_text 단어경계와 대비되는 분기 — 어디서도 단언 안 됨.)"""
    assert "지원금/바우처" in m.classify_support_type({"title": "공고", "support_field": "AI기술개발"})


def test_G003_body_rnd_ascii_token():
    """본문 'r&d'(ASCII 단어경계 키워드 R&D) → 지원금/바우처. 분야(field) 아닌 '본문' 경로 직접 커버."""
    assert "지원금/바우처" in m.classify_support_type({"title": "r&d 지원사업 공고"})


def test_G003_body_boro_substring_keyword():
    """본문 '보조'(비ASCII substring 키워드) → 지원금/바우처('보조사업'에 삼켜져도 인정·recall)."""
    assert "지원금/바우처" in m.classify_support_type({"title": "보조사업 참여기업 공고"})


def test_G003_support_match_passes_via_etc_in_narrow_group():
    """★recall 핵심(게이트 레벨): 키워드 무매칭 + support_field=융자 공고가, '그외'만 켜고 '지원금/바우처'는
    안 켠 그룹에서도 support_match=True(그외 자격 보존으로 통과) → 부당 누락 방지.
    (classify 의 '그외' 보존은 test_G003_etc_gate_preserved_with_field, 그 게이트 효과는 여기서 단언.)"""
    item = {"title": "고양시 창업도약 참여기업 모집", "support_field": "융자"}
    assert m.support_match(item, ["컨설팅·교육·상담", "그외"]) is True


def test_G003_support_match_partial_intersection_false():
    """precision: 복수라벨(투자+컨설팅) 공고도 enabled 와 교집합 0이면 False(좁은 그룹 정확 배제)."""
    assert m.support_match({"title": "투자유치 및 컨설팅 지원"}, ["지원금/바우처"]) is False


# ══════════════════════════════════════════════════════════════════
# G004 게시일 — previous_business_day / 직전영업일 윈도 / 날짜불명 / 수집윈도 밖 / 위험도
#   (주말 recall·too_old 는 test_accuracy_improve / test_mail_targeting 가 커버 — 여기선 진리표 정리)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("y,mo,d,db,expected", [
    (2026, 6, 15, 1, date(2026, 6, 12)),   # 월요일 → 직전영업일=금(주말 건너뜀)
    (2026, 6, 16, 1, date(2026, 6, 15)),   # 화요일 → 월
    (2026, 6, 14, 1, date(2026, 6, 12)),   # 일요일 → 금
    (2026, 6, 15, 2, date(2026, 6, 11)),   # 월요일, 2영업일 전 → 목
    (2026, 6, 13, 1, date(2026, 6, 12)),   # ★토요일 실행 → 직전영업일=금(주말 실행 target 미커버)
    (2026, 6, 16, 0, date(2026, 6, 15)),   # ★days_back=0 → max(1,·) 클램프 → 화의 직전영업일=월
    (2026, 6, 16, -3, date(2026, 6, 15)),  # ★days_back 음수 → 1 로 클램프(방어적 입력)
])
def test_G004_previous_business_day(y, mo, d, db, expected):
    assert m.previous_business_day(datetime(y, mo, d, 8, 0, tzinfo=m.KST), db) == expected


def test_G004_posted_date_missing_is_unknown():
    """게시일 빈값 → unknown 버킷(제외 아님; split 정책으로 recall 처리)."""
    items = [{"id": "a", "title": "공고", "posted_date": "", "is_aggregator": False}]
    matched, unknown, excluded = m.partition_posted_dates(items, days_back=1,
                                                          now_dt=datetime(2026, 6, 16, 8, 0, tzinfo=m.KST))
    assert [i["id"] for i in unknown] == ["a"] and matched == [] and excluded == []


def test_G004_posted_date_unparseable_is_unknown():
    """파싱 불가('상시') 게시일도 unknown(누락 금지)."""
    items = [{"id": "b", "title": "공고", "posted_date": "상시", "is_aggregator": False}]
    _matched, unknown, _excluded = m.partition_posted_dates(items, days_back=1,
                                                            now_dt=datetime(2026, 6, 16, 8, 0, tzinfo=m.KST))
    assert [i["id"] for i in unknown] == ["b"]


def test_G004_outside_window_excluded():
    """수집 윈도 밖(직전영업일보다 과거·주말 아님) → 제외(평일 단일일 동작)."""
    items = [{"id": "old", "title": "공고", "posted_date": "2026-06-11", "is_aggregator": False}]  # 목(2영업일 전)
    matched, _u, excluded = m.partition_posted_dates(items, days_back=1,
                                                     now_dt=datetime(2026, 6, 16, 8, 0, tzinfo=m.KST))  # 화
    assert matched == [] and [i["id"] for i in excluded] == ["old"]


@pytest.mark.parametrize("item,expected", [
    ({"title": "수요기업 모집", "description": "신청접수 모집공고",
      "link": "https://www.k-startup.go.kr/x"}, "높음"),     # 신청키워드+enrich호스트
    ({"title": "참여기업 모집", "description": "신청접수 모집공고"}, "중간"),   # 신청키워드만
    ({"title": "공고", "description": "안내", "deadline": "2026-12-31"}, "중간"),  # 마감 살아있음
    ({"title": "정기 뉴스레터", "description": "소식 안내"}, "낮음"),         # 신호 없음
])
def test_G004_date_unknown_risk(item, expected):
    """날짜불명 공고의 오늘 누락 위험도(recall 신호 강도)."""
    assert m.assess_date_unknown_risk(item) == expected


# ══════════════════════════════════════════════════════════════════
# G005 접수기간 — is_imminent(기존 테스트 전무!) + '접수예정' 단일 upcoming 경로
#   (open/closed/range-upcoming/상시·수시·연중수시/unknown 은 test_deadline_fix / test_monitor 가 커버)
# ══════════════════════════════════════════════════════════════════
_NOW_DAY = datetime.now(m.KST).date()


def _iso(offset_days):
    return (_NOW_DAY + timedelta(days=offset_days)).isoformat()


@pytest.mark.parametrize("offset,expected", [
    (0, True),    # 오늘(0일) — 임박
    (3, True),    # 3일 뒤
    (7, True),    # 7일 뒤(경계 포함)
    (8, False),   # 8일 뒤(경계 밖)
    (-1, False),  # 어제(이미 지남)
    (60, False),  # 먼 미래
])
def test_G005_is_imminent_window(offset, expected):
    """마감임박 = 마감일이 오늘~+7일. 0일·7일 경계 포함, 8일·과거는 제외."""
    assert m.is_imminent(_iso(offset)) is expected


def test_G005_is_imminent_no_date_false():
    """날짜 토큰 없는 문자열(상시접수 등)은 임박 아님."""
    assert m.is_imminent("상시접수") is False
    assert m.is_imminent("") is False


def test_G005_is_imminent_dotted_format():
    """'YYYY.MM.DD' 형식도 '-' 정규화 후 인식."""
    assert m.is_imminent(_iso(2).replace("-", ".")) is True


# [수정완료 2026-06-23 round4] is_imminent 가 고정위치 'YYYY-MM-DD'(tok[4]·tok[7]='-', len>=10)만
# 인식해 한글·한자리·연도생략 표기를 통째로 놓치던 recall 갭을 monitor.py 에서 _parse_date_candidates
# 재사용으로 해소. 아래 두 테스트가 그 수정을 회귀 고정한다(한글표기는 기존 코드에서 항상 False였음).
def _kdate(offset_days):
    d = _NOW_DAY + timedelta(days=offset_days)
    return f"{d.year}년 {d.month}월 {d.day}일"


@pytest.mark.parametrize("offset,expected", [(0, True), (3, True), (7, True), (8, False), (60, False)])
def test_G005_is_imminent_korean_date_format_2026_06_23(offset, expected):
    """recall 갭 수정(round4): 한글 표기 'YYYY년 M월 D일' 마감도 임박(0~7일) 정확 인식.
    기존 is_imminent 는 '-' 정규화 후 고정위치 검사라 한글 표기를 split 해도 어떤 토큰도 매칭 못 해
    항상 False → 마감 7일 이내인 한글표기 공고가 '⚠️ 마감 임박' 알림에서 누락(고객이 마감 놓침).
    _parse_date_candidates 의 'YYYY년 M월 D일' 패턴(459행)을 재사용해 해소."""
    assert m.is_imminent(_kdate(offset)) is expected


def test_G005_is_imminent_no_pad_dotted_imminent_true_2026_06_23():
    """recall 갭 수정(round4): '2026.6.30'처럼 월/일을 0으로 채우지 않은 점 표기도 인식.
    기존엔 '-' 정규화 후 tok[7]=='-' 위치 검사가 한자리 월('2026-6-30'은 index7='3')에서 깨져 누락.
    연·월·일을 그대로(zero-pad 없이) 찍은 단일미래 마감이 임박 윈도(3일) 안이면 True."""
    d = _NOW_DAY + timedelta(days=3)
    assert m.is_imminent(f"{d.year}.{d.month}.{d.day}") is True


def test_G005_upcoming_via_single_future_with_jeopsu_yejeong():
    """'접수 예정' + 미래 단일날짜 → upcoming(단일날짜 전용 경로; range 경로는 test_deadline_fix 커버)."""
    it = {"id": "x", "title": "지원 공고", "description": "접수 예정 2026.08.01 부터", "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "upcoming"


def test_G005_single_future_without_yejeong_is_open():
    """대조: '접수예정' 표현 없는 미래 단일날짜는 open(모집중으로 봄, recall)."""
    it = {"id": "x", "title": "지원 공고", "description": "마감 2026.08.01 까지", "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "open"


@pytest.mark.parametrize("term", ["상시접수", "수시접수", "예산 소진 시까지", "예산소진 시까지",
                                  "예산 소진시까지", "상시모집", "연중수시"])
def test_G005_open_deadline_terms(term):
    """상시/수시/예산소진/상시모집/연중수시 → open(마감 없는 모집)."""
    it = {"id": "x", "title": f"{term} 공고", "description": term, "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "open"


# ── 라운드3 보강(2026-06-22): 접수기간 경계값(오늘마감/오늘시작/deadline필드 상시/과거~미래 range) ──
def test_G005_deadline_ends_today_is_open():
    """종료일==오늘 → open(off-by-one 으로 당일 누락 금지·recall 경계·2019행 end<today). TODAY=2026-06-18."""
    it = {"id": "x", "title": "지원 공고", "description": "신청기간 2026.06.01 ~ 2026.06.18",
          "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_G005_yejeong_starts_today_is_open():
    """'접수예정' + 시작일==오늘 → open(오늘 시작=접수중, upcoming 으로 빼면 누락·2048행 start>today 경계)."""
    it = {"id": "x", "title": "지원 공고", "description": "접수 예정 2026.06.18 부터",
          "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_G005_open_term_in_deadline_field():
    """상시 표현이 deadline 필드에만 있어도 open(_notice_text 가 deadline 포함 → 2008행 매칭, 누락 금지)."""
    it = {"id": "x", "title": "지원 공고", "description": "사업 안내", "author": "", "deadline": "상시접수"}
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_G005_range_past_to_future_is_open():
    """한 줄 범위 '과거~미래'(시작 과거·종료 미래) → open(2043행 min/max: 과거 시작 때문에 closed/upcoming 오판 금지)."""
    it = {"id": "x", "title": "지원 공고", "description": "2025.01.01 ~ 2026.12.31 까지",
          "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "open"


# ══════════════════════════════════════════════════════════════════
# G006 교차조합 — '하나라도 부적합→제외' / '전부 적합→포함' 통합 게이트
#   (전부적합 cross 통과·region/deadline 4그룹은 test_decision_matrix 가 커버 — 여기선 합성 경기·임계·
#    업력 그룹으로 '게이팅 축 1개 부적합→제외'를 명시. 특히 BUSINESS_YEARS 게이팅은 타 테스트 미커버.)
#   ★4-버킷 인지: sync 가 region 미상을 'region_unknown' 버킷으로 surface 하므로 _bucket 도 4버킷 검사.
# ══════════════════════════════════════════════════════════════════
# 업력 (3,7] 까지 갖춘 합성 경기 그룹 (G006 전용·production 불변)
GYNG = gyeonggi_group(business_years={"min_exclusive": 3, "max_inclusive": 7})


def _gyeonggi_full_pass():
    """경기 own + open + 업력 적격(전체) + 키워드(or_keywords=[] permissive) — 전부 적합 기준 공고."""
    return {"id": "x", "title": "경기도 제조기업 성장지원 신청접수",
            "description": "경기 소재 제조 중소기업 신청접수 지원금 500만원", "author": "기관",
            "deadline": "2026-12-31",
            "application_period": {"start": "2026-06-01", "end": "2026-12-31", "display": "2026-06-01 ~ 2026-12-31"},
            "posted_date": "2026-06-18", "is_aggregator": False, "business_age_text": "전체"}


def _bucket(item, group=GYNG):
    d = m.filter_for_group_with_diagnostics([item], group, TODAY)
    for b in ("included", "review", "region_unknown", "excluded"):
        if d[b]:
            return b
    return "none"


def test_G006_all_fields_eligible_included():
    """전부 적합 → included."""
    assert _bucket(_gyeonggi_full_pass()) == "included"


def test_G006_one_axis_bad_deadline_excluded():
    """단일축 부적합(마감됨) → 나머지 다 적합이어도 excluded."""
    it = _gyeonggi_full_pass()
    it["application_period"] = {"start": "2026-05-01", "end": "2026-06-10", "display": "~2026-06-10"}
    it["deadline"] = "2026-06-10"
    ev = m.evaluate_notice(it, GYNG, TODAY)
    assert _bucket(it) == "excluded" and "CLOSED_DEADLINE" in ev["exclude_reason_codes"]


def test_G006_one_axis_bad_business_years_excluded():
    """단일축 부적합(업력 범위 밖) → excluded. 업력 (3,7]: '3년미만'(N=3, N>3 거짓)은 not_eligible.
    ★BUSINESS_YEARS 게이팅 end-to-end 는 이 진리표에서만 커버(decision_matrix·region_unknown 미커버).
    (금액 축은 sync 정책으로 더 이상 게이팅 아님 → G002 함수 테스트로 대체.)"""
    it = _gyeonggi_full_pass()
    it["business_age_text"] = "3년미만"
    ev = m.evaluate_notice(it, GYNG, TODAY)
    assert _bucket(it) == "excluded" and "BUSINESS_YEARS_NOT_ELIGIBLE" in ev["exclude_reason_codes"]


def test_G006_one_axis_bad_region_excluded():
    """단일축 부적합(타지역 권역) → excluded.
    ★주의(recall-safe override 특성): own('경기') 신호가 본문에 하나라도 있으면 타지역 토큰이
    있어도 override 가 미발동(=통과)한다. 그래서 '순수 타지역'을 보려면 own 신호를 모두 제거해야 한다.
    (지역 '미상'은 제외가 아니라 region_unknown 버킷으로 surface — test_region_unknown_policy 커버.)"""
    it = _gyeonggi_full_pass()
    it["title"] = "부산권 제조기업 성장지원 신청접수"
    it["description"] = "제조 중소기업 신청접수 지원금 500만원"  # '경기 소재' own 신호 제거
    it["region_field"] = "전국"
    ev = m.evaluate_notice(it, GYNG, TODAY)
    assert _bucket(it) == "excluded" and "REGION_NOT_ELIGIBLE" in ev["exclude_reason_codes"]


# ── 라운드3 보강(2026-06-22): 통합게이트의 '잠복 축' — production 4그룹이 모두 permissive(키워드 OR만·
#    support_types=ALL·and/exclude 빈) 라 한 번도 통합 검증된 적 없는 게이트. 미래 그룹이 제약을 거는 순간
#    무방비가 되지 않도록 합성 그룹으로 축 1개씩 격리 검증. ★production groups.json 불변 · 픽스처일 뿐. ──
def _gate_group(**over):
    """경기 own + permissive 기반에 게이팅 축 하나만 켜서 통합 효과를 격리하는 합성 그룹."""
    g = {"id": "grp_gate_synth", "active": True,
         "applicant_region_city": "경기도", "applicant_region_label": "경기",
         "required_conditions": {"regions": ["경기"]},
         "support_types": ["지원금/바우처", "투자", "그외"], "or_keywords": []}
    g.update(over)
    return g


def test_G006_priority_keyword_survives_keyword_fail_as_review():
    """★recall 안전판: or_keywords 불일치라도 우선키워드(스마트공장)가 있으면 제외 않고 review 로 surface.
    (INDUSTRY_NOT_MATCHED 는 review 제외집합 2627-2631 에 없음 → priority 공고는 살아남는다.)"""
    grp = _gate_group(or_keywords=["반도체"])
    it = _gyeonggi_full_pass()
    it["title"] = "경기도 스마트공장 구축 지원사업 신청접수"
    it["description"] = "경기 소재 스마트공장 구축 신청접수"
    d = m.filter_for_group_with_diagnostics([it], grp, TODAY)
    assert d["review"], d
    assert "INDUSTRY_NOT_MATCHED" in d["review"][0]["exclude_reason_codes"]


def test_G006_support_types_gate_excludes_unmatched():
    """support_types=['투자']만 켠 그룹에서 지원금 성격 공고 → INDUSTRY_NOT_MATCHED(2586행 게이트, 잠복축)."""
    grp = _gate_group(support_types=["투자"])
    it = _gyeonggi_full_pass()
    it["title"] = "경기도 제조기업 수출바우처 지원금 신청접수"
    it["description"] = "경기 소재 수출바우처 지원금 신청접수"
    ev = m.evaluate_notice(it, grp, TODAY)
    assert "INDUSTRY_NOT_MATCHED" in ev["exclude_reason_codes"]


@pytest.mark.parametrize("kwline,matched", [
    ("경기도 베트남 수출 지원사업 신청접수", True),    # 수출+베트남 모두 → AND 통과
    ("경기도 수출 지원사업 신청접수", False),          # 수출만 → AND 미충족
])
def test_G006_and_keyword_groups_gate(kwline, matched):
    """and_keyword_groups=[['수출','베트남']] → 두 키워드 모두 있어야 통과(2581-2582 AND 분기, 잠복축)."""
    grp = _gate_group(and_keyword_groups=[["수출", "베트남"]])
    it = _gyeonggi_full_pass()
    it["title"] = kwline
    it["description"] = kwline
    ev = m.evaluate_notice(it, grp, TODAY)
    assert ("INDUSTRY_NOT_MATCHED" in ev["exclude_reason_codes"]) is (not matched)


def test_G006_group_exclude_keywords_not_grant():
    """그룹별 exclude_keywords 매칭 → NOT_GRANT_NOTICE(2572-2575, 상수 EXCLUSION_RULES 와 별개 경로)."""
    grp = _gate_group(exclude_keywords=["성료"])
    it = _gyeonggi_full_pass()
    it["title"] = "경기도 제조기업 성장지원 신청접수 성료 안내"
    ev = m.evaluate_notice(it, grp, TODAY)
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]


# ══════════════════════════════════════════════════════════════════
# ══ 라운드3 보강 (2026-06-23 sync a755641 점검) ══
#   a755641 sync = coverage_alert(수집 이상탐지) 신규 — 5필드 매칭 함수는 한 줄도 안 바뀜.
#   따라서 기존 진리표 계약은 그대로 유효(459 passed·1 xfailed 재확인). 이번엔 6필드 함수
#   정밀 재trace(읽기전용 서브에이전트 6 + 코드 직접 확인)로 '여태 어떤 테스트도 단언 안 한'
#   분기·경계 셀을 추가한다. 모든 '현재 동작'은 추측이 아니라 코드 trace + pytest 실측.
# ══════════════════════════════════════════════════════════════════

# ── G001 지역 (신규: 명시적 배제구문 / region_field 드롭다운 타지역 / 복수광역 제목태그 / short-form 변형) ──
@pytest.mark.parametrize("phrase", ["수도권 제외", "인천 제외", "비수도권 기업 대상"])
def test_G001_exclude_phrase_not_eligible_2026_06_23(phrase):
    """REGION_EXCLUDE_PHRASES(343행) 매칭 → 최우선 not_eligible(2324행). '수도권/비수도권' 명시는
    인천(=수도권)을 명백히 배제하므로 recall-safe(정당 신청 가능 공고를 떨어뜨리는 게 아님)."""
    assert m.classify_region({"title": f"{phrase} 공고", "description": "중소기업 지원"}
                             )["region_status"] == "not_eligible"


def test_G001_region_field_other_metro_not_eligible_2026_06_23():
    """★미커버 분기(2362-2372): 제목·본문 지역신호 0인데 region_field 드롭다운이 타광역('경기도')만 →
    explicit_regions=['경기'], 인천無·전국無 → not_eligible. 인천 기업은 경기 전용 공고에 신청 불가라
    recall-safe 배제(누락 아님). (region_field='전국'은 eligible — test_G001_region_field_only_nationwide 가 커버.)"""
    item = {"title": "중소기업 지원사업 신청접수", "description": "중소기업 대상 신청", "region_field": "경기도"}
    assert m.classify_region(item)["region_status"] == "not_eligible"


def test_G001_multi_metro_title_tag_includes_incheon_eligible_2026_06_23():
    """★recall(2334-2342): 제목 복수광역 태그 '[서울ㆍ인천ㆍ경기]'처럼 인천이 포함되면 eligible 확정.
    (기존은 단일 '[인천]'만 커버 — 복수광역 태그에서 인천 포함 분기는 미커버였음.)"""
    rs = m.classify_region({"title": "[서울ㆍ인천ㆍ경기] 수도권 중소기업 수출지원",
                            "description": "수도권 소재 중소기업"})["region_status"]
    assert rs == "eligible"


def test_G001_incheon_jiyeok_nospace_variant_eligible_2026_06_23():
    """short-form 변형 '인천지역'(붙여쓰기)도 own 신호 → eligible(2396행 4변형 중 미커버였던 nospace)."""
    assert m.classify_region({"title": "인천지역 제조기업 지원", "description": "인천지역 중소기업 대상"}
                             )["region_status"] == "eligible"


# ── G002 지원금 (신규: 퍼센트=금액아님 / 조·천억 단위 추출) ──
def test_G002_percent_only_is_none_2026_06_23():
    """'최대 80%'처럼 퍼센트만 있고 단위금액 없음 → None(2160-2171 어느 단위패턴도 매칭 안 됨).
    None→unknown→비제외라 recall-safe(퍼센트 공고를 금액미달로 잘못 떨어뜨리지 않음)."""
    assert m.extract_support_amount("지원금 최대 80% 보조") is None


@pytest.mark.parametrize("text,ideal", [
    ("총 1조원 규모 지원", 1_000_000_000_000),   # 조 단위
    ("5천억원 출연", 500_000_000_000),            # 천억 단위
])
def test_G002_jo_cheoneok_unit_extracted_2026_06_23(text, ideal):
    """조·천억 단위 추출 — '조원'/'천억원' 표기를 정확 금액으로 추출(2160행 신규 루프).
    표시 금액 정확도↑ + 금액 게이트가 unknown 대신 eligible 로 확정(대규모 공고도 recall-safe).
    '제3조'·'3조2교대' 등 비금액 '조'는 '원' 접미 요구로 오추출 차단."""
    assert m.extract_support_amount(text) == ideal


# ── G003 지원사업성격 (신규: 복합분야 합집합 / R&D 무공백 경계 / 교집합True / 중복라벨 불가) ──
def test_G003_field_composite_multi_key_union_2026_06_23():
    """support_field 한 칸에 매핑키 2개('기술개발'+'컨설팅') → 두 버킷 합집합(1952-1954 substring 루프).
    (기존 test_G003_field_substring_partial_match 는 단일키 'AI기술개발'만 — 복합 합집합은 미커버.)"""
    types = m.classify_support_type({"title": "공고", "support_field": "기술개발 및 컨설팅 지원"})
    assert "지원금/바우처" in types and "컨설팅·교육·상담" in types


def test_G003_body_rnd_nospace_boundary_2026_06_23():
    """본문 'R&D사업'(공백 없이 한글 인접) → 지원금/바우처. ASCII 단어경계 regex(1993행)는 뒤가
    비ASCII('사')면 경계 성립 → 매칭. (기존은 'r&d 지원사업' 공백 케이스만 커버.)"""
    assert "지원금/바우처" in m.classify_support_type({"title": "R&D사업 공고"})


def test_G003_support_match_intersection_true_2026_06_23():
    """복수라벨(투자+컨설팅) 공고가 ['투자']만 켠 그룹에서 교집합 1개라도 있으면 True(2475-2476).
    (기존 test_G003_support_match_partial_intersection_false 의 대칭쌍 — 교집합 있을 때 통과=recall.)"""
    assert m.support_match({"title": "투자유치 및 컨설팅 지원", "description": "엔젤투자 멘토링"}, ["투자"]) is True


def test_G003_no_duplicate_labels_2026_06_23():
    """같은 버킷 키워드 5개(멘토링·코칭·교육·세미나·설명회) 동시 → 라벨은 정확히 1개(중복 없음).
    classify_support_type(1946행)은 RULES 버킷명 단위 list-comp 라 한 버킷이 두 번 들어갈 수 없다."""
    assert m.classify_support_type({"title": "멘토링 코칭 교육 세미나 설명회 과정"}) == ["컨설팅·교육·상담"]


# ── G004 게시일 (신규: 직전영업일·주말 matched 양성경로 / 점형식=unknown / 미래·당일=현재 excluded 관측) ──
@pytest.mark.parametrize("now_y,now_mo,now_d,posted,why", [
    (2026, 6, 16, "2026-06-15", "화 실행 → 직전영업일=월(정확일치)"),
    (2026, 6, 15, "2026-06-13", "월 실행 → 직전영업일=금, 그 직후 토요일 게시도 윈도 포함(주말 recall)"),
    (2026, 6, 15, "2026-06-14", "월 실행 → 금 직후 일요일 게시도 윈도 포함(주말 recall)"),
])
def test_G004_partition_matched_positive_2026_06_23(now_y, now_mo, now_d, posted, why):
    """★미커버 양성경로: 기존 G004 partition 테스트는 unknown·excluded만 봤고 'matched' 양성 케이스가
    함수레벨에 없었다. 직전영업일 정확일치 + 직전영업일 직후 주말(토/일) 게시 모두 matched(1864-1867·recall)."""
    items = [{"id": "p", "title": "공고", "posted_date": posted, "is_aggregator": False}]
    matched, _u, excluded = m.partition_posted_dates(
        items, days_back=1, now_dt=datetime(now_y, now_mo, now_d, 8, 0, tzinfo=m.KST))
    assert [i["id"] for i in matched] == ["p"] and excluded == [], why


def test_G004_dotted_posted_date_is_unknown_2026_06_23():
    """게시일이 점형식 '2026.06.15' → strptime('%Y-%m-%d') 파싱실패 → unknown(1875-1877).
    unknown 은 제외 아님(split 정책으로 surface) → 포맷 흔들려도 누락 안 됨(recall-safe)."""
    items = [{"id": "dot", "title": "공고", "posted_date": "2026.06.15", "is_aggregator": False}]
    _m, unknown, excluded = m.partition_posted_dates(
        items, days_back=1, now_dt=datetime(2026, 6, 16, 8, 0, tzinfo=m.KST))
    assert [i["id"] for i in unknown] == ["dot"] and excluded == []


@pytest.mark.parametrize("posted,label", [
    ("2026-06-18", "미래 게시일(now=6/16 기준 이틀 뒤)"),
    ("2026-06-16", "당일 게시일(==today)"),
])
def test_G004_future_and_sameday_currently_excluded_OBSERVED_2026_06_23(posted, label):
    """⚠️ 관측앵커(사람 판단 필요 · 올바름을 단언하지 않음): 미래·당일 게시일은 현재 _in_window(1863-1867)의
    'target < d < today' 엄격부등호에 안 걸려 조용히 excluded 된다. recall 관점에선 '마감이 당일~내일인
    당일등록 공고'·'타임존/파싱오차로 +1일된 공고'를 영구 누락할 위험 → 단정 대신 현재 동작만 고정한다.
    (이 테스트가 깨지면=동작이 바뀌면 사람이 recall 개선 의도인지 확인. NIGHT_REPORT '사람 판단 필요' 참조.)"""
    items = [{"id": "x", "title": "공고", "posted_date": posted, "is_aggregator": False}]
    matched, unknown, excluded = m.partition_posted_dates(
        items, days_back=1, now_dt=datetime(2026, 6, 16, 8, 0, tzinfo=m.KST))
    assert [i["id"] for i in excluded] == ["x"] and matched == [] and unknown == [], label


# ── G005 접수기간 (신규: deadline필드 '날짜' 폴백 / is_imminent 범위표기 any-토큰) ──
def test_G005_deadline_field_date_fallback_open_2026_06_23():
    """본문엔 날짜 0, deadline 필드에만 실제 '날짜'(상시용어 아님) → 폴백 파싱(2034-2037) → 미래면 open.
    (기존 test_G005_open_term_in_deadline_field 는 deadline='상시접수' 용어경로 — 실날짜 폴백은 미커버.)"""
    it = {"id": "x", "title": "지원 공고", "description": "사업 안내", "author": "", "deadline": "2026-12-31"}
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_G005_is_imminent_range_first_token_imminent_true_2026_06_23():
    """범위표기 '임박일 ~ 먼미래' → True. is_imminent(429행)은 split 후 '어떤 토큰이든' 윈도(0~7) 안이면 True.
    (기존 is_imminent 테스트는 단일 날짜만 — '~' 범위에서 토큰 분해 동작은 미커버.)"""
    assert m.is_imminent(f"{_iso(3)} ~ {_iso(60)}") is True


def test_G005_is_imminent_range_all_far_false_2026_06_23():
    """대조: 범위의 모든 토큰이 윈도 밖(둘 다 먼 미래) → False(어떤 토큰도 0~7 아님)."""
    assert m.is_imminent(f"{_iso(40)} ~ {_iso(80)}") is False


# ── G006 업력(business_years) 함수레벨 진리표 (신규: 멀티셀렉트 합집합 recall / 경계 / 예비창업자) ──
#   GYNG = 경기 합성·업력(3,7] (위 G006 섹션에서 정의). business_years_status 는 business_age_text 있으면
#   parse_kstartup_business_buckets 경로(2136-2138) — 이 경로는 lo(min_exclusive=3)만 보고 'N>lo' 판정.
def test_G006_business_years_multiselect_union_recall_2026_06_23():
    """★recall 핵심(2107-2109 명시 버그수정 고정): K-Startup '창업업력' 멀티셀렉트 '1년미만,5년미만,10년미만'은
    합집합='가장 큰 N(10)까지 허용' → any(N>3) 참 → eligible. (예전엔 max=1 로 접어 정당공고 대량누락하던
    recall 버그 — 이 동작을 회귀고정.)"""
    assert m.business_years_status({"business_age_text": "1년미만, 5년미만, 10년미만"}, GYNG) == "eligible"


def test_G006_business_years_bucket_just_over_lo_eligible_2026_06_23():
    """업력버킷 '5년미만'(N=5 > lo=3) → eligible. (기존은 '전체'·'3년미만'만 — lo 직상 경계는 미커버.)"""
    assert m.business_years_status({"business_age_text": "5년미만"}, GYNG) == "eligible"


def test_G006_business_years_bucket_at_lo_not_eligible_2026_06_23():
    """업력버킷 '1년미만'(N=1, 1>3 거짓) → not_eligible. lo 이하 단일버킷 배제(precision, recall-safe:
    업력 (3,7] 신청자는 1년미만 전용 공고에 신청 불가)."""
    assert m.business_years_status({"business_age_text": "1년미만"}, GYNG) == "not_eligible"


def test_G006_business_years_preliminary_founder_only_not_eligible_2026_06_23():
    """'예비창업자'만(연수버킷 없음) → not_eligible(2124-2125). 업력 보유 기업 전용 그룹엔 부적격(recall-safe)."""
    assert m.business_years_status({"business_age_text": "예비창업자"}, GYNG) == "not_eligible"


# ══════════════════════════════════════════════════════════════════
# ══ 라운드3 재보강 (2026-06-23 sync 1c2f9c4·a755641 점검 — 6필드 적대적 재검증) ══
#   1c2f9c4 = 진리표/테스트 갱신본의 origin 유입, a755641 = coverage_alert(수집 이상탐지) 신규.
#   둘 다 5필드 매칭 함수는 '한 줄도' 안 바꿈(git diff·hunk 헤더로 확인 — coverage_alert 는 파일 끝
#   3570행대, 5필드 함수는 1944~2413행대로 물리적 분리). 이어서 6개 독립 read-only 분석가가
#   기존 483 단언 + TRUTH_TABLE '현재 동작' 주장 vs 실제 코드를 적대 교차검증 → 불일치 0건 재확인.
#   아래는 그 과정에서 '여태 어떤 테스트도 단언 안 한' 분기/경계를 코드 trace + pytest 실측으로 고정.
# ══════════════════════════════════════════════════════════════════

# ── G001: own지역 + 타지역 혼재 신호 — own 인식의 '조사 부착' 비대칭 갭 (★신규 발견, recall) ──
def test_G001_own_nospace_plus_other_region_eligible_2026_06_23():
    """대조(현재 통과·회귀고정): own(인천)이 공백으로 분리돼 '인천 부산 소재'면 _detect_target_regions 의
    '인천+공백' hint(558행)가 인천을 잡아 explicit_regions=['인천','부산'] → 2365-2366 other_only 분기 미발동
    → 2400행 '인천' in text → eligible. own 신호가 hint 에 인식되면 타지역 혼재여도 통과(recall 보존)."""
    assert m.classify_region({"title": "인천 부산 공동 수출지원사업",
                              "description": "인천 부산 소재 중소기업 대상"})["region_status"] == "eligible"


def test_G001_own_with_josa_plus_other_region_should_be_eligible_2026_06_23():
    """recall 갭 수정됨(round1, 2026-06-23): own 광역명(인천)이 조사 '과/와'로 붙어('인천과') 공백이 없고
    타지역명(부산)만 '…소재'로 나와도 eligible. 기존엔 _detect_target_regions hint(558행)가 '인천+공백'을
    요구해 '인천과'를 놓쳐 explicit_regions=['부산']만 남고 other_only 분기가 not_eligible 로 배제했다.
    수정: classify_region other_only 분기에 own substring('인천' in text) 재확인을 추가해
    _other_region_block own_present(substring) 기준과 정렬 → 표기위치 비대칭 누락 해소.
    대조쌍 test_G001_own_nospace_plus_other_region_eligible(공백형=eligible)과 동일 판정으로 수렴."""
    assert m.classify_region({"title": "인천과 부산 공동 수출지원사업",
                              "description": "인천과 부산 소재 중소기업 대상"})["region_status"] == "eligible"


# ── G002: '만' + '원' 글자 없이 단독 표기도 금액 추출 (recall-safe) ──
def test_G002_man_without_won_suffix_extracted_2026_06_23():
    """'300만'(원 글자 없이, 뒤가 비차단어 '지원') → 3,000,000. 2168행 패턴의 '원?' 은 optional 이고
    음수전방탐색 (?![명개건회사세팀]) 에 '지'는 안 걸려 추출된다. 실공고 '최대 300만 지원' 빈출 표기.
    (기존 G002 만원 케이스는 전부 '…만원' 풀표기만 — '원' 생략 변형은 미커버였음.)"""
    assert m.extract_support_amount("최대 300만 지원") == 3_000_000


# ── G003: support_field 무구분자 복합키 / body RULES 키워드(사업화자금) ──
def test_G003_field_concat_no_separator_union_2026_06_23():
    """support_field 가 구분자 없이 두 매핑키를 연결('기술개발교육') → 1952-1954 substring 루프가
    '기술개발'·'교육' 모두 잡아 지원금/바우처 + 컨설팅 합집합. (기존 복합분야 테스트는 ' 및 ' 구분자
    있는 'A 및 B' 만 커버 — 구분자 0 연결형은 미커버였음. 그외 자격도 함께 보존되나 두 버킷만 단언.)"""
    types = m.classify_support_type({"title": "공고", "support_field": "기술개발교육"})
    assert "지원금/바우처" in types and "컨설팅·교육·상담" in types


def test_G003_body_keyword_saeopwha_jagum_2026_06_23():
    """본문 '사업화자금'(SUPPORT_TYPE_RULES 지원금/바우처 키워드, 114행, 한글 substring 경로) →
    지원금/바우처. KSTARTUP support_field '사업화' 매핑(권위경로)과 별개인 '본문 키워드' 경로를 직접
    커버 — 기존 본문 G003 은 r&d·보조만 단언했고 '사업화자금' 본문매칭은 미커버였음."""
    assert "지원금/바우처" in m.classify_support_type({"title": "사업화자금 지원사업 공고"})


# ── G005: 라벨 경로 단일 미래날짜 = upcoming (본문폴백 단일미래 open 과 비대칭 · 관측앵커) ──
def test_G005_label_single_future_is_upcoming_OBSERVED_2026_06_23():
    """⚠️ 관측앵커(사람 판단 필요 · 올바름 단언 안 함): '신청기간:' 라벨 + 단일 미래날짜는
    extract_application_period 가 start==end==미래로 만들어(515행) classify_deadline_status 2021행
    start>today 로 upcoming 을 준다. 그런데 동일한 단일 미래날짜가 '라벨 없이 본문'에만 오면
    (test_G005_single_future_without_yejeong_is_open) open 이다 → 같은 날짜가 표기 위치(라벨 vs 본문)에
    따라 upcoming/open 으로 갈리는 비대칭. 그 단일 날짜가 사실은 '마감일'인 공고라면 upcoming 버킷이
    검토/제외로 처리될 때 누락 위험이 있어, 올바름을 단정하지 않고 현재 동작만 고정한다(이 테스트가
    깨지면=동작이 바뀌면 사람이 recall 개선 의도인지 확인. _tmp_trace_g005.py·NIGHT_REPORT 참조)."""
    it = {"id": "x", "title": "지원 공고", "description": "신청기간: 2026.12.31",
          "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "upcoming"


# ── G006: 다중 축 동시 부적합 → excluded + 두 제외코드 모두 적립 ──
def test_G006_multi_axis_both_bad_excluded_both_codes_2026_06_23():
    """두 게이팅 축(지역=부산권 + 업력=3년미만((3,7] 밖))이 '동시에' 부적합 → excluded 이고
    REGION_NOT_ELIGIBLE 와 BUSINESS_YEARS_NOT_ELIGIBLE 가 둘 다 적립된다(한 축이 early-return 으로
    다른 축의 코드 적립을 가리지 않음). 단일축 부적합만 보던 G006-2~4 의 '다중축 동시' 확장 —
    여러 사유가 겹쳐도 사용자에게 전부 surface 되는지 함수레벨로 처음 고정."""
    it = _gyeonggi_full_pass()
    it["title"] = "부산권 제조기업 성장지원 신청접수"
    it["description"] = "제조 중소기업 신청접수 지원금 500만원"  # '경기 소재' own 신호 제거
    it["region_field"] = "전국"
    it["business_age_text"] = "3년미만"
    ev = m.evaluate_notice(it, GYNG, TODAY)
    assert _bucket(it) == "excluded"
    assert "REGION_NOT_ELIGIBLE" in ev["exclude_reason_codes"]
    assert "BUSINESS_YEARS_NOT_ELIGIBLE" in ev["exclude_reason_codes"]


# ══════════════════════════════════════════════════════════════════
# ══ 라운드5 (2026-06-23) — '수도권' 묶음신호 recall 갭 (★신규 발견) ══
#   배경: 한국 정부공고는 대상지역을 개별 광역(인천/서울/경기) 대신 '수도권' 한 단어로
#   적는 경우가 매우 흔하다. 수도권 = 서울·인천·경기. 활성 그룹은 전부 수도권 family
#   (grp_default/grp_bnco=인천, grp_ai_saas/grp_prestartup_ai=서울)이므로 '수도권 소재
#   기업' 공고는 전 그룹이 신청 가능해야 한다. 그런데 KNOWN_REGIONS(134행)에 '수도권'이
#   들어 있어 classify_region 최종 폴백(2418행)·classify_region_for_group 폴백(2322행)이
#   '수도권'을 '타지역'으로 오인해 not_eligible 로 떨어뜨렸다 → 정당 공고 누락(recall 손실).
#   ※ '수도권 제외/소재기업 제외/신청불가', '비수도권 …'은 REGION_EXCLUDE_PHRASES(343행)·
#     '비수도권' 가드로 그대로 배제 유지(아래 가드 테스트로 고정).
# ══════════════════════════════════════════════════════════════════
def test_G001_incheon_metro_capital_area_eligible_round5():
    """recall 갭 수정: 인천 그룹은 '수도권 소재 중소기업' 공고에 eligible(인천 ⊂ 수도권).
    기존엔 '수도권'이 KNOWN_REGIONS 라 2418행 폴백이 not_eligible 로 누락시켰다."""
    assert m.classify_region(
        {"title": "수도권 중소기업 수출지원사업", "description": "수도권 소재 중소기업 대상"}
    )["region_status"] == "eligible"


def test_G001_incheon_metro_capital_area_title_tag_eligible_round5():
    """제목 '[수도권]' 태그도 own 신호 → eligible. (_title_region_tags 는 수도권을 광역약칭으로
    잡지 않아 tags=[] → 본문 폴백 경로로 흐르므로 본문 '수도권' 인식 분기에서 처리.)"""
    assert m.classify_region(
        {"title": "[수도권] 제조기업 수출바우처"}
    )["region_status"] == "eligible"


def test_G001_seoul_group_metro_capital_area_eligible_round5():
    """서울 그룹(grp_ai_saas, extra 없음)도 '수도권 소재 기업' 공고에 eligible(서울 ⊂ 수도권).
    grp_prestartup_ai 는 extra_eligible_regions 에 '수도권'이 있어 이미 통과했지만, extra 없는
    순수 서울 그룹은 2322행 폴백에서 not_eligible 로 누락됐다 → 수도권 family 공통 보정."""
    assert region_status(
        {"title": "수도권 소재 AI 스타트업 지원", "description": "수도권 중소기업"},
        "grp_ai_saas") == "eligible"


def test_G001_incheon_non_capital_area_still_excluded_round5():
    """회귀 가드: '비수도권 소재 기업'은 인천 배제 신호이므로 여전히 not_eligible.
    ('수도권'이 '비수도권'의 substring 이라도 '비수도권' 가드로 eligible 오판을 막는다.)"""
    assert m.classify_region(
        {"title": "비수도권 소재 기업 지원", "description": "비수도권 중소기업 대상"}
    )["region_status"] == "not_eligible"


# ══════════════════════════════════════════════════════════════════
# ══ 라운드6 (2026-06-23) — 구조화 region_field own지역 단독 recall 갭 (★신규 발견) ══
#   배경: K-Startup 등 상세페이지는 '지역' 드롭다운을 region_field 로 거둔다(143행).
#   제목·본문엔 지역어가 없고 region_field 만 'own 광역'(인천/서울)인 공고가 흔하다
#   (예: 제목 "2026년 ○○ 지원사업" + 지역="인천"). 그런데 own지역 긍정 판정 분기는
#   _notice_text(=title+desc+author+deadline, region_field 제외)만 보고, 타지역 배제는
#   raw_text(region_field 포함)·explicit_regions(region_field 포함)를 본다 → 비대칭.
#   그 결과 region_field='인천' 단독이면 classify_region 이 unknown→region_match False 로
#   '인천 전용 공고'를 인천 고객에게 누락(recall 손실). 대조로 region_field='부산'은 이미
#   not_eligible(타지역은 region_field 반영) — own 만 반영 안 되는 순수 recall 갭이다.
#   수정: own지역 긍정 분기가 explicit_regions(region_field 포함)의 own 신호도 인정하도록
#   classify_region·classify_region_for_group 을 보정(타지역 배제 경로는 불변).
# ══════════════════════════════════════════════════════════════════
def test_G001_incheon_region_field_only_eligible_round6():
    """recall 갭 수정: 제목·본문 지역어 없이 region_field='인천'(K-Startup 지역 드롭다운)만
    있어도 eligible. 기존엔 own지역 분기가 region_field 를 안 봐 unknown→누락이었다."""
    assert m.classify_region(
        {"title": "2026년 중소기업 수출바우처 지원사업",
         "description": "수출 지원 중소기업 모집", "region_field": "인천"}
    )["region_status"] == "eligible"


def test_G001_incheon_region_field_fullname_only_eligible_round6():
    """region_field 가 광역 풀네임 '인천광역시'여도 own 신호로 인정 → eligible."""
    assert m.classify_region(
        {"title": "2026년 제조혁신 바우처 지원사업",
         "description": "중소기업 모집", "region_field": "인천광역시"}
    )["region_status"] == "eligible"


# ══════════════════════════════════════════════════════════════════
# ══ 라운드8 (2026-06-23) — 제목 '연속 분리 대괄호' own광역 누락 recall 갭 (★신규) ══
#   배경: 한국 정부공고 제목은 광역을 한 대괄호에 'ㆍ'로 묶기도([서울ㆍ인천ㆍ경기])
#   하지만, 별도 대괄호로 잇따라 표기하는 형태([서울][인천] …)도 흔하다(공동·권역
#   사업·상담회). 그런데 _title_region_tags(2221행)의 _TITLE_TAG_RE 는 제목 맨 앞
#   '첫 번째' 대괄호만 읽어, own 광역이 둘째 이후 대괄호에 있으면 놓친다. 그 결과
#   classify_region / classify_region_for_group 의 태그 분기가 첫 태그만 보고
#   '타지역 한정'으로 오판 → own 고객(인천/서울 등)에게 정당 공고를 누락(recall 손실).
#   대조: 같은 의미의 단일 대괄호 'ㆍ' 묶음([서울ㆍ인천])은 이미 eligible(라운드3·라인667).
#   수정: _title_region_tags 가 맨 앞에 잇따른 대괄호를 모두 스캔하도록 일반화 →
#   표기형태(ㆍ묶음 vs 분리 대괄호)에 따른 비대칭 누락 해소. 'ㆍ묶음'과 동일 판정 수렴.
# ══════════════════════════════════════════════════════════════════
def test_G001_split_bracket_tags_includes_incheon_eligible_round8():
    """recall 갭 수정: 제목 '[서울][인천] …'처럼 own(인천)이 둘째 대괄호에 있어도 eligible.
    기존엔 첫 대괄호 '[서울]'만 읽어 '인천' 누락 → not_eligible 로 정당 공고를 떨어뜨렸다."""
    assert m.classify_region(
        {"title": "[서울][인천] 수도권 공동 수출상담회",
         "description": "수도권 소재 중소기업 대상"})["region_status"] == "eligible"


def test_G001_split_bracket_tags_incheon_second_with_doctype_eligible_round8():
    """문서종류 태그가 앞에 와도('[모집공고][인천] …') 둘째 대괄호의 own(인천)을 잡아 eligible."""
    assert m.classify_region(
        {"title": "[모집공고][인천] 2026년 수출바우처 지원"})["region_status"] == "eligible"


def test_G001_split_bracket_tags_other_only_still_not_eligible_round8():
    """precision 가드: '[서울][부산]'처럼 둘 다 타지역(인천 미포함)이면 여전히 not_eligible.
    (연속 대괄호 전체 스캔이 own 미포함 타지역 한정을 풀어버리지 않음을 회귀 고정.)"""
    assert m.classify_region(
        {"title": "[서울][부산] 영남권 제조기업 지원",
         "description": "제조 중소기업 대상"})["region_status"] == "not_eligible"


def test_G001_split_bracket_tags_for_group_own_second_eligible_round8():
    """for_group(서울 그룹)도 동일: '[부산][서울] …'의 둘째 대괄호 own(서울)을 잡아 eligible.
    기존엔 첫 태그 '[부산]'만 봐 not_eligible 로 누락했다. (제목에 '전국' 없음 → 순수 태그스캔 경로 검증.)"""
    rs = m.classify_region_for_group(
        {"title": "[부산][서울] 청년 스타트업 수출지원"},
        m._normalize_group(G["grp_prestartup_ai"]))["region_status"]
    assert rs == "eligible"


def test_G001_split_bracket_other_tags_with_explicit_nationwide_eligible_round8():
    """recall 갭(잔여 엣지) 수정: 첫 대괄호가 비지역('[모집공고]')이고 둘째가 타지역('[부산]')이라도
    사람이 제목/설명에 '전국'을 명시하면 태그 차단을 면제해 eligible. _other_region_block 의
    explicit_nationwide 면제(2252행)와 태그 분기를 정합화 — 명시적 전국 공고 누락 금지(누락 제로)."""
    assert m.classify_region(
        {"title": "[모집공고][부산] 청년창업 지원사업 (전국 모집)"})["region_status"] == "eligible"
    rs = m.classify_region_for_group(
        {"title": "[공고][부산] 전국 제조기업 수출바우처"},
        m._normalize_group(G["grp_prestartup_ai"]))["region_status"]
    assert rs == "eligible"


def test_G001_region_field_other_region_still_not_eligible_round6():
    """회귀 가드: region_field='부산'(타지역) 단독은 여전히 not_eligible(누락 아님).
    own지역 보정이 타지역 배제까지 풀어버리지 않는지 고정."""
    assert m.classify_region(
        {"title": "2026년 중소기업 수출 지원사업",
         "description": "중소기업 대상 신청", "region_field": "부산"}
    )["region_status"] == "not_eligible"


def test_G001_seoul_group_region_field_only_eligible_round6():
    """recall 갭 수정(for_group 동형): 서울 그룹도 region_field='서울' 단독이면 eligible.
    classify_region_for_group 의 region_hit 가 region_field own 신호를 인정하도록 보정."""
    assert region_status(
        {"title": "2026년 AI 솔루션 지원사업",
         "description": "AI 스타트업 모집", "region_field": "서울"},
        "grp_ai_saas") == "eligible"


def test_G001_seoul_group_region_field_other_region_not_eligible_round6():
    """회귀 가드: 서울 그룹에 region_field='부산'(타지역) 단독은 eligible 로 오판되지 않는다."""
    assert region_status(
        {"title": "2026년 제조기업 지원사업",
         "description": "제조 중소기업 모집", "region_field": "부산"},
        "grp_ai_saas") != "eligible"


# ══════════════════════════════════════════════════════════════════
# ══ 라운드7 (2026-06-23) — '마감 없는 모집' open-term 누락 recall 갭 (★신규 발견·수정) ══
#   배경: classify_deadline_status(2009행)는 OPEN_DEADLINE_TERMS 의 '마감 없는 모집' 용어를
#   날짜 로직보다 먼저 검사해 open 을 반환한다. 그런데 한국 공고에 매우 흔한
#   '선착순', '연중상시', '(예산/재원/물량) 소진 시 마감' 표현이 목록에 빠져 있었다.
#   이런 공고는 보통 과거 시작일('접수 2026.03.01부터 …')을 함께 적는데, open-term 을
#   놓치면 날짜 로직(2044-2046행)이 과거 시작일 하나만 보고 closed 로 판정 → 게이트가 제외 →
#   아직 열려있는(선착순/소진 시까지) 공고를 고객이 누락(recall 손실).
#   수정: OPEN_DEADLINE_TERMS 에 '선착순', '연중상시', 그리고 접두어·공백 무관하게
#   '소진 시'/'소진시'(예산·재원·물량·기금 소진 공통)를 추가. '소진으로 종료'(과거형 마감)는
#   '소진 시'·'소진시' 어디에도 안 걸려 closed 유지 → precision 회귀 가드(아래 테스트로 고정).
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("phrase", [
    "선착순 마감",          # 선착순 모집(소진까지 열림) — 마감일 없는 모집
    "연중상시 모집",        # 연중상시(기존 '연중수시'의 짝)
    "재원 소진 시 마감",    # '소진 시'(예산 아닌 재원도) — 공백 표기
    "물량 소진시 종료",     # '소진시'(공백 없는 표기)
    "예산 소진 시 마감",    # '예산 소진' 의 '마감' 변형(기존엔 '…까지'만 등록)
])
def test_G005_open_until_full_terms_round7(phrase):
    """recall 갭 수정(round7): 과거 시작일이 함께 적힌 '마감 없는 모집' 공고를 open 으로 인식.
    기존엔 OPEN_DEADLINE_TERMS 미등록 → 날짜 로직이 과거 시작일(03.01)만 보고 closed 오판 → 누락."""
    it = {"id": "x", "title": "청년창업 지원사업",
          "description": f"접수기간 2026.03.01 부터 {phrase}", "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_G005_budget_exhausted_past_tense_still_closed_round7():
    """회귀 가드(precision): '예산 소진으로 조기 마감'(과거형 종료)은 여전히 closed.
    신규 open-term '소진 시'/'소진시'는 '소진으로'에 안 걸려, 이미 마감된 공고를 open 으로 되살리지 않는다."""
    it = {"id": "x", "title": "지원 공고",
          "description": "접수기간 2026.03.01 ~ 2026.05.31 (예산 소진으로 조기 마감)",
          "author": "", "deadline": ""}
    assert m.classify_deadline_status(it, TODAY) == "closed"

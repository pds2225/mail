"""[제목 앵커] 비공고 정적 페이지 제외 회귀 테스트 (2026-07-20).

배경: 사용자 O/X 피드백에서 '사전정보공표'(기관 정보공개 정적 페이지)가 공고로
발송돼 ❌를 받았다. monitor.non_notice_reason() 이 제목 완전일치·링크 스킴만 보고
그런 정적 페이지를 걸러 NOT_GRANT_NOTICE 를 붙인다.

★이 파일의 절반 이상은 'precision 기능'이 아니라 'recall 가드'다.
   이 repo 평생 원칙 = 누락 제로(recall) > 정확도(precision).
   따라서 아래를 회귀로 못박는다:
     - 공고성 토큰(모집·공고·신청·접수·참가·선정·공모·지원사업)이 제목에 있으면 절대 안 막힌다.
     - 본문(description)에만 해당 단어가 있으면 절대 안 막힌다(제목만 본다).
     - 부분포함으로는 절대 안 막힌다(제목 완전일치만).
     - 진짜 공고 반례가 있는 문자열('정보공개'·'개인정보처리방침'·'지원사업공고')은 목록에 없다.
     - 환경변수 MONITOR_NO_NONNOTICE_FILTER=1 로 즉시 무력화된다.
"""
import json
import os
import sys
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

G = {g["id"]: g for g in json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))}


def notice(title, description="", link="https://example.go.kr/notice/view.do?id=1", **kw):
    """평가용 공고 1건. link 기본값은 정상 상세페이지(링크 룰에 안 걸리게)."""
    return {"title": title, "description": description, "link": link,
            "source": "테스트기관", "posted_date": "2026-07-16", **kw}


def blocked_by_filter(item) -> bool:
    """evaluate_notice 결과가 '이 필터 때문에' 제외됐는지 판정.

    NOT_GRANT_NOTICE 는 다른 경로(그룹 exclude_keywords·application_like 없음)에서도
    붙으므로, 코드 존재만으로는 이 필터의 동작을 증명하지 못한다. 이 필터는 근거
    문자열을 excluded_keywords 에 남기므로 그것까지 함께 확인한다.
    """
    ev = m.evaluate_notice(item)
    hit = m.non_notice_reason(item)
    return bool(hit) and hit in ev["excluded_keywords"] and "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]


# ─────────────────────────── (a) 실제 사례 ───────────────────────────

def test_사전정보공표_실제사례_제외된다():
    """★사용자 O/X 피드백 실제 사례 — gokams 정보공개 정적페이지."""
    item = notice("사전정보공표", link="https://www.gokams.or.kr/06_info/openData4.aspx")
    ev = m.evaluate_notice(item)
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]
    assert "사전정보공표" in ev["excluded_keywords"]   # 이 필터가 붙였음을 증명
    assert ev["is_relevant"] is False


@pytest.mark.parametrize("title", [
    "정보공개제도", "정보공개청구", "이용약관", "저작권정책", "기관소개", "연혁",
    "오시는길", "회원가입", "로그인", "FAQ", "부패신고센터", "업무추진비",
    "공공데이터개방", "채용정보", "입찰정보", "뉴스레터", "언론보도", "번호",
    "고정형 영상정보처리기기운영관리 방침", "국민비서 구삐", "1588-2188",
])
def test_정적페이지_명칭_자체는_제외된다(title):
    assert blocked_by_filter(notice(title))


def test_제목_정규화_공백_대소문자_무시():
    """앞뒤 공백·연속 공백·대소문자가 달라도 같은 정적 페이지로 본다."""
    assert m.non_notice_reason(notice("  사전정보공표 "))
    assert m.non_notice_reason(notice("English"))
    assert m.non_notice_reason(notice("조직  및   업무"))


def test_링크_스킴_도메인_룰():
    """tel:/mailto:/SNS 도메인 — 공고 상세가 될 수 없다(오탐 0)."""
    # 제목이 목록에 없어도 링크만으로 판정된다(정부24 '1588-2188' 계열의 일반형)
    assert m.non_notice_reason(notice("대표번호 안내", link="tel:110")) == "tel:"
    assert m.non_notice_reason(notice("문의", link="mailto:a@b.go.kr")) == "mailto:"
    # 제목·링크 둘 다 걸리면 제목 근거를 우선 반환(리포트 가독성)
    assert m.non_notice_reason(notice("110", link="tel:110")) == "110"
    assert m.non_notice_reason(
        notice("국세청 인스타그램", link="https://www.instagram.com/nts_korea")) == "instagram.com"
    assert m.non_notice_reason(notice("국세청 X", link="https://x.com/ntskorea")) == "x.com"


# ────────────────── (b) ★recall 가드: 공고성 토큰 ──────────────────

@pytest.mark.parametrize("title", [
    # 실측 반례들 — 부분포함으로 막았다면 전부 누락됐을 '진짜 공고'
    "정보공개 시스템 구축 사업 참여기업 모집",
    "「2026년 정보공개 고객 모니터링단」모집공고",
    "2026년 중소사업자 개인정보 안전조치 모니터링 지원 사업 공고",
    "2026년 2차 K-콘텐츠 해외 저작권 등록ㆍ출원 지원 대상기업 모집 공고",
    "제42회 국제의료기기병원설비전시회(KIMES 2027) 강원공동관 참가기업 모집 공고",
    "2026년 공공데이터 활용기업 AI연계 맞춤형 성장 지원사업 참여기업 모집 공고",
    "[입찰공고] 농신보 통합문서고 운영 · 관리 용역 입찰공고",
    "2026년 제2차 인재채용[NCS기반 능력중심 블라인드 채용] 공고",
    "♡ 뉴스레터 7월호를 만나보세요~",
    "개인정보처리방침 변경 안내",
    "수출바우처사업 「부정행위 집중신고기간 」 운영 (~7.23일까지)",
    # 목록 문자열 + 공고성 토큰 조합 (이중 안전장치가 우선한다)
    "이용약관 개정 안내 및 의견수렴 참가 신청",
    "온라인 참가신청",
    "공모사업 안내",
    "지원/신청",
])
def test_공고성_토큰_있으면_절대_안막힌다(title):
    """★recall 가드 — 제목에 모집/공고/신청/접수/참가/선정/공모/지원사업이 하나라도 있으면 통과."""
    item = notice(title)
    assert m.non_notice_reason(item) == ""
    assert title.strip() not in m.evaluate_notice(item)["excluded_keywords"]


def test_부분포함으로는_막지_않는다():
    """★recall 가드 — 완전일치만. 정적 페이지 명칭을 포함한 긴 제목은 통과."""
    for title in ["연혁 및 주요성과 자료", "기관소개 자료집 배포", "FAQ 개편 의견 수렴"]:
        assert m.non_notice_reason(notice(title)) == ""


@pytest.mark.parametrize("term", ["정보공개", "개인정보처리방침", "지원사업공고", "공지사항", "사업공고"])
def test_진짜공고_반례있는_문자열은_목록에_없다(term):
    """★recall 가드 — 이 문자열들은 타 기관 진짜 공고 제목으로 실재하므로 등재 금지."""
    assert term.casefold() not in m.NON_NOTICE_TITLES


def test_차단목록_전체가_공고성토큰_가드와_모순없다():
    """목록의 모든 항목은 (i) 실제로 차단되거나 (ii) 공고성 토큰 가드에 먼저 걸려 통과한다.
    후자는 의도된 recall 우선 동작 — '차단목록에 넣었는데 조용히 아무 일도 안 함'을 방지."""
    for term in m.NON_NOTICE_TITLES:
        has_token = any(tok in term for tok in m.NOTICE_SIGNAL_TOKENS)
        hit = m.non_notice_reason(notice(term))
        assert bool(hit) != has_token, f"{term}: 토큰={has_token} 차단={bool(hit)}"


# ──────────── (c) ★recall 가드: 본문에만 있는 경우 ────────────

@pytest.mark.parametrize("word", [
    "사전정보공표", "정보공개제도", "이용약관", "저작권정책", "업무추진비", "채용정보",
])
def test_본문에만_있으면_막히지_않는다(word):
    """★recall 가드 — EXCLUSION_RULES(제목+본문)에 넣지 않은 이유. 제목만 본다."""
    title = "2026년 스마트공장 구축 지원사업 참여기업 모집 공고"
    item = notice(title, description=f"자세한 내용은 홈페이지 {word} 메뉴를 참고하세요. 접수기간 2026.07.01~2026.08.31")
    assert m.non_notice_reason(item) == ""
    assert word not in m.evaluate_notice(item)["excluded_keywords"]


def test_본문에_있어도_included_판정이_유지된다():
    """정상 공고가 본문 우연일치로 버킷이 바뀌지 않는지 end-to-end 확인."""
    title = "2026년 인천 중소기업 스마트공장 구축 지원사업 참여기업 모집 공고"
    body = "접수기간 2026.07.01~2026.12.31 / 인천 남동구 소재 중소기업 / 홈페이지 이용약관 및 정보공개제도 참고"
    base = m.evaluate_notice(notice(title, description=body.replace(" 이용약관 및 정보공개제도 참고", "")))
    with_word = m.evaluate_notice(notice(title, description=body))
    assert with_word["exclude_reason_codes"] == base["exclude_reason_codes"]
    assert with_word["is_relevant"] == base["is_relevant"]


# ──────────────────── (d) 환경변수 kill switch ────────────────────

def test_환경변수로_끄면_막히지_않는다(monkeypatch):
    """MONITOR_NO_NONNOTICE_FILTER=1 → 필터 전체 비활성(오차단 발견 시 즉시 무력화)."""
    item = notice("사전정보공표", link="https://www.gokams.or.kr/06_info/openData4.aspx")
    assert m.non_notice_reason(item)                      # 기본값: 차단
    monkeypatch.setenv("MONITOR_NO_NONNOTICE_FILTER", "1")
    assert m.non_notice_reason(item) == ""                # 끄면 통과
    assert "사전정보공표" not in m.evaluate_notice(item)["excluded_keywords"]
    assert m.non_notice_reason(notice("110", link="tel:110")) == ""   # 링크 룰도 함께 꺼짐


def test_환경변수_다른값은_필터_유지(monkeypatch):
    """오타·'0' 등으로 조용히 꺼지지 않게 — 정확히 '1' 일 때만 비활성."""
    monkeypatch.setenv("MONITOR_NO_NONNOTICE_FILTER", "0")
    assert m.non_notice_reason(notice("사전정보공표"))


# ──────────────────────── 기타 계약 ────────────────────────

def test_빈제목_빈링크는_판정하지_않는다():
    for item in [notice(""), notice("   "), {"title": None, "link": None}]:
        assert m.non_notice_reason(item) == ""


def test_새코드_신설하지_않았다():
    """하위 도구·리포트가 아는 기존 코드만 쓴다(feedback_suggest.py 등)."""
    ev = m.evaluate_notice(notice("사전정보공표"))
    assert "NON_NOTICE_PAGE" not in ev["exclude_reason_codes"]
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]


# ─────────── (b-2) 적대적 반증에서 나온 경계 사례 보강 (recall) ───────────

def test_링크도메인_룰이_진짜공고를_막지_않는다():
    """SNS 도메인 룰 + '지원' 토큰 — 홍보영상 지원공고가 youtube 링크를 달아도 통과."""
    item = notice(
        "중소기업 홍보영상 제작 지원(유튜브)",
        link="https://www.youtube.com/watch?v=abcd1234",
    )
    assert m.non_notice_reason(item) == ""


def test_지원_설명회_토큰이_비공고판정을_건너뛴다():
    """느슨하게만 만드는 토큰 — 차단목록 문자열이 섞여도 공고성 제목이면 통과."""
    for title in ["사업안내 지원", "기관소개 설명회", "정보공개제도 개선 지원"]:
        assert m.non_notice_reason(notice(title)) == ""


def test_토큰보강이_실제_정크차단력을_해치지_않는다():
    """★사용자가 X 준 실제 사례와 대표 정크는 토큰 보강 후에도 그대로 차단된다."""
    for title in ["사전정보공표", "이용약관", "채용정보", "번호", "기관소개"]:
        assert m.non_notice_reason(notice(title)), title

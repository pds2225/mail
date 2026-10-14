"""MAIL-037: 10/14 22:03 실수집 사전점검(K-Startup) 실제 제목 기반 회귀."""
from datetime import date

import monitor
from mail_core.delivery import digest_table as dt

TODAY = date(2026, 10, 14)


def _item(title, deadline="2026-10-31", **kw):
    return {"id": title[:12], "title": title, "deadline": deadline, "description": kw.pop("description", ""),
            "link": "https://example.test/n", **kw}


BD = "출연연, 대학 연구소기업 Business Development 프로그램 참여 예비창업자 모집 (10월)"
IR = "대학생 예비 창업가의 아이디어를 검증할 실전 무대, 2026 『신한 스퀘어브릿지』 HERO IR 참가자 모집(~11/2)"
GUIDE = "[2026 창업지원사업 통합공고 요약본, 챗봇 제공] 지원사업 준비를 AI와 함께 하는 방법"
AITRAIN = "2026 중소기업AI훈련 맞춤 컨설팅 100% 정부지원 프로그램 참여기업 모집모집"
ANES = "해외진출 기업 대상 AI 통역 서비스 「아네스노트」 이용권 지원 (10월)"


def test_source_voucher_tag_alone_is_not_voucher():
    for t in (BD, AITRAIN, ANES):
        assert monitor._mail_support_cell(_item(t, _types=["바우처"], support_field="사업화")) != "바우처", t


def test_voucher_by_title_or_clear_body():
    assert monitor._mail_support_cell(_item("2026년 2차 일반 물류바우처 사업 참여기업 모집 공고")) == "바우처"
    assert monitor._mail_support_cell(_item(AITRAIN, description="선정 기업에 컨설팅 바우처를 지급합니다")) == "바우처"
    assert monitor._mail_support_cell(_item(BD, description="선정 기업에는 사업화 바우처 연계 안내")) != "바우처"


def test_events_go_to_gita():
    for t in (IR, "2026 AI 스타트업 경연 참가팀 모집", "2026년 광명 글로컬 데모데이 참관객 모집",
              "2026 창업 IR 데이 참가기업 모집"):
        assert monitor._mail_support_cell(_item(t, _types=["바우처"], description="바우처 지원")) == "기타", t


def test_info_guide_post_excluded_conservatively():
    assert monitor.is_info_guide_post(_item(GUIDE))
    assert monitor._digest_is_closed(_item(GUIDE, "2027-02-07"), TODAY)
    # 모집·신청 표현이 있으면 유지(보수적)
    for t in ("2026 창업지원사업 통합공고 요약본 설명회 참가자 모집",
              "지원사업 신청하는 방법 안내 및 접수", BD, "2026년 중앙부처 및 지자체 창업지원사업 통합공고"):
        assert not monitor.is_info_guide_post(_item(t)), t
    body = monitor.fallback_body([_item(GUIDE, "2027-02-07"), _item(BD)], today=TODAY)
    assert "요약본" not in body and "Business Development" in body


def test_doubled_trailing_word_collapsed():
    assert monitor.clean_mail_title(AITRAIN) == "2026 중소기업AI훈련 맞춤 컨설팅 100% 정부지원 프로그램 참여기업 모집"
    assert monitor.clean_mail_title("2026 하하 모집") == "2026 하하 모집"


def test_org_not_cut_mid_word():
    assert dt.short_org("중소기업AI훈련확산센터") == "중소기업AI훈련확산센터"
    long_spaced = "한국산업기술진흥원 지역산업 혁신본부 사업기획팀"
    out = dt.short_org(long_spaced)
    assert out.endswith("…") and long_spaced.startswith(out[:-1]) and out[:-1].split()[-1] in long_spaced.split()
    assert dt.short_org("넥스트러너스주식회사") == "넥스트러너스주식회사"

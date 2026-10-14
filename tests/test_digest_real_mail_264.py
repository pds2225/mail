"""2026-10-13 13:38 KST 실발송(run #264, main d383295) 3개 그룹 메일 원문 기반 회귀."""
from datetime import date, datetime

import monitor
from mail_core.delivery import digest_table as dt

TODAY = date(2026, 10, 13)
POSTED = "2026-10-08"


def _item(title, deadline="", desc="", **kw):
    return {"id": kw.pop("id", title[:20]), "title": title, "deadline": deadline, "description": desc,
            "link": "https://example.org/" + str(abs(hash(title)) % 10000), **kw}


KISTI = "2026년 서울테크노파크-KISTI(한국과학기술정보연구원) 기술협력 파트너링 데이 참여기업 모집(~9.30)"
KRIBB = "2026년 서울테크노파크-KRIBB(한국생명공학연구원) 기술협력 파트너링 데이 참여기업 모집(~9.30)"
CHALLENGE = "지역 현안 해결 솔루션 챌린지 공고(~10. 11.(일), 18:00)"


# (a) 연도 없는 마감
def test_infer_year_only_rolls_when_far_before_posted():
    posted = date(2026, 10, 8)
    assert monitor._infer_deadline_year(9, 30, posted) == date(2026, 9, 30)
    assert monitor._infer_deadline_year(10, 11, posted) == date(2026, 10, 11)
    assert monitor._infer_deadline_year(1, 15, posted) == date(2027, 1, 15)


def test_seoultp_shortform_deadlines_are_past_and_filtered():
    for t in (KISTI, KRIBB, CHALLENGE):
        it = _item(t, posted_date=POSTED, author="서울테크노파크")
        assert monitor._digest_is_closed(it, TODAY), t
    body = monitor.fallback_body([_item(t, posted_date=POSTED) for t in (KISTI, KRIBB, CHALLENGE)], today=TODAY)
    assert "D-352" not in body and "D-363" not in body and "파트너링" not in body


# (b) 게시판 메뉴 문구
def test_board_menu_text_is_support_junk():
    assert monitor.is_support_junk("기업지원공고 전체")
    it = _item("기술협력 지원사업", "2026-10-30", "기업지원공고 전체", posted_date=POSTED)
    assert monitor._mail_support_summary(it) == ""


# (c) 제목 건수·🙋 목록 = 표시 카드
def test_subject_count_and_feedback_match_shown_cards(monkeypatch):
    monkeypatch.setattr(monitor, "_feedback_links_enabled", lambda: True)
    live = _item("모집중(2026-207호) 2026년 강원 미래모빌리티 기업지원 프로그램 모집 통합공고", "2026-10-13",
                 posted_date=POSTED, id="imp_live")
    dead = [_item("인천서구]2025년 해외지사화 지원사업 2차 참가신청 모집", "2025-09-03", id="ema_dead"),
            _item("[교육안내] 2026년 양주시 중소기업 온라인 마케팅 교육 안내 (7.10)", "7/8", id="gtp_dead"),
            _item(KISTI, posted_date=POSTED, id="stp_dead")]
    out = monitor._build_group_mail_content(
        group={"name": "예비창업 AI (전국·서울강조)"}, g_items=[live] + dead, ru_mail_items=[], ru_items=[],
        ru_limit=10, filtered_new=[live] + dead, window_label="2026-10-08 ~ 2026-10-12", days_back=3,
        date_str="10/13 오전", now=datetime(2026, 10, 13, 12, 57, tzinfo=monitor.KST))
    assert out["subject"] == "[예비창업 AI (전국·서울강조)] 1건 (10/13 오전)"
    body = out["body"]
    assert "그룹 매칭 1건" in body
    fb = body[body.index("🙋"):]
    assert "1. 2026년 강원 미래모빌리티 기업지원 프로그램 모집 통합공고" in fb
    assert "모집중(2026-207호)" not in fb and "2. " not in fb.split("ⓘ")[0]


# (d) 📍 지역 확인
def test_region_unknown_section_format_and_expired_dropped():
    items = [
        _item("2025 글로벌 여성IP 리더십 아카데미 참가신청 안내"),
        _item("2026년 2차 일반 물류바우처 사업 참여기업 모집 공고", "", "예산 소진시까지", author="중소벤처기업부"),
        _item("침해사고 예방을 위한 취약점 점검 무료 지원 모집 공고", "2026-05-19 ~ 2026-12-11", author="과학기술정보통신부"),
        _item("한-독 제조혁신 기술 및 R&D 협력 포럼 개최 안내"),
    ]
    txt = monitor.render_region_unknown(items, limit=10, total_count=93)
    assert "여성IP" not in txt
    import re
    assert re.search(r"마감: 12/11 \(D-\d+\)", txt)  # 오늘 날짜 무관
    assert "마감: 상시" in txt
    assert "마감: 확인필요" in txt
    assert "미기재 | 마감: 미기재" not in txt and "2026-05-19 ~" not in txt


# (e) 지역·바우처
def test_region_org_name_and_not_tuja_daejeon():
    gw = _item("2026년 강원 미래모빌리티 기업지원 프로그램 모집 통합공고", "2026-10-13", author="강원TP")
    assert monitor._mail_region_cell(gw) == "강원"
    bio = _item("2026 제약바이오 투자대전(해외 투자유치ᆞ수출 상담회) 참가기업 모집", "2026-10-23",
                author="비즈오케이", region_status="eligible", applicant_region_city="인천",
                eligible_regions=["인천"])
    assert "대전" not in monitor._mail_region_cell(bio)


def test_events_and_education_are_not_voucher():
    for t in (KISTI, "2026년 광명 글로컬 데모데이 참관객 모집",
              "2026 제약바이오 투자대전(해외 투자유치ᆞ수출 상담회) 참가기업 모집"):
        assert monitor._mail_support_cell(_item(t, _types=["바우처"])) != "바우처", t
    assert monitor._mail_support_cell(_item("2026년 2차 일반 물류바우처 사업 참여기업 모집 공고")) == "바우처"


def test_wanryo_title_is_closed():
    assert monitor.is_title_closed({"title": "완료(2026-204호) 2026년 전기차 고전압 안전교육 모집 공고"})

"""실발송 메일 모바일 본문·지역미상·MIME 회귀 테스트."""
# 실제 SMTP 발송 없이 최종 plain/HTML MIME 결과를 고정한다.
# 지원내용은 모바일 한 화면 기준(160자 + 말줄임표)으로 제한한다.
import os
from email import message_from_bytes
from pathlib import Path
import sys

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402


def _item(idx=1, **extra):
    base = {
        "id": f"n{idx}", "title": "2026년 AI 사업화 지원 &amp; 참여기업 모집 새로운게시글",
        "author": "지원기관 &amp; 센터",
        "description": ("<div>메인 회원가입 로그인 고객센터 재단소개 인사말 조직도 업무안내 알림마당 "
            "공지사항 자료실 정보공개</div><p>지원대상: 서울 소재 AI 중소기업. "
            "지원내용: 사업화 자금과 전문가 컨설팅을 지원합니다.</p> "
            "담당자: 홍길동 이메일 test@example.com 전화 02-1234-5678 "
            "[신청](https://example.com/apply) 개인정보처리방침 Copyright"),
        "target_field": "서울 소재 AI 중소기업",
        "support_field": "사업화 자금과 전문가 컨설팅을 지원하며 선정기업별 세부 지원규모는 공고문에서 확인",
        "deadline": "2099-12-31", "posted_date": "2026-07-24", "source": "기업마당",
        "link": f"https://example.com/{idx}", "_types": ["지원금/바우처"],
        "priority_keyword": False, "region_status": "eligible", "eligible_regions": [],
        "applicant_region_city": "서울특별시",
    }
    base.update(extra)
    return base


def test_mail_support_blurb_strips_noise_and_caps_length():
    text = m._mail_support_blurb(_item())
    assert len(text) <= 162
    assert "회원가입" not in text and "개인정보처리방침" not in text
    assert "test@example.com" not in text and "02-1234-5678" not in text
    assert "[신청](" not in text and "사업화 자금" in text


# 2026-08-04 실발송 회귀 — 아래 3건은 그날 실제로 나간 메일 본문에서 그대로 가져온 것이다.
# ① 게시판 메뉴만 긁힌 항목의 '지원내용' 에 메뉴바가 통째로 실렸다.
# ② 정상 공고도 담당자 이름·조회수·D-N 카운트다운이 그대로 노출됐다.
# ③ 우선 추천이 비면 본문이 "2. 일반 추천" 부터 시작했다(1번이 없어 보였다).
_REAL_MENU_ONLY = (
    "주요소식 공지사항 No 카테고리 전체보기 회원서비스 공지사항 사업공고 교육 행사 입주공고 "
    "유관기관 제목 글쓴이 작성시간 조회수 좋아요 공지사항 공지사항 [공지] KOVWA 명절마켓 "
    "추석 특가전 판매기업 모집(~8/17) N 한국여성벤처협회 1일전 조회수 40 0 입주공고 입주공고 [입주"
)
_REAL_BOARD_LIST = (
    "전체메뉴 닫기 전체메뉴 닫기 공지사항 사업고시/공고 사업고시/공고 사업고시/공고 유관사업 "
    "고시/공고 센터뉴스 뉴스레터신청 총 273 건 검색하기 구분 제목 작성일 조회 접수기간 상태 공지 "
    "[공지] 2026년도 중소기업 디자인개발지원사업 하반기 일반기업 지원분야 선정결과 안내 [알림] 0"
)
_REAL_NOTICE = (
    "사업구분 : 신청기간 : 2026-08-03 14:00 ~ 2026-08-31 15:00 ( D-27 ) 주관기관 : 이종석 "
    "2026-08-03 777 내용 2026 년 2 차 XR 기업성장지원센터 입주기업 모집 공고문 신청 자격은 "
    "XR 분야 창업 7년 이내 중소기업이며 입주 공간과 장비 이용을 지원합니다"
)


def test_support_blurb_hides_board_menu_instead_of_showing_junk():
    for desc in (_REAL_MENU_ONLY, _REAL_BOARD_LIST):
        text = m._mail_support_blurb(_item(description=desc, support_field=""))
        assert text == "상세 공고문 확인", text
        for junk in ("전체보기", "글쓴이", "좋아요", "전체메뉴", "검색하기"):
            assert junk not in text


def test_support_blurb_keeps_notice_content_but_drops_board_meta():
    text = m._mail_support_blurb(_item(description=_REAL_NOTICE, support_field=""))
    for meta in ("이종석", "777", "D-27", "사업구분 :"):
        assert meta not in text, f"{meta!r} 가 남았다: {text}"
    assert "XR" in text and "입주" in text


def test_fallback_body_numbers_only_visible_sections():
    only_general = m.fallback_body([_item(1, priority_keyword=False)])
    first = next(line for line in only_general.splitlines() if line.strip())
    assert not first.startswith("2."), first
    assert first.strip() == "일반 추천"

    both = m.fallback_body([_item(1, priority_keyword=True), _item(2, priority_keyword=False)])
    assert "1. 우선 추천" in both and "2. 일반 추천" in both


def test_fallback_body_uses_eight_line_mobile_card():
    body = m.fallback_body([_item()])
    card = body.split("──────────────────", 1)[1].strip().splitlines()
    assert len(card) == 7
    assert "📌 2026년 AI 사업화 지원 & 참여기업 모집" in body
    assert "• 대상: 서울 소재 AI 중소기업" in body and "• 지원내용:" in body
    assert "• 원문: https://example.com/1" in body
    assert "등록일:" not in body and "출처:" not in body and "담당자" not in body
    assert "&amp;" not in body


def test_region_unknown_mail_is_limited_to_ten_and_filters_junk(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "LOGS_DIR", tmp_path)
    items = [_item(i, title=f"정상 지원사업 {i}", region_status="unknown") for i in range(1, 13)]
    items.append(_item(99, title="채용 결과 안내", region_status="unknown"))
    shown = m.select_region_unknown_for_mail(items, limit=10)
    assert len(shown) == 10 and all("채용" not in it["title"] for it in shown)
    report = m.write_region_unknown_report(items, "AI팀")
    assert report and report.exists()
    body = m.render_region_unknown(shown, limit=10, total_count=len(items))
    assert body.count("\n▸ ") == 10 and "나머지 3건" in body


def test_mime_plain_and_html_render_same_clean_content():
    body = m.fallback_body([_item()])
    msg = m._build_mime_message("[AI팀] 1건", body, "recipient@example.test")
    parsed = message_from_bytes(msg.as_bytes())
    parts = {part.get_content_type(): part.get_payload(decode=True).decode(part.get_content_charset())
             for part in parsed.walk() if part.get_content_maintype() != "multipart"}
    plain = parts["text/plain"]
    html_part = parts["text/html"]
    assert "사업화 자금" in plain and "사업화 자금" in html_part
    assert "&amp;amp;" not in html_part and '<a href="https://example.com/1">' in html_part
    assert "test@example.com" not in plain and "개인정보처리방침" not in html_part


def test_mail_support_blurb_long_text_stays_within_one_mobile_screen():
    item = _item(
        support_field=(
            "사업화 자금, 시제품 제작, 전문가 컨설팅, 국내외 판로개척, "
            "홍보물 제작, 인증 취득, 시험분석 및 후속 투자연계를 지원합니다. " * 12
        )
    )
    text = m._mail_support_blurb(item)
    assert len(text) <= 162
    assert text.endswith(" …")
    body = m.fallback_body([item])
    support_line = next(line for line in body.splitlines() if line.startswith("• 지원내용:"))
    assert len(support_line.removeprefix("• 지원내용: ")) <= 162

"""실발송 메일 모바일 본문·지역미상·MIME 회귀 테스트."""
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
    assert len(text) <= 482
    assert "회원가입" not in text and "개인정보처리방침" not in text
    assert "test@example.com" not in text and "02-1234-5678" not in text
    assert "[신청](" not in text and "사업화 자금" in text


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

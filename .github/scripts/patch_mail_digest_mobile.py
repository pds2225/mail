from __future__ import annotations

import json
from pathlib import Path

MONITOR = Path("monitor.py")
SETTINGS = Path("config/settings.json")
TEST = Path("tests/test_mail_digest_mobile.py")


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    s = text.index(start)
    e = text.index(end, s)
    return text[:s] + replacement.rstrip() + "\n\n" + text[e:]


text = MONITOR.read_text(encoding="utf-8")

mail_block = r'''def _plain_text(s: str, limit: int = 1500) -> str:
    """HTML 태그·엔티티 제거 → 사용자용 평문. 길면 자른다."""
    if not s:
        return ""
    if "<" in s:
        s = BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:limit].rstrip() + " …") if len(s) > limit else s


MAIL_SUPPORT_BLURB_LIMIT = 480
REGION_UNKNOWN_MAIL_LIMIT = 10

_MAIL_FOOTER_MARKERS = (
    "개인정보처리방침", "영상정보처리기기", "이메일무단수집거부", "Copyright",
    "이 페이지에서 제공하는 정보", "패밀리 사이트", "목록으로 바로가기",
)
_MAIL_NAV_TOKENS = (
    "메인", "회원가입", "로그인", "고객센터", "재단소개", "인사말", "연 혁", "조직도",
    "업무안내", "알림마당", "공지사항", "채용정보", "자료실", "홍보마당", "정보공개",
)


def _mail_clean_text(value: object, *, limit: int = MAIL_SUPPORT_BLURB_LIMIT) -> str:
    """메일 표시용 텍스트 정제: HTML·Markdown·연락처·메뉴/푸터·긴 URL 제거."""
    raw = str(value or "")
    raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", raw)
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    text = _plain_text(raw, limit=6000)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", text)
    text = re.sub(r"(?:\+?82[-. ]?)?0\d{1,2}[-. )]\d{3,4}[-. ]\d{4}", " ", text)
    text = re.sub(r"(?:담당자|연락처|전화|이메일|팩스|fax|tel)\s*[:：]?\s*[^|·•]{0,45}", " ", text, flags=re.I)
    for marker in _MAIL_FOOTER_MARKERS:
        pos = text.find(marker)
        if pos >= 80:
            text = text[:pos]
    nav_hits = sum(1 for token in _MAIL_NAV_TOKENS if token in text[:500])
    if nav_hits >= 5:
        anchors = [text.find(token) for token in ("지원대상", "사업내용", "지원내용", "모집개요", "신청자격", "☞")]
        anchors = [pos for pos in anchors if pos >= 0]
        if anchors:
            text = text[min(anchors):]
    text = re.sub(r"\s+", " ", text).strip(" -·•|/")
    return (text[:limit].rstrip() + " …") if len(text) > limit else text


def _mail_target_text(item: dict) -> str:
    for key in ("target_field", "target_age_field", "business_age_text"):
        value = _mail_clean_text(item.get(key), limit=180)
        if value:
            return value
    return "공고문 확인"


def _mail_support_blurb(item: dict, limit: int = MAIL_SUPPORT_BLURB_LIMIT) -> str:
    """구조화 지원내용을 우선하고, 없으면 상세본문을 모바일 길이로 정제한다."""
    structured = _mail_clean_text(item.get("support_field"), limit=limit)
    description = _mail_clean_text(item.get("description"), limit=limit)
    candidate = structured if len(structured) >= 25 else description or structured
    title = _mail_clean_text(item.get("title"), limit=200)
    if title and candidate.startswith(title):
        candidate = candidate[len(title):].lstrip(" :-·•")
    return candidate or "상세 공고문 확인"


def _mail_fit_reason(item: dict) -> str:
    for key in ("fit_reason", "match_reason", "company_match_reason"):
        value = _mail_clean_text(item.get(key), limit=160)
        if value:
            return value
    types = [str(v) for v in (item.get("_types") or []) if str(v).strip()]
    region = _region_label(item)
    parts = []
    if item.get("priority_keyword"):
        parts.append("우선 검토 대상")
    if types:
        parts.append("·".join(types[:2]))
    if region != "확인 필요" and not region.endswith("전체"):
        parts.append(region)
    return " / ".join(parts) or "그룹 조건과 일치"


def fallback_body(items: list[dict]) -> str:
    """모바일 메일용 8줄 카드. 내부판정값·원문전체·연락처는 표시하지 않는다."""
    lines: list[str] = []
    items = sorted(items, key=_notice_sort_key)
    imminent = [it for it in items if is_imminent(it.get("deadline", ""))]
    if imminent:
        lines.append("⚠️ 7일 이내 마감: " + ", ".join(
            _mail_clean_text(it.get("title"), limit=45) for it in imminent[:5]
        ))
        lines.append("")
    sections = [
        ("1. 우선 추천", [it for it in items if it.get("priority_keyword")]),
        ("2. 일반 추천", [it for it in items if not it.get("priority_keyword")]),
    ]
    for section_title, section_items in sections:
        if not section_items:
            continue
        lines.append(section_title)
        for it in section_items:
            title = _mail_clean_text(it.get("title") or "(제목없음)", limit=160)
            author = _mail_clean_text(it.get("author") or "미기재", limit=80)
            types = " · ".join(str(v) for v in (it.get("_types") or ["미분류"])[:2])
            region = _region_label(it)
            lines.extend([
                "──────────────────",
                f"📌 {title}",
                f"• 기관: {author} | 유형: {types}",
                f"• 대상: {_mail_target_text(it)}",
                f"• 지원내용: {_mail_support_blurb(it)}",
                f"• 마감: {resolve_item_deadline(it) or '미기재'} | 지역: {region}",
                f"• 적합사유: {_mail_fit_reason(it)}",
                f"• 원문: {it.get('link') or '미기재'}",
            ])
        lines.append("")
    return "\n".join(lines).strip()
'''

text = replace_between(text, "def _plain_text(", "def _region_label(", mail_block)

region_block = r'''def select_region_unknown_for_mail(items: list[dict], limit: int = REGION_UNKNOWN_MAIL_LIMIT) -> list[dict]:
    """지원사업성이 확인된 지역미상만 우선순위순으로 최대 limit건 표시한다."""
    clean = [it for it in items if not is_admin_noise(it) and not is_report_junk(it)]
    clean = sorted(clean, key=lambda it: (
        0 if it.get("priority_keyword") else 1,
        _notice_sort_key(it),
    ))
    return clean[:max(0, int(limit))]


def write_region_unknown_report(items: list[dict], group_name: str, *, run_at: datetime | None = None) -> Path | None:
    """메일에서 생략된 지역미상 전체 목록을 관리자 로그로 저장한다."""
    if not items:
        return None
    run_at = run_at or datetime.now(KST)
    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(group_name or "group")).strip("_")[:50] or "group"
    path = LOGS_DIR / f"region_unknown_{run_at:%Y%m%d}_{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 지역 미상 관리자 리포트 — {group_name}", "",
        f"- 생성: {run_at.strftime('%Y-%m-%d %H:%M KST')}",
        f"- 전체: {len(items)}건", "",
    ]
    for it in items:
        lines.append(
            f"- {it.get('title') or '(제목없음)'} | {it.get('author') or '미기재'} | "
            f"마감 {resolve_item_deadline(it) or '미기재'} | {it.get('link') or ''}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_region_unknown(items: list[dict], limit: int = REGION_UNKNOWN_MAIL_LIMIT, *, total_count: int | None = None) -> str:
    """메일에는 최대 10건만 표시하고 나머지는 관리자 리포트로 분리한다."""
    if not items:
        return ""
    shown = select_region_unknown_for_mail(items, limit=limit)
    total = len(items) if total_count is None else int(total_count)
    if not shown:
        return ""
    lines = [
        "\n\n────────────────────────────────",
        f"📍 지역 확인 필요 — 메일 표시 {len(shown)}건 / 전체 {total}건",
    ]
    for it in shown:
        lines.append(f"\n▸ {_mail_clean_text(it.get('title') or '(제목없음)', limit=120)}")
        lines.append(
            f"  기관: {_mail_clean_text(it.get('author') or '미기재', limit=70)}"
            f" | 마감: {resolve_item_deadline(it) or '미기재'}"
        )
        if it.get("link"):
            lines.append(f"  원문: {it['link']}")
    if total > len(shown):
        lines.append(f"\n나머지 {total - len(shown)}건은 관리자 지역미상 리포트에 저장했습니다.")
    return "\n".join(lines)
'''
text = replace_between(text, "def render_region_unknown(", "def claude_summarize(", region_block)

old = '''        ru_items = diagnostics["region_unknown"]
        excluded_items = diagnostics["excluded"]'''
new = '''        ru_items = diagnostics["region_unknown"]
        ru_limit = int(settings.get("region_unknown_mail_limit", REGION_UNKNOWN_MAIL_LIMIT))
        ru_mail_items = select_region_unknown_for_mail(ru_items, limit=ru_limit)
        if ru_items:
            write_region_unknown_report(ru_items, str(group.get("name") or "group"), run_at=now)
        excluded_items = diagnostics["excluded"]'''
if old not in text:
    raise RuntimeError("region_unknown assignment anchor not found")
text = text.replace(old, new, 1)
text = text.replace('''                "region_unknown_items": len(ru_items),''', '''                "region_unknown_items": len(ru_items),
                "region_unknown_mail_items": len(ru_mail_items),''', 1)
text = text.replace('''        if not g_items and not ru_items:''', '''        if not g_items and not ru_mail_items:''', 1)
text = text.replace('''            "region_unknown_items": len(ru_items),''', '''            "region_unknown_items": len(ru_mail_items),
            "region_unknown_total_items": len(ru_items),''', 1)
text = text.replace('''            region_unknown_block = render_region_unknown(ru_items)''', '''            region_unknown_block = render_region_unknown(
                ru_mail_items, limit=ru_limit, total_count=len(ru_items),
            )''', 1)
text = text.replace('''            subj_count = f"{len(g_items)}건" + (f"+지역미상 {len(ru_items)}건" if ru_items else "")''', '''            subj_count = f"{len(g_items)}건" + (
                f"+지역확인 {len(ru_mail_items)}건" if ru_mail_items else ""
            )''', 1)
text = text.replace('''                        notice_ids=[str(it.get("id") or "") for it in (g_items + ru_items)],''', '''                        notice_ids=[str(it.get("id") or "") for it in (g_items + ru_mail_items)],''', 1)
MONITOR.write_text(text, encoding="utf-8")

settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
settings["region_unknown_mail_limit"] = 10
SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

TEST.write_text(r'''"""실발송 메일 모바일 본문·지역미상·MIME 회귀 테스트."""
import os
from email import message_from_bytes
from pathlib import Path
import sys

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
os.environ.setdefault("MONITOR_NO_FEEDBACK_LINKS", "1")
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
    assert "📌 2026년 AI 사업화 지원 & 참여기업 모집 새로운게시글" in body
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
''', encoding="utf-8")

print("patched monitor.py, config/settings.json, tests/test_mail_digest_mobile.py")

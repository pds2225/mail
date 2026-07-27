"""사용자 O/X 피드백 루프(Tier C 골든) 회귀 가드.

실제 나간 메일에 붙는 O/X 링크 → 제목 파싱 → 골든 누적 → 측정 반영까지의 계약을 고정한다.
★ 안전 가드: 이 기능은 '표시·측정' 전용 — 발송(SMTP/IMAP)은 하지 않는다(테스트도 mock 없음).
단독 foreground: python -m pytest test_feedback_loop.py -q
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
os.environ.setdefault("MAIL_FEEDBACK_SECRET", "feedback-loop-test-secret")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mail_core.delivery import feedback  # noqa: E402
import monitor  # noqa: E402

NID = "PBLN_000000000092578"


def _subject(verdict: str, notice_id: str) -> str:
    return f"[MAIL-FB] {verdict} {notice_id} {feedback.feedback_token.sign(verdict, notice_id)}"


# ── 제목 파싱 ──────────────────────────────────────────────
def test_parse_subject_basic():
    got = feedback.parse_feedback_subject(_subject("X", NID))
    assert got == {"verdict": "X", "id": NID}


def test_parse_subject_with_reply_prefix_and_lowercase():
    got = feedback.parse_feedback_subject("Re: " + _subject("O", NID).replace("[MAIL-FB] O", "[mail-fb] o"))
    assert got == {"verdict": "O", "id": NID}


def test_parse_subject_percent_encoded():
    from urllib.parse import quote
    got = feedback.parse_feedback_subject(quote(_subject("X", NID)))
    assert got == {"verdict": "X", "id": NID}


def test_parse_subject_rejects_unrelated_mail():
    assert feedback.parse_feedback_subject("[서울 AI] 12건 (2026-07-16)") is None
    assert feedback.parse_feedback_subject("") is None
    assert feedback.parse_feedback_subject("[MAIL-FB] 안녕하세요") is None


def test_mailto_roundtrip():
    url = feedback.feedback_mailto("me@example.com", "X", NID)
    assert url.startswith("mailto:me%40example.com?subject=")
    from urllib.parse import unquote
    assert feedback.parse_feedback_subject(unquote(url)) == {"verdict": "X", "id": NID}
    assert feedback.feedback_link_label(url) == "❌ 아니에요"
    assert feedback.feedback_link_label(feedback.feedback_mailto("me@example.com", "O", NID)) == "⭕ 맞아요"
    assert feedback.feedback_link_label("https://example.com") == ""


# ── digest 블록 렌더 ────────────────────────────────────────
def test_render_block_has_both_links_per_item():
    items = [{"id": NID, "title": "서울 AI 바우처 지원사업"}]
    block = feedback.render_feedback_block(items, "me@example.com")
    assert "1. 서울 AI 바우처 지원사업" in block
    assert block.count(f"subject=%5BMAIL-FB%5D") == 2   # O/X 두 개
    assert "이 추천, 맞았나요?" in block


def test_render_block_empty_when_no_items_or_no_addr():
    assert feedback.render_feedback_block([], "me@example.com") == ""
    assert feedback.render_feedback_block([{"id": NID, "title": "t"}], "") == ""
    assert feedback.render_feedback_block([{"title": "id 없음"}], "me@example.com") == ""


def test_render_block_respects_limit():
    items = [{"id": f"ID{i}", "title": f"공고 {i}"} for i in range(5)]
    block = feedback.render_feedback_block(items, "me@example.com", limit=2)
    assert "1. 공고 0" in block and "2. 공고 1" in block
    assert "3. 공고 2" not in block
    assert "외 3건" in block


# ── 골든 누적(append-only, 최신 verdict 반영) ────────────────
def test_merge_labels_add_update_dedupe(tmp_path):
    p = tmp_path / "feedback_labels.jsonl"
    s1 = feedback.merge_feedback_labels([{"id": NID, "verdict": "X"}], p)
    assert (s1["added"], s1["total"]) == (1, 1)
    # 같은 판정 재수집 → 중복 아님(unchanged), 파일 안 늘어남
    s2 = feedback.merge_feedback_labels([{"id": NID, "verdict": "X"}], p)
    assert (s2["added"], s2["unchanged"], s2["total"]) == (0, 1, 1)
    # 마음이 바뀌면 최신 판정이 이긴다
    s3 = feedback.merge_feedback_labels([{"id": NID, "verdict": "O"}], p)
    assert (s3["updated"], s3["total"]) == (1, 1)
    assert feedback.feedback_verdicts(p) == {NID: "O"}
    rec = feedback.load_feedback_labels(p)[NID]
    assert rec["tier"] == "C" and rec["first_seen"] and rec["last_seen"]


def test_merge_labels_ignores_garbage(tmp_path):
    p = tmp_path / "f.jsonl"
    st = feedback.merge_feedback_labels(
        [{"id": "", "verdict": "X"}, {"id": NID, "verdict": "?"}, {}], p)
    assert st["invalid"] == 3 and st["total"] == 0
    assert not p.exists()


def test_load_labels_missing_file_is_empty(tmp_path):
    assert feedback.load_feedback_labels(tmp_path / "none.jsonl") == {}
    assert feedback.feedback_verdicts(tmp_path / "none.jsonl") == {}


# ── 메일 HTML 파트: 링크가 실제로 눌리는가 ────────────────────
def test_linkify_makes_feedback_links_clickable_with_friendly_label():
    url = feedback.feedback_mailto("me@example.com", "O", NID)
    out = monitor._linkify_html(f"눌러주세요: {url}\n다음줄")
    assert f'<a href="{url}">⭕ 맞아요</a>' in out
    assert "<br>" in out


def test_linkify_keeps_notice_links_and_escapes_text():
    out = monitor._linkify_html("🔗 https://bizinfo.go.kr/a?b=1&c=2 <script>")
    assert '<a href="https://bizinfo.go.kr/a?b=1&amp;c=2">' in out
    assert "&lt;script&gt;" in out          # 본문 텍스트는 그대로 이스케이프
    assert "<script>" not in out


def test_linkify_excludes_trailing_punctuation():
    out = monitor._linkify_html("자세히: https://example.com/a.")
    assert '<a href="https://example.com/a">' in out and out.endswith(".")


def test_mime_message_html_part_contains_anchor():
    url = feedback.feedback_mailto("me@example.com", "X", NID)
    msg = monitor._build_mime_message("제목", f"본문\n{url}", "me@example.com")
    html_part = msg.get_payload()[1].get_payload(decode=True).decode("utf-8")
    assert f'<a href="{url}">❌ 아니에요</a>' in html_part


# ── monitor 쪽 스위치 ───────────────────────────────────────
def test_monitor_block_can_be_disabled_by_env(monkeypatch):
    items = [{"id": NID, "title": "공고"}]
    assert "MAIL-FB" in monitor._render_feedback_block(items)
    monkeypatch.setenv("MONITOR_NO_FEEDBACK_LINKS", "1")
    assert monitor._render_feedback_block(items) == ""


def test_monitor_block_empty_for_no_items():
    assert monitor._render_feedback_block([]) == ""


# ── 수집기(collect_feedback): 읽기전용 계약 + 실제 MIME 헤더 파싱 ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_feedback  # noqa: E402


class _FakeIMAP:
    """imaplib.IMAP4_SSL 대역 — 실제 접속 없이 수집 경로를 검증한다."""
    instances: list = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.select_calls: list = []
        self.fetch_specs: list = []
        _FakeIMAP.instances.append(self)

    def login(self, user, pw):
        return ("OK", [b"ok"])

    def list(self, ref, pattern):
        return ("OK", [rb'(\HasNoChildren \All) "/" "[Gmail]/All Mail"'])

    def select(self, folder, readonly=False):
        self.select_calls.append((folder, readonly))
        return ("OK", [b"2"])

    def search(self, charset, *criteria):
        self.criteria = criteria
        return ("OK", [b"1 2"])

    def fetch(self, num, spec):
        from email.header import Header
        self.fetch_specs.append(spec)
        subject = _subject("X", NID) if num == b"1" else str(Header(_subject("O", NID + "b"), "utf-8").encode())
        raw = f"Subject: {subject}\r\nDate: Thu, 16 Jul 2026 09:00:00 +0900\r\n\r\n".encode()
        return ("OK", [(b"1 (BODY[HEADER])", raw)])

    def close(self):
        pass

    def logout(self):
        pass


def test_collect_is_readonly_and_parses_real_mime_headers(monkeypatch):
    _FakeIMAP.instances.clear()
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setattr(collect_feedback.imaplib, "IMAP4_SSL", _FakeIMAP)
    got = collect_feedback.fetch_feedback_mails(days=7)
    assert got[0]["id"] == NID and got[0]["verdict"] == "X"
    assert got[1]["id"] == NID + "b" and got[1]["verdict"] == "O"   # MIME 인코딩 제목도 해독
    imap = _FakeIMAP.instances[0]
    # ★ 안전 계약: 반드시 읽기전용 SELECT + PEEK (읽음표시·삭제·발송 없음)
    assert imap.select_calls and all(ro is True for _, ro in imap.select_calls)
    assert all("BODY.PEEK" in s for s in imap.fetch_specs)


def test_collect_masks_address():
    assert collect_feedback._mask("test-recipient@example.test") == "te************@example.test"
    assert collect_feedback._mask("") == "***"


def test_collect_requires_credentials(monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        collect_feedback.fetch_feedback_mails(days=1)

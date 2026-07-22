"""첨부 안전 가드 회귀 테스트 (진단서 #27 악성첨부·#28 ZIP Bomb).

is_blocked_extension(실행/스크립트 차단)와 _read_capped(크기 상한)를 순수 검증한다.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")
os.environ.setdefault("NTFY_TOPIC", "x")

sys.path.insert(0, str(Path(__file__).parent))
import scripts.fetch_notice_attachments as fna  # noqa: E402


def test_blocked_extensions():
    for bad in ("virus.exe", "run.BAT", "x.js", "a.vbs", "m.ps1", "s.scr", "p.msi", "k.jar", "z.lnk"):
        assert fna.is_blocked_extension(bad) is True, bad


def test_allowed_document_extensions():
    for ok in ("공고문.hwp", "notice.pdf", "form.docx", "budget.xlsx", "slides.pptx",
               "files.zip", "img.png", "scan.jpg", "data.txt"):
        assert fna.is_blocked_extension(ok) is False, ok


def test_no_extension_not_blocked():
    assert fna.is_blocked_extension("attachment") is False
    assert fna.is_blocked_extension("") is False


class _FakeResp:
    def __init__(self, chunks):
        self._chunks = chunks

    def iter_bytes(self):
        for c in self._chunks:
            yield c


def test_read_capped_under_limit():
    data = fna._read_capped(_FakeResp([b"abc", b"def"]), max_bytes=100)
    assert data == b"abcdef"


def test_read_capped_over_limit_raises():
    big = [b"x" * 1000] * 5   # 5000 bytes
    try:
        fna._read_capped(_FakeResp(big), max_bytes=2048)
        assert False, "상한 초과는 RuntimeError 여야 함"
    except RuntimeError as e:
        assert "상한 초과" in str(e)


def test_read_capped_exact_limit_ok():
    assert fna._read_capped(_FakeResp([b"a" * 50]), max_bytes=50) == b"a" * 50


def test_count_and_size_constants_sane():
    assert fna.MAX_ATTACH_COUNT >= 10 and fna.MAX_ATTACH_BYTES >= 1024 * 1024

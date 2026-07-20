"""scripts/monitor_dry_run.py 콘솔 출력 견고화 회귀 — cp949 스트림에서도 크래시 없음.

배경: 요약의 '지역 미상' 헤더에 em-dash(—)가 있어 cp949 콘솔(Windows 기본)에서
요약 정상 출력 직후 UnicodeEncodeError 로 크래시했다(RESUME 미결 ①, line 57).
수정: _ensure_utf8_stdout() 이 stdout/stderr 를 UTF-8(errors=replace)로 재구성
(fetch_notice_attachments.py 관례 재사용). 네트워크·발송 없음(출력 함수만 검증).
"""
from __future__ import annotations

import io
import os
import sys

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

from scripts import monitor_dry_run as mdr  # noqa: E402


def _cp949_stream() -> io.TextIOWrapper:
    """Windows cp949 콘솔 흉내 — em-dash(—) 쓰면 strict 에선 UnicodeEncodeError."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")


def test_print_summary_survives_cp949_console(monkeypatch):
    """em-dash 헤더 포함 요약이 cp949 콘솔 흉내 스트림에서도 크래시 없이 출력된다."""
    fake_out = _cp949_stream()
    fake_err = _cp949_stream()
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)

    mdr._ensure_utf8_stdout()
    mdr._print_summary(
        {"total_new": 3, "region_unknown_total": 1},
        [{
            "name": "AI SaaS",
            "region_unknown_items": 1,
            "region_unknown_titles": ["서울 — AI 바우처 모집"],  # em-dash 포함 제목
        }],
    )

    fake_out.flush()
    raw = fake_out.buffer.getvalue()
    text = raw.decode("utf-8")
    assert "=== monitor dry-run summary ===" in text
    assert "지역 미상(확인 필요) — 보고 메일 하단에 함께 발송" in text  # em-dash 살아있음
    assert "서울 — AI 바우처 모집" in text


def test_cp949_stream_without_fix_would_crash():
    """전제 검증: 재구성 없이 cp949 strict 스트림에 em-dash 를 쓰면 실제로 죽는다."""
    stream = _cp949_stream()
    try:
        stream.write("— em-dash —")
        stream.flush()
    except UnicodeEncodeError:
        return
    raise AssertionError("cp949 strict 스트림이 em-dash 를 통과시킴 — 전제 붕괴")


def test_ensure_utf8_stdout_tolerates_streams_without_reconfigure(monkeypatch):
    """reconfigure 가 없는 스트림(StringIO 등)에서도 helper 가 조용히 통과한다."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    mdr._ensure_utf8_stdout()  # 예외 없이 통과해야 함
    mdr._print_summary({"total_new": 0}, [])
    assert "monitor dry-run summary" in sys.stdout.getvalue()

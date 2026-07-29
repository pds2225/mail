#!/usr/bin/env python3
"""운영 monitor.py 호환 엔트리포인트.

기존 CLI 인자를 그대로 monitor.py에 전달하되, 보호 파일을 수정하지 않고 현재
K-Startup 상세 DOM 어댑터를 먼저 설치한다. 실행 뒤에는 읽기 전용 소량 표본으로
핵심 소스 필드 품질을 기록한다. 품질 기록 실패는 본 수집/발송 결과를 바꾸지 않는다.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "monitor.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _github_command_escape(value: object) -> str:
    return (
        str(value or "")
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def _notify_quality_p0_nonfatal(report: dict) -> None:
    """P0 필드 회귀를 발송 실패로 바꾸지 않고 Actions·폰에 노출."""
    if report.get("status") != "P0":
        return
    issues = [
        str(issue.get("fingerprint") or "")
        for issue in (report.get("issues") or [])
        if issue.get("severity") == "P0"
    ]
    issue_summary = ", ".join(filter(None, issues[:6])) or "unknown"
    message = f"핵심소스 필드 품질 P0: {issue_summary}"
    print(
        f"::error title=Core-source field quality P0::"
        f"{_github_command_escape(message)}",
        file=sys.stderr,
    )

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print(
            "::warning::NTFY_TOPIC 미설정 — P0 폰 알림 생략",
            file=sys.stderr,
        )
        return
    try:
        notification = request.Request(
            f"https://ntfy.sh/{parse.quote(topic, safe='')}",
            data=message.encode("utf-8"),
            headers={
                "Title": "mail core-source quality P0",
                "Priority": "urgent",
                "Tags": "rotating_light",
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST",
        )
        with request.urlopen(notification, timeout=10):
            pass
    except Exception as exc:
        print(
            f"::warning::source field quality P0 ntfy failed (non-fatal): "
            f"{type(exc).__name__}",
            file=sys.stderr,
        )


def _record_quality_nonfatal() -> None:
    if os.environ.get("MONITOR_SKIP_FIELD_QUALITY") == "1":
        return
    try:
        from source_field_quality_gate import run_live_and_record

        report = run_live_and_record()
        _notify_quality_p0_nonfatal(report)
    except Exception as exc:  # 품질 계측은 본 발송을 절대 실패시키지 않는다.
        print(
            f"::warning::source field quality audit failed (non-fatal): "
            f"{type(exc).__name__}: {str(exc)[:160]}",
            file=sys.stderr,
        )


def _run_protected_monitor() -> None:
    """보호 파일 로드 중 상수 정의 직후 런타임 호스트 어댑터를 설치."""
    from mail_core.operations.detail_runtime_adapter import (
        install_priority_detail_hosts_adapter,
    )

    target = os.path.normcase(os.path.abspath(MONITOR))
    previous_trace = sys.gettrace()
    installed = False

    def install_after_host_definition(frame, event, arg):
        nonlocal installed
        frame_path = os.path.normcase(os.path.abspath(frame.f_code.co_filename))
        if (
            not installed
            and event == "line"
            and frame_path == target
            and "DETAIL_ENRICH_HOSTS" in frame.f_globals
        ):
            install_priority_detail_hosts_adapter(frame.f_globals)
            installed = True
            sys.settrace(previous_trace)
            return previous_trace
        return install_after_host_definition

    sys.settrace(install_after_host_definition)
    try:
        runpy.run_path(str(MONITOR), run_name="__main__")
    finally:
        sys.settrace(previous_trace)


def main() -> int:
    from mail_core.operations.detail_runtime_adapter import (
        install_kstartup_body_selector_adapter,
    )

    install_kstartup_body_selector_adapter()
    old_argv0 = sys.argv[0]
    sys.argv[0] = str(MONITOR)
    exit_code = 0
    pending_error: BaseException | None = None
    try:
        _run_protected_monitor()
    except SystemExit as exc:
        exit_code = int(exc.code or 0) if isinstance(exc.code, int) else 1
    except BaseException as exc:  # noqa: BLE001 - 원래 예외를 계측 뒤 재전파
        pending_error = exc
    finally:
        sys.argv[0] = old_argv0
        _record_quality_nonfatal()
    if pending_error is not None:
        raise pending_error
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

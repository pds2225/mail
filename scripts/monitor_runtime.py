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

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "monitor.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _record_quality_nonfatal() -> None:
    if os.environ.get("MONITOR_SKIP_FIELD_QUALITY") == "1":
        return
    try:
        from source_field_quality_gate import run_live_and_record

        run_live_and_record()
    except Exception as exc:  # 품질 계측은 본 발송을 절대 실패시키지 않는다.
        print(
            f"::warning::source field quality audit failed (non-fatal): "
            f"{type(exc).__name__}: {str(exc)[:160]}",
            file=sys.stderr,
        )


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
        runpy.run_path(str(MONITOR), run_name="__main__")
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

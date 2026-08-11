"""Windows exe / 더블클릭용 공고첨부 다운로더 진입점.

PyInstaller 로 묶으면 이 파일이 실행 파일이 된다.
인수 없이 실행(더블클릭)하면 대화형(--interactive) 모드로 들어간다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> Path:
    """실행 파일(또는 저장소) 루트를 잡고 UTF-8/더미 env 를 준비한다."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # monitor.py import 시 필수 env (메일은 안 보냄)
    os.environ.setdefault("BIZINFO_API_KEY", "dummy")
    os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
    os.environ.setdefault("GMAIL_ADDRESS", "dummy@example.com")
    os.environ.setdefault("GMAIL_APP_PASSWORD", "dummy")

    if getattr(sys, "frozen", False):
        # onefile exe: 실제 파일이 있는 폴더
        root = Path(sys.executable).resolve().parent
        # PyInstaller 가 풀어 둔 모듈 경로
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and meipass not in sys.path:
            sys.path.insert(0, str(meipass))
    else:
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    os.environ["MAIL_ATTACH_ROOT"] = str(root)
    return root


def main() -> int:
    _bootstrap()
    # 더블클릭(인수 없음) → 대화형. 인수가 있으면 그대로 전달.
    double_click = len(sys.argv) == 1
    if double_click:
        sys.argv.extend(["--interactive", "--open", "--notify", "--quiet"])

    from scripts.fetch_notice_attachments import main as fetch_main

    code = int(fetch_main() or 0)
    # exe 더블클릭 시 창이 바로 닫히지 않게
    if double_click:
        try:
            input("\nEnter 키를 누르면 종료합니다...")
        except Exception:
            pass
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] {type(exc).__name__}: {exc}")
        try:
            input("\nEnter 키를 누르면 종료합니다...")
        except Exception:
            pass
        raise SystemExit(1)

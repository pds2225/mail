"""비개발자용 공고첨부 다운로더 1회 설치.

Windows 의 ``처음설치_한번만.cmd`` 가 이 스크립트를 호출한다.
- 가상환경(.venv) 생성
- 최소 패키지(requirements-attach.txt) 설치
- 바탕화면 저장 폴더를 notice_download_config.json 에 기록

사용:
    python scripts/setup_attach_downloader.py
    python scripts/setup_attach_downloader.py --check   # 설치됐는지만 확인(0=OK)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
REQ = ROOT / "scripts" / "requirements-attach.txt"
CONFIG = ROOT / "scripts" / "notice_download_config.json"
# 가상환경 생성 실패(ensurepip 없음 등)여도 설치 완료를 표시할 수 있게 루트에 둔다.
MARKER = ROOT / ".attach_setup_ok"


def _desktop_out_dir() -> Path:
    """OS/언어별 바탕화면 후보 중 존재하는 곳에 저장 폴더를 잡는다."""
    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "OneDrive" / "Desktop",
        home / "OneDrive" / "바탕 화면",
        home / "바탕 화면",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" if os.environ.get("USERPROFILE") else None,
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "바탕 화면" if os.environ.get("USERPROFILE") else None,
    ]
    for base in candidates:
        if base and base.is_dir():
            return base / "지원사업_공고첨부"
    return home / "지원사업_공고첨부"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _write_config(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"out_dir": str(out_dir)}
    CONFIG.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _imports_ok(py_exe: str | Path) -> bool:
    try:
        subprocess.run(
            [str(py_exe), "-c", "import httpx, bs4, cryptography"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def is_ready() -> bool:
    if not MARKER.is_file():
        return False
    py = _venv_python()
    if py.is_file() and _imports_ok(py):
        return True
    # 가상환경 없이 시스템 Python 에 설치한 경우
    return _imports_ok(sys.executable)


def _pip_ok(py_exe: str | Path) -> bool:
    try:
        subprocess.run(
            [str(py_exe), "-m", "pip", "--version"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _ensure_pip(py_exe: str | Path, say) -> bool:
    if _pip_ok(py_exe):
        return True
    say("   ⚠ pip 없음 → ensurepip 시도…")
    try:
        subprocess.run(
            [str(py_exe), "-m", "ensurepip", "--upgrade"],
            check=True,
            capture_output=not False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        say(f"   ❌ pip 설치 실패: {exc}")
        return False
    return _pip_ok(py_exe)


def _pip_install(py_exe: str | Path, *, user: bool, verbose: bool) -> None:
    say = (lambda m: print(m)) if verbose else (lambda m: None)
    if not _ensure_pip(py_exe, say):
        raise subprocess.CalledProcessError(1, "ensurepip")
    user_flag = ["--user"] if user else []
    subprocess.run(
        [str(py_exe), "-m", "pip", "install", "--upgrade", "pip", *user_flag],
        check=True,
        capture_output=not verbose,
        timeout=300,
    )
    subprocess.run(
        [str(py_exe), "-m", "pip", "install", "-r", str(REQ), *user_flag],
        check=True,
        capture_output=not verbose,
        timeout=600,
    )


def _ensure_venv(say) -> Path | None:
    """가상환경 Python 경로를 돌려준다. 만들 수 없으면 None."""
    import shutil

    py = _venv_python()
    if py.is_file() and _pip_ok(py):
        say("   ✅ 기존 가상환경 사용")
        return py
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    try:
        venv.create(str(VENV_DIR), with_pip=True, clear=False)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        say(f"   ⚠ 가상환경 생성 실패 → 시스템 Python 으로 설치합니다 ({type(exc).__name__})")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        return None
    if not py.is_file() or not _pip_ok(py):
        say("   ⚠ 가상환경 pip 사용 불가 → 시스템 Python 으로 설치합니다")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        return None
    say("   ✅ 가상환경 생성 완료")
    return py


def run_setup(verbose: bool = True) -> int:
    def say(msg: str) -> None:
        if verbose:
            print(msg)

    say("=" * 52)
    say(" 지원사업 공고첨부 받기 — 처음 설치")
    say("=" * 52)
    say(f" 설치 위치: {ROOT}")
    say(f" Python   : {sys.version.split()[0]}")
    say("")

    if not REQ.is_file():
        print(f"❌ 설치 목록 파일이 없습니다: {REQ}")
        return 1

    say("① 가상환경(.venv) 준비 중…")
    py: Path | str | None = _ensure_venv(say)
    use_user = False
    if py is None:
        py = sys.executable
        use_user = True

    say("② 필요한 프로그램 설치 중… (인터넷 필요, 1~3분)")
    try:
        _pip_install(py, user=use_user, verbose=verbose)
    except subprocess.CalledProcessError as exc:
        print("❌ 패키지 설치에 실패했습니다.")
        print(f"   상세: {exc}")
        print("   Python 재설치 시 [Add python.exe to PATH] 와 [pip] 를 꼭 체크하세요.")
        print("   인터넷·회사 방화벽을 확인한 뒤 다시 실행해 주세요.")
        return 1
    except subprocess.TimeoutExpired:
        print("❌ 설치 시간이 너무 오래 걸려 중단되었습니다. 다시 실행해 주세요.")
        return 1

    if not _imports_ok(py):
        print("❌ 설치 후에도 필수 패키지를 불러오지 못했습니다.")
        return 1

    say("③ 저장 폴더 설정 중…")
    out_dir = _desktop_out_dir()
    _write_config(out_dir)
    say(f"   ✅ 첨부 저장 위치: {out_dir}")

    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text("ok\n", encoding="utf-8")
    say("")
    say("=" * 52)
    say(" ✅ 설치 완료!")
    say(" 이제 「지원사업 공고첨부_받기.cmd」 를 더블클릭하세요.")
    say("=" * 52)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="공고첨부 다운로더 1회 설치")
    parser.add_argument("--check", action="store_true", help="설치 여부만 확인(0=준비됨)")
    parser.add_argument("--quiet", action="store_true", help="안내 문구 최소화")
    args = parser.parse_args()
    if args.check:
        return 0 if is_ready() else 1
    return run_setup(verbose=not args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())

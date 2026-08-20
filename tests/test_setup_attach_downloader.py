"""비개발자용 공고첨부 설치 스크립트 단위 테스트."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.fetch_notice_attachments import _default_out_dir, selfcheck_repo_files
from scripts.setup_attach_downloader import _desktop_out_dir, _write_config, is_ready
import scripts.fetch_notice_attachments as fetch_mod

ROOT = Path(__file__).resolve().parents[1]


def test_default_out_dir_ends_with_folder_name(tmp_path, monkeypatch):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("USERPROFILE", raising=False)
    out = _default_out_dir()
    assert out.name == "지원사업_공고첨부"
    assert out.parent == desk


def test_desktop_out_dir_prefers_existing_desktop(tmp_path, monkeypatch):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert _desktop_out_dir() == desk / "지원사업_공고첨부"


def test_write_config_creates_json(tmp_path, monkeypatch):
    cfg = tmp_path / "notice_download_config.json"
    monkeypatch.setattr("scripts.setup_attach_downloader.CONFIG", cfg)
    out = tmp_path / "지원사업_공고첨부"
    _write_config(out)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["out_dir"] == str(out)
    assert out.is_dir()


def test_is_ready_false_without_venv(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.setup_attach_downloader.VENV_DIR", tmp_path / "missing_venv")
    monkeypatch.setattr(
        "scripts.setup_attach_downloader.MARKER",
        tmp_path / "missing_venv" / ".attach_setup_ok",
    )
    assert is_ready() is False


def test_oneclick_launcher_files_exist():
    required = [
        ROOT / "처음설치_한번만.cmd",
        ROOT / "지원사업 공고첨부_받기.cmd",
        ROOT / "배포용_압축하기.cmd",
        ROOT / "사용방법_공고첨부.txt",
        ROOT / "오류해결.txt",
        ROOT / "scripts" / "setup_attach_downloader.py",
        ROOT / "scripts" / "requirements-attach.txt",
        ROOT / "scripts" / "attach_downloader_app.py",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    assert missing == []


def test_first_install_cmd_mentions_setup_script():
    text = (ROOT / "처음설치_한번만.cmd").read_text(encoding="utf-8", errors="replace")
    assert "setup_attach_downloader.py" in text
    assert "Python.Python.3.12" in text


def test_selfcheck_skipped_when_frozen(monkeypatch):
    monkeypatch.setattr(fetch_mod.sys, "frozen", True, raising=False)
    assert selfcheck_repo_files() == 0

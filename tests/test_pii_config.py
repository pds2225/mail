"""PII 격리 로더 회귀 테스트 (진단서 #96·#149).

실 수신자(groups.json)·기업 프로필(companies.json)을 Git 평문 커밋 대신 환경변수(GitHub Secret)
로 주입할 수 있어야 한다. 환경변수 우선, 없거나 깨지면 파일로 폴백(운영 중단 방지).
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")
os.environ.setdefault("NTFY_TOPIC", "x")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monitor as m  # noqa: E402


def test_env_json_overrides_file(monkeypatch):
    called = {"file": False}
    def file_loader():
        called["file"] = True
        return [{"id": "from_file"}]
    monkeypatch.setenv("MAIL_TEST_CFG", json.dumps([{"id": "from_env"}]))
    out = m._pii_config("MAIL_TEST_CFG", file_loader)
    assert out == [{"id": "from_env"}] and called["file"] is False   # 환경변수 우선, 파일 미접근


def test_missing_env_falls_back_to_file(monkeypatch):
    monkeypatch.delenv("MAIL_TEST_CFG", raising=False)
    out = m._pii_config("MAIL_TEST_CFG", lambda: [{"id": "from_file"}])
    assert out == [{"id": "from_file"}]


def test_broken_env_falls_back_to_file(monkeypatch):
    monkeypatch.setenv("MAIL_TEST_CFG", "{not json")
    out = m._pii_config("MAIL_TEST_CFG", lambda: [{"id": "from_file"}])
    assert out == [{"id": "from_file"}]                              # 깨진 값 → 파일 폴백(중단 없음)


def test_load_groups_honors_env(monkeypatch):
    monkeypatch.setenv("MAIL_GROUPS_JSON", json.dumps([
        {"id": "g1", "name": "그룹1", "active": True, "recipients": ["a@corp.com"]},
        {"id": "g2", "name": "비활성", "active": False},
    ]))
    groups = m.load_groups()
    ids = {g["id"] for g in groups}
    assert ids == {"g1"}                                            # active 만, 환경변수 소스에서

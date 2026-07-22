"""config_env 로더 + load_groups/load_companies 환경변수 주입(PII 미커밋) 회귀 테스트.

핵심 계약:
- MAIL_GROUPS_JSON / MAIL_COMPANIES_JSON 가 설정되면 그 값(인라인 JSON 또는 파일경로)을
  우선 사용하고, 없거나 파싱 실패면 기존 파일로 폴백한다(하위호환).
- load_companies(path=...) 처럼 경로가 명시되면 환경변수를 무시한다(테스트 하위호환).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config_env  # noqa: E402
import company_match  # noqa: E402


# ── config_env.load_config ────────────────────────────────────────────────────

def test_env_inline_json_list(monkeypatch):
    monkeypatch.setenv("CFG_TEST", '[{"id": "a"}, {"id": "b"}]')
    out = config_env.load_config("CFG_TEST", ROOT / "____nope____.json", [])
    assert out == [{"id": "a"}, {"id": "b"}]


def test_env_inline_json_dict(monkeypatch):
    monkeypatch.setenv("CFG_TEST", '{"companies": [{"id": "a"}]}')
    out = config_env.load_config("CFG_TEST", ROOT / "____nope____.json", None)
    assert out == {"companies": [{"id": "a"}]}


def test_env_as_file_path(monkeypatch, tmp_path):
    f = tmp_path / "payload.json"
    f.write_text(json.dumps([{"id": "z"}]), encoding="utf-8")
    monkeypatch.setenv("CFG_TEST", str(f))
    out = config_env.load_config("CFG_TEST", ROOT / "____nope____.json", [])
    assert out == [{"id": "z"}]


def test_env_unset_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CFG_TEST", raising=False)
    f = tmp_path / "file.json"
    f.write_text(json.dumps({"k": 1}), encoding="utf-8")
    out = config_env.load_config("CFG_TEST", f, None)
    assert out == {"k": 1}


def test_env_blank_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CFG_TEST", "   ")  # 공백만 → 미설정 취급
    f = tmp_path / "file.json"
    f.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    out = config_env.load_config("CFG_TEST", f, [])
    assert out == [1, 2, 3]


def test_env_invalid_json_falls_back_and_calls_on_error(monkeypatch, tmp_path):
    monkeypatch.setenv("CFG_TEST", "{not valid json")
    f = tmp_path / "file.json"
    f.write_text(json.dumps({"ok": True}), encoding="utf-8")
    seen = []
    out = config_env.load_config("CFG_TEST", f, None, on_error=seen.append)
    assert out == {"ok": True}
    assert len(seen) == 1 and isinstance(seen[0], Exception)


def test_env_bad_path_falls_back_to_file(monkeypatch, tmp_path):
    # 인라인 JSON 이 아니고 존재하지 않는 경로 → OSError → 파일 폴백
    monkeypatch.setenv("CFG_TEST", str(tmp_path / "missing_payload.json"))
    f = tmp_path / "file.json"
    f.write_text(json.dumps([9]), encoding="utf-8")
    out = config_env.load_config("CFG_TEST", f, [])
    assert out == [9]


def test_all_missing_returns_default(monkeypatch):
    monkeypatch.delenv("CFG_TEST", raising=False)
    out = config_env.load_config("CFG_TEST", ROOT / "____nope____.json", "DEFAULT")
    assert out == "DEFAULT"


def test_env_never_leaks_pii_on_error(monkeypatch, caplog):
    """파싱 실패 예외 문자열에 원문(이메일 등)이 새지 않아야 한다."""
    secret = "top-secret@example.com"
    monkeypatch.setenv("CFG_TEST", "{bad " + secret)  # 유효하지 않은 JSON, PII 포함
    captured = []
    config_env.load_config("CFG_TEST", ROOT / "____nope____.json", None,
                           on_error=lambda e: captured.append(str(e)))
    assert captured, "on_error 가 호출되어야 함"
    assert secret not in captured[0]


# ── monitor.load_groups (MAIL_GROUPS_JSON) ────────────────────────────────────

def test_load_groups_env_override(monkeypatch):
    import monitor
    groups = [
        {"id": "g_env", "name": "env group", "active": True},
        {"id": "g_off", "name": "inactive", "active": False},
    ]
    monkeypatch.setenv("MAIL_GROUPS_JSON", json.dumps(groups))
    out = monitor.load_groups()
    ids = {g["id"] for g in out}
    assert "g_env" in ids
    assert "g_off" not in ids  # active=False 는 제외


def test_load_groups_env_unset_uses_file(monkeypatch):
    import monitor
    monkeypatch.delenv("MAIL_GROUPS_JSON", raising=False)
    out = monitor.load_groups()
    # 레포 groups.json 이 그대로 로드되어야 함(회귀 방지)
    assert isinstance(out, list)
    assert len(out) >= 1


def test_load_groups_env_non_list_is_safe(monkeypatch):
    import monitor
    monkeypatch.setenv("MAIL_GROUPS_JSON", '{"oops": "dict not list"}')
    out = monitor.load_groups()
    assert out == []  # 리스트가 아니면 빈 목록(크래시 없음)


# ── company_match.load_companies (MAIL_COMPANIES_JSON) ─────────────────────────

def test_load_companies_env_override(monkeypatch):
    data = {"companies": [
        {"id": "c_env", "email": company_match.TEST_RECIPIENT, "active": True},
        {"id": "c_off", "email": company_match.TEST_RECIPIENT, "active": False},
    ]}
    monkeypatch.setenv("MAIL_COMPANIES_JSON", json.dumps(data))
    out = company_match.load_companies()  # path 미지정 → env 우선
    ids = {c["id"] for c in out}
    assert ids == {"c_env"}


def test_load_companies_env_inline_bare_list(monkeypatch):
    # 최상위가 배열(companies 래핑 없음)이어도 지원
    monkeypatch.setenv("MAIL_COMPANIES_JSON",
                       json.dumps([{"id": "solo", "email": company_match.TEST_RECIPIENT}]))
    out = company_match.load_companies()
    assert [c["id"] for c in out] == ["solo"]


def test_load_companies_explicit_path_ignores_env(monkeypatch, tmp_path):
    # env 가 설정돼 있어도 명시 path 가 이기고, env 는 무시된다(하위호환).
    monkeypatch.setenv("MAIL_COMPANIES_JSON",
                       json.dumps({"companies": [{"id": "from_env",
                                                  "email": company_match.TEST_RECIPIENT}]}))
    p = tmp_path / "companies.json"
    p.write_text(json.dumps({"companies": [{"id": "from_path",
                                            "email": company_match.TEST_RECIPIENT}]}),
                 encoding="utf-8")
    out = company_match.load_companies(p)
    assert [c["id"] for c in out] == ["from_path"]


def test_load_companies_env_invalid_falls_back_to_file(monkeypatch):
    # env 가 깨진 JSON 이면 레포 companies.json 으로 폴백(빈 목록이 아님).
    monkeypatch.setenv("MAIL_COMPANIES_JSON", "{broken")
    out = company_match.load_companies()
    assert len(out) >= 1
    assert all(c["email"] == company_match.TEST_RECIPIENT for c in out)

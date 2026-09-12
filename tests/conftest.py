"""pytest 공통 설정 — monitor import 크래시 방지 env 단일화.

monitor.py 는 import 시점에 `_require_env` 로 4개 키를 요구한다. 테스트 수집
초기에 import 되는 conftest 가 멱등 setdefault 로 env 를 보장하면, 각 테스트
파일이 보일러플레이트 없이 `import monitor` 할 수 있다.

setdefault 만 사용하므로 이미 env 가 있으면 덮어쓰지 않는다(멱등·무해). 기존
test_*.py 들도 동일한 setdefault 를 자체적으로 수행하므로 동작 변화 없음.
seen_ids 저장 차단(MONITOR_NO_PERSIST_SEEN=1)으로 실저장도 방지.
"""
import os

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

import pytest


@pytest.fixture(autouse=True)
def isolate_private_config_db(tmp_path, monkeypatch):
    """테스트가 워크스페이스 ``secrets/mail_private.sqlite3`` 을 읽지 않게 한다.

    #284 이후 ciphertext 가 있는데 키가 없으면 load 가 fail-closed 로 예외를 낸다.
    수집/스코어링 테스트는 그 운영 DB 와 무관해야 한다. 명시 경로를 넘기는
    private-config 테스트는 이 fixture 의 기본 경로를 쓰지 않으므로 그대로다.
    """
    isolated = tmp_path / "isolated_mail_private.sqlite3"
    monkeypatch.setattr("mail_core.security.private_config.PRIVATE_DB_PATH", isolated)

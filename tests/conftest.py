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

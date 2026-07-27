"""발송 멱등·체크포인트 회귀 테스트 (진단서 #113·#114·#115·#116·#144).

delivery_state 모듈(순수)과 monitor.send_to_list 의 idem 경로를 검증한다.
핵심 성질:
  · (일자·그룹·수신자) 단위 멱등 — 재실행 시 성공 수신자 중복 발송 없음
  · 발송 성공 즉시 체크포인트 저장 — 부분실패 후 재실행이 실패분만 재시도
  · idem 없으면 종전 동작(전량 발송) 하위호환
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")
os.environ.setdefault("NTFY_TOPIC", "x")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mail_core.delivery import state as ds  # noqa: E402
import monitor as m  # noqa: E402


# ── delivery_state 순수 모듈 ──
def test_key_normalizes_recipient():
    assert ds.key("2026-07-21", "g_ai", " A@B.com ") == ds.key("2026-07-21", "g_ai", "a@b.com")
    assert ds.key("2026-07-21", "g_ai", "a@b.com") != ds.key("2026-07-21", "g_incheon", "a@b.com")


def test_load_missing_or_broken_is_empty(tmp_path):
    assert ds.load(tmp_path / "nope.json") == set()
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    assert ds.load(p) == set()


def test_save_load_roundtrip_atomic(tmp_path):
    p = tmp_path / "d.json"
    keys = {ds.key("2026-07-21", "g", "a@b.com"), ds.key("2026-07-21", "g", "c@d.com")}
    ds.save(p, keys)
    assert ds.load(p) == keys
    assert "@" not in p.read_text(encoding="utf-8")
    # 트레일링 개행 없음(seen_ids 포맷 규약)
    assert not p.read_text(encoding="utf-8").endswith("\n")


def test_prune_keeps_recent_dates(tmp_path):
    p = tmp_path / "d.json"
    keys = {f"2026-06-{d:02d}|g|a@b.com" for d in range(1, 1 + ds.MAX_KEEP_DATES + 5)}
    ds.save(p, keys)
    loaded = ds.load(p)
    dates = {k.split("|", 1)[0] for k in loaded}
    assert len(dates) == ds.MAX_KEEP_DATES          # 최근 N일만 유지
    assert "2026-06-01" not in dates                 # 가장 오래된 날짜 잘림


def test_mark_checkpoints_immediately(tmp_path):
    p = tmp_path / "d.json"
    key = ds.key("2026-07-21", "g", "a@b.com")
    cache = ds.mark(p, key)
    assert key in cache
    assert ds.load(p) == cache                        # 즉시 파일에 반영(체크포인트)


# ── monitor.send_to_list 멱등 경로 ──
def _arm_send(monkeypatch):
    """SMTP 게이트 열고 send_email 을 카운터로 대체. (호출된 수신자, 강제실패셋) 제어."""
    calls = []
    fail = set()
    monkeypatch.setattr(m, "_ALLOW_SMTP_SEND", True)
    monkeypatch.setattr(m, "_DRAFT_MODE", False)
    monkeypatch.setattr(m, "_ONLY_TO", None, raising=False)

    def fake_send(subject, body, to):
        calls.append(to)
        if to in fail:
            raise RuntimeError("smtp boom")
    monkeypatch.setattr(m, "send_email", fake_send)
    # validate_recipients 는 실제 정규식 사용(유효 주소만 통과)
    return calls, fail


def test_idempotent_skip_on_rerun(tmp_path, monkeypatch):
    calls, _ = _arm_send(monkeypatch)
    idem = {"date": "2026-07-21", "group": "g_ai", "path": str(tmp_path / "d.json")}
    recips = ["a@b.com", "c@d.com"]
    m.send_to_list("s", "b", recips, idem=idem)
    assert sorted(calls) == ["a@b.com", "c@d.com"]     # 1차: 전원 발송
    m.send_to_list("s", "b", recips, idem=idem)        # 2차(재실행): 전원 멱등 skip
    assert sorted(calls) == ["a@b.com", "c@d.com"]     # 추가 발송 0건


def test_partial_failure_retries_only_failed(tmp_path, monkeypatch):
    calls, fail = _arm_send(monkeypatch)
    fail.add("c@d.com")                                 # c 는 1차에서 실패
    idem = {"date": "2026-07-21", "group": "g_ai", "path": str(tmp_path / "d.json")}
    recips = ["a@b.com", "c@d.com"]
    m.send_to_list("s", "b", recips, idem=idem)         # a 성공(체크포인트), c 실패(미기록)
    fail.discard("c@d.com")                             # c 복구
    calls.clear()
    m.send_to_list("s", "b", recips, idem=idem)         # 재실행: a skip, c 만 재시도
    assert calls == ["c@d.com"]


def test_no_idem_is_backward_compatible(tmp_path, monkeypatch):
    calls, _ = _arm_send(monkeypatch)
    recips = ["a@b.com", "c@d.com"]
    m.send_to_list("s", "b", recips)                    # idem 없음 → 종전 전량 발송
    m.send_to_list("s", "b", recips)                    # 다시 호출해도 멱등 없음(전량 재발송)
    assert calls.count("a@b.com") == 2 and calls.count("c@d.com") == 2

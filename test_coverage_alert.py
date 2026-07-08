"""커버리지 이상탐지 회귀 테스트 (오프라인·결정적, 네트워크/SMTP/ntfy 없음).

목적 고정: "평소 N건 수집되던 사이트가 오늘 0건/급감/수집실패하면 감지·알림".
보수성(오탐 방지) 고정: 신규/이력없음 사이트는 절대 알림하지 않고, 안정 상태도 알림하지 않는다.
실제 전송 0: alert_ntfy 를 monkeypatch 로 가로채 네트워크를 차단한다.
실제 baseline 파일 오염 0: run_coverage_anomaly_check 의 load/save 를 monkeypatch 한다.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import coverage_alert as ca  # noqa: E402


def _row(site_id, *, item_count, fetch_success=True, fetch_error="", enabled=True, name=None):
    return {
        "site_id": site_id,
        "site_name": name or site_id.upper(),
        "enabled": enabled,
        "fetch_success": fetch_success,
        "fetch_error": fetch_error,
        "item_count": item_count,
        "url": f"https://example.com/{site_id}",
    }


def _entry(day, item_count):
    return {"date": day, "item_count": item_count}


# ── detect ───────────────────────────────────────────────────────────────────
def test_detect_healthy_drop_to_zero_is_high():
    """(a) 평소 충분(>=min_healthy)했는데 오늘 0건 → high 1건."""
    rows = [_row("a", item_count=0)]
    baseline = {"a": [5, 6, 5, 7]}
    anomalies = ca.detect_coverage_anomalies(rows, baseline)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a["severity"] == "high"
    assert a["reason"] == "0건 급락"
    assert a["current"] == 0
    assert a["baseline"] == 5.5  # median([5,6,5,7])


def test_detect_stable_is_no_alert():
    """(b) 현재≈baseline → 알림 없음."""
    rows = [_row("a", item_count=6)]
    baseline = {"a": [5, 6, 5, 7]}
    assert ca.detect_coverage_anomalies(rows, baseline) == []


def test_detect_new_site_no_history_is_no_alert():
    """(c) 이력 없는 신규 사이트는 0건이어도 알림하지 않음(첫 실행 오탐 방지)."""
    rows = [_row("b", item_count=0)]
    baseline = {"a": [5, 6]}  # b 이력 없음
    assert ca.detect_coverage_anomalies(rows, baseline) == []


def test_detect_fetch_fail_is_high():
    """(d) 평소 수집됐는데 오늘 수집 실패 → high '수집실패'."""
    rows = [_row("a", item_count=0, fetch_success=False, fetch_error="timeout")]
    baseline = {"a": [4, 5, 6]}
    anomalies = ca.detect_coverage_anomalies(rows, baseline)
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "high"
    assert anomalies[0]["reason"] == "수집실패"


def test_detect_fetch_fail_even_when_history_was_zero_polluted():
    """과거 0건 학습으로 대표값이 0이어도 수집실패는 high 로 감지."""
    rows = [_row("a", item_count=0, fetch_success=False, fetch_error="timeout")]
    baseline = {"a": [0] * 14}
    anomalies = ca.detect_coverage_anomalies(rows, baseline)
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "high"
    assert anomalies[0]["reason"] == "수집실패"


def test_detect_sharp_drop_is_medium():
    """(e) floor 이상 baseline 인데 current>0 이고 ratio 미만 → medium '급감'."""
    rows = [_row("a", item_count=3)]  # baseline median 10, 10*0.5=5 > 3
    baseline = {"a": [10, 10, 12, 9]}
    anomalies = ca.detect_coverage_anomalies(rows, baseline)
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "medium"
    assert anomalies[0]["reason"] == "급감"


def test_detect_disabled_site_ignored():
    """enabled=False 사이트는 비교 대상 제외."""
    rows = [_row("a", item_count=0, enabled=False)]
    baseline = {"a": [5, 6, 5]}
    assert ca.detect_coverage_anomalies(rows, baseline) == []


def test_detect_low_baseline_does_not_trip_medium():
    """대표값이 floor 미만이면 작은 변동은 급감으로 보지 않음(오탐 방지)."""
    rows = [_row("a", item_count=0)]
    baseline = {"a": [1, 1, 1]}  # rep=1 >= min_healthy=1 → 0건은 high 로 잡힘
    anomalies = ca.detect_coverage_anomalies(rows, baseline)
    # rep(1) >= min_healthy(1) 이고 item_count==0 → high 1건 (0건 급락은 항상 위험)
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "high"


def test_detect_zero_polluted_history_still_uses_healthy_counts():
    """이미 0건 이력이 섞여 있어도 남은 정상 양수 이력으로 급락을 감지."""
    rows = [_row("a", item_count=0)]
    baseline = {"a": [5, 6] + [0] * 12}
    anomalies = ca.detect_coverage_anomalies(rows, baseline)
    assert len(anomalies) == 1
    assert anomalies[0]["reason"] == "0건 급락"


# ── update ───────────────────────────────────────────────────────────────────
def test_update_appends_only_success_days():
    """성공일만 append, 실패일은 baseline 미오염."""
    baseline = {"a": [5]}
    rows = [
        _row("a", item_count=6),  # 성공 → append
        _row("a", item_count=0, fetch_success=False, fetch_error="x"),  # 실패 → 무시
    ]
    # 같은 site_id 가 둘이면 마지막 성공만 의미 있지만, 여기선 성공 1건만 반영되는지 확인
    updated = ca.update_coverage_baseline({"a": [5]}, [rows[0]], today="2026-06-22")
    assert updated["a"] == [5, _entry("2026-06-22", 6)]
    # 실패 row 만 주면 baseline 변화 없음
    updated_fail = ca.update_coverage_baseline({"a": [5]}, [rows[1]], today="2026-06-22")
    assert updated_fail["a"] == [5]


def test_update_window_drops_oldest():
    """window 초과 시 가장 오래된 값 drop."""
    baseline = {"a": [1, 2, 3]}
    rows = [_row("a", item_count=4)]
    updated = ca.update_coverage_baseline(baseline, rows, window=3, today="2026-06-22")
    assert updated["a"] == [2, 3, _entry("2026-06-22", 4)]  # 1 drop, 4 append


def test_update_new_site_starts_history():
    """이력 없던 사이트도 성공일이면 새 리스트로 시작."""
    updated = ca.update_coverage_baseline({}, [_row("z", item_count=9)], today="2026-06-22")
    assert updated["z"] == [_entry("2026-06-22", 9)]


def test_update_does_not_mutate_input():
    """입력 baseline 을 직접 변형하지 않는다(부작용 없음)."""
    baseline = {"a": [5]}
    ca.update_coverage_baseline(baseline, [_row("a", item_count=6)])
    assert baseline == {"a": [5]}


def test_update_skips_anomalous_zero_to_preserve_baseline():
    """성공 응답 0건 급락은 baseline 에 학습하지 않아 반복 알림 가능성을 유지."""
    baseline = {"a": [5, 6, 5, 7]}
    rows = [_row("a", item_count=0)]
    updated = ca.update_coverage_baseline(baseline, rows, today="2026-06-22")
    assert updated["a"] == [5, 6, 5, 7]


def test_update_replaces_same_day_entry():
    """같은 날짜 재실행은 window 슬롯을 추가로 쓰지 않고 마지막 값을 교체."""
    baseline = {"a": [5, _entry("2026-06-22", 6)]}
    rows = [_row("a", item_count=7)]
    updated = ca.update_coverage_baseline(baseline, rows, today="2026-06-22")
    assert updated["a"] == [5, _entry("2026-06-22", 7)]


# ── format ───────────────────────────────────────────────────────────────────
def test_format_high_first_and_core_fields():
    """high 우선 정렬 + 핵심필드(사이트명·reason·baseline·current) 포함."""
    anomalies = [
        {"site_id": "m", "site_name": "MED", "severity": "medium",
         "reason": "급감", "baseline": 10, "current": 3, "url": "u"},
        {"site_id": "h", "site_name": "HIGH", "severity": "high",
         "reason": "0건 급락", "baseline": 5, "current": 0, "url": "u"},
    ]
    msg = ca.format_anomaly_message(anomalies)
    lines = msg.splitlines()
    assert lines[0].find("HIGH") != -1  # high 가 먼저
    assert "MED" in msg
    assert "0건 급락" in msg and "급감" in msg
    assert "5" in lines[0] and "0건" in lines[0]


def test_format_empty():
    assert ca.format_anomaly_message([]) == "수집 이상 없음"


# ── alert / run_coverage_anomaly_check (실전송 0, 실파일 오염 0) ───────────────
def test_run_coverage_anomaly_check_no_network_no_real_file(monkeypatch, tmp_path):
    """run_coverage_anomaly_check: ntfy 모킹으로 네트워크 0, baseline 을 tmp 로 격리."""
    import monitor as m

    # baseline 입출력을 tmp 파일로 격리 (실제 coverage_baseline.json 오염 금지)
    import json as _json
    bpath = tmp_path / "cb.json"

    def _load(*a, **k):
        return _json.loads(bpath.read_text(encoding="utf-8")) if bpath.exists() else {}

    def _save(data, *a, **k):
        bpath.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(ca, "load_coverage_baseline", _load)
    monkeypatch.setattr(ca, "save_coverage_baseline", _save)

    # 실제 이메일 발송 차단 + 호출 캡처 (알림은 폰 ntfy → PC 이메일로 전환됨)
    calls = []
    monkeypatch.setattr(m, "alert_email", lambda *a, **k: calls.append((a, k)))

    # 사전 baseline: a 는 평소 5~7건
    _save({"a": [5, 6, 5, 7]})

    rows = [_row("a", item_count=0)]  # 오늘 0건 → high
    anomalies = m.run_coverage_anomaly_check(rows, allow_alert=True)

    assert len(anomalies) == 1 and anomalies[0]["severity"] == "high"
    assert len(calls) == 1  # high 1건 → PC(이메일) 알림 1회
    # baseline 갱신: 0건 급락은 fetch_success=True 여도 정상으로 학습하지 않음(오염 방지)
    assert _load()["a"] == [5, 6, 5, 7]
    # 실제 파일은 건드리지 않음
    assert not (m.BASE_DIR / "coverage_baseline.json").exists()


def test_run_coverage_anomaly_check_no_alert_when_allow_false(monkeypatch, tmp_path):
    """allow_alert=False 면 high 가 있어도 ntfy 호출 안 함."""
    import monitor as m
    import json as _json

    bpath = tmp_path / "cb.json"
    monkeypatch.setattr(ca, "load_coverage_baseline",
                        lambda *a, **k: _json.loads(bpath.read_text("utf-8")) if bpath.exists() else {})
    monkeypatch.setattr(ca, "save_coverage_baseline",
                        lambda data, *a, **k: bpath.write_text(_json.dumps(data), encoding="utf-8"))
    calls = []
    monkeypatch.setattr(m, "alert_email", lambda *a, **k: calls.append(1))

    bpath.write_text(_json.dumps({"a": [5, 6, 5]}), encoding="utf-8")
    rows = [_row("a", item_count=0)]
    anomalies = m.run_coverage_anomaly_check(rows, allow_alert=False)
    assert len(anomalies) == 1  # 감지는 됨
    assert calls == []  # 알림은 안 함


def test_run_coverage_anomaly_check_no_alert_when_healthy(monkeypatch, tmp_path):
    """안정 상태면 알림 없음."""
    import monitor as m
    import json as _json

    bpath = tmp_path / "cb.json"
    monkeypatch.setattr(ca, "load_coverage_baseline",
                        lambda *a, **k: _json.loads(bpath.read_text("utf-8")) if bpath.exists() else {})
    monkeypatch.setattr(ca, "save_coverage_baseline",
                        lambda data, *a, **k: bpath.write_text(_json.dumps(data), encoding="utf-8"))
    calls = []
    monkeypatch.setattr(m, "alert_email", lambda *a, **k: calls.append(1))

    bpath.write_text(_json.dumps({"a": [5, 6, 5]}), encoding="utf-8")
    anomalies = m.run_coverage_anomaly_check([_row("a", item_count=6)], allow_alert=True)
    assert anomalies == []
    assert calls == []

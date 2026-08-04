"""기업마당(Bizinfo) 수집 폴백·워밍업·빠른실패 회귀 테스트.

배경: bizinfo.go.kr 직결 API 가 GitHub Actions 러너 IP 에서 WAF/지역차단(timeout)돼 수집 실패.
수정: (a) 직결에 워밍업 세션+빠른실패, (b) DATA_GO_KR_KEY 있으면 data.go.kr 폴백.
핵심 성질(직결 실패 신호 규약 보존):
  · 직결이 건을 모으면 그대로 사용(폴백 안 탐)
  · 직결 하드 실패 + 키 없음 → 예외 재발생(커버리지 '수집실패' 신호 유지)
  · 직결 하드 실패 + 키 있음 → data.go.kr 폴백
  · 0건은 fail-closed(예외) — BIZINFO_ALLOW_EMPTY=1 일 때만 [] 허용 (TASK-03)
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")
os.environ.setdefault("NTFY_TOPIC", "x")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monitor as m  # noqa: E402

SITE = {"name": "기업마당(Bizinfo)", "url": "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do",
        "is_aggregator": True}


def test_datagokr_rows_envelope_variants():
    std = {"response": {"body": {"items": {"item": [{"pblancId": "a"}, {"pblancId": "b"}]}}}}
    assert len(m._datagokr_rows(std)) == 2
    assert len(m._datagokr_rows({"jsonArray": [{"pblancId": "c"}]})) == 1
    # 단건 dict → 리스트로 승격
    single = {"response": {"body": {"items": {"item": {"pblancId": "z"}}}}}
    assert len(m._datagokr_rows(single)) == 1
    assert m._datagokr_rows({}) == []


def test_parse_item_common_fields():
    it = m._bizinfo_parse_item(
        {"pblancId": "p1", "pblancNm": "제목", "pblancUrl": "http://x",
         "regDt": "2026-07-21 10:00", "bsnsSumryCn": "요약"}, "기업마당", True)
    assert it["id"] == "p1" and it["posted_date"] == "2026-07-21"
    assert it["source"] == "기업마당" and it["is_aggregator"] is True


def test_direct_success_skips_fallback(monkeypatch):
    """키 없음(직결 전용): 직결 성공이면 data.go.kr 은 호출하지 않는다.

    ★ DATA_GO_KR_KEY 를 명시적으로 비운다 — 환경(.env)에 키가 있으면 data.go.kr 우선이라
      직결 mock 이 안 돌아 이 테스트가 무의미해진다(순서 의존 제거).
    """
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "")
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", lambda s: [m._item("i1", "T", "", "", "", "", s["name"])])
    called = {"fb": False}
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", lambda s: called.__setitem__("fb", True) or [])
    out = m.fetch_bizinfo(SITE)
    assert len(out) == 1 and called["fb"] is False


def test_direct_fail_no_key_reraises(monkeypatch):
    def boom(s):
        raise RuntimeError("기업마당 API 접속 실패 (page 1, 3회 시도)")
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", boom)
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "")
    try:
        m.fetch_bizinfo(SITE)
        assert False, "예외가 나야 함(커버리지 수집실패 신호)"
    except RuntimeError as e:
        assert "접속 실패" in str(e)


def test_datagokr_primary_used_when_key(monkeypatch):
    """키 있으면 data.go.kr 우선(검증됨) — 성공하면 bizinfo 직결은 호출하지 않는다."""
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr",
                        lambda s: [m._item("g1", "DG", "", "", "", "", s["name"])])
    called = {"direct": False}
    monkeypatch.setattr(m, "_fetch_bizinfo_direct",
                        lambda s: called.__setitem__("direct", True) or [m._item("x", "X", "", "", "", "", s["name"])])
    out = m.fetch_bizinfo(SITE)
    assert len(out) == 1 and out[0]["id"] == "g1" and called["direct"] is False


def test_fall_to_direct_when_datagokr_hard_fails(monkeypatch):
    """data.go.kr 이 하드 실패하면 bizinfo 직결로 폴백한다."""
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    def boom(s):
        raise RuntimeError("data.go.kr 오류")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", boom)
    monkeypatch.setattr(m, "_fetch_bizinfo_direct",
                        lambda s: [m._item("d1", "DIRECT", "", "", "", "", s["name"])])
    out = m.fetch_bizinfo(SITE)
    assert len(out) == 1 and out[0]["id"] == "d1"


def test_direct_empty_no_key_raises_fail_closed(monkeypatch):
    """0건은 fail-closed — 키 없이 직결만 있으면 RuntimeError."""
    monkeypatch.delenv("BIZINFO_ALLOW_EMPTY", raising=False)
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", lambda s: [])
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "")
    with pytest.raises(RuntimeError, match="fail-closed"):
        m.fetch_bizinfo(SITE)


def test_direct_empty_allowed_when_env_set(monkeypatch):
    """BIZINFO_ALLOW_EMPTY=1 이면 0건 [] 허용."""
    monkeypatch.setenv("BIZINFO_ALLOW_EMPTY", "1")
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", lambda s: [])
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "")
    assert m.fetch_bizinfo(SITE) == []


def test_datagokr_requires_key(monkeypatch):
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "")
    try:
        m._fetch_bizinfo_datagokr(SITE)
        assert False
    except RuntimeError as e:
        assert "DATA_GO_KR_KEY" in str(e)


def test_both_paths_hard_fail_raises(monkeypatch):
    """두 경로 모두 하드 실패 → 0건으로 숨기지 않고 예외를 올린다(커버리지 수집실패 신호)."""
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    def dg_boom(s):
        raise RuntimeError("data.go.kr 오류: 트래픽초과")
    def direct_boom(s):
        raise RuntimeError("기업마당 API 접속 실패 (timeout)")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", dg_boom)
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", direct_boom)
    try:
        m.fetch_bizinfo(SITE)
        assert False, "둘 다 하드 실패면 예외여야 함"
    except RuntimeError as e:
        assert "data.go.kr 오류" in str(e)   # 첫 경로(primary) 예외를 대표로 올린다


def test_datagokr_error_envelope_detected():
    """data.go.kr 200-OK 에러 봉투(resultCode/returnReasonCode)를 에러로 인식."""
    # 표준 header
    assert m._datagokr_error(
        {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}}})
    # 레거시 cmmMsgHeader
    assert m._datagokr_error(
        {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"returnReasonCode": "22", "errMsg": "LIMITED"}}})
    # 성공 코드는 에러 아님
    assert m._datagokr_error({"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL"}}}) == ""
    assert m._datagokr_error({"response": {"header": {"resultCode": "0000"}}}) == ""
    assert m._datagokr_error({}) == ""


def test_datagokr_raises_on_error_header(monkeypatch):
    """폴백이 에러 봉투를 받으면(빈 items) '진짜 0건'이 아니라 RuntimeError."""
    class _Resp:
        def json(self):
            return {"response": {"header": {"resultCode": "30", "resultMsg": "NO KEY"}},
                    "body": {"items": ""}}
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_http_get", lambda *a, **k: _Resp())
    try:
        m._fetch_bizinfo_datagokr(SITE)
        assert False, "에러 봉투는 예외여야 함"
    except RuntimeError as e:
        assert "data.go.kr 오류" in str(e)


def test_datagokr_zero_falls_through_to_direct(monkeypatch):
    """primary 0건은 fail-closed → 직결 폴백을 시도한다(TASK-03)."""
    monkeypatch.delenv("BIZINFO_ALLOW_EMPTY", raising=False)
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", lambda s: [])
    called = {"direct": False}
    monkeypatch.setattr(
        m,
        "_fetch_bizinfo_direct",
        lambda s: called.__setitem__("direct", True)
        or [m._item("z", "Z", "", "", "", "", s["name"])],
    )
    out = m.fetch_bizinfo(SITE)
    assert called["direct"] is True
    assert len(out) == 1 and out[0]["id"] == "z"


def test_datagokr_retries_transient_failure(monkeypatch):
    """폴백도 api_retries 만큼 재시도(첫 시도 None → 재시도 성공)."""
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_HTTP_RETRY_BACKOFF", 0)  # 테스트 즉시 실행
    calls = {"n": 0}

    class _Resp:
        def json(self):
            return {"response": {"header": {"resultCode": "00"},
                    "body": {"items": {"item": [{"pblancId": "r1", "pblancNm": "T"}]}}}}

    def fake_get(*a, **k):
        calls["n"] += 1
        return None if calls["n"] == 1 else _Resp()   # 1회차 실패 → 재시도 성공
    monkeypatch.setattr(m, "_http_get", fake_get)
    out = m._fetch_bizinfo_datagokr({**SITE, "api_retries": 2, "datagokr_max_pages": 1})
    assert len(out) == 1 and calls["n"] == 2   # 재시도로 성공(1 실패 + 1 성공)


def test_datagokr_happy_path(monkeypatch):
    """정상 header + items → 파싱 성공."""
    class _Resp:
        def json(self):
            return {"response": {"header": {"resultCode": "00"},
                    "body": {"items": {"item": [{"pblancId": "x1", "pblancNm": "T"}]}}}}
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_http_get", lambda *a, **k: _Resp())
    out = m._fetch_bizinfo_datagokr({**SITE, "datagokr_num_rows": 500})
    assert len(out) == 1 and out[0]["id"] == "x1"


def test_dead_earlier_path_is_recorded_even_when_collection_succeeds(monkeypatch):
    """앞 경로가 죽고 뒤 경로가 살려낸 run 은 page_stat 에 흔적을 남긴다.

    2026-08-02 부터 data.go.kr 이 매 실행 NO_MANDATORY_REQUEST_PARAMETERS_ERROR 로
    죽었는데 직결이 받쳐 수집은 성공했다. 그래서 INFO 로그만 남고 아무도 몰랐다.
    안전망이 1개로 줄어든 것을 조용히 넘기면, 남은 경로가 실패하는 날 곧바로 0건이 된다
    (실제로 2026-07-17~20 에 양쪽 동시 실패로 5회 0건이 났다).
    """
    m.reset_page_stats()
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")

    def _dead(_site):
        raise RuntimeError("기업마당 data.go.kr 오류: 04 NO_MANDATORY_REQUEST_PARAMETERS_ERROR")

    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", _dead)
    monkeypatch.setattr(
        m, "_fetch_bizinfo_direct",
        lambda _s: [m._bizinfo_parse_item({"pblancId": "d1", "pblancNm": "T"}, "기업마당", True)])

    got = m.fetch_bizinfo({**SITE, "id": "bizinfo"})

    assert len(got) == 1                      # 수집·발송은 정상 진행(경보는 별개)
    stat = m.page_stats_snapshot()["bizinfo"]
    assert stat["fallback_degraded"] is True
    assert stat["fallback_recovered_by"] == "bizinfo 직결"
    assert any("data.go.kr" in path for path in stat["fallback_failed_paths"])


def test_healthy_first_path_leaves_no_degraded_flag(monkeypatch):
    """첫 경로가 성공하면 흔적을 남기지 않는다 — 매일 뜨는 경고는 무시당한다."""
    m.reset_page_stats()
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(
        m, "_fetch_bizinfo_datagokr",
        lambda _s: [m._bizinfo_parse_item({"pblancId": "g1", "pblancNm": "T"}, "기업마당", True)])
    monkeypatch.setattr(
        m, "_fetch_bizinfo_direct",
        lambda _s: pytest.fail("첫 경로가 성공했는데 폴백을 타면 안 된다"))

    assert len(m.fetch_bizinfo({**SITE, "id": "bizinfo"})) == 1
    assert m.page_stats_snapshot().get("bizinfo", {}).get("fallback_degraded") is None

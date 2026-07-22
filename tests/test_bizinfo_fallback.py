"""기업마당(Bizinfo) 수집 폴백·워밍업·빠른실패 회귀 테스트.

배경: bizinfo.go.kr 직결 API 가 GitHub Actions 러너 IP 에서 WAF/지역차단(timeout)돼 수집 실패.
수정: (a) 직결에 워밍업 세션+빠른실패, (b) DATA_GO_KR_KEY 있으면 data.go.kr 폴백.
핵심 성질(직결 실패 신호 규약 보존):
  · 직결이 건을 모으면 그대로 사용(폴백 안 탐)
  · 직결 하드 실패 + 키 없음 → 예외 재발생(커버리지 '수집실패' 신호 유지)
  · 직결 하드 실패 + 키 있음 → data.go.kr 폴백
  · 직결 진짜 0건 + 키 없음 → [] (예외 아님)
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


def test_direct_empty_no_key_returns_empty(monkeypatch):
    """진짜 0건(빈 배열)은 예외 아님 — 키 없으면 그대로 [] 반환."""
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


def test_datagokr_legit_zero_trusted(monkeypatch):
    """primary(data.go.kr)가 정상 0건(예외 아님)이면 그 응답을 신뢰 — 직결로 안 넘어간다."""
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", lambda s: [])   # 정상 0건(권위)
    called = {"direct": False}
    monkeypatch.setattr(m, "_fetch_bizinfo_direct",
                        lambda s: called.__setitem__("direct", True) or [m._item("z", "Z", "", "", "", "", s["name"])])
    out = m.fetch_bizinfo(SITE)
    assert out == [] and called["direct"] is False, "primary 정상 0건은 직결로 안 넘어가야 함"


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

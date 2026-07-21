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

sys.path.insert(0, str(Path(__file__).parent))
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


def test_direct_fail_with_key_uses_fallback(monkeypatch):
    def boom(s):
        raise RuntimeError("timeout")
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", boom)
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr",
                        lambda s: [m._item("d1", "FB", "", "", "", "", s["name"])])
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


def test_empty_fallback_does_not_hide_direct_failure(monkeypatch):
    """직결 하드 실패 + 폴백 빈 결과 → 0건으로 숨기지 않고 직결 예외 재발생(수집실패 신호)."""
    def boom(s):
        raise RuntimeError("timeout")
    monkeypatch.setattr(m, "_fetch_bizinfo_direct", boom)
    monkeypatch.setattr(m, "DATA_GO_KR_KEY", "SVCKEY")
    monkeypatch.setattr(m, "_fetch_bizinfo_datagokr", lambda s: [])   # 폴백도 0건
    try:
        m.fetch_bizinfo(SITE)
        assert False, "직결 하드 실패가 0건에 묻히면 안 됨"
    except RuntimeError as e:
        assert "timeout" in str(e)


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

"""SSRF 가드 회귀 테스트 (진단서 #20).

net_guard.check_url 이 사설/내부 IP·비 http(s)·메타데이터 호스트를 차단하고,
공인 호스트는 통과시키며, DNS 미해석은 (심층방어 특성상) 통과시키는지 검증한다.
실제 DNS 를 타지 않도록 호스트명 해석 케이스는 socket.getaddrinfo 를 monkeypatch 한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import net_guard as ng  # noqa: E402


def test_blocks_non_http_scheme():
    assert ng.check_url("ftp://example.com/x")[0] is False
    assert ng.check_url("file:///etc/passwd")[0] is False
    assert ng.check_url("gopher://1.2.3.4")[0] is False


def test_blocks_localhost_and_metadata():
    assert ng.check_url("http://localhost/x")[0] is False
    assert ng.check_url("http://metadata.google.internal/")[0] is False


def test_blocks_private_ip_literals():
    for u in ("http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.1.1/",
              "http://172.16.0.1/", "https://169.254.169.254/latest/meta-data/",
              "http://[::1]/", "http://0.0.0.0/"):
        ok, why = ng.check_url(u)
        assert ok is False, f"{u} 는 차단돼야 함 ({why})"


def test_blocks_ipv4_mapped_ipv6_private():
    assert ng.check_url("http://[::ffff:10.0.0.1]/")[0] is False


def test_allows_public_ip_literal():
    assert ng.check_url("http://8.8.8.8/")[0] is True
    assert ng.check_url("https://1.1.1.1/")[0] is True


def test_hostname_resolving_to_private_is_blocked(monkeypatch):
    def fake_gai(host, port, *a, **k):
        return [(2, 1, 6, "", ("10.1.2.3", port))]   # 사설로 해석
    monkeypatch.setattr(ng.socket, "getaddrinfo", fake_gai)
    ok, why = ng.check_url("https://evil.example.com/")
    assert ok is False and "사설" in why


def test_hostname_resolving_to_public_is_allowed(monkeypatch):
    def fake_gai(host, port, *a, **k):
        return [(2, 1, 6, "", ("93.184.216.34", port))]  # 공인
    monkeypatch.setattr(ng.socket, "getaddrinfo", fake_gai)
    assert ng.check_url("https://example.com/")[0] is True


def test_dns_failure_passes(monkeypatch):
    """DNS 미해석은 통과(정상 사이트 블립 오차단 방지 — 실제 요청 실패로 자연 차단)."""
    def boom(host, port, *a, **k):
        raise OSError("no dns")
    monkeypatch.setattr(ng.socket, "getaddrinfo", boom)
    ok, why = ng.check_url("https://transient-dns.example.com/")
    assert ok is True and "dns" in why


def test_empty_or_hostless():
    assert ng.check_url("")[0] is False
    assert ng.check_url("http:///nohost")[0] is False


def test_is_safe_shortcut():
    assert ng.is_safe("https://8.8.8.8/") is True
    assert ng.is_safe("http://127.0.0.1/") is False


# ── 위험 보강(de-risk): 킬스위치·화이트리스트·reserved 오탐 제거 ──
def test_kill_switch_disables_guard(monkeypatch):
    """MONITOR_NO_NET_GUARD=1 이면 사설 IP 도 통과(라이브 오차단 즉시 복구)."""
    monkeypatch.setenv("MONITOR_NO_NET_GUARD", "1")
    assert ng.check_url("http://127.0.0.1/")[0] is True
    assert ng.check_url("http://10.0.0.1/")[0] is True


def test_host_allowlist_overrides_block(monkeypatch):
    """NET_GUARD_ALLOW_HOSTS 에 있으면 무조건 통과(정상 소스 오차단 escape hatch)."""
    monkeypatch.setenv("NET_GUARD_ALLOW_HOSTS", "internal.gov.kr, other.example")
    ok, why = ng.check_url("http://internal.gov.kr/notice")
    assert ok is True and "allowlist" in why


def test_critical_ranges_still_blocked():
    """de-risk 후에도 SSRF 핵심 대역은 여전히 차단(커버리지 회귀 가드)."""
    for ip in ("10.0.0.1", "127.0.0.1", "169.254.169.254", "0.0.0.0",
               "192.168.0.1", "172.16.0.1"):
        assert ng._ip_blocked(ip) is True, ip
    assert ng._ip_blocked("8.8.8.8") is False and ng._ip_blocked("93.184.216.34") is False

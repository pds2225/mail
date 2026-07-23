#!/usr/bin/env python3
"""net_guard — 아웃바운드 요청 SSRF 가드 (진단서 #20).

문제: _http_get/_soup 이 임의 URL 을 follow_redirects=True 로 그대로 GET 한다. sites.json 오설정·
  리다이렉트·(streamlit) 사용자 입력 URL 이 사설/내부망 IP(10.x·192.168.x·127.x·169.254.169.254
  메타데이터 등)를 가리키면 내부 자원에 접근할 수 있다.

이 모듈: fetch 전에 URL 을 검사해 (1) http/https 외 scheme, (2) localhost/메타데이터 호스트,
  (3) 사설·루프백·링크로컬·예약 IP(리터럴 또는 DNS 해석 결과)를 차단한다. 리다이렉트 최종 URL 도
  같은 기준으로 재검사한다(호출측에서 response.url 로 check_url 재호출).

안전(정상 사이트 오차단 방지):
  - DNS 해석이 실패하면 통과시킨다(정상 사이트의 일시적 DNS 블립으로 수집을 막지 않음 —
    실제 요청이 실패하면 상위에서 자연히 걸러진다). 확정된 사설 IP 만 차단한다.
  - 큐레이션된 소스 리스트에 대한 심층방어(defense-in-depth) 계층이다.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTS = {
    "localhost", "localhost.localdomain", "ip6-localhost",
    "metadata", "metadata.google.internal",
}
_ALLOW_SCHEMES = ("http", "https")


def _ip_blocked(value: str) -> bool:
    """IP 문자열이 SSRF 위험 대역(사설/루프백/링크로컬/예약/멀티캐스트/미지정)이면 True.

    IPv4 예약대역(240/4)은 Python 상 is_private 이기도 해 어차피 차단되므로, 커버리지를 위해
    원 판정을 유지한다. '정상 소스 오차단' 우려는 check_url 의 킬스위치·화이트리스트로 무코드
    복구할 수 있게 하여 완화한다(실 소스는 공인 IP 라 오탐 확률 자체가 낮음).
    """
    try:
        a = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        a = a.ipv4_mapped  # ::ffff:10.0.0.1 같은 매핑도 검사
    return bool(
        a.is_private or a.is_loopback or a.is_link_local
        or a.is_reserved or a.is_multicast or a.is_unspecified
    )


def _disabled() -> bool:
    """킬스위치 — MONITOR_NO_NET_GUARD=1 이면 가드 전체 비활성(라이브 오차단 시 즉시 복구)."""
    return os.environ.get("MONITOR_NO_NET_GUARD", "").strip() in ("1", "true", "True")


def _host_allowlisted(host: str) -> bool:
    """운영자 화이트리스트 — NET_GUARD_ALLOW_HOSTS(쉼표구분)에 있으면 무조건 통과(escape hatch)."""
    allow = os.environ.get("NET_GUARD_ALLOW_HOSTS", "")
    if not allow:
        return False
    hosts = {h.strip().lower() for h in allow.split(",") if h.strip()}
    return host.lower() in hosts


def check_url(url: str, *, allow_schemes: tuple[str, ...] = _ALLOW_SCHEMES) -> tuple[bool, str]:
    """(안전여부, 사유). 안전하면 (True, 'ok...'), 아니면 (False, 차단사유)."""
    if _disabled():
        return True, "ok(net_guard 비활성)"
    p = urlparse(url or "")
    scheme = (p.scheme or "").lower()
    if scheme not in allow_schemes:
        return False, f"허용되지 않은 scheme: {p.scheme or '(없음)'}"
    host = p.hostname
    if not host:
        return False, "호스트 없음"
    if _host_allowlisted(host):                 # 운영자 화이트리스트 우선(오차단 escape hatch)
        return True, "ok(allowlist)"
    if host.lower() in _BLOCKED_HOSTS:
        return False, f"차단 호스트: {host}"
    if _ip_blocked(host):                       # IP 리터럴 직접 차단
        return False, f"사설/내부 IP: {host}"
    try:
        port = p.port or (443 if scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return True, "ok(dns 미해석 — 통과)"     # 정상 사이트 DNS 블립 오차단 방지
    for info in infos:
        ip = info[4][0]
        if _ip_blocked(ip):
            return False, f"사설/내부 IP 로 해석됨: {host} → {ip}"
    return True, "ok"


def is_safe(url: str) -> bool:
    return check_url(url)[0]

# -*- coding: utf-8 -*-
"""diagnose_site_parse 결과 + 진단 로그를 대조해 EMPTY 를 세분류.

EMPTY(row0) = 접속실패(SSL/404/DNS/header) + 접속성공·파싱0 이 섞여 있다.
로그의 '접속 실패 <url>: <err>' 줄로 접속실패 URL 을 추출해 분리한다.

사용: python scripts/classify_diag.py <diag_json> <log_output_file>
"""
from __future__ import annotations
import sys, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def err_bucket(err: str) -> str:
    e = err.lower()
    if "sslv3_alert_handshake" in e or "handshake failure" in e:
        return "ssl_handshake"
    if "certificate_verify_failed" in e or "certificate verify" in e:
        return "ssl_cert"
    if "getaddrinfo failed" in e or "name or service" in e or "nodename" in e:
        return "dns_fail"
    if "404" in e:
        return "http_404"
    if "403" in e:
        return "http_403"
    if "illegal header" in e:
        return "bad_header"
    if "timeout" in e or "timed out" in e:
        return "timeout"
    if "connecterror" in e or "10054" in e or "connection" in e:
        return "connect_reset"
    return "other"


def main() -> int:
    diag_path = Path(sys.argv[1])
    log_path = Path(sys.argv[2])
    results = json.loads(diag_path.read_text(encoding="utf-8"))

    # 로그에서 접속 실패 URL -> 에러 추출
    fail_url_err: dict[str, str] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"접속 실패 (https?://\S+?): (.+)$", line)
        if m:
            fail_url_err[m.group(1)] = m.group(2)

    ok = [r for r in results if r["status"] == "ok"]
    empty = [r for r in results if r["status"] == "empty"]

    connect_fail, parse_empty = [], []
    for r in empty:
        if r["url"] in fail_url_err:
            r = {**r, "fail_err": fail_url_err[r["url"]], "bucket": err_bucket(fail_url_err[r["url"]])}
            connect_fail.append(r)
        else:
            parse_empty.append(r)

    from collections import Counter
    buckets = Counter(r["bucket"] for r in connect_fail)

    print(f"총 진단: {len(results)}")
    print(f"  OK(row>=1)          : {len(ok)}   -> enabled 유지")
    print(f"  접속O·파싱0(parse)   : {len(parse_empty)}   -> 셀렉터 보강 대상")
    print(f"  접속실패(connect)    : {len(connect_fail)}   -> 끄기/URL수정/SSL보강")
    print("\n[접속실패 에러 분포]")
    for b, c in buckets.most_common():
        print(f"  {b:16s}: {c}")

    # 분류 결과 저장
    out = ROOT / "reports" / "diag_classified.json"
    out.write_text(json.dumps({
        "ok": ok, "parse_empty": parse_empty, "connect_fail": connect_fail,
        "buckets": dict(buckets),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n분류 저장: {out}")

    print("\n[parse_empty 샘플 12 — 셀렉터 보강 후보]")
    for r in parse_empty[:12]:
        print(f"  {r['id']} | {r['name'][:24]} | {r['url'][:68]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

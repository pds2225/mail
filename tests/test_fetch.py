"""실제 HTTP 요청 기반 사이트 수집 테스트

사용법:
    BIZINFO_API_KEY=키값 python test_fetch.py
    BIZINFO_API_KEY=키값 python test_fetch.py --filter 기업마당
    BIZINFO_API_KEY=키값 python test_fetch.py --type html_table
    BIZINFO_API_KEY=키값 python test_fetch.py --type bizinfo_api iris_api
"""
from __future__ import annotations

import argparse, os, sys, time, traceback

# monitor.py 임포트 전에 필수 환경변수 설정
os.environ.setdefault("BIZINFO_API_KEY",    os.environ.get("BIZINFO_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_API_KEY",  "dummy")
os.environ.setdefault("GMAIL_APP_PASSWORD", "dummy")

from monitor import FETCHERS, load_sites  # noqa: E402


def _quality(items: list[dict]) -> tuple[int, int]:
    no_date = sum(1 for it in items if not it.get("posted_date"))
    no_dl   = sum(1 for it in items if not it.get("deadline"))
    return no_date, no_dl


def run(sites: list[dict]) -> None:
    results: list[tuple[str, str, int | None, str, int, int]] = []
    # columns: status, name, count, error, no_date, no_dl

    for site in sites:
        fn = FETCHERS.get(site.get("type", ""))
        if fn is None:
            results.append(("❓", site["name"], None, "타입 미지원: " + site.get("type", ""), 0, 0))
            continue

        t0 = time.time()
        try:
            items = fn(site)
            elapsed = time.time() - t0
            no_date, no_dl = _quality(items)
            status = "✅" if items else "⚠️ "
            results.append((status, site["name"], len(items), f"{elapsed:.1f}s", no_date, no_dl))
        except Exception:
            elapsed = time.time() - t0
            err = traceback.format_exc().strip().splitlines()[-1][:70]
            results.append(("❌", site["name"], None, err, 0, 0))

    # ── 출력 ───────────────────────────────────────────────────────
    w = max(len(r[1]) for r in results) + 2
    print()
    print(f"사이트 수집 테스트 ({len(sites)}개 대상)")
    print("=" * (w + 40))
    for status, name, count, note, no_date, no_dl in results:
        if count is None:
            print(f"{status} {name:<{w}} 오류: {note}")
        else:
            qual = f"날짜없음:{no_date:3d}  마감없음:{no_dl:3d}" if (no_date or no_dl) else ""
            print(f"{status} {name:<{w}} {count:4d}건  {note:<8}  {qual}")

    print("=" * (w + 40))
    ok   = sum(1 for r in results if r[2] is not None and r[2] > 0)
    zero = sum(1 for r in results if r[2] == 0)
    err  = sum(1 for r in results if r[2] is None)
    print(f"정상: {ok}개 / 0건: {zero}개 / 오류: {err}개")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="사이트별 실제 수집 테스트")
    parser.add_argument("--filter", nargs="*", metavar="KEYWORD",
                        help="사이트명에 포함된 키워드로 필터")
    parser.add_argument("--type",   nargs="*", metavar="TYPE",
                        help="fetcher 타입으로 필터 (예: html_table bizinfo_api)")
    args = parser.parse_args()

    sites = load_sites()

    if args.filter:
        sites = [s for s in sites if any(kw in s["name"] for kw in args.filter)]
    if args.type:
        sites = [s for s in sites if s.get("type") in args.type]

    if not sites:
        print("조건에 맞는 사이트가 없습니다.")
        sys.exit(1)

    run(sites)


if __name__ == "__main__":
    main()

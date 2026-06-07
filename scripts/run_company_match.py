r"""run_company_match — 기업 맞춤 공고 매칭 dry-run 진입점.

실행 (PowerShell, D:\mail 에서):
  python scripts\run_company_match.py --sample            # 샘플 데이터 (네트워크/API 불필요)
  python scripts\run_company_match.py --input data.json   # 기존 수집 JSON 으로 매칭
  python scripts\run_company_match.py --collect           # 실제 수집 후 매칭 (BIZINFO_API_KEY 필요)

산출물 (reports/company_match/):
  {date}_{company_id}.md        — 기업별 매칭 리포트
  {date}_{company_id}_draft.txt — 기업별 발송 초안 (발송 금지)

금지:
  SMTP 호출 없음 — 실제 발송 절대 금지. 초안/리포트만 생성.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import company_match  # noqa: E402

KST = timezone(timedelta(hours=9))
REPORT_DIR = BASE_DIR / "reports" / "company_match"

# 네트워크/API 없이 동작하는 샘플 공고 (monitor item 형태 + 한국어 dict 혼용)
SAMPLE_ITEMS: list[dict[str, Any]] = [
    {
        "title": "인천 남동구 제조기업 스마트공장 구축 지원사업 신청접수",
        "author": "인천테크노파크",
        "deadline": "2026-06-30",
        "description": "인천 남동구 소재 제조업 영위 기업 대상. 공장보유 기업 우대. 스마트공장 보급.",
        "link": "https://example.com/incheon-smart",
        "source": "인천TP",
        "_types": ["지원금/바우처"],
    },
    {
        "title": "K-뷰티 화장품 수출 해외전시회 참가 지원 (베트남)",
        "author": "KOTRA",
        "deadline": "2026-07-10",
        "description": "화장품·뷰티 중소기업 해외진출. 베트남 박람회 부스 지원. 전국.",
        "link": "https://example.com/kbeauty-export",
        "source": "KOTRA",
        "_types": ["지원금/바우처"],
    },
    {
        "title": "부산 지역 소재 기업 전용 물류비 지원사업",
        "author": "부산경제진흥원",
        "deadline": "2026-06-25",
        "description": "부산광역시 소재 기업만 신청 가능. 부산 외 지역 제외.",
        "link": "https://example.com/busan-logistics",
        "source": "부산",
        "_types": ["지원금/바우처"],
    },
    {
        "title": "중소기업 정책자금 운영 설명회 교육 안내",
        "author": "중소벤처기업진흥공단",
        "deadline": "2026-06-20",
        "description": "정책자금 신청방법 설명회. 교육 일정 안내.",
        "link": "https://example.com/info-session",
        "source": "중진공",
        "_types": ["컨설팅·교육·상담"],
    },
    {
        "title": "서울 AI·데이터 SaaS 스타트업 사업화 지원",
        "author": "서울경제진흥원",
        "deadline": "2026-07-05",
        "description": "서울 소재 인공지능·데이터·SaaS 기업 대상 사업화 자금.",
        "link": "https://example.com/seoul-ai",
        "source": "SBA",
        "_types": ["지원금/바우처"],
    },
]


def _fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _load_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.sample:
        print(f"샘플 데이터 {len(SAMPLE_ITEMS)}건 사용")
        return SAMPLE_ITEMS
    if args.input:
        p = Path(args.input)
        if not p.exists():
            print(f"[ERR] 입력 파일 없음: {p}", file=sys.stderr)
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        print(f"입력 파일 로드: {len(items)}건 ({p})")
        return items
    if args.collect:
        print("실제 수집 시작 (환경변수·네트워크 필요)...")
        try:
            try:
                from dotenv import load_dotenv
                load_dotenv(BASE_DIR / ".env", override=False)
            except ImportError:
                pass
            from monitor import fetch_all, load_sites  # type: ignore
            items = fetch_all(load_sites())
            print(f"수집 완료: {len(items)}건")
            return _enrich_with_evaluate(items)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] 수집 실패: {exc}", file=sys.stderr)
            print("  -> --sample 로 샘플 데이터 사용 가능", file=sys.stderr)
            return []
    return []


def _enrich_with_evaluate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """monitor.evaluate_notice 가 가능하면 하드 제외 판정 필드를 부여(있으면 재사용)."""
    try:
        from monitor import evaluate_notice  # type: ignore
    except Exception:  # noqa: BLE001
        return items
    enriched = []
    for it in items:
        try:
            enriched.append(evaluate_notice(it))
        except Exception:  # noqa: BLE001
            enriched.append(it)
    return enriched


def _write_company_report(company: dict[str, Any], result: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    cid = company.get("id", "company")
    matched = result["matched"]
    rejected = result["rejected"]

    md: list[str] = [
        f"# 기업 맞춤 매칭 리포트 — {company.get('name')} ({today})",
        "",
        "> ⚠️ 발송 금지. 이 리포트는 검수용 초안입니다.",
        "",
        f"- 수신(마스킹): {company_match.mask_email(company.get('email', ''))}",
        f"- 적합도 임계값: {company.get('match_threshold')}",
        f"- ✅ 맞춤 {len(matched)}건 / ❌ 제외 {len(rejected)}건",
        "",
        f"## ✅ 맞춤 공고 ({len(matched)}건)",
        "",
    ]
    if matched:
        for it in matched:
            reasons = ", ".join(it.get("_match_reasons", [])) or "키워드 적합"
            md.extend([
                f"- **{it.get('title') or '(제목없음)'}**  (적합도 {it.get('_match_score', 0)})",
                f"  - 기관: {it.get('author') or it.get('agency') or '미기재'}",
                f"  - 마감: {it.get('deadline') or it.get('end_date') or '미기재'}",
                f"  - 사유: {reasons}",
                f"  - 링크: {it.get('link') or it.get('url') or '미기재'}",
            ])
    else:
        md.append("_(맞춤 공고 없음)_")
    md.extend(["", f"## ❌ 제외 공고 ({len(rejected)}건)", ""])
    if rejected:
        for it in rejected:
            mism = ", ".join(it.get("_match_mismatches", [])) or it.get("_match_reason", "임계값 미만")
            md.append(f"- {it.get('title') or '(제목없음)'} (적합도 {it.get('_match_score', 0)}) — {mism}")
    else:
        md.append("_(제외 공고 없음)_")

    report_path = output_dir / f"{today}_{cid}.md"
    report_path.write_text("\n".join(md), encoding="utf-8")

    draft_path = output_dir / f"{today}_{cid}_draft.txt"
    draft_path.write_text(company_match.build_company_digest(company, matched), encoding="utf-8")
    return {"report": report_path, "draft": draft_path}


def main(argv: list[str] | None = None) -> int:
    _fix_console_encoding()
    parser = argparse.ArgumentParser(
        description="기업 맞춤 공고 매칭 dry-run (발송 없음)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sample", action="store_true", help="샘플 데이터로 실행")
    parser.add_argument("--collect", action="store_true", help="실제 수집 후 매칭")
    parser.add_argument("--input", type=str, default="", help="입력 JSON 파일")
    parser.add_argument("--companies", type=str, default="", help="기업 프로필 JSON (기본 companies.json)")
    parser.add_argument("--output-dir", type=str, default=str(REPORT_DIR), help="결과 출력 디렉토리")
    args = parser.parse_args(argv)

    companies = company_match.load_companies(args.companies or None)
    if not companies:
        print("[ERR] 활성 기업 프로필 없음 (companies.json 확인)", file=sys.stderr)
        return 1
    print(f"활성 기업 {len(companies)}곳 로드")

    # 안전장치: 테스트 단계 수신자 검증 (발송 경로는 없지만 초안 단계에서 경고)
    ok, violations = company_match.assert_test_recipient_only(companies)
    if not ok:
        masked = ", ".join(company_match.mask_email(v) for v in violations)
        print(f"[WARN] 테스트 수신자 외 주소 감지(초안만 생성, 발송 없음): {masked}", file=sys.stderr)

    items = _load_items(args)
    if not items:
        print("[ERR] 매칭할 공고 없음", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    summary: dict[str, Any] = {"ok": True, "input_items": len(items), "companies": {}}
    print("\n[기업별 매칭 결과]")
    for company in companies:
        result = company_match.match_for_company(items, company)
        paths = _write_company_report(company, result, output_dir)
        n_match = len(result["matched"])
        print(f"  - {company.get('name'):20s}: 맞춤 {n_match}건 / 제외 {len(result['rejected'])}건"
              f"  -> {paths['report'].name}")
        summary["companies"][company.get("id")] = {
            "name": company.get("name"),
            "matched": n_match,
            "rejected": len(result["rejected"]),
            "report": str(paths["report"]),
            "draft": str(paths["draft"]),
        }

    print("\n[안전] SMTP 미호출 — 초안/리포트만 생성됨")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

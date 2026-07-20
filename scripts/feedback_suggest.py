#!/usr/bin/env python3
r"""feedback_suggest — 사용자 O/X 골든 라벨로 '왜 놓쳤나' 진단 + 개선 제안 (제안 전용, B단계 1).

무엇을 하나 (자동학습 로드맵 B, Phase-1 = 제안만·무수정):
  accuracy_matrix.build() 가 산출한 공고별 판정(그룹별 is_relevant·region_status·reason_codes)
  과 사람 O/X 골든(feedback)을 대조해,
    · O(관련)인데 어느 그룹도 추천 안 함 = '놓침' → 원인 진단(키워드/지역/날짜/제외) + 제안
    · X(무관)인데 추천/발송됨 = '오발송' → 검토 플래그
  을 만들어 workspace/feedback_suggestions_*.json + 사람용 요약으로 낸다.

안전(불변):
  - **제안만 한다.** groups.json/companies.json/settings.json 등 어떤 설정도 자동 수정하지 않는다.
  - 판정 로직 무수정. 읽기 전용 분석. (B Phase-2 에서 신뢰도 게이트로 자동적용+롤백 예정.)

핵심 진단 규칙(각 그룹의 reason_codes 로부터):
  - 키워드 매칭됨(INDUSTRY_NOT_MATCHED 없음) + 지역만 미상  → region_hint(전국/소스 힌트)
  - 키워드 매칭됨 + 날짜만 막힘                         → date_window(날짜창/파싱)
  - 키워드 매칭됨 + 특정 제외규칙만 막힘                → exclude_relax(그 규칙 완화)
  - 어느 그룹도 키워드 매칭 안 됨(전부 INDUSTRY_NOT_MATCHED) → keyword_add(제목서 후보어 추출)

사용:
  python scripts/feedback_suggest.py            # accuracy_matrix 로 오늘자 분석→제안 리포트
  python scripts/feedback_suggest.py --date 2026-07-20
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

# reason_code → 원인 범주
REGION_UNKNOWN_CODES = {"REGION_UNKNOWN", "LOW_CONFIDENCE"}          # 지역 미상(=승격 여지, recall)
REGION_HARD_CODES = {"REGION_NOT_ELIGIBLE", "DISTRICT_NOT_ELIGIBLE"}  # 확실한 타지역(승격 대상 아님)
DATE_CODES = {"CLOSED_DEADLINE", "MISSING_APPLICATION_PERIOD"}
KEYWORD_MISS = "INDUSTRY_NOT_MATCHED"
# 제외규칙 계열(억울한 제외 후보) — recall 관점에서 완화 검토 대상
EXCLUDE_CODES = {
    "NOT_GRANT_NOTICE", "GUIDELINE_OR_MANUAL", "EDUCATION_ONLY", "INFO_SESSION",
    "SUPPLIER_ONLY", "SELECTED_COMPANY_ONLY", "SMART_FACTORY_INFO_ONLY",
    "LOW_PRIORITY_SERVICE_KEYWORD", "ONLY_SPECIFIC_INDUSTRIAL_COMPLEX",
}

# 키워드 후보에서 제외할 범용 공고 용어(추가해도 변별력 없음).
GENERIC_TERMS = {
    "모집", "공고", "지원", "사업", "안내", "신청", "참여", "선정", "개최", "추가",
    "기업", "대상", "센터", "프로그램", "교육", "설명회", "수요", "기관", "운영",
    "년도", "하반기", "상반기", "차수", "재공고", "결과", "발표", "접수", "참가",
}
_HANGUL_TOKEN = re.compile(r"[가-힣]{2,}")
_ACRONYM = re.compile(r"\b([A-Za-z][A-Za-z0-9]{1,6})\b")


def candidate_terms(title: str, existing: set[str], *, limit: int = 4) -> list[str]:
    """제목에서 그룹 키워드 후보를 뽑는다(범용어·기존 키워드 제외)."""
    title = title or ""
    existing_l = {e.lower() for e in existing}
    seen: list[str] = []
    for tok in _ACRONYM.findall(title):
        t = tok.strip()
        if len(t) >= 2 and t.lower() not in existing_l and t.lower() not in {g.lower() for g in GENERIC_TERMS}:
            if t not in seen:
                seen.append(t)
    for tok in _HANGUL_TOKEN.findall(title):
        t = tok.strip()
        if t in GENERIC_TERMS or t.lower() in existing_l:
            continue
        # 접미 범용어 제거(예: 'AI바우처지원사업' 통짜는 스킵, 순수 명사만)
        if any(t.endswith(g) and len(t) > len(g) for g in ("사업", "공고", "지원", "모집")):
            continue
        if t not in seen:
            seen.append(t)
    return seen[:limit]


def diagnose_notice(
    notice: dict,
    group_keywords: dict[str, list[str]],
    *,
    suggest_keywords: bool = True,
) -> list[dict]:
    """공고 1건의 O/X 골든과 그룹별 판정으로 제안 목록을 만든다(제안 전용).

    notice: accuracy_matrix build()["matrix"]["notices"] 원소
      {id,title,feedback,groups:{gid:{is_relevant,region_status,region_unknown_review,
                                       reason_codes,keyword_pass}}}
    group_keywords: {gid: [or_keywords...]}  (기존 키워드 재제안 방지용)
    suggest_keywords: False 면 keyword_add 제안을 억제한다(기존 키워드 목록을 모를 때 —
      예: groups.json 로드 실패 → 중복어 추천 방지).
    """
    fb = (notice.get("feedback") or "").upper()
    if fb not in ("O", "X"):
        return []
    groups = notice.get("groups") or {}
    # '발송/추천됨' 판정은 accuracy_matrix 와 동일하게 그룹(is_relevant)+기업(matched) 두 경로를
    # 모두 본다. 그룹만 보면 기업 경로로 나간 O 공고를 '놓침'으로 오진단하고, X 오발송을 놓친다.
    comps = notice.get("companies") or {}
    rec_groups = [gid for gid, gv in groups.items() if gv.get("is_relevant")]
    rec_comps = [cid for cid, cv in comps.items() if cv.get("decision") == "matched"]
    recommended = bool(rec_groups or rec_comps)
    nid = notice.get("id", "")
    title = notice.get("title", "")
    out: list[dict] = []

    # ── X(무관)인데 추천/발송됨 = 오발송 → 검토 플래그(정밀도) ──
    if fb == "X":
        if recommended:
            out.append({
                "kind": "false_send_review", "notice_id": nid, "title": title,
                "groups": rec_groups, "companies": rec_comps,
                "suggestion": "사람이 X(무관)로 표시했는데 발송됨 — 해당 그룹/기업 키워드·조건 정밀도 점검.",
            })
        return out

    # ── 여기부터 O(관련) ──
    if recommended:
        return []  # O 이고 이미 추천됨(그룹 또는 기업 경로) = 정상(놓침 아님)

    # O 인데 어느 그룹도 추천 안 함 = 놓침. 그룹별로 '한 끗 차이' 원인 진단.
    all_keyword_missed = True
    all_region_hard = True   # 모든 그룹이 확실한 타지역이면 키워드를 더해도 못 살림(제안 억제).
    for gid, gv in groups.items():
        codes = set(gv.get("reason_codes") or [])
        # 키워드 미스 판정: keyword_pass 신호가 있으면 그걸 우선한다. INDUSTRY_NOT_MATCHED 는
        # (a) 키워드 게이트 실패(진짜 미스)와 (b) 지원유형 불일치(키워드는 맞음) 둘 다에서 붙어
        # 코드만 보면 (b)를 키워드 미스로 오진단한다 → keyword_pass 로 (a)/(b)를 가른다.
        kw_pass = gv.get("keyword_pass")
        if kw_pass is None:
            kw_missed = KEYWORD_MISS in codes           # 신호 없음(레거시/합성) → 코드 기반
        else:
            kw_missed = not kw_pass
        # 지원유형 불일치: 키워드는 통과했는데 INDUSTRY_NOT_MATCHED 가 붙은 경우(=3685행 경로).
        support_blocked = (KEYWORD_MISS in codes) and not kw_missed
        if not kw_missed:
            all_keyword_missed = False
        region_hard = bool(codes & REGION_HARD_CODES) or gv.get("region_status") == "not_eligible"
        if not region_hard:
            all_region_hard = False
        region_unknown = (
            gv.get("region_unknown_review")
            or gv.get("region_status") == "unknown"
            or bool(codes & REGION_UNKNOWN_CODES)
        )
        date_blocked = bool(codes & DATE_CODES)
        excl_blocked = sorted(codes & EXCLUDE_CODES)

        # 키워드가 매칭된 그룹만 '이 그룹이 원했다'고 볼 수 있어 지역/날짜/제외 제안을 낸다.
        if kw_missed or region_hard:
            continue
        if region_unknown:
            out.append({
                "kind": "region_hint", "notice_id": nid, "title": title, "group": gid,
                "evidence": sorted(codes),
                "suggestion": f"[{gid}] 키워드는 맞는데 지역 미상으로 강등됨 — 소스에 '전국' 힌트 "
                              "보강 또는 그룹 extra_eligible_regions 검토(누락 방지).",
            })
        elif date_blocked:
            out.append({
                "kind": "date_window", "notice_id": nid, "title": title, "group": gid,
                "evidence": sorted(codes),
                "suggestion": f"[{gid}] 키워드는 맞는데 날짜(마감/게시)로 막힘 — days_back·불명 허용창 "
                              "또는 마감 파싱 점검.",
            })
        elif excl_blocked:
            out.append({
                "kind": "exclude_relax", "notice_id": nid, "title": title, "group": gid,
                "evidence": excl_blocked,
                "suggestion": f"[{gid}] 키워드는 맞는데 제외규칙({', '.join(excl_blocked)})에 걸림 — "
                              "억울한 제외면 그룹 화이트리스트/규칙 완화 검토.",
            })
        elif support_blocked:
            out.append({
                "kind": "support_relax", "notice_id": nid, "title": title, "group": gid,
                "evidence": ["INDUSTRY_NOT_MATCHED"],
                "suggestion": f"[{gid}] 키워드는 맞는데 지원유형(support_types) 불일치로 막힘 — "
                              "제목 토큰 추가가 아니라 그룹 support_types 범위 점검이 필요.",
            })

    # 어느 그룹도 키워드 매칭 안 됨 → 키워드 후보 제안(그룹 미지정, 전역 풀).
    # 단, 모든 그룹이 확실한 타지역(region_hard)이면 키워드를 더해도 못 살리므로 제안하지 않는다.
    # groups.json 을 몰라(로드 실패) 기존 키워드 중복 방지가 불가한 경우에도 억제한다.
    if suggest_keywords and all_keyword_missed and groups and not all_region_hard:
        existing = set()
        for kws in group_keywords.values():
            existing |= {str(k) for k in (kws or [])}
        cands = candidate_terms(title, existing)
        if cands:
            out.append({
                "kind": "keyword_add", "notice_id": nid, "title": title, "group": None,
                "candidates": cands,
                "suggestion": f"어느 그룹 키워드에도 안 걸림 — 관련 그룹에 후보어 추가 검토: {', '.join(cands)}",
            })
    return out


def build_suggestions(notices: list[dict], groups: list[dict], *, keywords_known: bool = True) -> dict:
    """공고 목록(accuracy_matrix)·그룹으로 제안 리포트를 만든다(제안 전용·집계).

    keywords_known: False 면(groups.json 로드 실패 등 기존 키워드 목록 부재) keyword_add 제안을
      억제한다 — 기존 키워드와 중복되는 후보를 걸러낼 수 없어 잘못된 추천이 나가는 것을 막는다.
    """
    gkw = {(g.get("id") or g.get("name") or "grp"): (g.get("or_keywords") or []) for g in (groups or [])}
    suggestions: list[dict] = []
    for n in notices or []:
        suggestions.extend(diagnose_notice(n, gkw, suggest_keywords=keywords_known))

    by_kind = Counter(s["kind"] for s in suggestions)
    # 키워드 후보 빈도 집계(여러 놓침에서 반복되는 후보 = 강한 신호).
    kw_freq: Counter = Counter()
    for s in suggestions:
        if s["kind"] == "keyword_add":
            kw_freq.update(s.get("candidates") or [])
    return {
        "counts": dict(by_kind),
        "labeled_misses": sum(1 for s in suggestions if s["kind"] != "false_send_review"),
        "false_sends": by_kind.get("false_send_review", 0),
        "top_keyword_candidates": kw_freq.most_common(15),
        "suggestions": suggestions,
        "note": "제안 전용(Phase-1) — 자동 적용 아님. 사람이 검토 후 groups.json 등 반영.",
    }


def _format_summary(report: dict) -> str:
    c = report["counts"]
    lines = [
        "📋 O/X 피드백 개선 제안 (제안 전용 · 자동적용 아님)",
        f"  놓침 제안 {report['labeled_misses']}건 · 오발송 {report['false_sends']}건",
        f"  종류별: {c or '없음'}",
    ]
    if report["top_keyword_candidates"]:
        top = ", ".join(f"{t}×{n}" for t, n in report["top_keyword_candidates"][:8])
        lines.append(f"  키워드 후보(빈도): {top}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="O/X 골든 → 개선 제안(제안 전용)")
    ap.add_argument("--date", default=None, help="분석 날짜(YYYY-MM-DD). 생략 시 전체 raw store.")
    ap.add_argument("--cap", type=int, default=None, help="공고 수 상한(디버그)")
    ap.add_argument("--out", default=None, help="리포트 경로(기본 workspace/feedback_suggestions_*.json)")
    args = ap.parse_args(argv)

    import accuracy_matrix  # noqa: E402
    import monitor  # noqa: E402

    res = accuracy_matrix.build(args.date, args.cap)
    if res.get("error"):
        print(f"[skip] {res['error']}")
        return 0
    notices = (res.get("matrix") or {}).get("notices") or []
    keywords_known = True
    try:
        groups = monitor.load_groups()
    except Exception as e:  # noqa: BLE001
        groups = []
        keywords_known = False   # 기존 키워드 목록 부재 → keyword_add 억제(중복 추천 방지)
        print(f"[warn] load_groups 실패: {e} — keyword_add 제안 억제", file=sys.stderr)

    report = build_suggestions(notices, groups, keywords_known=keywords_known)
    print(_format_summary(report))

    stamp = (args.date or "all").replace("-", "")
    out = Path(args.out) if args.out else (ROOT / "workspace" / f"feedback_suggestions_{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[out] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

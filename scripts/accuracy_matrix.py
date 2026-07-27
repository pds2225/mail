r"""accuracy_matrix — 전수 채점 매트릭스 + FP/FN 후보 + 자기모순 탐지 (읽기전용).

정확도 오케스트레이터(mail-accuracy-orchestrator)의 S2(match-runner) 실행 엔진.
raw store 의 전수 공고를 두 경로(기업단위 company_match · 그룹단위 monitor.evaluate_notice)로
동시 채점하고, 결정론적 규칙으로 FP/FN 후보와 경로 자기모순을 surface 한다.
판정 로직은 절대 수정하지 않고 **호출만** 한다(코드 미수정 원칙).

산출물 (D:\mail\.omc\accuracy\runs\{date}\):
  matrix.json         전수 (공고 × 기업3 × 그룹3) 결정·점수·지역상태·약라벨·모순플래그
  fp_candidates.json  오탐 후보(사유코드별, 상한 캡) — fp-hunter 입력
  fn_candidates.json  누락 후보(사유코드별, 상한 캡) — fn-hunter 입력
  contradictions.json 두 경로 지역 verdict 불일치(#15 류 신호)
  summary.json        KPI(region_FP·FN후보·recall@labeled·매칭수·drift)

실행 (PowerShell, D:\mail 에서):
  python scripts\accuracy_matrix.py            # 전수(모든 날짜)
  python scripts\accuracy_matrix.py --date 2026-07-07   # 특정 날짜만
  python scripts\accuracy_matrix.py --max 500  # 빠른 스모크(앞 N건)
종료코드: region_FP==0 이면 0, 아니면 1 (CI 게이트 가능).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
for p in (BASE_DIR, BASE_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from mail_core.matching import company_match  # noqa: E402
import monitor  # noqa: E402
from mail_core.delivery import feedback  # noqa: E402 (사용자 O/X 피드백 = Tier C 사람 정답)
from run_company_match import _enrich_for_company  # noqa: E402 (#15 인천고정 버그 수정 반영)

# region_field 가 이 값이면 기업 지역 무관하게 적격(타지역 아님)
_REGION_OK_TOKENS = ("전국", "수도권", "전국(지역무관)", "지역무관", "")
_CANDIDATE_CAP = 300  # 후보 파일당 상한(전체 건수는 summary 에 별도 기록)


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _notice_key(it: dict) -> str:
    for f in ("id", "notice_id", "url", "link", "detail_url"):
        v = it.get(f)
        if v:
            return str(v)
    return "t:" + str(it.get("title", ""))[:90]


def _load_items(data_root: Path, date: str | None, cap: int | None) -> list[dict]:
    items: list[dict] = []
    if date:
        globs = [f"{date}/notices/*/meta.json"]
    else:
        globs = ["*/notices/*/meta.json"]
    seen: set[str] = set()
    for g in globs:
        for mp in sorted(data_root.glob(g)):
            try:
                d = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not (isinstance(d, dict) and (d.get("title") or d.get("description"))):
                continue
            k = _notice_key(d)
            if k in seen:  # 날짜 교차 중복 제거(최초 유지)
                continue
            seen.add(k)
            items.append(d)
            if cap and len(items) >= cap:
                return items
    return items


def _is_region_fp(region_field: str, city: str) -> bool:
    """matched 공고의 region_field 가 기업 지역이 아닌 명백한 타지역인가(하드 KPI)."""
    rf = (region_field or "").strip()
    if not rf or rf in _REGION_OK_TOKENS:
        return False
    if "전국" in rf or "수도권" in rf:
        return False
    return bool(city) and (city not in rf)


def _rf_is_own(region_field: str, city: str) -> bool:
    rf = (region_field or "").strip()
    return bool(rf) and bool(city) and (city in rf)


def _rf_is_nationwide(region_field: str) -> bool:
    rf = (region_field or "").strip()
    return ("전국" in rf) or ("수도권" in rf)


_REGION_SUFFIXES = ("특별자치도", "특별자치시", "특별시", "광역시", "자치도", "자치시", "도", "시")


def _short_region(tok: str) -> str:
    """광역명 → 짧은형(서울특별시→서울, 경기도→경기)."""
    t = (tok or "").strip()
    for suf in _REGION_SUFFIXES:
        if t.endswith(suf) and len(t) > len(suf):
            return t[: -len(suf)]
    return t


def _own_in_bracket_tag(title: str, city: str) -> bool:
    """제목의 대괄호 태그 [서울ㆍ인천ㆍ경기ㆍ강원] 안에 own 시가 토큰으로 있는가.
    접두어(prefix)뿐 아니라 태그 어느 위치든 잡는다 — 다지역 태그 own 오차단(누락) 색출."""
    if not city:
        return False
    cs = _short_region(city)
    for grp in re.findall(r"\[([^\]]{1,40})\]", title or ""):
        for tk in re.split(r"[ㆍ·|/,、\s]+", grp):
            if tk and _short_region(tk) == cs:
                return True
    return False


def _field_health(item: dict) -> dict:
    """공고 1건의 5필드 중 지역 외 4필드(게시일·접수기간·지원금·성격) 추출 건전성.
    monitor 추출함수를 '호출만' 해 present/valid 여부를 본다(판정로직 미수정). 값:
      posted: ok|missing|bad / period: ok|missing / deadline_status: open|closed|upcoming|unknown
      amount: present|none / type: classified|unclassified
    """
    # 게시일
    pd = str(item.get("posted_date") or "").strip()
    if not pd:
        posted = "missing"
    else:
        try:
            datetime.strptime(pd[:10], "%Y-%m-%d")
            posted = "ok"
        except Exception:  # noqa: BLE001
            posted = "bad"
    # 접수기간 / 마감
    try:
        dstat = monitor.classify_deadline_status(item)
    except Exception:  # noqa: BLE001
        dstat = "unknown"
    try:
        dl = str(monitor.resolve_item_deadline(item) or "").strip()
    except Exception:  # noqa: BLE001
        dl = ""
    has_period = bool(item.get("application_period")) or bool(dl and not dl.startswith("2099"))
    period = "ok" if has_period else "missing"
    # 지원금
    try:
        amt = monitor.extract_support_amount(monitor._notice_text(item))
    except Exception:  # noqa: BLE001
        amt = None
    amount = "present" if amt else "none"
    # 성격(지원유형)
    try:
        types = monitor.classify_support_type(item)
    except Exception:  # noqa: BLE001
        types = ["그외"]
    typ = "classified" if [t for t in types if t != "그외"] else "unclassified"
    return {"posted": posted, "period": period, "deadline_status": dstat,
            "amount": amount, "type": typ}


def _load_golden_regions() -> dict[str, str]:
    """골든셋(id→region_field) — meta 에 region_field 없는 공고의 약라벨 보충용.

    Tier A(소스 제공)는 meta 에 이미 있으므로 여기 값은 주로 Tier B(제목태그)·
    Tier C(사람확인). meta 값이 있으면 meta 우선(골든이 meta 를 덮지 않음).
    """
    path = BASE_DIR / "data" / "golden" / "region_labels.jsonl"
    out: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                i = str(d.get("id") or "")
                rf = str(d.get("region_field") or "").strip()
                if i and rf and i not in out:
                    out[i] = rf
    except OSError:
        pass
    return out


def build(date: str | None, cap: int | None) -> dict:
    data_root = BASE_DIR / "data" / "raw"
    if not data_root.exists():
        return {"error": f"raw store 없음: {data_root}"}
    items = _load_items(data_root, date, cap)
    companies = company_match.load_companies()
    try:
        groups = monitor.load_groups()
    except Exception as e:  # noqa: BLE001
        groups = []
        print(f"[warn] load_groups 실패: {e}", file=sys.stderr)
    if not items or not companies:
        return {"error": f"공고 {len(items)} / 기업 {len(companies)} — 측정 불가"}

    golden_rf = _load_golden_regions()
    fb_verdicts = feedback.feedback_verdicts()   # 사람 정답(Tier C): {공고id: 'O'|'X'}

    # 공고 인덱스 (키 기준)
    notices: dict[str, dict] = {}
    order: list[str] = []
    for it in items:
        k = _notice_key(it)
        if k in notices:
            continue
        order.append(k)
        notices[k] = {
            "id": k,
            "title": str(it.get("title", ""))[:110],
            "source": str(it.get("source") or it.get("site") or it.get("agency") or ""),
            "region_field": str(it.get("region_field") or "").strip() or golden_rf.get(k, ""),
            "feedback": fb_verdicts.get(k, ""),
            "fields": _field_health(it),
            "companies": {},
            "groups": {},
        }

    company_city = {c.get("id"): (c.get("region") or {}).get("city", "") or "" for c in companies}

    # ── 기업 경로 (기업별 enrich = #15 회피) ──
    for c in companies:
        cid = c.get("id")
        enriched = _enrich_for_company(items, c)
        res = company_match.match_for_company(enriched, c)
        for it in res["matched"]:
            bd = it.get("_match_breakdown", {}) or {}
            notices[_notice_key(it)]["companies"][cid] = {
                "decision": "matched",
                "score": int(it.get("_match_score", 0)),
                "region_status": bd.get("region_status"),
                "exclude_hits": bd.get("exclude_hits", 0),
                "mismatches": (it.get("_match_mismatches") or [])[:2],
            }
        for it in res["rejected"]:
            bd = it.get("_match_breakdown", {}) or {}
            reason = it.get("_match_reason")
            notices[_notice_key(it)]["companies"][cid] = {
                "decision": "rejected_hard" if reason else "rejected_score",
                "score": int(it.get("_match_score", 0)),
                "region_status": bd.get("region_status"),
                "exclude_hits": bd.get("exclude_hits", 0),
                "reason": reason,
                "mismatches": (it.get("_match_mismatches") or [])[:2],
            }

    # ── 그룹 경로 ──
    group_city: dict[str, str] = {}
    for g in groups:
        gid = g.get("id") or g.get("name") or "grp"
        group_city[gid] = (g.get("applicant_region_city") or "").strip()
        for it in items:
            try:
                ev = monitor.evaluate_notice(it, g)
            except Exception:  # noqa: BLE001
                continue
            notices[_notice_key(it)]["groups"][gid] = {
                "is_relevant": bool(ev.get("is_relevant")),
                "region_status": ev.get("region_status"),
                "region_unknown_review": bool(ev.get("region_unknown_review")),
                # 전체 코드 보존(잘리면 feedback_suggest 의 키워드/지역/제외 진단이 오판하고
                # 아래 grp_region_blocked 판정도 코드가 3번째 밖이면 놓친다). 표시는 소비측에서 자른다.
                "reason_codes": list(ev.get("exclude_reason_codes") or []),
                # 키워드 게이트 통과 여부(순수). INDUSTRY_NOT_MATCHED 는 키워드 미스와 지원유형
                # 불일치 둘 다에서 붙으므로, feedback_suggest 가 둘을 구분하려면 이 신호가 필요하다.
                "keyword_pass": bool(ev.get("group_keyword_pass", True)),
            }

    # ── 후보·모순·KPI 산출 ──
    fp: dict[str, list] = defaultdict(list)
    fn: dict[str, list] = defaultdict(list)
    contradictions: list[dict] = []
    region_fp_hits: list[dict] = []
    labeled_own_or_nw = 0
    labeled_own_or_nw_fn = 0

    _REGION_BLOCKED = {"other_only", "nationwide_other_region"}

    for k in order:
        n = notices[k]
        rf = n["region_field"]
        for cid, cv in n["companies"].items():
            city = company_city.get(cid, "")
            dec = cv["decision"]
            rstat = cv.get("region_status")
            matched = dec == "matched"
            # region_FP (하드 KPI, 약라벨 기반)
            if matched and _is_region_fp(rf, city):
                region_fp_hits.append({"id": k, "cid": cid, "city": city, "rf": rf, "title": n["title"][:60]})
            # ── FP 후보 (matched-but-suspect) ──
            if matched:
                if _is_region_fp(rf, city):
                    fp["fp_weaklabel_otherregion"].append({"id": k, "cid": cid, "city": city, "rf": rf, "title": n["title"]})
                if rstat in _REGION_BLOCKED:
                    fp["fp_region_leak"].append({"id": k, "cid": cid, "city": city, "region_status": rstat, "title": n["title"]})
                if cv.get("exclude_hits", 0):
                    fp["fp_exclude_leak"].append({"id": k, "cid": cid, "exclude_hits": cv["exclude_hits"], "score": cv["score"], "title": n["title"]})
            # ── FN 후보 (rejected-but-suspect) ──
            if dec == "rejected_score":
                if _rf_is_own(rf, city):
                    fn["fn_weaklabel_own"].append({"id": k, "cid": cid, "city": city, "rf": rf, "score": cv["score"], "title": n["title"]})
                if _rf_is_nationwide(rf) and rstat in _REGION_BLOCKED:
                    fn["fn_nationwide_blocked"].append({"id": k, "cid": cid, "rf": rf, "region_status": rstat, "title": n["title"]})
                # 제목 대괄호 태그 안에 own 시가 토큰으로 있는데 지역차단(다지역 태그 own 오차단 포함)
                if _own_in_bracket_tag(n["title"], city) and rstat in _REGION_BLOCKED:
                    fn["fn_titletag_own"].append({"id": k, "cid": cid, "city": city, "region_status": rstat, "title": n["title"]})

        # 지역 recall@labeled 분모: own/전국 약라벨이 있는 (공고,기업) 쌍.
        # 누락(FN)은 '지역 사유로 차단'(region_status ∈ blocked)한 경우만 카운트한다.
        # 산업·점수 미달로 인한 미매칭은 지역 누락이 아니므로 제외(recall 왜곡 방지).
        for cid, cv in n["companies"].items():
            city = company_city.get(cid, "")
            if _rf_is_own(rf, city) or (_rf_is_nationwide(rf) and city):
                labeled_own_or_nw += 1
                if cv.get("region_status") in _REGION_BLOCKED:
                    labeled_own_or_nw_fn += 1

        # ── 자기모순(경로 지역 verdict 불일치, #15 신호) ──
        # 같은 지역(city)을 신청자로 갖는 그룹과 그 지역 기업의 지역판정이 반대 방향인가
        for cid, cv in n["companies"].items():
            city = company_city.get(cid, "")
            if not city:
                continue
            comp_region_blocked = cv.get("region_status") in _REGION_BLOCKED
            comp_region_ok = cv.get("region_status") in {"city", "district", "nationwide"}
            for gid, gv in n["groups"].items():
                if group_city.get(gid, "") != city:
                    continue
                grp_region_blocked = "REGION_NOT_ELIGIBLE" in gv.get("reason_codes", []) or gv.get("region_status") == "not_eligible"
                grp_region_ok = gv.get("region_status") == "eligible"
                if (comp_region_blocked and grp_region_ok) or (comp_region_ok and grp_region_blocked):
                    contradictions.append({
                        "id": k, "city": city, "cid": cid, "gid": gid,
                        "company_region_status": cv.get("region_status"),
                        "group_region_status": gv.get("region_status"),
                        "group_reason_codes": gv.get("reason_codes", []),
                        "title": n["title"][:70],
                    })

    # ── 사람 정답(Tier C 피드백) 대조 ──
    # "실제 나간 메일이 맞았나"가 최종 정답. 우리가 추천(그룹 발송 대상 또는 기업 매칭)한 것과
    # 사람 O/X 가 어긋난 건만 뽑아 하네스(fp-hunter/fn-hunter)의 최우선 입력으로 넘긴다.
    fb_agree = fb_fp = fb_fn = 0
    fb_mismatch: list[dict] = []
    for k in order:
        n = notices[k]
        v = n.get("feedback") or ""
        if not v:
            continue
        rec_groups = [gid for gid, gv in n["groups"].items() if gv.get("is_relevant")]
        rec_comps = [cid for cid, cv in n["companies"].items() if cv.get("decision") == "matched"]
        recommended = bool(rec_groups or rec_comps)
        if v == "X" and recommended:
            fb_fp += 1
            fb_mismatch.append({"id": k, "kind": "feedback_fp", "title": n["title"],
                                "groups": rec_groups, "companies": rec_comps,
                                "note": "사람 X 인데 추천/발송됨"})
        elif v == "O" and not recommended:
            fb_fn += 1
            fb_mismatch.append({"id": k, "kind": "feedback_fn", "title": n["title"],
                                "groups": [], "companies": [],
                                "note": "사람 O 인데 추천 안 됨(누락)"})
        else:
            fb_agree += 1
    fb_labeled = fb_agree + fb_fp + fb_fn

    # 매칭 총량(그룹/기업)
    matched_by_company = Counter()
    for k in order:
        for cid, cv in notices[k]["companies"].items():
            if cv["decision"] == "matched":
                matched_by_company[cid] += 1
    relevant_by_group = Counter()
    for k in order:
        for gid, gv in notices[k]["groups"].items():
            if gv.get("is_relevant"):
                relevant_by_group[gid] += 1

    # ── 5필드 추출 건전성 집계(지역 외 4필드: 게시일·접수기간·지원금·성격) ──
    field_counts = {f: Counter() for f in ("posted", "period", "deadline_status", "amount", "type")}
    field_cand: dict[str, list] = defaultdict(list)
    for k in order:
        fh = notices[k]["fields"]
        for f, v in fh.items():
            field_counts[f][v] += 1
        # 이상 후보 — 디지털 표시/게이트에 영향(누락제로 관점: 미상은 버리지 말고 surface)
        if fh["posted"] != "ok":
            field_cand["field_posted_bad"].append({"id": k, "posted": fh["posted"], "title": notices[k]["title"]})
        if fh["period"] == "missing" and fh["deadline_status"] == "unknown":
            field_cand["field_period_unknown"].append({"id": k, "title": notices[k]["title"]})
        if fh["type"] == "unclassified":
            field_cand["field_type_unclassified"].append({"id": k, "title": notices[k]["title"]})
    field_health = {f: dict(c) for f, c in field_counts.items()}
    field_cand_counts = {c: len(v) for c, v in field_cand.items()}

    region_fp_total = len(region_fp_hits)
    fp_counts = {code: len(v) for code, v in fp.items()}
    fn_counts = {code: len(v) for code, v in fn.items()}
    region_recall_at_labeled = None
    if labeled_own_or_nw:
        region_recall_at_labeled = round(1 - labeled_own_or_nw_fn / labeled_own_or_nw, 4)

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_filter": date or "ALL",
        "n_notices": len(order),
        "n_companies": len(companies),
        "n_groups": len(groups),
        "region_field_labeled": sum(1 for k in order if notices[k]["region_field"]),
        "kpi": {
            "region_FP": region_fp_total,
            "region_recall_at_labeled": region_recall_at_labeled,
            "region_recall_denom": labeled_own_or_nw,
            "region_recall_fn": labeled_own_or_nw_fn,
        },
        "matched_by_company": dict(matched_by_company),
        "relevant_by_group": dict(relevant_by_group),
        "fp_candidate_counts": fp_counts,
        "fn_candidate_counts": fn_counts,
        "contradiction_count": len(contradictions),
        "feedback": {
            "labeled": fb_labeled,
            "agree": fb_agree,
            "feedback_fp": fb_fp,
            "feedback_fn": fb_fn,
            "agreement": round(fb_agree / fb_labeled, 4) if fb_labeled else None,
        },
        "field_health": field_health,
        "field_candidate_counts": field_cand_counts,
    }

    return {
        "summary": summary,
        "matrix": {"meta": {k: summary[k] for k in ("generated_utc", "date_filter", "n_notices", "n_companies", "n_groups")},
                   "notices": [notices[k] for k in order]},
        "fp": {"counts": fp_counts, "cap": _CANDIDATE_CAP, "candidates": {c: v[:_CANDIDATE_CAP] for c, v in fp.items()}},
        "fn": {"counts": fn_counts, "cap": _CANDIDATE_CAP, "candidates": {c: v[:_CANDIDATE_CAP] for c, v in fn.items()}},
        "field": {"counts": field_cand_counts, "cap": _CANDIDATE_CAP, "candidates": {c: v[:_CANDIDATE_CAP] for c, v in field_cand.items()}},
        "contradictions": contradictions[: _CANDIDATE_CAP * 2],
        "region_fp_hits": region_fp_hits,
        "feedback_mismatch": fb_mismatch[: _CANDIDATE_CAP * 2],
    }


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    ap = argparse.ArgumentParser(description="전수 채점 매트릭스 (읽기전용)")
    ap.add_argument("--date", default=None, help="특정 날짜만(예: 2026-07-07). 생략=전수")
    ap.add_argument("--max", type=int, default=None, help="앞 N건만(스모크)")
    ap.add_argument("--out", default=None, help="산출 디렉터리(기본 .omc/accuracy/runs/{today})")
    args = ap.parse_args(argv)

    res = build(args.date, args.max)
    if res.get("error"):
        print(f"[SKIP] {res['error']}")
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(args.out) if args.out else (BASE_DIR / ".omc" / "accuracy" / "runs" / today)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "matrix.json").write_text(json.dumps(res["matrix"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "fp_candidates.json").write_text(json.dumps(res["fp"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "fn_candidates.json").write_text(json.dumps(res["fn"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "contradictions.json").write_text(json.dumps(res["contradictions"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "field_candidates.json").write_text(json.dumps(res["field"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(res["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "feedback_mismatch.json").write_text(json.dumps(res["feedback_mismatch"], ensure_ascii=False, indent=1), encoding="utf-8")

    s = res["summary"]
    print(f"[matrix] 공고 {s['n_notices']} × 기업 {s['n_companies']} × 그룹 {s['n_groups']}  (라벨 {s['region_field_labeled']}건)")
    print(f"[KPI] region_FP={s['kpi']['region_FP']}  region_recall@labeled={s['kpi']['region_recall_at_labeled']} (분모 {s['kpi']['region_recall_denom']}, 지역차단 FN {s['kpi']['region_recall_fn']})")
    print(f"[FP후보] {s['fp_candidate_counts']}")
    print(f"[FN후보] {s['fn_candidate_counts']}")
    print(f"[자기모순] {s['contradiction_count']}건")
    fb = s["feedback"]
    if fb["labeled"]:
        print(f"[사람정답(O/X 피드백)] 라벨 {fb['labeled']}건 · 일치 {fb['agree']} "
              f"(일치율 {fb['agreement']}) · 오추천 {fb['feedback_fp']} · 누락 {fb['feedback_fn']}")
    else:
        print("[사람정답(O/X 피드백)] 라벨 0건 — 메일의 O/X 링크를 누르면 여기 쌓입니다"
              " (python scripts/collect_feedback.py)")
    fh = s["field_health"]
    n = max(s["n_notices"], 1)
    print("[5필드 건전성(지역 외 4)]")
    print(f"  게시일 ok={fh['posted'].get('ok',0)} / missing={fh['posted'].get('missing',0)} / bad={fh['posted'].get('bad',0)}")
    print(f"  접수기간 ok={fh['period'].get('ok',0)} / missing={fh['period'].get('missing',0)}  마감상태={dict(fh['deadline_status'])}")
    print(f"  지원금 present={fh['amount'].get('present',0)} / none={fh['amount'].get('none',0)}")
    print(f"  성격 classified={fh['type'].get('classified',0)} / unclassified={fh['type'].get('unclassified',0)}")
    print(f"[필드이상후보] {s['field_candidate_counts']}")
    print(f"[out] {out_dir}")
    return 0 if s["kpi"]["region_FP"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

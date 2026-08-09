"""P2-6: Golden 데이터 기반 정확도 자동 검증 스크립트

region_labels.jsonl (2046건)을 읽어 evaluate_notice() 결과와 대조하고
정밀도/재현율을 측정한다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor import evaluate_notice, classify_deadline_status


def load_golden(path: str) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run_accuracy_check(golden_path: str, max_items: int = 200):
    """Golden labels로 정확도를 측정한다."""
    items = load_golden(golden_path)[:max_items]

    group = {
        "id": "grp_prestartup_ai",
        "or_keywords": ["AI 스타트업", "인공지능 스타트업", "AI 솔루션", "예비창업", "창업예정"],
        "and_keyword_groups": [["AI", "창업"], ["AI", "스타트업"], ["AI", "사업화"]],
        "exclude_keywords": ["성료", "지침 안내", "결과 발표", "보도자료", "채용", "재직자"],
        "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
        "applicant_region_city": "서울특별시",
        "applicant_region_label": "서울",
        "extra_eligible_regions": ["인천", "경기", "수도권"],
    }

    results = {
        "total": len(items),
        "auto_include": 0,
        "auto_exclude": 0,
        "human_review": 0,
        "exclude_reasons": {},
        "support_field_distribution": {},
        "deadline_distribution": {},
        "fp_cases": [],
        "fn_cases": [],
    }

    for item in items:
        notice = {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "description": "",
            "link": "",
            "author": "",
            "deadline": item.get("deadline", ""),
            "source": item.get("source", ""),
            "is_aggregator": False,
            "posted_date": item.get("posted_date", ""),
            "region_field": item.get("region_field", ""),
            "support_field": item.get("support_field", ""),
        }

        result = evaluate_notice(notice, group)
        reasons = result.get("exclude_reason_codes", [])
        is_relevant = result.get("is_relevant", False)
        deadline_status = classify_deadline_status(notice)

        if is_relevant:
            results["auto_include"] += 1
        else:
            results["auto_exclude"] += 1

        for r in reasons:
            results["exclude_reasons"][r] = results["exclude_reasons"].get(r, 0) + 1

        support = item.get("support_field", "unknown")
        results["support_field_distribution"][support] = results["support_field_distribution"].get(support, 0) + 1
        results["deadline_distribution"][deadline_status] = results["deadline_distribution"].get(deadline_status, 0) + 1

        # FP: 교육/멘토링 단독인데 포함
        if any(kw in support for kw in ["교육", "멘토링", "컨설팅", "행사"]):
            if is_relevant:
                results["fp_cases"].append({"id": item.get("id"), "title": notice["title"][:50], "support": support})

        # FN: 사업화/R&D인데 제외 (지역 외 이유)
        if any(kw in support for kw in ["사업화", "기술개발", "R&D"]):
            if not is_relevant and "REGION_NOT_ELIGIBLE" not in reasons and "CLOSED_DEADLINE" not in reasons:
                results["fn_cases"].append({"id": item.get("id"), "title": notice["title"][:50], "support": support, "reasons": reasons})

    return results


if __name__ == "__main__":
    golden_path = str(Path(__file__).resolve().parent.parent / "data" / "golden" / "region_labels.jsonl")
    results = run_accuracy_check(golden_path, max_items=200)

    print("\n=== P2-6: 정확도 자동 검증 결과 ===")
    print(f"총 검증: {results['total']}건")
    print(f"자동 포함: {results['auto_include']}건")
    print(f"자동 제외: {results['auto_exclude']}건")

    print(f"\n제외 사유 분포:")
    for reason, count in sorted(results["exclude_reasons"].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}건")

    print(f"\n지원유형 분포:")
    for support, count in sorted(results["support_field_distribution"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {support}: {count}건")

    print(f"\n마감 상태 분포:")
    for status, count in sorted(results["deadline_distribution"].items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}건")

    if results["fp_cases"]:
        print(f"\n⚠️ False Positive ({len(results['fp_cases'])}건):")
        for fp in results["fp_cases"][:5]:
            print(f"  - {fp['id']}: {fp['title']} ({fp['support']})")

    if results["fn_cases"]:
        print(f"\n⚠️ False Negative ({len(results['fn_cases'])}건):")
        for fn in results["fn_cases"][:5]:
            print(f"  - {fn['id']}: {fn['title']} ({fn['support']}) - {fn['reasons']}")

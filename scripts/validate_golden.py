"""Milestone C — Golden 데이터 기반 실데이터 검증 스크립트

region_labels.jsonl (2046건)을 읽어 evaluate_notice() 결과와 대조한다.
"""
import json
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor import evaluate_notice, classify_deadline_status, classify_support_type


def load_golden(path: str) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def validate_region_labels(golden_path: str, max_items: int = 200):
    """region_labels.jsonl의 공고를 evaluate_notice()로 판정하고 결과를 집계한다."""
    items = load_golden_path = load_golden(golden_path)

    # 최대 max_items건만 검증
    items = items[:max_items]

    stats = {
        "total": len(items),
        "included": 0,
        "excluded": 0,
        "conditional": 0,
        "review": 0,
        "unknown": 0,
        "exclude_reasons": {},
        "support_types": {},
        "deadline_statuses": {},
        "region_eligible": 0,
        "region_not_eligible": 0,
        "region_unknown": 0,
    }

    # 기본 그룹 설정 (grp_prestartup_ai 유사)
    group = {
        "id": "grp_prestartup_ai",
        "or_keywords": ["AI 스타트업", "인공지능 스타트업", "AI 솔루션"],
        "and_keyword_groups": [["AI", "창업"], ["AI", "스타트업"], ["AI", "사업화"]],
        "exclude_keywords": ["성료", "지침 안내", "결과 발표", "보도자료", "채용", "재직자"],
        "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
        "applicant_region_city": "서울특별시",
        "applicant_region_label": "서울",
        "extra_eligible_regions": ["인천", "경기", "수도권"],
    }

    fp_cases = []  # False Positive: 포함되면 안 되는데 포함된 경우
    fn_cases = []  # False Negative: 포함되어야 하는데 제외된 경우

    for item in items:
        # evaluate_notice()에 전달할 형식으로 변환
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
        region_status = result.get("region_status", "unknown")
        deadline_status = classify_deadline_status(notice)

        # 통계 집계
        if is_relevant:
            stats["included"] += 1
        elif "REGION_NOT_ELIGIBLE" in reasons:
            stats["excluded"] += 1
            stats["region_not_eligible"] += 1
        elif "CLOSED_DEADLINE" in reasons:
            stats["excluded"] += 1
        elif "CONSULTING_ONLY" in reasons or "INVESTMENT_ONLY" in reasons:
            stats["excluded"] += 1
        elif "INDUSTRY_NOT_MATCHED" in reasons:
            stats["excluded"] += 1
        elif "NOT_GRANT_NOTICE" in reasons:
            stats["excluded"] += 1
        else:
            stats["unknown"] += 1

        for r in reasons:
            stats["exclude_reasons"][r] = stats["exclude_reasons"].get(r, 0) + 1

        stats["deadline_statuses"][deadline_status] = stats["deadline_statuses"].get(deadline_status, 0) + 1

        # FP/FN 탐지 (간단한 휴리스틱)
        support_field = item.get("support_field", "")
        title = item.get("title", "")

        # FP: 교육/멘토링/컨설팅/행사 단독인데 포함된 경우
        if any(kw in support_field for kw in ["교육", "멘토링", "컨설팅", "행사", "네트워크"]):
            if is_relevant:
                fp_cases.append({"id": item.get("id"), "title": title[:50], "support_field": support_field, "reason": "교육/멘토링 단독인데 포함"})

        # FN: 사업화/기술개발인데 제외된 경우 (지역 외 이유)
        if any(kw in support_field for kw in ["사업화", "기술개발", "R&D"]):
            if not is_relevant and "REGION_NOT_ELIGIBLE" not in reasons and "CLOSED_DEADLINE" not in reasons:
                fn_cases.append({"id": item.get("id"), "title": title[:50], "support_field": support_field, "reasons": reasons})

    return stats, fp_cases, fn_cases


if __name__ == "__main__":
    golden_path = str(Path(__file__).resolve().parent.parent / "data" / "golden" / "region_labels.jsonl")
    stats, fp_cases, fn_cases = validate_region_labels(golden_path, max_items=200)

    print("\n=== 실데이터 검증 결과 ===")
    print(f"총 검증: {stats['total']}건")
    print(f"포함: {stats['included']}건")
    print(f"제외: {stats['excluded']}건")
    print(f"미분류: {stats['unknown']}건")
    print(f"\n제외 사유 분포:")
    for reason, count in sorted(stats["exclude_reasons"].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}건")
    print(f"\n마감 상태 분포:")
    for status, count in sorted(stats["deadline_statuses"].items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}건")

    if fp_cases:
        print(f"\n=== False Positive ({len(fp_cases)}건) ===")
        for case in fp_cases[:10]:
            print(f"  {case['id']}: {case['title']} ({case['support_field']}) - {case['reason']}")

    if fn_cases:
        print(f"\n=== False Negative ({len(fn_cases)}건) ===")
        for case in fn_cases[:10]:
            print(f"  {case['id']}: {case['title']} ({case['support_field']}) - {case['reasons']}")

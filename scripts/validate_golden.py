"""Golden 데이터 기반 검증 스크립트

- region_labels.jsonl: 지역 정답지 (지역 ground truth, relevance 정답 아님)
- feedback_labels.jsonl: O/X 피드백 (relevance ground truth, 소량)
- unlabeled corpus: 정답 없이 INCLUDE/EXCLUDE 분포만 집계

정밀도/재현율은 relevance 라벨이 있을 때만 계산하고,
없으면 NOT_MEASURABLE이라고 명확히 표시한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os_environ = __import__("os").environ
os_environ.setdefault("BIZINFO_API_KEY", "dummy")
os_environ.setdefault("ANTHROPIC_API_KEY", "dummy")
os_environ.setdefault("GMAIL_ADDRESS", "dummy@example.com")
os_environ.setdefault("GMAIL_APP_PASSWORD", "dummy")

from monitor import evaluate_notice, classify_deadline_status  # noqa: E402


def load_jsonl(path: str) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_group_config(group_id: str = "grp_prestartup_ai") -> dict | None:
    """config/groups.json에서 실제 그룹 설정을 읽는다."""
    groups_path = ROOT / "config" / "groups.json"
    if not groups_path.exists():
        return None
    groups = json.loads(groups_path.read_text(encoding="utf-8"))
    for g in groups:
        if g.get("id") == group_id:
            return g
    return None


def run_corpus_validation(items: list[dict], group: dict) -> dict:
    """Unlabeled corpus: INCLUDE/EXCLUDE/CONDITIONAL 분포만 집계 (FP/FN 아님)."""
    results = {
        "total": len(items),
        "auto_include": 0,
        "auto_exclude": 0,
        "human_review": 0,
        "exclude_reasons": {},
        "support_field_distribution": {},
        "deadline_distribution": {},
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

    return results


def run_labeled_benchmark(feedback_path: str, group: dict) -> dict:
    """Labeled benchmark: O/X 피드백으로 precision/recall 계산."""
    items = load_jsonl(feedback_path)
    if not items:
        return {"status": "NOT_MEASURABLE", "reason": "no feedback labels found", "labeled_count": 0}

    tp = fp = tn = fn = 0
    for item in items:
        verdict = item.get("verdict", "").upper()
        if verdict not in ("O", "X"):
            continue
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
        predicted = result.get("is_relevant", False)
        actual = verdict == "O"

        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    total = tp + fp + tn + fn
    if total == 0:
        return {"status": "NOT_MEASURABLE", "reason": "no valid O/X labels", "labeled_count": 0}

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "status": "MEASURED",
        "labeled_count": total,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


if __name__ == "__main__":
    # 실제 그룹 설정 사용 (하드코딩 금지)
    group = load_group_config("grp_prestartup_ai")
    if not group:
        print("ERROR: grp_prestartup_ai not found in config/groups.json")
        sys.exit(1)

    print("=== Unlabeled Corpus Validation (region_labels.jsonl) ===")
    print("NOTE: region_labels.jsonl은 지역 정답지입니다. relevance ground truth가 아닙니다.")
    region_path = str(ROOT / "data" / "golden" / "region_labels.jsonl")
    region_items = load_jsonl(region_path)
    corpus = run_corpus_validation(region_items, group)
    print(f"총 검증: {corpus['total']}건")
    print(f"INCLUDE: {corpus['auto_include']}건")
    print(f"EXCLUDE: {corpus['auto_exclude']}건")
    print(f"\n제외 사유 분포:")
    for reason, count in sorted(corpus["exclude_reasons"].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}건")
    print(f"\n지원유형 분포:")
    for support, count in sorted(corpus["support_field_distribution"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {support}: {count}건")
    print(f"\n마감 상태 분포:")
    for status, count in sorted(corpus["deadline_distribution"].items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}건")

    print("\n=== Labeled Benchmark (feedback_labels.jsonl) ===")
    feedback_path = str(ROOT / "data" / "golden" / "feedback_labels.jsonl")
    labeled = run_labeled_benchmark(feedback_path, group)
    print(f"상태: {labeled['status']}")
    if labeled["status"] == "MEASURED":
        print(f"라벨 수: {labeled['labeled_count']}건")
        print(f"TP={labeled['tp']} FP={labeled['fp']} TN={labeled['tn']} FN={labeled['fn']}")
        print(f"Precision: {labeled['precision']}")
        print(f"Recall: {labeled['recall']}")
        print(f"F1: {labeled['f1']}")
    else:
        print(f"사유: {labeled.get('reason', 'unknown')}")

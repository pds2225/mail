r"""expand_golden_labels — 제목 지역태그 기반 골든셋 확대 (Tier B, append-only).

extract_golden_labels(Tier A: meta.json 의 소스 제공 region_field)가 모으지 못하는
공고들의 지역 정답을, 공고 게시기관이 제목 앞에 붙인 지역 태그([서울]·[경기] 등)에서
추출해 Tier B 약라벨로 골든셋에 추가한다. recall@labeled 의 분모를 넓혀
"라벨 28개 위 만점" 착시를 해소하는 것이 목적.

판정기(monitor/company_match)와 독립된 신호(게시기관 부여 태그)만 사용한다 —
판정기 로직을 베끼면 정답지가 판정기를 재생산해 채점이 무의미해지기 때문(순환 채점 방지).

보수 원칙(라벨 오염 < 빈칸):
  · 태그 전체가 광역 지역명(정식/축약/통용 변형)일 때만 라벨 생성.
  · "광주"는 광주광역시/경기 광주시 모호 → 라벨 금지, 리뷰 큐로.
  · 기관명 태그([인천테크노파크] 등)·시군구 태그([미추홀구])는 라벨 금지, 리뷰 큐로
    (기관 소재지 ≠ 지원대상 지역일 수 있음 — 사람확인 승격 대상).
  · 기존 golden id 는 절대 덮어쓰지 않음(Tier A·사람확인 Tier C 보존, append-only).

산출물:
  data/golden/region_labels.jsonl   Tier B 라벨 append (1줄=1라벨)
  data/golden/review_queue.jsonl    애매 후보 append (사람확인 큐, S1 승격 대상)

실행 (PowerShell, repo 루트에서):
  python scripts\expand_golden_labels.py                # 전 날짜 스캔
  python scripts\expand_golden_labels.py --date 2026-07-16
  python scripts\expand_golden_labels.py --dry-run      # 쓰기 없이 통계만
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GOLDEN = BASE_DIR / "data" / "golden" / "region_labels.jsonl"
REVIEW = BASE_DIR / "data" / "golden" / "review_queue.jsonl"


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _notice_key(it: dict) -> str:
    """accuracy_matrix._notice_key 와 동일 규칙 — golden id 가 매트릭스 키와 일치해야 보충됨."""
    for f in ("id", "notice_id", "url", "link", "detail_url"):
        v = it.get(f)
        if v:
            return str(v)
    return "t:" + str(it.get("title", ""))[:90]


# 광역 정식명칭 (기존 Tier A 라벨 값 형식과 동일)
_CANON: dict[str, str] = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도", "전국": "전국", "수도권": "수도권",
    # "광주" 축약은 경기 광주시와 모호 → 의도적으로 제외(정식명칭만 허용)
}
_VARIANTS: dict[str, str] = {
    "서울시": "서울특별시", "부산시": "부산광역시", "대구시": "대구광역시", "인천시": "인천광역시",
    "광주시": "", "대전시": "대전광역시", "울산시": "울산광역시", "세종시": "세종특별자치시",
    "경기도": "경기도", "강원도": "강원특별자치도", "강원특별자치도": "강원특별자치도",
    "충청북도": "충청북도", "충청남도": "충청남도",
    "전라북도": "전북특별자치도", "전북특별자치도": "전북특별자치도", "전북도": "전북특별자치도",
    "전라남도": "전라남도", "경상북도": "경상북도", "경상남도": "경상남도",
    "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
    "서울특별시": "서울특별시", "부산광역시": "부산광역시", "대구광역시": "대구광역시",
    "인천광역시": "인천광역시", "광주광역시": "광주광역시", "대전광역시": "대전광역시",
    "울산광역시": "울산광역시", "세종특별자치시": "세종특별자치시",
    "전국(지역무관)": "전국", "지역무관": "전국",
}
# 지역 힌트(리뷰 큐 후보 감지용)
_REGION_HINT_RX = re.compile(
    "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|"
    "충청|전라|경상|수도권"
)
# 제목 선두 태그: [X] (X) 【X】
_TAG_RX = re.compile(r"^\s*[\[\(【]\s*([^\]\)】]{1,25})\s*[\]\)】]")


def canon_region(tag_text: str) -> str | None:
    """태그 내용 전체가 광역 지역명일 때만 정식명칭 반환. 아니면 None."""
    x = re.sub(r"\s+", "", tag_text or "")
    if not x:
        return None
    if x in _CANON:
        return _CANON[x]
    v = _VARIANTS.get(x)
    return v or None  # ""(모호 표기 광주시)·미등재 → None


def classify_title(title: str) -> tuple[str | None, str | None, str | None]:
    """제목 → (라벨 region_field, 리뷰 사유, 태그원문). 라벨/리뷰 모두 아니면 (None, None, None)."""
    m = _TAG_RX.match(title or "")
    if not m:
        return None, None, None
    tag = m.group(1).strip()
    rf = canon_region(tag)
    if rf:
        return rf, None, tag
    compact = re.sub(r"\s+", "", tag)
    if re.fullmatch(r"[가-힣]{1,6}[시군구]", compact):
        # 순수 시군구 태그([고양시]·[미추홀구]) — 광역 매핑은 사람확인으로
        return None, "sub_region", tag
    if _REGION_HINT_RX.search(tag):
        # 기관명(인천테크노파크)·모호(광주) 등 — 사람확인 대상
        return None, "org_or_ambiguous", tag
    return None, None, None


def _load_jsonl_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(str(json.loads(line).get("id") or ""))
                except Exception:  # noqa: BLE001
                    continue
    except OSError:
        pass
    ids.discard("")
    return ids


def _iter_meta(raw_root: Path, date: str | None):
    pattern = f"{date}/notices/*/meta.json" if date else "*/notices/*/meta.json"
    seen: set[str] = set()
    for mp in sorted(raw_root.glob(pattern)):
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict) or not d.get("title"):
            continue
        k = _notice_key(d)
        if k in seen:  # 날짜 교차 중복(최초 유지)
            continue
        seen.add(k)
        yield k, d


def main() -> int:
    _fix_console()
    ap = argparse.ArgumentParser(description="제목 지역태그 → Tier B 골든 라벨 확대 (append-only)")
    ap.add_argument("--raw-root", default=str(BASE_DIR / "data" / "raw"))
    ap.add_argument("--date", default=None, help="특정 날짜만(예: 2026-07-16). 생략=전 날짜")
    ap.add_argument("--dry-run", action="store_true", help="쓰기 없이 통계만")
    args = ap.parse_args()

    raw_root = Path(args.raw_root)
    if not raw_root.exists():
        print(f"[expand] raw 없음: {raw_root}")
        return 1

    golden_ids = _load_jsonl_ids(GOLDEN)
    review_ids = _load_jsonl_ids(REVIEW)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    n_scan = n_label = n_review = n_skip_exist = 0
    labels: list[dict] = []
    reviews: list[dict] = []
    by_region: dict[str, int] = {}

    for k, it in _iter_meta(raw_root, args.date):
        n_scan += 1
        if str(it.get("region_field") or "").strip():
            continue  # Tier A 원천 있음 → extract_golden_labels 소관
        rf, reason, tag = classify_title(str(it.get("title") or ""))
        if rf:
            if k in golden_ids:
                n_skip_exist += 1
                continue
            golden_ids.add(k)
            n_label += 1
            by_region[rf] = by_region.get(rf, 0) + 1
            labels.append({
                "id": k, "region_field": rf, "source": str(it.get("source") or ""),
                "title": str(it.get("title") or "")[:110], "tier": "B",
                "labeled_by": "title_tag", "tag": tag,
                "first_seen": now, "last_seen": now,
            })
        elif reason:
            if k in golden_ids or k in review_ids:
                continue
            review_ids.add(k)
            n_review += 1
            reviews.append({
                "id": k, "title": str(it.get("title") or "")[:110],
                "source": str(it.get("source") or ""), "tag": tag,
                "reason": reason, "queued_at": now,
            })

    print(f"[expand] 스캔 {n_scan}건 → 신규 Tier B 라벨 {n_label}건, "
          f"리뷰 큐 {n_review}건, 기존 보존 {n_skip_exist}건")
    for rf, c in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {rf}: {c}")

    if args.dry_run:
        print("[expand] dry-run — 쓰기 없음")
        return 0

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN.open("a", encoding="utf-8") as f:
        for row in labels:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with REVIEW.open("a", encoding="utf-8") as f:
        for row in reviews:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[expand] 저장: {GOLDEN.name} +{n_label} / {REVIEW.name} +{n_review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

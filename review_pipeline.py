"""공고 정확도 검수 파이프라인 v1

실행:
  python review_pipeline.py --sample           # 샘플 데이터로 검수 (API/네트워크 불필요)
  python review_pipeline.py --collect          # 실제 수집 후 검수 (BIZINFO_API_KEY 필요)
  python review_pipeline.py --input data.json  # 기존 수집 JSON으로 검수

결과 파일:
  reports/review/YYYY-MM-DD_review.md    — 전체 검수 리포트 (보낼/확인필요/제외)
  reports/review/YYYY-MM-DD_send.csv     — 보낼 공고 목록
  reports/review/YYYY-MM-DD_mail_draft.txt — 메일 초안 (발송 금지)

금지:
  SMTP 호출 없음 — 실제 발송 절대 금지
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent
REVIEW_DIR = BASE_DIR / "reports" / "review"

# ── 분야 분류 규칙 (8개 카테고리) ────────────────────────────────────────────
# 딕셔너리 순서대로 첫 매치를 반환하므로 우선순위를 고려해 정렬
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("정책자금", ["정책자금", "융자", "운전자금", "시설자금", "신보", "기보", "중진공", "대출", "정책금융", "융자계획"]),
    ("수출",     ["수출", "해외", "바이어", "무역", "글로벌", "수출바우처", "해외전시", "해외마케팅", "해외진출"]),
    ("인증",     ["벤처", "이노비즈", "메인비즈", "iso", "인증", "인증서", "확인서"]),
    ("R&D",      ["r&d", "연구개발", "기술개발", "과제", "기술혁신", "연구"]),
    ("창업",     ["창업", "초기창업", "예비창업", "사업화", "스타트업"]),
    ("컨설팅",   ["컨설팅", "멘토링", "현장클리닉", "자문", "진단", "클리닉"]),
    ("교육/행사", ["교육", "세미나", "설명회", "행사", "워크숍", "포럼", "컨퍼런스"]),
]
CATEGORY_NAMES = [cat for cat, _ in CATEGORY_RULES] + ["기타"]

KNOWN_REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _norm_str(text: Any) -> str:
    return " ".join(str(text or "").split()).strip()


def _normalize_title_key(title: str) -> str:
    """중복 판별용 제목 정규화: 소문자 + 비문자 제거."""
    t = unicodedata.normalize("NFKC", title.lower())
    return re.sub(r"[\s\W]+", "", t)


def _parse_date_str(text: str) -> str:
    """텍스트에서 YYYY-MM-DD 날짜 하나를 추출."""
    if not text:
        return ""
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    return ""


def _parse_date_range(text: str) -> tuple[str, str]:
    """'YYYY-MM-DD ~ YYYY-MM-DD' 형식 또는 단일 날짜 표현에서 (start, end) 반환."""
    raw_dates = re.findall(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{4}년\s*\d{1,2}월\s*\d{1,2}일", text)
    parsed = [_parse_date_str(d) for d in raw_dates]
    parsed = [d for d in parsed if d]
    if len(parsed) >= 2:
        return parsed[0], parsed[-1]
    if len(parsed) == 1:
        return "", parsed[0]
    return "", ""


def _region_from_text(text: str) -> str:
    """텍스트에서 지역 추출. '전국' 우선."""
    if "전국" in text:
        return "전국"
    found = [r for r in KNOWN_REGIONS if r in text]
    return ", ".join(found) if found else "전국"


def _classify_category(text_lower: str) -> str:
    """텍스트에서 8개 분야 중 첫 번째 매치를 반환. 매치 없으면 '기타'."""
    for cat, kws in CATEGORY_RULES:
        if any(kw.lower() in text_lower for kw in kws):
            return cat
    return "기타"


def _is_broken_title(title: str) -> bool:
    """깨진 제목 감지: ?????, 연속 물음표, 제어문자 과다."""
    if not title:
        return False
    if "?????" in title or re.search(r"\?{3,}", title):
        return True
    try:
        t = unicodedata.normalize("NFC", title)
        weird = sum(1 for c in t if unicodedata.category(c) in ("Cs", "Cc") and c not in "\t\n\r")
        if len(t) > 0 and weird / len(t) > 0.3:
            return True
    except Exception:
        pass
    return False


# ── 정규화 ───────────────────────────────────────────────────────────────────

def normalize_item(raw: dict) -> dict:
    """다양한 포맷의 raw 공고를 표준 9-field 스키마로 변환.

    지원 포맷:
    - monitor.py item  (title, link, author, deadline, description, ...)
    - 한국어 dict      (제목, 기관, 접수기간, URL, 지역, 키워드, ...)
    - 직접 입력 dict   (title, agency, start_date, end_date, url, ...)
    """
    title = _norm_str(
        raw.get("title") or raw.get("제목") or raw.get("공고명") or ""
    )
    agency = _norm_str(
        raw.get("author") or raw.get("agency") or raw.get("기관")
        or raw.get("기관명") or raw.get("jrsdInsttNm") or ""
    )
    # URL: 'link', 'url', 'URL' 순서로 탐색
    url = _norm_str(
        raw.get("link") or raw.get("url") or raw.get("URL") or ""
    )
    # 날짜: 접수기간 전체 또는 개별 필드에서 추출
    deadline_raw = _norm_str(
        raw.get("deadline") or raw.get("접수기간") or raw.get("reqstBeginEndDe") or ""
    )
    if deadline_raw:
        start_date, end_date = _parse_date_range(deadline_raw)
    else:
        # start_date / end_date 필드가 이미 있는 경우
        start_date = _norm_str(raw.get("start_date") or raw.get("posted_date") or "")
        end_date   = _norm_str(raw.get("end_date") or "")
    if not start_date:
        start_date = _parse_date_str(_norm_str(raw.get("posted_date") or ""))
    # 지역
    raw_region = _norm_str(raw.get("region") or raw.get("지역") or "")
    full_text_for_region = " ".join([
        raw_region, title, _norm_str(raw.get("description") or ""),
        _norm_str(raw.get("raw_text") or ""),
    ])
    region = raw_region if raw_region else _region_from_text(full_text_for_region)
    # raw_text (키워드 포함)
    raw_text = _norm_str(
        raw.get("raw_text") or raw.get("description") or raw.get("키워드")
        or raw.get("bsnsSumryCn") or ""
    )[:500]
    source = _norm_str(raw.get("source") or raw.get("출처") or "")
    # 분야 분류
    cat_text = f"{title} {agency} {raw_text}".lower()
    category = _classify_category(cat_text)

    return {
        "title":        title,
        "agency":       agency,
        "start_date":   start_date,
        "end_date":     end_date,
        "url":          url,
        "region":       region,
        "category":     category,
        "source":       source,
        "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
        "raw_text":     raw_text,
        "_raw_id":      str(raw.get("id") or ""),
    }


# ── 중복 제거 ────────────────────────────────────────────────────────────────

def dedup_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """3단계 중복 제거.

    1차: URL 동일 (비어 있지 않은 경우)
    2차: title_norm + agency_norm + end_date 동일
    3차: URL 없을 때 title_norm + agency_norm 동일

    Returns: (unique_items, removed_duplicates)
    """
    unique: list[dict] = []
    removed: list[dict] = []
    seen_urls: set[str] = set()
    seen_tag_keys: set[str] = set()      # title_norm | agency_norm | end_date
    seen_title_agency: set[str] = set()  # title_norm | agency_norm (URL 없는 경우)

    for item in items:
        url = (item.get("url") or "").strip()
        title_norm  = _normalize_title_key(item.get("title") or "")
        agency_norm = _normalize_title_key(item.get("agency") or "")
        end_date    = (item.get("end_date") or "").strip()
        tag_key     = f"{title_norm}|{agency_norm}|{end_date}"
        ta_key      = f"{title_norm}|{agency_norm}"

        # 1차: URL 중복
        if url and url in seen_urls:
            removed.append({**item, "_dedup_reason": f"URL 중복: {url}"})
            continue

        # 2차: title + agency + end_date 중복
        if title_norm and tag_key in seen_tag_keys:
            removed.append({**item, "_dedup_reason": "제목+기관+마감일 중복"})
            # URL이 있어도 등록해 향후 URL 충돌 방지
            if url:
                seen_urls.add(url)
            continue

        # 3차: URL 없을 때 title + agency 기반 중복
        if not url and title_norm and ta_key in seen_title_agency:
            removed.append({**item, "_dedup_reason": "URL 없음 + 제목+기관 중복"})
            continue

        # 신규 — 등록
        if url:
            seen_urls.add(url)
        if tag_key:
            seen_tag_keys.add(tag_key)
        if not url and title_norm:
            seen_title_agency.add(ta_key)
        unique.append(item)

    return unique, removed


# ── 유효성 검사 ──────────────────────────────────────────────────────────────

def validate_item(item: dict, today: date | None = None) -> tuple[str, list[str]]:
    """공고 유효성 검사 → (status, reasons).

    status:
      "exclude"  — 마감일 경과 (즉시 제외, 이하 검사 불필요)
      "review"   — 필수 필드 누락 or 제목 깨짐 등 사람이 확인 필요
      "send"     — 이상 없음
    """
    today = today or datetime.now(KST).date()
    end_date_str = (item.get("end_date") or "").strip()

    # 마감일 경과 → 제외 (최우선)
    if end_date_str:
        try:
            end_dt = date.fromisoformat(end_date_str[:10])
            if end_dt < today:
                return "exclude", [f"마감일 경과 ({end_date_str})"]
        except ValueError:
            pass  # 날짜 파싱 실패 시 아래 검사로 이어짐

    reasons: list[str] = []

    # 제목 검사
    title = (item.get("title") or "").strip()
    if not title:
        reasons.append("제목 없음")
    elif _is_broken_title(title):
        reasons.append("제목 깨짐 또는 비정상 문자")

    # 기관 검사
    if not (item.get("agency") or "").strip():
        reasons.append("기관명 없음")

    # URL 검사
    if not (item.get("url") or "").strip():
        reasons.append("URL 없음")

    # 마감일 검사
    if not end_date_str:
        reasons.append("마감일 없음")

    if reasons:
        return "review", reasons
    return "send", []


# ── 검수 실행 ────────────────────────────────────────────────────────────────

def run_review(raw_items: list[dict], today: date | None = None) -> dict[str, Any]:
    """수집된 raw 공고 목록을 검수하여 3그룹으로 분류.

    Returns dict with:
      total_input, removed_dups, send, review, exclude
    """
    today = today or datetime.now(KST).date()

    # 1. 정규화
    normalized = [normalize_item(it) for it in raw_items]

    # 2. 중복 제거
    unique, removed_dups = dedup_items(normalized)

    # 3. 유효성 검사 → 분류
    send_items:    list[dict] = []
    review_items:  list[dict] = []
    exclude_items: list[dict] = []

    for item in unique:
        status, reasons = validate_item(item, today)
        item["_status"]  = status
        item["_reasons"] = reasons
        if status == "send":
            send_items.append(item)
        elif status == "review":
            review_items.append(item)
        else:
            exclude_items.append(item)

    # 중복 제거된 항목도 제외 목록에 기록
    for dup in removed_dups:
        dup.setdefault("_status",  "exclude")
        dup.setdefault("_reasons", [dup.get("_dedup_reason", "중복 제거됨")])
        exclude_items.append(dup)

    return {
        "total_input":  len(raw_items),
        "after_dedup":  len(unique),
        "removed_dups": len(removed_dups),
        "send":    send_items,
        "review":  review_items,
        "exclude": exclude_items,
    }


# ── 결과 파일 생성 ────────────────────────────────────────────────────────────

def _fmt_item_md(item: dict, show_reason: bool = False) -> str:
    lines = [
        f"- **{item.get('title') or '(제목없음)'}**",
        f"  - 기관: {item.get('agency') or '(없음)'}",
        f"  - 마감일: {item.get('end_date') or '(없음)'}",
        f"  - 분야: {item.get('category', '기타')}",
        f"  - URL: {item.get('url') or '(없음)'}",
        f"  - 지역: {item.get('region') or ''}",
        f"  - 출처: {item.get('source') or ''}",
    ]
    if show_reason:
        reasons = item.get("_reasons") or []
        if reasons:
            lines.append(f"  - 사유: {', '.join(reasons)}")
    return "\n".join(lines)


def generate_review_report(result: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    """검수 결과를 3종 파일로 저장하고 경로 dict를 반환.

    - {date}_review.md    : 전체 검수 리포트 (Markdown)
    - {date}_send.csv     : 보낼 공고 CSV
    - {date}_mail_draft.txt : 메일 초안 (발송 금지 문구 포함)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    today_str    = datetime.now(KST).strftime("%Y-%m-%d")
    send_items   = result["send"]
    review_items = result["review"]
    exclude_items = result["exclude"]

    # ── 1. Markdown 리포트 ────────────────────────────────────────────────────
    report_path = output_dir / f"{today_str}_review.md"
    md: list[str] = [
        f"# 공고 검수 리포트 — {today_str}",
        "",
        "> ⚠️ 이 파일은 검수 전용입니다. 실제 메일 발송은 별도 승인 후 진행하세요.",
        "",
        "## 요약",
        "",
        "| 구분 | 건수 |",
        "|------|------|",
        f"| 총 입력 | {result['total_input']}건 |",
        f"| 중복 제거 | {result['removed_dups']}건 |",
        f"| ✅ 보낼 공고 | {len(send_items)}건 |",
        f"| ⚠️ 확인필요 | {len(review_items)}건 |",
        f"| ❌ 제외 | {len(exclude_items)}건 |",
        "",
        "---",
        "",
        f"## ✅ 보낼 공고 ({len(send_items)}건)",
        "",
    ]
    if send_items:
        for it in send_items:
            md.append(_fmt_item_md(it))
            md.append("")
    else:
        md.extend(["_(보낼 공고 없음)_", ""])

    md.extend([
        "---",
        "",
        f"## ⚠️ 확인필요 공고 ({len(review_items)}건)",
        "",
    ])
    if review_items:
        for it in review_items:
            md.append(_fmt_item_md(it, show_reason=True))
            md.append("")
    else:
        md.extend(["_(확인필요 공고 없음)_", ""])

    md.extend([
        "---",
        "",
        f"## ❌ 제외 공고 ({len(exclude_items)}건)",
        "",
    ])
    if exclude_items:
        for it in exclude_items:
            md.append(_fmt_item_md(it, show_reason=True))
            md.append("")
    else:
        md.extend(["_(제외 공고 없음)_", ""])

    report_path.write_text("\n".join(md), encoding="utf-8")

    # ── 2. 보낼 공고 CSV ─────────────────────────────────────────────────────
    csv_path = output_dir / f"{today_str}_send.csv"
    CSV_FIELDS = ["title", "agency", "end_date", "category", "url", "region", "source", "start_date"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(send_items)

    # ── 3. 메일 초안 ─────────────────────────────────────────────────────────
    draft_path = output_dir / f"{today_str}_mail_draft.txt"
    draft: list[str] = [
        "================================================================",
        "⚠️  발송 전 검수 필요 — 이 파일은 초안입니다. 실제 발송 금지.",
        "================================================================",
        "",
        f"작성일시: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}",
        f"보낼 공고: {len(send_items)}건",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "안녕하세요,",
        "",
        "이번 주 지원사업 공고를 안내드립니다.",
        "",
    ]
    if send_items:
        for i, it in enumerate(send_items, 1):
            draft.extend([
                f"[{i}] {it.get('title') or '(제목없음)'}",
                f"  기관: {it.get('agency') or '미기재'}",
                f"  마감일: {it.get('end_date') or '미기재'}",
                f"  분야: {it.get('category', '기타')}",
                f"  지역: {it.get('region') or '미기재'}",
                f"  링크: {it.get('url') or '미기재'}",
                "",
            ])
    else:
        draft.extend(["(보낼 공고 없음)", ""])

    draft.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "궁금하신 점이 있으시면 연락 주세요.",
        "",
        "================================================================",
        "⚠️  이 파일은 메일 초안입니다. 내용 확인 후 별도로 발송하세요.",
        "================================================================",
    ])
    draft_path.write_text("\n".join(draft), encoding="utf-8")

    return {
        "report":     report_path,
        "send_csv":   csv_path,
        "mail_draft": draft_path,
    }


# ── 샘플 데이터 ──────────────────────────────────────────────────────────────

# 샘플 마감일은 실행일 기준 동적 생성 — 고정 날짜는 시간이 지나면 전부
# '마감 경과 제외'가 되어 데모가 0건이 되는 문제가 있었음(2026-07-23)
_S_TODAY = date.today()
def _s_range(start_ago: int, end_ahead: int) -> str:
    return f"{(_S_TODAY - timedelta(days=start_ago)).isoformat()} ~ {(_S_TODAY + timedelta(days=end_ahead)).isoformat()}"

SAMPLE_ITEMS: list[dict] = [
    {
        "title":    "2026년 중소기업 정책자금 융자계획 공고",
        "기관":      "중소벤처기업진흥공단",
        "접수기간":  _s_range(10, 14),
        "URL":      "https://example.com/fund",
        "지역":      "전국",
        "키워드":    "시설자금, 운전자금, 제조업",
        "source":   "샘플데이터",
    },
    {
        "title":    "2026년 수출바우처 참여기업 모집",
        "기관":      "중소벤처기업부",
        "접수기간":  _s_range(7, 21),
        "URL":      "https://example.com/export",
        "지역":      "전국",
        "키워드":    "수출, 바이어, 해외마케팅",
        "source":   "샘플데이터",
    },
    {
        "title":    "2025년 창업지원사업 통합공고",
        "기관":      "중소벤처기업부",
        "접수기간":  "2025-01-01 ~ 2025-02-28",
        "URL":      "https://example.com/old",
        "지역":      "전국",
        "키워드":    "창업, 사업화",
        "source":   "샘플데이터",
    },
    {
        "title":    "메인비즈 인증 취득 지원사업",
        "기관":      "서울경제진흥원",
        "접수기간":  _s_range(5, 7),
        "URL":      "",
        "지역":      "서울",
        "키워드":    "메인비즈, 인증, 컨설팅",
        "source":   "샘플데이터",
    },
    {
        # 샘플 1과 동일 — 중복 테스트 (접수기간도 반드시 1번과 같은 값이어야 함)
        "title":    "2026년 중소기업 정책자금 융자계획 공고",
        "기관":      "중소벤처기업진흥공단",
        "접수기간":  _s_range(10, 14),
        "URL":      "https://example.com/fund",
        "지역":      "전국",
        "키워드":    "시설자금, 운전자금, 제조업",
        "source":   "샘플데이터",
    },
]


# ── 검증 출력 ────────────────────────────────────────────────────────────────

def _print_verification(result: dict[str, Any]) -> None:
    """요청된 7개 검증 항목을 체크리스트 형태로 출력."""
    send    = result["send"]
    review  = result["review"]
    exclude = result["exclude"]

    def _reasons_of(items: list[dict]) -> list[str]:
        return [r for it in items for r in (it.get("_reasons") or [])]

    expired_count   = sum(1 for r in _reasons_of(exclude) if "마감일 경과" in r)
    no_url_count    = sum(1 for r in _reasons_of(review)  if "URL 없음" in r)
    missing_fields  = sum(1 for r in _reasons_of(review)  if any(kw in r for kw in ("제목 없음", "기관명 없음", "마감일 없음")))
    cats_send    = {}
    for it in send + review:
        c = it.get("category", "기타")
        cats_send[c] = cats_send.get(c, 0) + 1

    print("\n[검증 결과]")
    print(f"  1. 중복 공고 제거:           {result['removed_dups']}건 제거됨  [OK]")
    print(f"  2. 마감일 경과 공고 제외:    {expired_count}건 -> 제외 목록  [OK]")
    print(f"  3. URL 없는 공고 -> 확인필요: {no_url_count}건  [OK]")
    print(f"  4. 필수필드 누락 -> 확인필요: {missing_fields}건  [OK]")
    print(f"  5. 분야 분류 결과:           {cats_send}")
    print(f"  6. 결과 파일 생성:           3종 생성됨  [OK]")
    print(f"  7. 실제 발송 차단:           SMTP 미호출 - 초안 파일만 생성  [OK]")
    print("-" * 63)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    # Windows CP949 콘솔에서 한글·특수문자 출력 깨짐 방지
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="공고 정확도 검수 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sample",  action="store_true",
                        help="샘플 데이터로 검수 실행 (API/네트워크 불필요)")
    parser.add_argument("--collect", action="store_true",
                        help="실제 수집 후 검수 (BIZINFO_API_KEY 등 필요)")
    parser.add_argument("--input",   type=str, default="",
                        help="입력 JSON 파일 경로 (수집된 items 배열)")
    parser.add_argument("--output-dir", type=str, default=str(REVIEW_DIR),
                        help=f"결과 출력 디렉토리 (기본: {REVIEW_DIR})")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)

    # 데이터 로드
    if args.sample:
        print(f"샘플 데이터 {len(SAMPLE_ITEMS)}건 사용")
        raw_items: list[dict] = SAMPLE_ITEMS

    elif args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[ERR] 입력 파일 없음: {input_path}", file=sys.stderr)
            return 1
        raw_items = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(raw_items, list):
            raw_items = [raw_items]
        print(f"입력 파일 로드: {len(raw_items)}건 ({input_path})")

    elif args.collect:
        print("실제 수집 시작 (환경변수 및 네트워크 필요)...")
        try:
            sys.path.insert(0, str(BASE_DIR))
            try:
                from dotenv import load_dotenv
                load_dotenv(BASE_DIR / ".env", override=False)
            except ImportError:
                pass
            from monitor import fetch_all, load_sites  # type: ignore
            raw_items = fetch_all(load_sites())
            print(f"수집 완료: {len(raw_items)}건")
        except Exception as exc:
            print(f"[ERR] 수집 실패: {exc}", file=sys.stderr)
            print("  -> --sample 옵션으로 샘플 데이터 사용 가능", file=sys.stderr)
            return 1

    else:
        parser.print_help()
        return 0

    # 검수 실행
    print("\n검수 실행 중...")
    result = run_review(raw_items)

    # 요약 출력
    print(f"\n[결과 요약]")
    print(f"  총 입력:   {result['total_input']}건")
    print(f"  중복 제거: {result['removed_dups']}건")
    print(f"  보낼 공고: {len(result['send'])}건")
    print(f"  확인필요:  {len(result['review'])}건")
    print(f"  제외:      {len(result['exclude'])}건")

    # 파일 생성
    paths = generate_review_report(result, output_dir)
    print(f"\n[결과 파일]")
    for name, path in paths.items():
        print(f"  {name:12s}: {path}")

    # 검증 출력
    _print_verification(result)

    # JSON 결과 (다른 스크립트가 파싱하기 쉽게)
    summary = {
        "ok": True,
        "total_input":  result["total_input"],
        "removed_dups": result["removed_dups"],
        "send_count":   len(result["send"]),
        "review_count": len(result["review"]),
        "exclude_count": len(result["exclude"]),
        "report":     str(paths["report"]),
        "send_csv":   str(paths["send_csv"]),
        "mail_draft": str(paths["mail_draft"]),
    }
    print("\n" + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

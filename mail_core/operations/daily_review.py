"""발송 후 당일 digest/메타 검수 + 누적 컨텍스트 적재.

IMAP/SMTP 없이 이미 남은 산출물(delivery_state·source_coverage·draft/log)만 본다.
실패 시 MDR-xxx 규칙 ID와 이유를 명확히 남긴다(L규칙/lessons-audit 스타일).

실행: python scripts/mail_daily_review.py
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from mail_core.paths import LOGS_DIR, REPO_ROOT, STATE_DIR, VAR_DIR

KST = timezone(timedelta(hours=9))

REVIEWS_DIR = VAR_DIR / "reviews"
DOCS_CONTEXT_DIR = REPO_ROOT / "docs" / "project" / "mail_daily_reviews" / "context"
LEDGER_PATH = DOCS_CONTEXT_DIR / "ledger.jsonl"

# 핵심 소스(기업마당·K-Startup·NIPA). 0건이면 MDR-002 FAIL.
CORE_SITE_IDS = ("bizinfo", "kstartup", "nipa")

# 외부(비-repo) 아침 메일 징후 — git 전수검색 0건이었던 머리글 문구.
EXTERNAL_SEND_FINGERPRINT = "기업마당 API + 마이페어 + K-Startup"
OFFICIAL_DIGEST_MARKERS = ("수집일시:", "재조회범위:")

# 제목 badge 잔재(품질). strip_title_badges 대상과 동일 계열.
TITLE_BADGE_RE = re.compile(
    r"(?:file|new|hot|첨부파일|파일있음|새로운게시글|새글|인기글)\s*$",
    re.IGNORECASE,
)

# 무증상 스킵 징후 문자열(로그/리포트 텍스트).
SILENT_SKIP_MARKERS = (
    "skipped_fetch=true",
    "skipped_fetch\": true",
    "already_delivered",
    "수집·발송 생략",
    "멱등 완료 — 수집·발송 생략",
)

# GHA 정상 수집 run 은 보통 수십 분. 이보다 짧고 coverage 없으면 의심.
SHORT_RUN_SEC = 300  # 5분


@dataclass
class CheckResult:
    id: str
    label: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


@dataclass
class ReviewReport:
    date: str
    slot: str
    cycle_key: str
    generated_at: str
    checks: list[CheckResult] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    overall: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "slot": self.slot,
            "cycle_key": self.cycle_key,
            "generated_at": self.generated_at,
            "overall": self.overall,
            "checks": [asdict(c) for c in self.checks],
            "inputs": self.inputs,
        }


def now_kst(when: datetime | None = None) -> datetime:
    moment = when or datetime.now(KST)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=KST)
    return moment.astimezone(KST)


def resolve_slot(when: datetime | None = None, *, pm_cutoff_hour: int = 14) -> str:
    return "am" if now_kst(when).hour < pm_cutoff_hour else "pm"


def cycle_key(date_s: str, slot: str) -> str:
    return f"{date_s}#{slot}"


def day_dir(date_s: str, *, root: Path | None = None) -> Path:
    return (root or REVIEWS_DIR) / date_s


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_delivery_keys(path: Path | None = None) -> set[str]:
    path = path or (STATE_DIR / "delivery_state.json")
    data = _read_json(path)
    if isinstance(data, dict):
        return {str(k) for k in data}
    if isinstance(data, list):
        return {str(k) for k in data}
    return set()


def keys_for_cycle(keys: Iterable[str], cycle: str) -> list[str]:
    """cycle 예: 2026-07-30#am — prefix 매칭. legacy YYYY-MM-DD| 도 허용."""
    cycle = (cycle or "").strip()
    date_only = cycle.split("#", 1)[0]
    out: list[str] = []
    for k in keys:
        if k.startswith(f"{cycle}|") or k.startswith(f"{date_only}|"):
            # 회차 키가 있으면 회차만, 없으면 날짜 prefix(레거시)도 카운트
            if "#" in cycle:
                if k.startswith(f"{cycle}|") or (
                    k.startswith(f"{date_only}|") and "#" not in k.split("|", 1)[0]
                ):
                    out.append(k)
            else:
                out.append(k)
    # Prefer exact slot matches when present
    exact = [k for k in out if k.startswith(f"{cycle}|")]
    return exact if exact else out


def find_coverage_payload(
    date_s: str,
    *,
    logs_dir: Path | None = None,
) -> tuple[Path | None, dict[str, Any] | None]:
    logs = logs_dir or LOGS_DIR
    compact = date_s.replace("-", "")
    candidates = [
        logs / f"source_coverage_{compact}.json",
        logs / f"source_coverage_{date_s}.json",
    ]
    # 같은 날 여러 회차 파일이 있으면 가장 최근 mtime
    globbed = sorted(logs.glob(f"source_coverage_{compact}*.json"), key=lambda p: p.stat().st_mtime)
    candidates.extend(reversed(globbed))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        data = _read_json(path)
        if isinstance(data, dict):
            return path, data
    return None, None


def core_source_zeros(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    zeros: list[dict[str, Any]] = []
    for src in payload.get("sources") or []:
        if not isinstance(src, dict):
            continue
        sid = str(src.get("site_id") or "")
        if sid not in CORE_SITE_IDS:
            continue
        count = int(src.get("item_count", 0) or 0)
        if count <= 0:
            zeros.append(
                {
                    "site_id": sid,
                    "item_count": count,
                    "status": src.get("status"),
                    "risk_level": src.get("risk_level"),
                    "reason_codes": list(src.get("reason_codes") or []),
                }
            )
    return zeros


def scan_text_blobs(paths: Iterable[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.is_file():
            chunks.append(_read_text(path))
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in {".md", ".txt", ".json", ".log", ".html"}:
                    chunks.append(_read_text(child))
    return "\n".join(chunks)


def detect_external_send(text: str) -> bool:
    if EXTERNAL_SEND_FINGERPRINT not in text:
        return False
    # 공식 digest 마커가 같이 있으면 repo 파이프라인으로 본다
    if any(m in text for m in OFFICIAL_DIGEST_MARKERS):
        return False
    return True


def find_title_badges(text: str) -> list[str]:
    hits: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 240:
            continue
        if TITLE_BADGE_RE.search(line):
            hits.append(line[:160])
            if len(hits) >= 8:
                break
    return hits


def detect_silent_skip_markers(text: str) -> list[str]:
    found = [m for m in SILENT_SKIP_MARKERS if m in text]
    # 중복 의미 축약
    uniq: list[str] = []
    for m in found:
        if m not in uniq:
            uniq.append(m)
    return uniq


def run_checks(
    *,
    date_s: str,
    slot: str,
    delivery_keys: set[str],
    coverage_path: Path | None,
    coverage: dict[str, Any] | None,
    scan_text: str,
    run_duration_sec: float | None = None,
    require_coverage: bool = True,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    cycle = cycle_key(date_s, slot)
    today_keys = keys_for_cycle(delivery_keys, cycle)

    # MDR-001: 무증상 스킵
    skip_markers = detect_silent_skip_markers(scan_text)
    short = run_duration_sec is not None and run_duration_sec < SHORT_RUN_SEC
    missing_cov = coverage is None
    if require_coverage and missing_cov and (skip_markers or short or not today_keys):
        why = []
        if missing_cov:
            why.append("source_coverage 없음")
        if skip_markers:
            why.append("skip 마커=" + ",".join(skip_markers[:3]))
        if short:
            why.append(f"실행 {run_duration_sec:.0f}s < {SHORT_RUN_SEC}s")
        if not today_keys:
            why.append("당일 delivery_state 키 없음")
        checks.append(
            CheckResult(
                "MDR-001",
                "무증상 스킵(skip/coverage)",
                "FAIL",
                "; ".join(why),
            )
        )
    elif require_coverage and missing_cov:
        checks.append(
            CheckResult(
                "MDR-001",
                "무증상 스킵(skip/coverage)",
                "FAIL",
                "source_coverage_YYYYMMDD.json 없음 - 수집·커버리지가 통째 생략됐을 수 있음",
            )
        )
    elif skip_markers and missing_cov:
        checks.append(
            CheckResult(
                "MDR-001",
                "무증상 스킵(skip/coverage)",
                "FAIL",
                "skip 마커 + coverage 없음: " + ",".join(skip_markers[:3]),
            )
        )
    else:
        if missing_cov:
            detail = "coverage 없음(require_coverage=off)"
        else:
            detail = "coverage OK"
            if coverage_path:
                detail += f" ({coverage_path.name})"
        if skip_markers and coverage is not None:
            detail += f"; skip 마커 있으나 coverage 존재(스킵+경보 경로일 수 있음): {','.join(skip_markers[:2])}"
        checks.append(CheckResult("MDR-001", "무증상 스킵(skip/coverage)", "PASS", detail))

    # MDR-002: 핵심소스 0건
    zeros = core_source_zeros(coverage)
    if coverage is None:
        checks.append(
            CheckResult(
                "MDR-002",
                "핵심소스 0건",
                "SKIP",
                "coverage 없음 - MDR-001에서 처리",
            )
        )
    elif zeros:
        parts = [f"{z['site_id']}={z['item_count']}" for z in zeros]
        checks.append(
            CheckResult(
                "MDR-002",
                "핵심소스 0건",
                "FAIL",
                "핵심소스 0건: " + ", ".join(parts),
            )
        )
    else:
        checks.append(
            CheckResult(
                "MDR-002",
                "핵심소스 0건",
                "PASS",
                "bizinfo/kstartup/nipa item_count > 0 또는 해당 소스 미포함(수집 성공)",
            )
        )

    # MDR-003: 08:54 외부발송 징후
    if detect_external_send(scan_text):
        checks.append(
            CheckResult(
                "MDR-003",
                "08:54 외부발송 징후",
                "FAIL",
                f"외부 머리글 감지: '{EXTERNAL_SEND_FINGERPRINT}' (공식 수집일시/재조회범위 없음)",
            )
        )
    elif EXTERNAL_SEND_FINGERPRINT in scan_text:
        checks.append(
            CheckResult(
                "MDR-003",
                "08:54 외부발송 징후",
                "PASS",
                "유사 문구 있으나 공식 digest 마커 동반 -> repo 파이프라인으로 판정",
            )
        )
    else:
        checks.append(
            CheckResult(
                "MDR-003",
                "08:54 외부발송 징후",
                "PASS",
                "외부 머리글 미검출(로그/draft 기준; IMAP 본문 미검수)",
            )
        )

    # MDR-004: delivery_state 당일(회차) 키
    if today_keys:
        checks.append(
            CheckResult(
                "MDR-004",
                "delivery_state 당일키",
                "PASS",
                f"{cycle} 키 {len(today_keys)}개",
            )
        )
    else:
        checks.append(
            CheckResult(
                "MDR-004",
                "delivery_state 당일키",
                "FAIL",
                f"{cycle} (또는 legacy {date_s}) 키 0개 - 발송 미기록/무증상 스킵 의심",
            )
        )

    # MDR-005: 제목 badge 품질
    badges = find_title_badges(scan_text)
    if badges:
        checks.append(
            CheckResult(
                "MDR-005",
                "제목 badge 품질",
                "FAIL",
                "badge 잔재 예: " + " | ".join(badges[:3]),
            )
        )
    else:
        checks.append(
            CheckResult(
                "MDR-005",
                "제목 badge 품질",
                "PASS",
                "스캔 텍스트에 제목 badge 잔재 없음",
            )
        )

    return checks


def render_markdown(report: ReviewReport) -> str:
    lines = [
        f"# Mail Daily Review — {report.date} ({report.slot})",
        "",
        f"- generated_at: {report.generated_at}",
        f"- cycle_key: `{report.cycle_key}`",
        f"- overall: **{report.overall}**",
        "",
        "## Checks (MDR = L규칙 스타일 일일 가드레일)",
        "",
    ]
    for c in report.checks:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}.get(c.status, "?")
        lines.append(f"- [{mark}] `{c.id}` {c.label}: {c.status} - {c.detail}")
    lines.extend(["", "## Inputs", ""])
    for k, v in report.inputs.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    return "\n".join(lines)


def append_ledger(report: ReviewReport, path: Path | None = None) -> Path:
    target = path or LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": report.generated_at,
        "date": report.date,
        "slot": report.slot,
        "cycle_key": report.cycle_key,
        "overall": report.overall,
        "fails": [
            {"id": c.id, "detail": c.detail}
            for c in report.checks
            if c.status == "FAIL"
        ],
        "pass_ids": [c.id for c in report.checks if c.status == "PASS"],
        "skip_ids": [c.id for c in report.checks if c.status == "SKIP"],
    }
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return target


def write_day_artifacts(report: ReviewReport, *, root: Path | None = None) -> dict[str, Path]:
    out_dir = day_dir(report.date, root=root)
    out_dir.mkdir(parents=True, exist_ok=True)
    # slot별 파일 — 하루 2회 발송 대비
    stem = f"review_{report.slot}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    # 최신 포인터(슬롯 무관 조회용)
    (out_dir / "review.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "review.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"dir": out_dir, "json": json_path, "md": md_path}


def collect_scan_paths(
    date_s: str,
    *,
    logs_dir: Path | None = None,
    reports_dir: Path | None = None,
    extra: Iterable[Path] | None = None,
) -> list[Path]:
    logs = logs_dir or LOGS_DIR
    reports = reports_dir or (VAR_DIR / "reports")
    compact = date_s.replace("-", "")
    paths: list[Path] = [
        logs / f"source_coverage_{compact}.md",
        logs / f"source_coverage_{compact}.json",
        logs / f"p0_collection_alert_{compact}.md",
        logs / "site_collection_coverage_report.md",
        reports / "review" / f"{date_s}_mail_draft.txt",
        reports / "review" / f"{date_s}_review.md",
        REVIEWS_DIR / date_s / "inbox_sample.txt",
        REVIEWS_DIR / "inbox_sample.txt",
    ]
    if extra:
        paths.extend(extra)
    return paths


def build_review(
    *,
    date_s: str | None = None,
    slot: str | None = None,
    when: datetime | None = None,
    delivery_state_path: Path | None = None,
    logs_dir: Path | None = None,
    run_duration_sec: float | None = None,
    require_coverage: bool = True,
    extra_scan: Iterable[Path] | None = None,
) -> ReviewReport:
    moment = now_kst(when)
    date_s = date_s or moment.date().isoformat()
    slot = slot or resolve_slot(moment)
    cycle = cycle_key(date_s, slot)

    delivery_path = delivery_state_path or (STATE_DIR / "delivery_state.json")
    keys = load_delivery_keys(delivery_path)
    cov_path, cov = find_coverage_payload(date_s, logs_dir=logs_dir)
    scan_paths = collect_scan_paths(date_s, logs_dir=logs_dir, extra=extra_scan)
    text = scan_text_blobs(scan_paths)

    checks = run_checks(
        date_s=date_s,
        slot=slot,
        delivery_keys=keys,
        coverage_path=cov_path,
        coverage=cov,
        scan_text=text,
        run_duration_sec=run_duration_sec,
        require_coverage=require_coverage,
    )
    overall = "FAIL" if any(c.status == "FAIL" for c in checks) else "PASS"
    return ReviewReport(
        date=date_s,
        slot=slot,
        cycle_key=cycle,
        generated_at=moment.strftime("%Y-%m-%dT%H:%M:%S%z"),
        checks=checks,
        overall=overall,
        inputs={
            "delivery_state": str(delivery_path),
            "delivery_keys_total": len(keys),
            "coverage": str(cov_path) if cov_path else None,
            "run_duration_sec": run_duration_sec,
            "scan_files": [str(p) for p in scan_paths if p.exists()],
        },
    )


def run_daily_review(
    *,
    date_s: str | None = None,
    slot: str | None = None,
    append_context: bool = True,
    reviews_root: Path | None = None,
    ledger_path: Path | None = None,
    **kwargs: Any,
) -> tuple[ReviewReport, dict[str, Path]]:
    report = build_review(date_s=date_s, slot=slot, **kwargs)
    paths = write_day_artifacts(report, root=reviews_root)
    if append_context:
        paths["ledger"] = append_ledger(report, path=ledger_path)
    return report, paths

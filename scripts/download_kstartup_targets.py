"""K-Startup target notice attachment downloader.

Usage:
    python scripts/download_kstartup_targets.py --dry-run
    python scripts/download_kstartup_targets.py
    python scripts/download_kstartup_targets.py --target-file targets/kstartup_20260623.txt --out-dir downloads/kstartup/20260623

This script is intentionally separated from monitor.py send mode. It reuses the
existing K-Startup collector, matches only the target titles listed in the target
file, opens each detail page, extracts likely attachment/download links, and
stores files by notice title.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from email.message import Message
from pathlib import Path
from difflib import SequenceMatcher
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse

# monitor.py requires these env vars at import time although K-Startup collection
# does not need the real values. Keep local downloader runnable without sending mail.
os.environ.setdefault("BIZINFO_API_KEY", "dummy")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
os.environ.setdefault("GMAIL_ADDRESS", "dummy@example.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

import monitor  # noqa: E402

KSTARTUP_SITE = {
    "id": "kstartup",
    "name": "K-Startup",
    "type": "kstartup_html",
    "url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do",
    "enabled": True,
    "is_aggregator": False,
}

ATTACHMENT_TEXT_RE = re.compile(
    r"첨부|붙임|파일|다운로드|download|공고문|신청서|사업계획서|양식|서식|안내문|모집공고|운영지침|zip|hwp|hwpx|pdf|docx?|xlsx?",
    re.IGNORECASE,
)
ATTACHMENT_URL_RE = re.compile(
    r"download|file|attach|atch|cmm/fms|FileDown|fileDown|\.hwp|\.hwpx|\.pdf|\.docx?|\.xlsx?|\.zip",
    re.IGNORECASE,
)
EXT_RE = re.compile(r"\.(hwp|hwpx|pdf|doc|docx|xls|xlsx|ppt|pptx|zip|7z|rar)(?:$|[?#])", re.IGNORECASE)
WINDOWS_BAD_CHARS = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


@dataclass
class AttachmentCandidate:
    url: str
    label: str
    source: str


@dataclass
class DownloadResult:
    target_title: str
    matched_title: str
    match_score: float
    detail_url: str
    status: str
    file_name: str = ""
    save_path: str = ""
    file_url: str = ""
    error: str = ""


def norm_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("새로운게시글", "")
    value = re.sub(r"\s+", "", value.lower())
    value = re.sub(r"[\[\]【】()（）『』「」<>〈〉·ㆍ,._~\-–—:;/'\"!@#$%^&*+=?]", "", value)
    return value


def safe_filename(value: str, max_len: int = 140) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = WINDOWS_BAD_CHARS.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    return (value[:max_len].strip(" ._") or "untitled")


def load_targets(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")]


def collect_kstartup_items() -> list[dict]:
    # Existing collector fetches public(PBC010) and private(PBC020) with viewCount=100 each.
    return monitor.fetch_kstartup(KSTARTUP_SITE)


def match_notice(target: str, items: Iterable[dict], min_score: float = 0.72) -> tuple[dict | None, float]:
    nt = norm_text(target)
    best: tuple[dict | None, float] = (None, 0.0)
    for item in items:
        title = str(item.get("title", ""))
        ni = norm_text(title)
        if not nt or not ni:
            continue
        if nt == ni:
            return item, 1.0
        if nt in ni or ni in nt:
            score = min(len(nt), len(ni)) / max(len(nt), len(ni))
            score = max(score, 0.92)
        else:
            score = SequenceMatcher(None, nt, ni).ratio()
        if score > best[1]:
            best = (item, score)
    if best[1] >= min_score:
        return best
    return None, best[1]


def extract_quoted_strings(value: str) -> list[str]:
    if not value:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", value)


def candidate_from_url(raw_url: str, label: str, base_url: str, source: str) -> AttachmentCandidate | None:
    raw_url = (raw_url or "").strip()
    if not raw_url or raw_url == "#":
        return None
    if raw_url.lower().startswith(("javascript:void", "mailto:", "tel:")):
        return None
    if raw_url.lower().startswith("javascript:"):
        return None
    abs_url = urljoin(base_url, raw_url)
    haystack = f"{label} {raw_url}"
    if not (ATTACHMENT_URL_RE.search(haystack) or ATTACHMENT_TEXT_RE.search(haystack)):
        return None
    return AttachmentCandidate(url=abs_url, label=label.strip(), source=source)


def extract_attachment_candidates(html: str, detail_url: str) -> list[AttachmentCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[AttachmentCandidate] = []

    def add(c: AttachmentCandidate | None) -> None:
        if not c:
            return
        key = c.url
        if key in seen:
            return
        seen.add(key)
        out.append(c)

    # 1) Direct anchors/buttons with href/data-url/action-like attrs.
    for el in soup.select("a, button"):
        label = " ".join(el.get_text(" ", strip=True).split())
        raw = " ".join([label, str(el.get("href", "")), str(el.get("onclick", "")), str(el.attrs)])
        if not (ATTACHMENT_TEXT_RE.search(raw) or ATTACHMENT_URL_RE.search(raw)):
            continue
        for attr in ("href", "data-url", "data-href", "data-download-url", "formaction"):
            add(candidate_from_url(str(el.get(attr, "")), label, detail_url, attr))
        onclick = str(el.get("onclick", ""))
        for q in extract_quoted_strings(onclick):
            add(candidate_from_url(q, label, detail_url, "onclick"))

    # 2) Any quoted URL in scripts or inline HTML.
    for q in extract_quoted_strings(html):
        if ATTACHMENT_URL_RE.search(q):
            add(candidate_from_url(q, "첨부파일", detail_url, "html-quoted"))

    return out


def content_disposition_filename(value: str) -> str:
    if not value:
        return ""
    msg = Message()
    msg["content-disposition"] = value
    filename = msg.get_filename()
    if filename:
        return unquote(filename)
    # Common non-RFC fallback: filename=...
    m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", value, re.IGNORECASE)
    return unquote(m.group(1).strip()) if m else ""


def guess_filename(candidate: AttachmentCandidate, response: httpx.Response | None = None, idx: int = 1) -> str:
    if response is not None:
        cd = response.headers.get("content-disposition", "")
        from_cd = content_disposition_filename(cd)
        if from_cd:
            return safe_filename(from_cd, 180)
    parsed = urlparse(candidate.url)
    base = safe_filename(unquote(Path(parsed.path).name), 180)
    if base and "." in base:
        return base
    label = safe_filename(candidate.label or f"attachment_{idx}", 120)
    ext = ""
    if response is not None:
        ext = mimetypes.guess_extension(response.headers.get("content-type", "").split(";")[0].strip()) or ""
    if not ext:
        m = EXT_RE.search(candidate.url)
        ext = f".{m.group(1).lower()}" if m else ".bin"
    return f"{label}{ext}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot create unique path for {path}")


def get_with_ssl_fallback(url: str, headers: dict, timeout: int) -> httpx.Response:
    last_err: Exception | None = None
    for stage in ("strict", "no_verify", "legacy"):
        verify = (
            True if stage == "strict"
            else False if stage == "no_verify"
            else monitor._legacy_ssl_ctx()
        )
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers, verify=verify) as client:
                r = client.get(url)
                r.raise_for_status()
                return r
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    raise RuntimeError(f"Failed to fetch {url}")


def fetch_detail_html(url: str) -> str:
    headers = {**monitor.HTTP_HEADERS, "Referer": KSTARTUP_SITE["url"]}
    return get_with_ssl_fallback(url, headers, timeout=60).text


def download_candidate(candidate: AttachmentCandidate, detail_url: str, notice_dir: Path, idx: int) -> tuple[str, Path]:
    headers = {**monitor.HTTP_HEADERS, "Referer": detail_url}
    r = get_with_ssl_fallback(candidate.url, headers, timeout=120)
    file_name = guess_filename(candidate, r, idx)
    save_path = unique_path(notice_dir / file_name)
    save_path.write_bytes(r.content)
    return file_name, save_path


def run(target_file: Path, out_dir: Path, dry_run: bool, min_score: float) -> dict:
    targets = load_targets(target_file)
    items = collect_kstartup_items()
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadResult] = []

    for target in targets:
        item, score = match_notice(target, items, min_score)
        if not item or score < min_score:
            results.append(DownloadResult(
                target_title=target,
                matched_title=str(item.get("title", "")) if item else "",
                match_score=round(score, 4),
                detail_url=str(item.get("link", "")) if item else "",
                status="NOT_FOUND",
            ))
            continue

        matched_title = str(item.get("title", ""))
        detail_url = str(item.get("link", ""))
        notice_dir = out_dir / safe_filename(matched_title, 120)

        try:
            html = fetch_detail_html(detail_url)
            candidates = extract_attachment_candidates(html, detail_url)
        except Exception as exc:
            results.append(DownloadResult(target, matched_title, round(score, 4), detail_url, "DETAIL_FETCH_FAILED", error=str(exc)))
            continue

        if not candidates:
            results.append(DownloadResult(target, matched_title, round(score, 4), detail_url, "NO_ATTACHMENTS"))
            continue

        notice_dir.mkdir(parents=True, exist_ok=True)
        for idx, cand in enumerate(candidates, start=1):
            if dry_run:
                predicted = notice_dir / guess_filename(cand, None, idx)
                results.append(DownloadResult(
                    target_title=target,
                    matched_title=matched_title,
                    match_score=round(score, 4),
                    detail_url=detail_url,
                    status="DRY_RUN",
                    file_name=predicted.name,
                    save_path=str(predicted),
                    file_url=cand.url,
                ))
                continue
            try:
                file_name, save_path = download_candidate(cand, detail_url, notice_dir, idx)
                results.append(DownloadResult(
                    target_title=target,
                    matched_title=matched_title,
                    match_score=round(score, 4),
                    detail_url=detail_url,
                    status="DOWNLOADED",
                    file_name=file_name,
                    save_path=str(save_path),
                    file_url=cand.url,
                ))
            except Exception as exc:
                results.append(DownloadResult(
                    target_title=target,
                    matched_title=matched_title,
                    match_score=round(score, 4),
                    detail_url=detail_url,
                    status="DOWNLOAD_FAILED",
                    file_url=cand.url,
                    error=str(exc),
                ))

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_file": str(target_file),
        "out_dir": str(out_dir),
        "dry_run": dry_run,
        "total_targets": len(targets),
        "total_rows": len(results),
        "status_counts": {},
        "results": [asdict(r) for r in results],
    }
    for r in results:
        summary["status_counts"][r.status] = summary["status_counts"].get(r.status, 0) + 1

    manifest = out_dir / ("download_manifest_dry_run.json" if dry_run else "download_manifest.json")
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Download attachments for selected K-Startup notices.")
    parser.add_argument("--target-file", default="targets/kstartup_20260623.txt")
    parser.add_argument("--out-dir", default="downloads/kstartup/20260623")
    parser.add_argument("--dry-run", action="store_true", help="Do not write attachment files; write planned manifest only.")
    parser.add_argument("--min-score", type=float, default=0.72)
    args = parser.parse_args()

    summary = run(
        target_file=(ROOT / args.target_file).resolve() if not Path(args.target_file).is_absolute() else Path(args.target_file),
        out_dir=(ROOT / args.out_dir).resolve() if not Path(args.out_dir).is_absolute() else Path(args.out_dir),
        dry_run=args.dry_run,
        min_score=args.min_score,
    )
    print(json.dumps({
        "dry_run": summary["dry_run"],
        "total_targets": summary["total_targets"],
        "total_rows": summary["total_rows"],
        "status_counts": summary["status_counts"],
        "manifest": str(Path(summary["out_dir"]) / ("download_manifest_dry_run.json" if summary["dry_run"] else "download_manifest.json")),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

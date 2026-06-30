"""공고 상세 페이지 링크 → 그 게시물의 첨부파일 전부 다운로드.

사용 예:
    python scripts/fetch_notice_attachments.py "<공고 URL>" --out-dir "<저장 폴더>"
    python scripts/fetch_notice_attachments.py "<URL1>" "<URL2>" --out-dir "<폴더>"
    python scripts/fetch_notice_attachments.py --url-file links.txt --out-dir "<폴더>"
    python scripts/fetch_notice_attachments.py --dry-run "<URL>"        # 받지 않고 미리보기

동작:
    1) 공고 상세 페이지를 가져와 공고 '제목'을 추출하고,
    2) 저장 폴더 안에 "NN_공고제목" 하위 폴더를 만든 뒤,
    3) 그 게시물의 첨부파일을 모두 내려받는다.

K-Startup(k-startup.go.kr)·기업마당(bizinfo.go.kr) 및 일반 정부포털의
직접 다운로드 링크를 지원한다. monitor.py 의 수집기/추출기를 재사용하되
파일명 인코딩(CP949/EUC-KR)·차단 HTML 거부를 자체적으로 보강한다.
이 스크립트는 메일을 전혀 보내지 않으며 monitor.py 를 수정하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# monitor.py 는 import 시점에 아래 env 를 요구한다(실제 값은 불필요 — 메일 안 보냄).
os.environ.setdefault("BIZINFO_API_KEY", "dummy")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
os.environ.setdefault("GMAIL_ADDRESS", "dummy@example.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "dummy")

import httpx  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

import monitor  # noqa: E402
from scripts.download_kstartup_targets import (  # noqa: E402
    AttachmentCandidate,
    EXT_RE,
    extract_attachment_candidates,
    extract_outbound_urls,
    safe_filename,
    unique_path,
)

log = logging.getLogger(__name__)

# 제목으로 부적합한 노이즈(로그인/공통 UI 텍스트)
TITLE_NOISE = {
    "모집중", "마감", "공고", "공지", "알림", "상세화면", "상세", "notice",
    "중소벤처24 통합로그인 사이트", "통합로그인", "로그인", "k-startup 창업지원포털",
}
TITLE_TAIL_RE = re.compile(r"\s*[>《<]\s*상세화면\s*$")
HTML_HEAD_RE = re.compile(rb"^\s*<(?:!doctype|html|head|body|center|br|table)\b", re.IGNORECASE)
DOC_EXT_RE = re.compile(r"\.(hwp|hwpx|pdf|docx?|xlsx?|pptx?|zip|7z|rar|txt|jpe?g|png|gif)$", re.IGNORECASE)


@dataclass
class FileResult:
    notice_title: str
    detail_url: str
    status: str
    file_name: str = ""
    save_path: str = ""
    file_url: str = ""
    error: str = ""


def decode_cd_filename(cd: str) -> str:
    """content-disposition 헤더에서 올바른(한글 복원) 파일명을 뽑는다.

    httpx 는 헤더 바이트를 latin-1 로 디코드해 노출하므로, 한국 정부사이트가
    CP949/EUC-KR 로 보낸 한글 파일명은 깨져 보인다. latin-1 로 되돌린 뒤
    적절한 인코딩으로 재디코딩한다. RFC 5987(filename*) 도 우선 처리한다.
    """
    if not cd:
        return ""
    # 1) RFC 5987: filename*=charset'lang'<percent-encoded>
    m = re.search(r"filename\*\s*=\s*([\w.\-]+)?'[^']*'([^;]+)", cd, re.IGNORECASE)
    if m:
        charset = (m.group(1) or "utf-8").strip()
        value = m.group(2).strip().strip('"')
        try:
            return unquote(value, encoding=charset, errors="strict")
        except Exception:
            try:
                return unquote(value)
            except Exception:
                pass
    # 2) filename="..." 또는 filename=...
    m = re.search(r'filename\s*=\s*"([^"]*)"', cd, re.IGNORECASE)
    if not m:
        m = re.search(r"filename\s*=\s*([^;]+)", cd, re.IGNORECASE)
    if not m:
        return ""
    name = m.group(1).strip().strip('"').strip()
    # 퍼센트 인코딩이면 먼저 푼다
    if "%" in name:
        try:
            decoded = unquote(name)
            if decoded:
                name = decoded
        except Exception:
            pass
    # latin-1 로 노출된 CP949/EUC-KR/UTF-8 한글 복원
    if any(ord(ch) > 0x7F for ch in name):
        try:
            raw = name.encode("latin-1")
        except Exception:
            raw = b""
        for enc in ("cp949", "euc-kr", "utf-8"):
            try:
                dec = raw.decode(enc)
            except Exception:
                continue
            if "�" in dec:
                continue
            # 한글이 하나라도 복원되면 채택(영문/숫자만이면 원본 유지가 안전)
            if re.search(r"[가-힣]", dec):
                return dec.strip()
    return name.strip()


def _good_title(text: str) -> str | None:
    text = " ".join((text or "").split())
    text = TITLE_TAIL_RE.sub("", text).strip()
    if not text or len(text) < 4:
        return None
    if text.lower() in TITLE_NOISE:
        return None
    return text


def extract_notice_title(html: str, url: str) -> str:
    """공고 상세 페이지에서 폴더명으로 쓸 제목을 추출한다."""
    soup = BeautifulSoup(html, "html.parser")

    og = soup.select_one('meta[property="og:title"]')
    if og:
        good = _good_title(og.get("content", ""))
        if good:
            return good

    for sel in (".title", "h3.tit", ".view_title", ".board_view .tit",
                ".tbl_view .tit", ".bbsV_tit", "h3", "h2.tit", ".pbanc_tit"):
        el = soup.select_one(sel)
        if el:
            good = _good_title(el.get_text(" ", strip=True))
            if good:
                return good

    if soup.title and soup.title.string:
        good = _good_title(soup.title.string)
        if good:
            return good

    # 최후: URL 식별자 기반 이름
    parsed = urlparse(url)
    ident = ""
    for key in ("pbancSn", "pblancId", "atchFileId", "seq", "idx", "no"):
        m = re.search(rf"{key}=([\w\-]+)", parsed.query, re.IGNORECASE)
        if m:
            ident = m.group(1)
            break
    return f"공고_{ident or parsed.netloc}"


def fetch_html(url: str) -> str:
    """공고 상세 페이지 HTML 을 가져온다(요청 사이트 origin 을 Referer 로)."""
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme else ""
    headers = {**monitor.HTTP_HEADERS}
    if referer:
        headers["Referer"] = referer
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers, verify=False) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def _looks_like_html_body(content: bytes) -> bool:
    head = content[:512].lstrip()
    return bool(HTML_HEAD_RE.match(head))


def download_attachment(cand: AttachmentCandidate, detail_url: str, notice_dir: Path, idx: int) -> tuple[str, Path]:
    """첨부 후보 하나를 내려받아 저장한다(파일명 인코딩 복원·차단 HTML 거부)."""
    headers = {**monitor.HTTP_HEADERS, "Referer": detail_url}
    with httpx.Client(timeout=180, follow_redirects=True, headers=headers, verify=False) as client:
        r = client.get(cand.url)
        r.raise_for_status()

        ctype = r.headers.get("content-type", "").lower()
        cd = r.headers.get("content-disposition", "")
        name_from_cd = decode_cd_filename(cd)

        cd_has_doc_ext = bool(name_from_cd and DOC_EXT_RE.search(name_from_cd))
        url_has_doc_ext = bool(EXT_RE.search(cand.url))

        # 차단/오류 HTML 을 첨부로 저장하지 않는다.
        # (정상 첨부는 content-disposition 에 문서 확장자가 있거나 octet-stream 이다)
        if not cd_has_doc_ext and not url_has_doc_ext:
            if "text/html" in ctype or _looks_like_html_body(r.content):
                raise RuntimeError(f"첨부가 아닌 HTML 응답(차단/오류 페이지 가능): {cand.url}")

        file_name = name_from_cd or _filename_from_url_or_label(cand, r, idx)
        file_name = safe_filename(file_name, 180)
        if not DOC_EXT_RE.search(file_name):
            ext = _guess_ext(ctype, cand.url)
            if ext and not file_name.lower().endswith(ext):
                file_name = f"{file_name}{ext}"

        save_path = unique_path(notice_dir / file_name)
        save_path.write_bytes(r.content)
        return file_name, save_path


def _guess_ext(ctype: str, url: str) -> str:
    m = EXT_RE.search(url)
    if m:
        return f".{m.group(1).lower()}"
    mt = (ctype or "").split(";")[0].strip()
    return mimetypes.guess_extension(mt) or ""


def _filename_from_url_or_label(cand: AttachmentCandidate, response: httpx.Response, idx: int) -> str:
    parsed = urlparse(cand.url)
    base = unquote(Path(parsed.path).name)
    if base and "." in base:
        return base
    label = (cand.label or f"attachment_{idx}").strip()
    return f"{idx:02d}_{label}"


def resolve_notice_dir(out_dir: Path, title: str, number: bool) -> Path:
    """저장 폴더 안의 공고별 하위 폴더 경로를 결정한다.

    같은 제목(번호 prefix 무시) 폴더가 이미 있으면 재사용하고,
    없으면 number=True 일 때 기존 최대 번호+1 을 prefix 로 붙인다.
    """
    safe = safe_filename(title, 110)
    existing_dirs = [d for d in out_dir.iterdir() if d.is_dir()] if out_dir.exists() else []

    for d in existing_dirs:
        stripped = re.sub(r"^\d+[_.\-]\s*", "", d.name)
        if stripped == safe or d.name == safe:
            return d

    if number:
        nums = []
        for d in existing_dirs:
            m = re.match(r"^(\d+)[_.\-]", d.name)
            if m:
                nums.append(int(m.group(1)))
        nxt = (max(nums) + 1) if nums else 1
        return out_dir / f"{nxt:02d}_{safe}"
    return out_dir / safe


def _dedup_key(file_name: str, size: int) -> tuple[str, int]:
    """파일명(공백·구두점 무시)+크기로 같은 첨부의 중복을 식별한다."""
    norm = re.sub(r"[\s+_.\-]", "", file_name).lower()
    return (norm, size)


def gather_candidates(url: str, html: str) -> list[AttachmentCandidate]:
    """상세 페이지에서 첨부 후보를 모은다.

    상세 페이지에 직접 첨부가 있으면 그것만 쓴다(K-Startup 원본사이트 중복 방지).
    상세에 첨부가 없을 때만 K-Startup '원본/사업안내' 외부 페이지를 추가로 본다.
    """
    candidates = extract_attachment_candidates(html, url)
    if not candidates and "k-startup.go.kr" in url.lower():
        for outbound in extract_outbound_urls(html, url)[:5]:
            try:
                candidates.extend(extract_attachment_candidates(fetch_html(outbound), outbound))
            except Exception as exc:
                log.warning("외부 페이지 확인 실패(%s): %s", outbound, exc)
    return candidates


def process_url(url: str, out_dir: Path, dry_run: bool) -> list[FileResult]:
    url = url.strip()
    results: list[FileResult] = []
    try:
        html = fetch_html(url)
    except Exception as exc:
        return [FileResult("", url, "PAGE_FETCH_FAILED", error=str(exc))]

    title = extract_notice_title(html, url)

    try:
        candidates = gather_candidates(url, html)
    except Exception as exc:
        return [FileResult(title, url, "EXTRACT_FAILED", error=str(exc))]

    # 중복 URL 제거(순서 유지)
    seen_urls: set[str] = set()
    candidates = [c for c in candidates if not (c.url in seen_urls or seen_urls.add(c.url))]

    if not candidates:
        return [FileResult(title, url, "NO_ATTACHMENTS")]

    notice_dir = resolve_notice_dir(out_dir, title, number=True)
    if not dry_run:
        notice_dir.mkdir(parents=True, exist_ok=True)

    seen_files: set[tuple[str, int]] = set()
    for idx, cand in enumerate(candidates, start=1):
        if dry_run:
            results.append(FileResult(
                notice_title=title, detail_url=url, status="DRY_RUN",
                file_name=f"(예정) {cand.label[:40]}", file_url=cand.url,
                save_path=str(notice_dir),
            ))
            continue
        try:
            file_name, save_path = download_attachment(cand, url, notice_dir, idx)
        except httpx.HTTPStatusError as exc:
            # 4xx 는 '진짜 첨부가 아닌 후보'(미리보기/깨진 링크) — 조용히 제외
            code = exc.response.status_code
            status = "NOT_A_FILE" if 400 <= code < 500 else "DOWNLOAD_FAILED"
            results.append(FileResult(title, url, status, file_url=cand.url, error=f"HTTP {code}"))
            continue
        except RuntimeError as exc:
            # HTML 차단/오류 페이지 — 첨부 아님으로 조용히 제외
            results.append(FileResult(title, url, "NOT_A_FILE", file_url=cand.url, error=str(exc)))
            continue
        except Exception as exc:
            results.append(FileResult(title, url, "DOWNLOAD_FAILED", file_url=cand.url, error=str(exc)))
            continue

        key = _dedup_key(file_name, save_path.stat().st_size)
        if key in seen_files:
            try:
                save_path.unlink()
            except Exception:
                pass
            results.append(FileResult(title, url, "DUPLICATE", file_name=file_name, file_url=cand.url))
            continue
        seen_files.add(key)
        results.append(FileResult(
            notice_title=title, detail_url=url, status="DOWNLOADED",
            file_name=file_name, save_path=str(save_path), file_url=cand.url,
        ))
    return results


def load_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []
    for raw in args.urls or []:
        # 한 칸/줄에 여러 링크가 붙어 들어와도 분리
        urls.extend(re.findall(r"https?://[^\s'\"]+", raw))
        if not re.search(r"https?://", raw) and raw.strip():
            urls.append(raw.strip())
    if args.url_file:
        text = Path(args.url_file).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    # 중복 제거(순서 유지)
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="공고 상세 페이지 링크의 첨부파일을 모두 다운로드한다.")
    parser.add_argument("urls", nargs="*", help="공고 상세 페이지 URL(여러 개 가능)")
    parser.add_argument("--url-file", help="URL 목록 파일(한 줄에 1개)")
    parser.add_argument("--out-dir", required=True, help="저장 폴더(공고별 하위 폴더가 생성됨)")
    parser.add_argument("--dry-run", action="store_true", help="받지 않고 받을 목록만 미리보기")
    parser.add_argument("--open", action="store_true", help="완료 후 저장 폴더 열기(Windows)")
    parser.add_argument("--quiet", action="store_true", help="httpx 등 로그 출력 최소화")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
    )
    if args.quiet:
        logging.getLogger("httpx").setLevel(logging.WARNING)

    urls = load_urls(args)
    if not urls:
        print("❌ 받을 링크가 없습니다. 공고 상세 페이지 URL 을 입력하세요.")
        return 2

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[FileResult] = []
    opened_dirs: set[str] = set()
    for url in urls:
        print(f"\n🔗 처리 중: {url}")
        results = process_url(url, out_dir, args.dry_run)
        all_results.extend(results)
        title = results[0].notice_title if results else ""
        downloaded = [r for r in results if r.status == "DOWNLOADED"]
        for r in results:
            if r.status == "DOWNLOADED":
                print(f"  ✅ {r.file_name}")
            elif r.status == "DRY_RUN":
                print(f"  ▶ {r.file_name}")
            elif r.status == "NO_ATTACHMENTS":
                print("  ⚠ 첨부파일을 찾지 못했습니다")
            elif r.status in ("PAGE_FETCH_FAILED", "EXTRACT_FAILED", "DOWNLOAD_FAILED"):
                print(f"  ❌ {r.status}: {r.error}")
            # NOT_A_FILE(미리보기·외부링크)·DUPLICATE(중복)는 조용히 제외
        if title:
            print(f"  📁 공고: {title}")
        if downloaded and not args.dry_run:
            folder = str(Path(downloaded[0].save_path).parent)
            print(f"  💾 저장 위치: {folder}")
            if args.open and folder not in opened_dirs:
                opened_dirs.add(folder)
                try:
                    os.startfile(folder)  # type: ignore[attr-defined]
                except Exception:
                    pass

    # manifest 기록
    manifest = out_dir / "_download_log.json"
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "out_dir": str(out_dir),
        "dry_run": args.dry_run,
        "total_urls": len(urls),
        "status_counts": {},
        "results": [asdict(r) for r in all_results],
    }
    for r in all_results:
        summary["status_counts"][r.status] = summary["status_counts"].get(r.status, 0) + 1
    try:
        prev = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None
        if isinstance(prev, dict) and isinstance(prev.get("history"), list):
            summary["history"] = prev["history"][-19:] + [{"at": summary["generated_at"], "counts": summary["status_counts"]}]
        else:
            summary["history"] = [{"at": summary["generated_at"], "counts": summary["status_counts"]}]
    except Exception:
        summary["history"] = [{"at": summary["generated_at"], "counts": summary["status_counts"]}]
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = summary["status_counts"]
    ok = counts.get("DOWNLOADED", 0)
    skipped = counts.get("NOT_A_FILE", 0) + counts.get("DUPLICATE", 0)
    real_fail = counts.get("DOWNLOAD_FAILED", 0) + counts.get("PAGE_FETCH_FAILED", 0) + counts.get("EXTRACT_FAILED", 0)
    print(f"\n{'='*48}")
    print(f"📊 완료: 받은 파일 {ok}개 / 처리한 링크 {len(urls)}개")
    if skipped:
        print(f"   ℹ 미리보기·중복·외부링크 {skipped}건 자동 제외(첨부 아님)")
    if counts.get("NO_ATTACHMENTS"):
        print(f"   ⚠ 첨부를 찾지 못한 링크 {counts['NO_ATTACHMENTS']}건")
    if real_fail:
        print(f"   ❌ 실제 실패 {real_fail}건 (자세한 내용은 _download_log.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

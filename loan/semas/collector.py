"""Command line scanner for the SEMAS policy loan page."""

from __future__ import annotations

import argparse
import json
import logging
import os
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Callable

import httpx

from loan.reports.report_writer import write_semas_report
from loan.semas.keywords import keyword_evidence, keyword_presence
from loan.semas.parser import SemasNotice, classify_notices, page_text_from_html, parse_notices


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "loan" / "config" / "semas.yml"
DEFAULT_REPORT_PATH = ROOT / "reports" / "loan" / "semas_loan_scan.md"
DEFAULT_SEEN_PATH = ROOT / "reports" / "loan" / "semas_seen_notices.json"
KST = timezone(timedelta(hours=9))

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

log = logging.getLogger(__name__)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv as _load_shared
        _load_shared(r"D:\.env.shared")
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "send"}


def _load_simple_yaml(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    if not path.is_file():
        return config
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line or line.startswith("-"):
            continue
        key, value = line.split(":", 1)
        config[key.strip()] = value.strip().strip("'\"")
    return config


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("JSON 설정 로드 실패: %s", exc)
        return default


def _split_emails(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def _valid_recipient(email: str) -> bool:
    return "@" in email and "[REDACTED]" not in email


def resolve_recipients() -> list[str]:
    """Use MAIL_TO first, then existing settings/groups recipients."""
    recipients: list[str] = []
    mail_to = os.environ.get("MAIL_TO", "").strip()
    if mail_to:
        recipients.extend(_split_emails(mail_to))

    settings = _read_json(ROOT / "settings.json", {})
    recipients.extend(settings.get("raw_all_recipients", []) or [])

    for group in _read_json(ROOT / "groups.json", []):
        recipients.extend(group.get("recipients", []) or [])

    deduped: list[str] = []
    seen: set[str] = set()
    for recipient in recipients:
        if not _valid_recipient(recipient) or recipient in seen:
            continue
        seen.add(recipient)
        deduped.append(recipient)
    return deduped


def mask_email(email: str) -> str:
    local, sep, domain = (email or "").partition("@")
    if not sep:
        return "***"
    if len(local) <= 2:
        return local[:1] + "*@" + domain
    return local[:2] + "*" * (len(local) - 2) + "@" + domain


def load_seen_keys(path: Path = DEFAULT_SEEN_PATH) -> set[str]:
    raw = _read_json(path, {"notice_keys": []})
    if isinstance(raw, list):
        return {str(item) for item in raw if item}
    return {str(item) for item in raw.get("notice_keys", []) if item} if isinstance(raw, dict) else set()


def save_seen_keys(keys: set[str], path: Path = DEFAULT_SEEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "notice_keys": sorted(keys)[-1000:],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_page(url: str, timeout: float = 20.0) -> dict[str, Any]:
    try:
        with httpx.Client(headers=HTTP_HEADERS, timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
        return {
            "ok": 200 <= response.status_code < 400,
            "status_code": response.status_code,
            "html": response.text,
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "status_code": None, "html": "", "error": str(exc)}


def build_email_body(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"실행일시: {result.get('run_at')}",
            f"대상 URL: {result.get('target_url')}",
            f"접속 결과: {result.get('connection_result')}",
            f"HTTP 상태: {result.get('http_status')}",
            f"신규 공지 수: {len(result.get('new_notices', []))}",
            f"중복 제외 공지 수: {result.get('deduped_notice_count', 0)}",
            f"정책자금 키워드: {'있음' if result.get('keyword_presence', {}).get('정책자금') else '없음'}",
            f"재도전특별자금 문구: {'있음' if result.get('keyword_presence', {}).get('재도전특별자금') else '없음'}",
            f"접수 문구: {'있음' if result.get('keyword_presence', {}).get('접수') else '없음'}",
            f"신청 문구: {'있음' if result.get('keyword_presence', {}).get('신청') else '없음'}",
            f"마감 문구: {'있음' if result.get('keyword_presence', {}).get('마감') else '없음'}",
            f"예산소진 문구: {'있음' if result.get('keyword_presence', {}).get('예산소진') else '없음'}",
            f"리포트 경로: {result.get('report_path')}",
            f"오류 및 제한사항: {'; '.join(result.get('errors', [])) or '없음'}",
        ]
    )


def send_email(subject: str, body: str, recipients: list[str]) -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "465") or "465")
    if not gmail_address or not gmail_password:
        raise RuntimeError("GMAIL_ADDRESS 또는 GMAIL_APP_PASSWORD 미설정")
    if not recipients:
        raise RuntimeError("수신자 없음: MAIL_TO 또는 기존 recipients 설정 필요")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = gmail_address
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipients, message.as_string())
    log.info("정책자금 점검 메일 발송 완료: %s", ", ".join(mask_email(item) for item in recipients))


def maybe_send_email(
    result: dict[str, Any],
    requested: bool,
    *,
    mail_sender: Callable[[str, str, list[str]], None] = send_email,
) -> tuple[str, str]:
    if not requested:
        return "미실행", "send_email=false"
    if not _parse_bool(os.environ.get("ALLOW_SEND_EMAIL"), default=False):
        return "미실행", "ALLOW_SEND_EMAIL=true 필요"

    recipients = resolve_recipients()
    try:
        mail_sender("[mail] 소진공 정책자금 공지 점검 결과", build_email_body(result), recipients)
    except Exception as exc:
        return "실패", str(exc)
    return "성공", f"{len(recipients)}명"


def _serialize_notice(notice: SemasNotice) -> dict[str, Any]:
    return {
        "title": notice.title,
        "url": notice.url,
        "posted_date": notice.posted_date,
        "keywords": notice.keywords,
        "key": notice.key,
    }


def _build_judgment(result: dict[str, Any], classified: dict[str, Any]) -> dict[str, str]:
    new_count = len(classified["new"])
    duplicate_count = int(classified["duplicate_removed_count"])
    notice_visible = bool(result.get("notice_page_visible"))
    notice_available = "가능" if classified["unique"] or notice_visible else ("미확인" if result["connection_result"] == "가능" else "불가")
    notice_basis = f"관련 후보 {len(classified['unique'])}건 추출"
    if not classified["unique"] and notice_visible:
        notice_basis = "공지/안내 페이지 문구 확인, 목록 후보 없음"
    return {
        "공지 확인 가능 여부": notice_available,
        "공지 확인 근거": notice_basis,
        "신규 공지 여부": "신규" if new_count else ("기존" if classified["existing"] else "미확인"),
        "신규 공지 근거": f"최근/날짜불명 후보 중 신규 {new_count}건",
        "중복 여부": "중복" if duplicate_count else "중복 아님",
        "중복 근거": f"동일 제목+URL+게시일 기준 {duplicate_count}건 제외",
    }


def run_scan(
    *,
    run_mode: str,
    send_email_requested: bool,
    lookback_days: int | None = None,
    fetcher: Callable[[str, float], dict[str, Any]] = fetch_page,
    mail_sender: Callable[[str, str, list[str]], None] = send_email,
    report_path: Path = DEFAULT_REPORT_PATH,
    seen_path: Path = DEFAULT_SEEN_PATH,
) -> dict[str, Any]:
    _load_dotenv()
    config = _load_simple_yaml(CONFIG_PATH)
    target_url = os.environ.get("SEMAS_LOAN_URL") or config.get("target_url", "")
    if not target_url:
        raise RuntimeError("SEMAS_LOAN_URL 또는 loan/config/semas.yml target_url 필요")

    effective_lookback = int(
        lookback_days
        or os.environ.get("LOOKBACK_DAYS")
        or config.get("lookback_days", "3")
    )
    timeout = float(config.get("request_timeout_seconds", "20"))
    now = datetime.now(KST)
    seen_keys = load_seen_keys(seen_path)
    fetched = fetcher(target_url, timeout)
    html = fetched.get("html") or ""
    page_text = page_text_from_html(html) if html else ""
    notices = parse_notices(html, target_url) if html else []
    classified = classify_notices(notices, seen_keys, effective_lookback, today=now.date())

    errors: list[str] = []
    if fetched.get("error"):
        errors.append(f"외부 사이트 접속 실패: {fetched['error']}")
    if fetched.get("status_code") and not fetched.get("ok"):
        errors.append(f"HTTP 상태 비정상: {fetched.get('status_code')}")
    if not notices and fetched.get("ok"):
        errors.append("로그인 없이 확인 가능한 관련 공지 후보를 찾지 못했습니다.")

    result: dict[str, Any] = {
        "run_at": now.strftime("%Y-%m-%d %H:%M:%S KST"),
        "target_url": target_url,
        "connection_result": "가능" if fetched.get("ok") else "불가",
        "http_status": fetched.get("status_code") or "미확인",
        "base_date": now.date().isoformat(),
        "lookback_days": effective_lookback,
        "new_notices": classified["new"],
        "existing_notices": classified["existing"],
        "deduped_notice_count": len(classified["unique"]),
        "duplicate_removed_count": classified["duplicate_removed_count"],
        "keyword_presence": keyword_presence(page_text) if page_text else {},
        "keyword_evidence": keyword_evidence(page_text) if page_text else {},
        "notice_page_visible": ("공지" in page_text or "안내" in page_text) if page_text else False,
        "errors": errors,
        "next_actions": [
            "신규 공지가 있으면 상세 내용을 검토하세요.",
            "외부 사이트 구조가 바뀌면 파서 selector 안정화를 진행하세요.",
        ],
        "report_path": str(report_path),
    }
    result["judgment"] = _build_judgment(result, classified)
    result["email_status"] = "미실행"
    result["email_reason"] = ""

    report_file = write_semas_report(result, report_path)
    result["report_path"] = str(report_file)
    email_status, email_reason = maybe_send_email(result, send_email_requested, mail_sender=mail_sender)
    result["email_status"] = email_status
    result["email_reason"] = email_reason
    write_semas_report(result, report_path)

    if run_mode == "live" and email_status != "실패":
        seen_keys.update(notice.key for notice in classified["recent_or_unknown"])
        save_seen_keys(seen_keys, seen_path)

    log.info(
        "SEMAS 정책자금 점검 완료: 접속=%s, 신규=%d, 리포트=%s, 메일=%s",
        result["connection_result"],
        len(result["new_notices"]),
        result["report_path"],
        result["email_status"],
    )
    result["new_notice_records"] = [_serialize_notice(notice) for notice in result["new_notices"]]
    result["existing_notice_records"] = [_serialize_notice(notice) for notice in result["existing_notices"]]
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SEMAS policy loan notice scanner")
    parser.add_argument("--run-mode", default=os.environ.get("DEFAULT_RUN_MODE", "dry-run"), choices=["dry-run", "live"])
    parser.add_argument("--send-email", default="false", help="true이면 안전장치 통과 시 실제 메일 발송")
    parser.add_argument("--lookback-days", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    result = run_scan(
        run_mode=args.run_mode,
        send_email_requested=_parse_bool(args.send_email),
        lookback_days=args.lookback_days,
    )
    print(json.dumps({
        "ok": True,
        "connection_result": result["connection_result"],
        "http_status": result["http_status"],
        "new_notices": len(result["new_notices"]),
        "report_path": result["report_path"],
        "email_status": result["email_status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


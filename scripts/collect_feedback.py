#!/usr/bin/env python3
r"""collect_feedback — 사용자가 보낸 ⭕/❌ 피드백 메일을 읽어 골든(Tier C)으로 축적.

digest 하단의 `⭕ 맞아요 / ❌ 아니에요` 링크를 누르면 제목이 `[MAIL-FB] X <공고id>` 인
메일이 사용자 자신에게 전송된다. 이 스크립트는 그 메일을 **읽기 전용**으로 수집해
data/golden/feedback_labels.jsonl (tier C = 사람확인)에 누적한다.

안전(RULES.md 준수):
  - 발송 없음. IMAP `SELECT readonly=True` + `BODY.PEEK[...]` → 읽음표시·삭제·이동 없음.
  - 로그에 메일 주소 마스킹, 본문·비밀번호 미출력(제목의 공고 id 만 사용).

사용 (repo 루트):
  python scripts/collect_feedback.py                 # 최근 60일 피드백 수집→누적
  python scripts/collect_feedback.py --days 7
  python scripts/collect_feedback.py --dry-run       # 수집만 하고 파일 기록 안 함
환경변수: GMAIL_ADDRESS, GMAIL_APP_PASSWORD (.env / ../.env.shared 자동 로드)
"""
from __future__ import annotations

import argparse
import email
import imaplib
import os
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from feedback import (  # noqa: E402
    SUBJECT_TAG,
    LABELS_PATH,
    merge_feedback_labels,
    parse_feedback_subject,
)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env.shared")


def _mask(addr: str) -> str:
    local, sep, domain = (addr or "").partition("@")
    if not sep:
        return "***"
    return (local[:2] + "*" * max(len(local) - 2, 1)) + "@" + domain


def _decode_subject(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw or "")))
    except Exception:  # noqa: BLE001
        return raw or ""


def _find_all_mail_folder(imap: imaplib.IMAP4) -> str:
    r"""Gmail '전체보관함'(\All) 폴더명을 로케일 무관하게 찾는다. 실패 시 INBOX."""
    try:
        typ, data = imap.list('""', "*")
        if typ != "OK":
            return "INBOX"
        for raw in data or []:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            attrs = line.split(")")[0]
            if "\\All" in attrs:
                m = re.search(r'"([^"]*)"\s*$', line.strip())
                if m:
                    return f'"{m.group(1)}"'
        return "INBOX"
    except Exception:  # noqa: BLE001
        return "INBOX"


def fetch_feedback_mails(days: int = 60) -> list[dict]:
    """IMAP(읽기전용)으로 `[MAIL-FB]` 제목 메일을 찾아 {'id','verdict','received'} 목록 반환."""
    addr = os.environ.get("GMAIL_ADDRESS", "")
    pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not addr or not pw:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD 환경변수가 필요합니다(.env).")
    since = (datetime.now() - timedelta(days=max(days, 1))).strftime("%d-%b-%Y")
    out: list[dict] = []
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(addr, pw)
        folder = _find_all_mail_folder(imap)
        typ, _ = imap.select(folder, readonly=True)   # ★ 읽기 전용
        if typ != "OK":
            imap.select("INBOX", readonly=True)
        # Gmail 은 대괄호를 IMAP SEARCH 에서 잘 다루지 못해 태그 본체(MAIL-FB)로 찾는다.
        typ, data = imap.search(None, "SUBJECT", '"MAIL-FB"', "SINCE", since)
        if typ != "OK":
            return out
        nums = (data[0] or b"").split()
        for num in nums:
            typ, msg_data = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
            if typ != "OK" or not msg_data:
                continue
            raw = next((p[1] for p in msg_data if isinstance(p, tuple) and p[1]), None)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            parsed = parse_feedback_subject(_decode_subject(msg.get("Subject", "")))
            if not parsed:
                continue
            out.append({
                "id": parsed["id"],
                "verdict": parsed["verdict"],
                "received": (msg.get("Date") or "").strip(),
                "source": "mail-feedback",
            })
    finally:
        try:
            imap.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{SUBJECT_TAG} 피드백 메일 수집(읽기전용)")
    ap.add_argument("--days", type=int, default=60, help="최근 N일치만 검색(기본 60)")
    ap.add_argument("--dry-run", action="store_true", help="수집만 하고 골든 파일에 기록하지 않음")
    args = ap.parse_args(argv)

    _load_env()
    try:
        mails = fetch_feedback_mails(args.days)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 피드백 메일 수집 실패: {e}")
        return 2

    addr = _mask(os.environ.get("GMAIL_ADDRESS", ""))
    o = sum(1 for m in mails if m["verdict"] == "O")
    x = sum(1 for m in mails if m["verdict"] == "X")
    print(f"[feedback] {addr} 최근 {args.days}일 → 피드백 메일 {len(mails)}건 (⭕{o} / ❌{x})")
    if args.dry_run:
        print("[dry-run] 기록 생략")
        return 0
    stats = merge_feedback_labels(mails)
    print(f"[golden] {LABELS_PATH.name}: 신규 {stats['added']} · 변경 {stats['updated']} · "
          f"동일 {stats['unchanged']} · 무시 {stats['invalid']} → 총 {stats['total']}건(tier C)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Markdown report writer for SEMAS loan scans."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _cell(value: Any) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ").strip()
    return text or "-"


def _yn_unknown(value: bool | None) -> str:
    if value is True:
        return "있음"
    if value is False:
        return "없음"
    return "미확인"


def write_semas_report(result: dict[str, Any], path: str | Path) -> Path:
    """Write the required SEMAS Markdown report and return its path."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    new_notices = result.get("new_notices", [])
    existing_notices = result.get("existing_notices", [])
    keyword_presence = result.get("keyword_presence", {})
    evidence = result.get("keyword_evidence", {})
    judgment = result.get("judgment", {})
    errors = result.get("errors", []) or ["없음"]
    next_actions = result.get("next_actions", []) or ["수동 실행 결과를 확인하세요."]

    lines: list[str] = [
        "# 소진공 정책자금 공지 점검 리포트",
        "",
        "## 1. 실행 요약",
        f"- 실행일시: {result.get('run_at', '-')}",
        f"- 대상 URL: {result.get('target_url', '-')}",
        f"- 접속 결과: {result.get('connection_result', '-')}",
        f"- HTTP 상태: {result.get('http_status', '-')}",
        "- 로그인 필요 여부: 아니오",
        f"- 조회 기준일: {result.get('base_date', '-')}",
        f"- 조회 기간: 최근 {result.get('lookback_days', '-')}일",
        f"- 신규 공지 수: {len(new_notices)}",
        f"- 중복 제외 공지 수: {result.get('deduped_notice_count', 0)}",
        f"- 메일 발송 여부: {result.get('email_status', '미실행')}",
        "",
        "## 2. 신규 감지 공지",
        "",
        "| 번호 | 게시일 | 제목 | URL | 감지 키워드 |",
        "|---:|---|---|---|---|",
    ]

    if new_notices:
        for idx, notice in enumerate(new_notices, start=1):
            lines.append(
                f"| {idx} | {_cell(getattr(notice, 'posted_date', ''))} | "
                f"{_cell(getattr(notice, 'title', ''))} | {_cell(getattr(notice, 'url', ''))} | "
                f"{_cell(', '.join(getattr(notice, 'keywords', []) or []))} |"
            )
    else:
        lines.append("| - | - | 신규 감지 공지 없음 | - | - |")

    lines += [
        "",
        "### 기존/중복 제외 공지",
        "",
        "| 번호 | 게시일 | 제목 | URL | 감지 키워드 |",
        "|---:|---|---|---|---|",
    ]
    if existing_notices:
        for idx, notice in enumerate(existing_notices, start=1):
            lines.append(
                f"| {idx} | {_cell(getattr(notice, 'posted_date', ''))} | "
                f"{_cell(getattr(notice, 'title', ''))} | {_cell(getattr(notice, 'url', ''))} | "
                f"{_cell(', '.join(getattr(notice, 'keywords', []) or []))} |"
            )
    else:
        lines.append("| - | - | 기존/중복 제외 공지 없음 | - | - |")

    lines += [
        "",
        "## 3. 감지된 주요 문구",
        "",
        "| 구분 | 내용 |",
        "|---|---|",
        f"| 정책자금 | {_cell(evidence.get('정책자금'))} |",
        f"| 재도전특별자금 | {_cell(evidence.get('재도전특별자금'))} |",
        f"| 접수/신청 | {_cell(evidence.get('접수') or evidence.get('신청'))} |",
        f"| 마감/예산소진 | {_cell(evidence.get('마감') or evidence.get('예산소진'))} |",
        f"| 공지/안내 | {_cell(evidence.get('공지/안내'))} |",
        "",
        "## 4. 정책자금 관련 판단",
        "",
        "| 항목 | 결과 | 근거 |",
        "|---|---|---|",
        f"| 공지 확인 가능 여부 | {judgment.get('공지 확인 가능 여부', '미확인')} | {_cell(judgment.get('공지 확인 근거'))} |",
        f"| 정책자금 문구 | {_yn_unknown(keyword_presence.get('정책자금'))} | {_cell(evidence.get('정책자금'))} |",
        f"| 재도전특별자금 문구 | {_yn_unknown(keyword_presence.get('재도전특별자금'))} | {_cell(evidence.get('재도전특별자금'))} |",
        f"| 접수 문구 | {_yn_unknown(keyword_presence.get('접수'))} | {_cell(evidence.get('접수'))} |",
        f"| 신청 문구 | {_yn_unknown(keyword_presence.get('신청'))} | {_cell(evidence.get('신청'))} |",
        f"| 마감 문구 | {_yn_unknown(keyword_presence.get('마감'))} | {_cell(evidence.get('마감'))} |",
        f"| 예산소진 문구 | {_yn_unknown(keyword_presence.get('예산소진'))} | {_cell(evidence.get('예산소진'))} |",
        f"| 오류/점검 문구 | {_yn_unknown(keyword_presence.get('오류/점검'))} | {_cell(evidence.get('오류/점검'))} |",
        f"| 신규 공지 여부 | {judgment.get('신규 공지 여부', '미확인')} | {_cell(judgment.get('신규 공지 근거'))} |",
        f"| 중복 여부 | {judgment.get('중복 여부', '미확인')} | {_cell(judgment.get('중복 근거'))} |",
        "",
        "## 5. 오류 및 제한사항",
    ]
    lines.extend(f"- {_cell(error)}" for error in errors)
    lines += ["", "## 6. 다음 조치"]
    lines.extend(f"- {_cell(action)}" for action in next_actions)
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


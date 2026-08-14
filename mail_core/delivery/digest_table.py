"""공고 안내 메일 8컬럼 표 (표시 전용).

컬럼 순서: 상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감
수집·매칭·발송 정책은 변경하지 않는다. 추천이유/바로가기/사이트명 컬럼은 만들지 않는다.
"""
from __future__ import annotations

import html
import re
from typing import Callable

COLUMNS: tuple[str, ...] = ("상태", "적합", "공고", "지원", "대상", "기관", "지역", "마감")
HEADER_LINE = " | ".join(COLUMNS)
EMPTY_DIGEST = "현재 조건에 맞는 신규 공고가 없습니다."
# 공고 셀: "제목 «url»" — HTML 에서 제목을 링크로 쓰고, plain 에서는 제목만 보여도 되게 파싱한다.
_TITLE_URL_RE = re.compile(r"^(?P<title>.*?)(?:\s*«(?P<url>https?://[^»]+)»)?\s*$", re.DOTALL)
_MISSING = "확인필요"
_PARSE_FAIL = "추출실패"


def notice_url(item: dict) -> str:
    for key in ("source_url", "link"):
        raw = str(item.get(key) or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
    return ""


def encode_notice_cell(title: str, url: str) -> str:
    title = (title or "(제목없음)").replace("|", "/").strip() or "(제목없음)"
    url = (url or "").strip()
    if url:
        return f"{title} «{url}»"
    return title


def decode_notice_cell(cell: str) -> tuple[str, str]:
    text = str(cell or "").strip()
    m = _TITLE_URL_RE.match(text)
    if not m:
        return text or "(제목없음)", ""
    title = (m.group("title") or "").strip() or "(제목없음)"
    url = (m.group("url") or "").strip()
    return title, url


def render_plain(rows: list[dict], *, preamble: str = "") -> str:
    if not rows:
        return EMPTY_DIGEST
    lines: list[str] = []
    pre = (preamble or "").rstrip()
    if pre:
        lines.append(pre)
        lines.append("")
    lines.append(HEADER_LINE)
    for row in rows:
        cells = []
        for col in COLUMNS:
            if col == "공고":
                cells.append(encode_notice_cell(str(row.get("공고") or ""), str(row.get("url") or "")))
            else:
                val = str(row.get(col) if row.get(col) is not None else _MISSING)
                cells.append(val.replace("|", "/").strip() or _MISSING)
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def parse_plain_table(body: str) -> tuple[str, list[dict] | None, str]:
    """본문에서 8컬럼 표를 분리한다. 표가 없으면 rows=None."""
    text = body or ""
    idx = text.find(HEADER_LINE)
    if idx < 0:
        return text, None, ""
    before = text[:idx].rstrip()
    rest = text[idx + len(HEADER_LINE):].lstrip("\n")
    rows: list[dict] = []
    after_lines: list[str] = []
    in_table = True
    for line in rest.splitlines():
        if in_table and " | " in line:
            parts = [p.strip() for p in line.split(" | ")]
            if len(parts) < len(COLUMNS):
                parts.extend([_MISSING] * (len(COLUMNS) - len(parts)))
            row = {col: parts[i] if i < len(parts) else _MISSING for i, col in enumerate(COLUMNS)}
            title, url = decode_notice_cell(row.get("공고") or "")
            row["공고"] = title
            row["url"] = url
            rows.append(row)
            continue
        in_table = False
        after_lines.append(line)
    after = "\n".join(after_lines).strip("\n")
    return before, rows, after


def render_html_table(rows: list[dict]) -> str:
    th = "".join(
        f"<th style='border:1px solid #d1d5db;background:#f3f4f6;padding:6px 8px;"
        f"text-align:left;font-size:12px'>{html.escape(col)}</th>"
        for col in COLUMNS
    )
    body_rows = []
    for row in rows:
        tds = []
        for col in COLUMNS:
            if col == "공고":
                title = str(row.get("공고") or "(제목없음)")
                url = str(row.get("url") or "").strip()
                if url:
                    inner = (
                        f'<a href="{html.escape(url, quote=True)}">'
                        f"{html.escape(title)}</a>"
                    )
                else:
                    inner = html.escape(title)
            else:
                inner = html.escape(str(row.get(col) or _MISSING))
            tds.append(
                f"<td style='border:1px solid #d1d5db;padding:6px 8px;"
                f"font-size:12px;vertical-align:top'>{inner}</td>"
            )
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    return (
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' "
        "style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif'>"
        f"<thead><tr>{th}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    )


def html_email_inner(body: str, linkify: Callable[[str], str]) -> str:
    """Gmail용 HTML. 8컬럼 표가 있으면 table, 나머지는 기존 링크화."""
    before, rows, after = parse_plain_table(body)
    if rows is None:
        stripped = (body or "").strip()
        if stripped == EMPTY_DIGEST:
            return f"<p>{html.escape(EMPTY_DIGEST)}</p>"
        return f"<pre style='white-space:pre-wrap;font-family:inherit'>{linkify(body or '')}</pre>"

    parts: list[str] = []
    if before.strip():
        parts.append(f"<div>{linkify(before)}</div>")
    if not rows:
        parts.append(f"<p>{html.escape(EMPTY_DIGEST)}</p>")
    else:
        parts.append(render_html_table(rows))
    if after.strip():
        parts.append(f"<div>{linkify(after)}</div>")
    return "".join(parts)


def cell_or_fallback(value: object, *, parse_error: bool = False) -> str:
    if parse_error:
        return _PARSE_FAIL
    text = str(value or "").strip()
    return text if text else _MISSING

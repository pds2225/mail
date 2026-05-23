"""실행 결과 Markdown 보고서."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from customer_intake.extractor import ExtractedRecord
from customer_intake.config import reports_dir
from customer_intake.sheets_writer import WritePreview, WriteResult

KST = timezone(timedelta(hours=9))


@dataclass
class RunSummary:
    input_path: str
    dry_run: bool
    files_processed: int
    records: list[ExtractedRecord]
    write_result: WriteResult | None
    errors: list[str]
    used_mock_ocr: bool
    ocr_mode_label: str = ""
    env_gaps: list[str] | None = None


def save_report(summary: RunSummary, *, reports_root: Path | None = None) -> Path:
    out_dir = (reports_root or reports_dir()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"customer_intake_{ts}.md"

    lines: list[str] = [
        "# 고객사 서류 OCR intake 보고서",
        "",
        f"- **실행일시**: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} (KST)",
        f"- **입력경로**: `{summary.input_path}`",
        f"- **보고서 저장**: `{path}`",
        f"- **dry_run**: `{summary.dry_run}`",
        f"- **OCR 모드**: `{summary.ocr_mode_label or ('Mock' if summary.used_mock_ocr else 'CLOVA API')}`",
        f"- **처리 파일 수**: {summary.files_processed}",
        "",
    ]

    if summary.env_gaps:
        lines.append("## 환경변수 (.env) 미설정 항목")
        lines.append("")
        lines.append("처리는 Mock OCR / dry_run 으로 완료되었습니다. 실제 연동 시 `D:\\mail\\.env` 에 설정하세요.")
        lines.append("")
        for g in summary.env_gaps:
            lines.append(f"- {g}")
        lines.append("")

    if summary.errors:
        lines.append("## 오류")
        for e in summary.errors:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("## 추출 결과")
    for i, rec in enumerate(summary.records, 1):
        lines.extend(
            [
                f"### 문서 {i}: {rec.파일명}",
                "",
                "| 항목 | 값 |",
                "|------|-----|",
                f"| 고객사명 | {rec.고객사명} |",
                f"| 대표자명 | {rec.대표자명} |",
                f"| 사업자등록번호 | {rec.사업자등록번호} |",
                f"| 법인등록번호 | {rec.법인등록번호} |",
                f"| 사업장주소 | {rec.사업장주소} |",
                f"| 개업일 | {rec.개업일} |",
                f"| 업태 | {rec.업태} |",
                f"| 종목 | {rec.종목} |",
                f"| 과세유형 | {rec.과세유형} |",
                f"| 서류종류 | {rec.서류종류} |",
                f"| 확인상태 | {rec.확인상태} |",
                f"| 확인필요사항 | {rec.확인필요사항 or '-'} |",
                "",
            ]
        )

    if summary.write_result and summary.write_result.preview:
        wr = summary.write_result
        p = wr.preview
        lines.extend(
            [
                "## Google Sheets 기록 요약",
                "",
                f"- 마스터 신규 예정: **{wr.master_inserted}**",
                f"- 마스터 중복 스킵: **{wr.master_skipped}**",
                f"- 제출서류 기록: **{wr.documents_inserted}**",
                "",
            ]
        )
        if p and p.skipped_master_biz_nos:
            lines.append("### 중복 스킵 사업자번호")
            for b in p.skipped_master_biz_nos:
                lines.append(f"- {b}")
            lines.append("")

    if summary.dry_run:
        lines.extend(
            [
                "## Sheets 기록 안내",
                "",
                "이번 실행은 Google Sheets에 기록하지 않았습니다 (dry_run).",
                "`.env`에 GOOGLE_SHEET_ID·서비스 계정이 있으면 자동 기록 모드로 동작합니다.",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path

"""OCR 텍스트에서 고객사 기본정보 추출 (추정 금지, 미추출 시 확인필요)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from customer_intake.clova_ocr_client import OcrImageResult

CONFIRM_NEEDED = "확인필요"
KST = timezone(timedelta(hours=9))

BIZ_NO_RE = re.compile(r"\d{3}[-\s]?\d{2}[-\s]?\d{5}")
CORP_NO_RE = re.compile(r"\d{6}[-\s]?\d{7}")
DATE_RE = re.compile(
    r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
    r"|(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"
)

LABEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("고객사명", re.compile(r"(?:상\s*호|법\s*인\s*명|회\s*사\s*명)\s*[:：]?\s*(.+)", re.I)),
    ("대표자명", re.compile(r"(?:대\s*표\s*자|성\s*명)\s*[:：]?\s*(.+)", re.I)),
    ("사업자등록번호", re.compile(r"사업자\s*등록\s*번호\s*[:：]?\s*([\d\-\s]+)", re.I)),
    ("법인등록번호", re.compile(r"법인\s*등록\s*번호\s*[:：]?\s*([\d\-\s]+)", re.I)),
    ("사업장주소", re.compile(r"(?:사업장\s*소재지|소재지)\s*[:：]?\s*(.+)", re.I)),
    ("개업일", re.compile(r"개\s*업\s*일\s*[:：]?\s*(.+)", re.I)),
    ("업태", re.compile(r"업\s*태\s*[:：]?\s*(.+)", re.I)),
    ("종목", re.compile(r"종\s*목\s*[:：]?\s*(.+)", re.I)),
    ("과세유형", re.compile(r"(?:과세\s*유형|과세형태)\s*[:：]?\s*(.+)", re.I)),
]

FIELD_NAME_MAP = {
    "companyname": "고객사명",
    "repname": "대표자명",
    "registernumber": "사업자등록번호",
    "corpregisternumber": "법인등록번호",
    "address": "사업장주소",
    "opendate": "개업일",
    "biztype": "업태",
    "bizitem": "종목",
    "taxtype": "과세유형",
}


@dataclass
class ExtractedRecord:
    고객사명: str = CONFIRM_NEEDED
    대표자명: str = CONFIRM_NEEDED
    사업자등록번호: str = CONFIRM_NEEDED
    법인등록번호: str = CONFIRM_NEEDED
    사업장주소: str = CONFIRM_NEEDED
    개업일: str = CONFIRM_NEEDED
    업태: str = CONFIRM_NEEDED
    종목: str = CONFIRM_NEEDED
    과세유형: str = CONFIRM_NEEDED
    서류종류: str = CONFIRM_NEEDED
    파일명: str = CONFIRM_NEEDED
    파일경로: str = CONFIRM_NEEDED
    추출일시: str = ""
    확인상태: str = CONFIRM_NEEDED
    확인필요사항: str = ""

    def as_master_row(self) -> list[str]:
        return [
            self.고객사명,
            self.대표자명,
            self.사업자등록번호,
            self.법인등록번호,
            self.사업장주소,
            self.개업일,
            self.업태,
            self.종목,
            self.과세유형,
            self.확인상태,
            self.확인필요사항,
            self.추출일시,
        ]

    def as_document_row(self) -> list[str]:
        return [
            self.고객사명,
            self.사업자등록번호,
            self.서류종류,
            self.파일명,
            self.파일경로,
            self.추출일시,
            self.확인상태,
            self.확인필요사항,
        ]

    def master_dict(self) -> dict[str, str]:
        return {
            "고객사명": self.고객사명,
            "대표자명": self.대표자명,
            "사업자등록번호": self.사업자등록번호,
            "법인등록번호": self.법인등록번호,
            "사업장주소": self.사업장주소,
            "개업일": self.개업일,
            "업태": self.업태,
            "종목": self.종목,
            "과세유형": self.과세유형,
            "확인상태": self.확인상태,
            "확인필요사항": self.확인필요사항,
            "추출일시": self.추출일시,
        }


def _normalize_biz_no(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    if len(digits) != 10:
        return CONFIRM_NEEDED
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def _normalize_corp_no(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    if len(digits) != 13:
        return CONFIRM_NEEDED
    return f"{digits[:6]}-{digits[6:]}"


def _normalize_date(text: str) -> str:
    text = text.strip()
    m = DATE_RE.search(text)
    if not m:
        return CONFIRM_NEEDED if not text else text.strip()
    if m.group(1):
        y, mo, d = m.group(1), m.group(2), m.group(3)
    else:
        y, mo, d = m.group(4), m.group(5), m.group(6)
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _clean_label_value(value: str) -> str:
    v = value.strip()
    v = re.split(r"\s{2,}|\t", v)[0].strip()
    return v if v else CONFIRM_NEEDED


def _text_blob(ocr: OcrImageResult) -> str:
    parts: list[str] = []
    for ln in ocr.lines:
        if ln:
            parts.append(ln)
    for f in ocr.fields:
        t = f.get("inferText") or ""
        if t:
            parts.append(str(t))
    return "\n".join(parts)


def _apply_structured_fields(data: dict[str, str], ocr: OcrImageResult) -> None:
    for f in ocr.fields:
        key = (f.get("name") or "").replace(" ", "").lower()
        label = FIELD_NAME_MAP.get(key)
        if not label:
            continue
        val = (f.get("inferText") or "").strip()
        if not val:
            continue
        if label == "사업자등록번호":
            data[label] = _normalize_biz_no(val)
        elif label == "법인등록번호":
            data[label] = _normalize_corp_no(val)
        elif label == "개업일":
            data[label] = _normalize_date(val)
        else:
            data[label] = _clean_label_value(val)


def _apply_line_patterns(data: dict[str, str], text: str) -> None:
    for label, pat in LABEL_PATTERNS:
        if data.get(label) not in (None, CONFIRM_NEEDED, ""):
            continue
        m = pat.search(text)
        if not m:
            continue
        raw = m.group(1).strip()
        if label == "사업자등록번호":
            data[label] = _normalize_biz_no(raw)
        elif label == "법인등록번호":
            data[label] = _normalize_corp_no(raw)
        elif label == "개업일":
            data[label] = _normalize_date(raw)
        else:
            data[label] = _clean_label_value(raw)

    if data.get("사업자등록번호") == CONFIRM_NEEDED:
        m = BIZ_NO_RE.search(text)
        if m:
            data["사업자등록번호"] = _normalize_biz_no(m.group(0))

    if data.get("법인등록번호") == CONFIRM_NEEDED:
        m = CORP_NO_RE.search(text)
        if m:
            data["법인등록번호"] = _normalize_corp_no(m.group(0))


def _finalize_status(data: dict[str, str]) -> tuple[str, str]:
    required = [
        "고객사명",
        "대표자명",
        "사업자등록번호",
        "사업장주소",
        "개업일",
        "업태",
        "종목",
    ]
    missing = [k for k in required if data.get(k, CONFIRM_NEEDED) == CONFIRM_NEEDED]
    optional_missing = [
        k
        for k in ("법인등록번호", "과세유형")
        if data.get(k, CONFIRM_NEEDED) == CONFIRM_NEEDED
    ]
    notes: list[str] = []
    if missing:
        notes.append("필수미추출: " + ", ".join(missing))
    if optional_missing:
        notes.append("선택미추출: " + ", ".join(optional_missing))
    if missing:
        return CONFIRM_NEEDED, "; ".join(notes) if notes else CONFIRM_NEEDED
    status = "확인필요" if optional_missing else "추출완료"
    return status, "; ".join(notes) if notes else ""


def extract_from_ocr(
    ocr: OcrImageResult,
    *,
    file_path: Path,
    doc_type: str,
) -> ExtractedRecord:
    text = _text_blob(ocr)
    data: dict[str, str] = {k: CONFIRM_NEEDED for k, _ in LABEL_PATTERNS}
    data["과세유형"] = CONFIRM_NEEDED

    _apply_structured_fields(data, ocr)
    _apply_line_patterns(data, text)

    status, notes = _finalize_status(data)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    return ExtractedRecord(
        고객사명=data.get("고객사명", CONFIRM_NEEDED),
        대표자명=data.get("대표자명", CONFIRM_NEEDED),
        사업자등록번호=data.get("사업자등록번호", CONFIRM_NEEDED),
        법인등록번호=data.get("법인등록번호", CONFIRM_NEEDED),
        사업장주소=data.get("사업장주소", CONFIRM_NEEDED),
        개업일=data.get("개업일", CONFIRM_NEEDED),
        업태=data.get("업태", CONFIRM_NEEDED),
        종목=data.get("종목", CONFIRM_NEEDED),
        과세유형=data.get("과세유형", CONFIRM_NEEDED),
        서류종류=doc_type,
        파일명=file_path.name,
        파일경로=str(file_path.resolve()),
        추출일시=now,
        확인상태=status,
        확인필요사항=notes,
    )

"""로컬 폴더·inbox·단일 파일에서 PDF/PNG/JPG 탐색 (사업자등록증 우선)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from customer_intake.config import SUPPORTED_SUFFIXES, inbox_dir
BUSINESS_REG_KEYWORDS = (
    "사업자등록증",
    "사업자등록",
    "사업자 등록",
    "business_registration",
    "biz_reg",
)


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    priority: int  # 낮을수록 먼저 처리
    doc_type_hint: str


def _priority_for(path: Path) -> tuple[int, str]:
    name_lower = path.stem.lower()
    for i, kw in enumerate(BUSINESS_REG_KEYWORDS):
        if kw.lower() in name_lower or kw in path.stem:
            return (0, "사업자등록증")
    return (1, "기타서류")


def scan_input(path_str: str) -> list[ScannedFile]:
    """
    폴더면 하위 PDF/PNG/JPG 재귀 탐색, 파일이면 단일 항목.
    사업자등록증 키워드 파일을 우선 정렬.
    """
    root = Path(path_str).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"경로 없음: {root}")

    files: list[Path] = []
    if root.is_file():
        if root.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(
                f"지원하지 않는 확장자: {root.suffix} "
                f"(지원: {', '.join(sorted(SUPPORTED_SUFFIXES))})"
            )
        files.append(root)
    else:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
                files.append(p)

    if not files:
        raise FileNotFoundError(f"처리할 문서 없음: {root}")

    scanned: list[ScannedFile] = []
    for p in sorted(files, key=lambda x: (str(x).lower())):
        pri, hint = _priority_for(p)
        scanned.append(ScannedFile(path=p, priority=pri, doc_type_hint=hint))

    scanned.sort(key=lambda s: (s.priority, s.path.name.lower()))
    return scanned


def scan_inbox(inbox: Path | None = None) -> list[ScannedFile]:
    """inbox 폴더 직하위 문서만 탐색 (사업자등록증 우선 정렬)."""
    root = (inbox or inbox_dir()).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"inbox 폴더 없음: {root}")

    files: list[Path] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(p)

    scanned: list[ScannedFile] = []
    for p in files:
        pri, hint = _priority_for(p)
        scanned.append(ScannedFile(path=p, priority=pri, doc_type_hint=hint))

    scanned.sort(key=lambda s: (s.priority, s.path.name.lower()))
    return scanned

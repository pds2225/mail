from pathlib import Path

import pytest

from customer_intake.clova_ocr_client import OcrImageResult
from customer_intake.extractor import CONFIRM_NEEDED, extract_from_ocr
from customer_intake.file_scanner import scan_input
from customer_intake.privacy import (
    mask_address,
    mask_business_number,
    mask_company_name,
    mask_corp_number,
    mask_person_name,
)
from customer_intake.processed_store import ProcessedStore


def make_ocr(*, fields=None, lines=None):
    return OcrImageResult(
        name="sample",
        infer_result="SUCCESS",
        fields=fields or [],
        lines=lines or [],
    )


def test_extract_from_ocr_normalizes_structured_fields(tmp_path):
    file_path = tmp_path / "사업자등록증.pdf"
    file_path.write_bytes(b"pdf")
    ocr = make_ocr(
        fields=[
            {"name": "companyName", "inferText": "테스트상사"},
            {"name": "repName", "inferText": "홍길동"},
            {"name": "registerNumber", "inferText": "1234567890"},
            {"name": "corpRegisterNumber", "inferText": "1101111234567"},
            {"name": "address", "inferText": "서울특별시 강남구 테헤란로 1"},
            {"name": "openDate", "inferText": "2024년 1월 2일"},
            {"name": "bizType", "inferText": "도소매"},
            {"name": "bizItem", "inferText": "화장품"},
            {"name": "taxType", "inferText": "일반과세자"},
        ]
    )

    record = extract_from_ocr(ocr, file_path=file_path, doc_type="사업자등록증")

    assert record.고객사명 == "테스트상사"
    assert record.대표자명 == "홍길동"
    assert record.사업자등록번호 == "123-45-67890"
    assert record.법인등록번호 == "110111-1234567"
    assert record.개업일 == "2024-01-02"
    assert record.확인상태 == "추출완료"
    assert record.확인필요사항 == ""
    assert record.서류종류 == "사업자등록증"
    assert record.파일명 == file_path.name


def test_extract_from_ocr_uses_line_fallback_and_reports_missing_required(tmp_path):
    file_path = tmp_path / "통장사본.png"
    file_path.write_bytes(b"png")
    ocr = make_ocr(
        lines=[
            "상호: 라인테스트",
            "사업자 등록 번호: 987-65-43210",
            "법인등록번호: 123456-7654321",
        ]
    )

    record = extract_from_ocr(ocr, file_path=file_path, doc_type="기타서류")

    assert record.고객사명 == "라인테스트"
    assert record.사업자등록번호 == "987-65-43210"
    assert record.법인등록번호 == "123456-7654321"
    assert record.대표자명 == CONFIRM_NEEDED
    assert record.확인상태 == CONFIRM_NEEDED
    assert "필수미추출" in record.확인필요사항
    assert "대표자명" in record.확인필요사항
    assert "선택미추출" in record.확인필요사항


def test_processed_store_deduplicates_by_content_hash(tmp_path):
    store_path = tmp_path / "processed_files.json"
    first = tmp_path / "first.pdf"
    duplicate = tmp_path / "renamed.pdf"
    first.write_bytes(b"same document")
    duplicate.write_bytes(b"same document")

    store = ProcessedStore(store_path)
    digest = store.mark(first, status="done", report_path="report.md", note="ok")

    found = store.is_processed(duplicate)
    reloaded = ProcessedStore(store_path).is_processed(duplicate)

    assert found is not None
    assert found.sha256 == digest
    assert found.original_name == "first.pdf"
    assert found.status == "done"
    assert reloaded is not None
    assert reloaded.report_path == "report.md"


def test_privacy_masks_sensitive_customer_fields():
    assert mask_business_number("123-45-67890") == "123-**-***90"
    assert mask_business_number("not-a-number") == "***"
    assert mask_corp_number("110111-1234567") == "110111-*******"
    assert mask_person_name("홍길동") == "홍*동"
    assert mask_person_name("김") == "*"
    assert mask_company_name("가나상사") == "가나**"
    assert mask_address("서울특별시 강남구 테헤란로 1") == "서울특별시 강남구 ***"
    assert mask_address(CONFIRM_NEEDED) == CONFIRM_NEEDED


def test_scan_input_filters_supported_files_and_prioritizes_business_registration(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    business = nested / "사업자등록증.pdf"
    image = tmp_path / "z_receipt.PNG"
    unsupported = tmp_path / "notes.txt"
    business.write_bytes(b"pdf")
    image.write_bytes(b"png")
    unsupported.write_text("skip", encoding="utf-8")

    scanned = scan_input(str(tmp_path))

    assert [item.path for item in scanned] == [
        business.resolve(),
        image.resolve(),
    ]
    assert scanned[0].priority == 0
    assert scanned[0].doc_type_hint == "사업자등록증"
    assert scanned[1].priority == 1
    assert scanned[1].doc_type_hint == "기타서류"


def test_scan_input_rejects_unsupported_single_file(tmp_path):
    file_path = tmp_path / "customer.txt"
    file_path.write_text("unsupported", encoding="utf-8")

    with pytest.raises(ValueError, match="지원하지 않는 확장자"):
        scan_input(str(file_path))

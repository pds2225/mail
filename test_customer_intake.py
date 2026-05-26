import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from customer_intake.clova_ocr_client import OcrImageResult
from customer_intake.extractor import CONFIRM_NEEDED, ExtractedRecord, extract_from_ocr
from customer_intake.processed_store import ProcessedStore
from customer_intake.sheets_writer import SheetsWriter


def _ocr_result(*, fields=None, lines=None):
    return OcrImageResult(
        name="test",
        infer_result="SUCCESS",
        fields=fields or [],
        lines=lines or [],
        raw={},
    )


def _record(**overrides):
    defaults = {
        "고객사명": "주식회사 테스트",
        "대표자명": "홍길동",
        "사업자등록번호": "123-45-67890",
        "법인등록번호": "110111-1234567",
        "사업장주소": "서울시 중구 테스트로 1",
        "개업일": "2026-05-26",
        "업태": "제조업",
        "종목": "화장품",
        "과세유형": "일반과세자",
        "서류종류": "사업자등록증",
        "파일명": "사업자등록증.pdf",
        "파일경로": "/tmp/사업자등록증.pdf",
        "추출일시": "2026-05-26 10:00:00",
        "확인상태": "추출완료",
        "확인필요사항": "",
    }
    defaults.update(overrides)
    return ExtractedRecord(**defaults)


def test_extract_from_ocr_normalizes_structured_fields(tmp_path):
    ocr = _ocr_result(
        fields=[
            {"name": "companyName", "inferText": "주식회사 테스트"},
            {"name": "repName", "inferText": "홍길동"},
            {"name": "registerNumber", "inferText": "123 45 67890"},
            {"name": "corpRegisterNumber", "inferText": "1101111234567"},
            {"name": "address", "inferText": "서울시 중구 테스트로 1"},
            {"name": "openDate", "inferText": "2026년 5월 6일"},
            {"name": "bizType", "inferText": "제조업"},
            {"name": "bizItem", "inferText": "화장품"},
            {"name": "taxType", "inferText": "일반과세자"},
        ],
        lines=[
            "사업자등록번호: 999-99-99999",
            "개업일: 2000.01.01",
        ],
    )

    record = extract_from_ocr(
        ocr,
        file_path=tmp_path / "사업자등록증.pdf",
        doc_type="사업자등록증",
    )

    assert record.사업자등록번호 == "123-45-67890"
    assert record.법인등록번호 == "110111-1234567"
    assert record.개업일 == "2026-05-06"
    assert record.확인상태 == "추출완료"
    assert record.확인필요사항 == ""


def test_extract_from_ocr_marks_missing_required_fields(tmp_path):
    ocr = _ocr_result(lines=["사업자등록번호: 123-45-67890"])

    record = extract_from_ocr(
        ocr,
        file_path=tmp_path / "통장사본.pdf",
        doc_type="기타서류",
    )

    assert record.사업자등록번호 == "123-45-67890"
    assert record.고객사명 == CONFIRM_NEEDED
    assert record.확인상태 == CONFIRM_NEEDED
    assert "필수미추출: 고객사명" in record.확인필요사항
    assert "선택미추출: 법인등록번호, 과세유형" in record.확인필요사항


def test_sheets_writer_dry_run_skips_duplicate_master_rows_in_batch():
    writer = SheetsWriter(dry_run=True)
    records = [
        _record(고객사명="주식회사 테스트", 사업자등록번호="123-45-67890"),
        _record(
            고객사명="주식회사 테스트 지점",
            사업자등록번호="1234567890",
            파일명="통장사본.pdf",
            서류종류="기타서류",
        ),
    ]

    result = writer.write_batch(
        records,
        input_path="/tmp/inbox",
        report_path="/tmp/report.md",
        errors=[],
    )

    assert result.master_inserted == 1
    assert result.master_skipped == 1
    assert result.documents_inserted == 2
    assert result.preview is not None
    assert len(result.preview.master_rows) == 1
    assert len(result.preview.document_rows) == 2
    assert result.preview.skipped_master_biz_nos == ["1234567890"]


def test_processed_store_dedupes_files_by_content_hash(tmp_path):
    first = tmp_path / "사업자등록증.pdf"
    renamed = tmp_path / "renamed.pdf"
    store_path = tmp_path / "processed_files.json"
    first.write_bytes(b"same document bytes")
    renamed.write_bytes(b"same document bytes")

    store = ProcessedStore(store_path)
    store.mark(first, status="done", report_path="/tmp/report.md")

    duplicate = ProcessedStore(store_path).is_processed(renamed)

    assert duplicate is not None
    assert duplicate.original_name == "사업자등록증.pdf"
    assert duplicate.status == "done"

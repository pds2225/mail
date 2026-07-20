"""field 즉효픽스 회귀 가드 — 지원유형 매핑 확장 + 수시모집 상시판정.

field 헌터(④)가 발굴한 '그외 미분류' 축소 픽스. ★게이트 중립(ALL_SUPPORT_TYPES 불변)이라
그룹 매칭(발송량)은 변하지 않고 표시 정확도만 오른다 — recall 무손상 확인.
단독 foreground: python -m pytest test_field_quickfixes.py -q
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monitor  # noqa: E402


def test_support_type_new_keywords_existing_buckets():
    """전시회·수출·기술지원 등이 '그외'가 아닌 기존 버킷으로 분류(표시 완성)."""
    assert monitor.classify_support_type({"title": "글로벌 전시회(IFA) 참가기업 모집"}) == ["지원금/바우처"]
    assert monitor.classify_support_type({"title": "베트남 엑스포 출품지원 기업 모집"}) == ["지원금/바우처"]
    assert monitor.classify_support_type({"title": "중소기업 기술지원단 참여기업 모집"}) == ["컨설팅·교육·상담"]
    assert monitor.classify_support_type({"title": "소상공인 신용대출 융자 지원"}) == ["지원금/바우처"]


def test_all_support_types_unchanged_gate_neutral():
    """★게이트 중립 보장: 신규 버킷을 만들지 않아 ALL_SUPPORT_TYPES 는 3버킷+그외 그대로."""
    assert set(monitor.ALL_SUPPORT_TYPES) == {"투자", "지원금/바우처", "컨설팅·교육·상담", "그외"}


def test_susi_recruit_open():
    """'수시모집' 은 상시(open) 로 판정 — 마감불명이던 것 복구(recall)."""
    it = {"title": "1인 기업실 사용기업 수시모집 공고", "posted_date": "2026-07-01", "description": ""}
    assert monitor.classify_deadline_status(it) == "open"


def test_plain_notice_still_그외():
    """지원유형 신호 없는 공고는 여전히 '그외'(과잉 분류 방지)."""
    assert monitor.classify_support_type({"title": "2026년 정기총회 개최 안내"}) == ["그외"]

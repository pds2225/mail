"""accuracy_eval 측정엔진 단위 테스트 — region_FP 판정 로직.

region_FP = matched 공고의 region_field(정답 지역)가 기업 지역도 전국/수도권도 아닌 타지역.
전수 측정(main)은 raw store·시간 의존이라 수동 실행으로 두고, 여기선 판정 로직만 가드한다.
self-contained (네트워크/raw 불필요).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import accuracy_eval as ae  # noqa: E402


def test_region_fp_true_on_other_region():
    """서울 기업에 '대구' 공고가 추천되면 region_FP (타지역 오추천)."""
    assert ae._is_region_fp("대구광역시", "서울") is True
    assert ae._is_region_fp("경상북도", "인천") is True


def test_region_fp_false_on_own_region():
    """기업 지역과 일치하면 정상(FP 아님)."""
    assert ae._is_region_fp("서울특별시", "서울") is False
    assert ae._is_region_fp("인천광역시", "인천") is False


def test_region_fp_false_on_nationwide_or_metro():
    """전국·수도권·빈값은 타지역 아님(판단 보류 = FP 아님)."""
    assert ae._is_region_fp("전국", "서울") is False
    assert ae._is_region_fp("수도권", "부산") is False
    assert ae._is_region_fp("", "서울") is False
    assert ae._is_region_fp(None, "서울") is False

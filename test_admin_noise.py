"""원본전체 메일의 '비지원 행정고지' 노이즈 제외 회귀 테스트 (네트워크/SMTP 없음).

사용자가 실제 받은 [원본전체] 메일에 김포·남양주시청의 주민등록·CCTV·행정예고 등
지원사업과 무관한 행정고지가 섞여 나온 문제를 고정한다.
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

import monitor as m  # noqa: E402


def _it(title, desc=""):
    return {"id": "x", "title": title, "description": desc}


# 사용자가 실제로 받은 오포함 항목 — 전부 제외되어야 한다
REAL_NOISE = [
    "주민등록 무단전출자 최고 공고(정0근)",
    "주민등록증 신규발급대상자 발급 통지 반송 공고(2009년 5월생)",
    "은빛공원 방범용 CCTV 설치 행정예고",
]

# 추가 행정고지(같은 류) — 제외되어야 한다
MORE_NOISE = [
    "2026년 제1회 추가경정예산 입찰공고",
    "도시관리계획 변경 결정 의견청취 공고",
    "지방세 체납자 명단 공개",
    "공유재산 매각공고",
]

# 진짜 지원사업 공고 — 절대 제외되면 안 된다(recall 보호)
REAL_GRANTS = [
    "2026년 수출바우처 지원사업 공고",
    "인천 중소기업 스마트공장 구축 지원사업 모집공고",
    "창업기업 사업화 자금 지원 안내",
    "여성기업 해외 판로개척 마케팅 지원사업",
    "혁신바우처 참여기업 모집",
    # 행정 신호+지원 신호 동시 → 보수적으로 유지(recall 우선)
    "창업기업 지원 공유재산 무상임대 공모",
]


def test_real_user_noise_is_filtered():
    for t in REAL_NOISE:
        assert m.is_admin_noise(_it(t)) is True, f"제외돼야 함: {t}"


def test_more_admin_noise_is_filtered():
    for t in MORE_NOISE:
        assert m.is_admin_noise(_it(t)) is True, f"제외돼야 함: {t}"


def test_real_grants_are_kept():
    for t in REAL_GRANTS:
        assert m.is_admin_noise(_it(t)) is False, f"유지돼야 함(지원공고): {t}"


def test_no_admin_signal_is_kept():
    """행정 신호가 전혀 없는 일반 항목은 영향 없음(필터 무관)."""
    assert m.is_admin_noise(_it("2026 해외전시회 참가기업 모집")) is False
    assert m.is_admin_noise(_it("아무 제목")) is False


def test_execute_monitor_excludes_noise_from_raw_all(monkeypatch):
    """파이프라인 통합: 행정고지가 섞여도 원본전체 발송대상에서 빠진다(실발송 없음)."""
    items = [
        {"id": "n1", "title": REAL_NOISE[0], "description": "", "link": "https://x/1",
         "author": "김포시청", "deadline": "", "source": "김포시청",
         "posted_date": "", "is_aggregator": False},
        {"id": "n2", "title": REAL_NOISE[2], "description": "", "link": "https://x/2",
         "author": "남양주시청", "deadline": "", "source": "남양주시청",
         "posted_date": "", "is_aggregator": False},
        {"id": "g1", "title": REAL_GRANTS[0], "description": "전국 중소기업 대상 신청접수",
         "link": "https://x/3", "author": "기관", "deadline": "2099-12-31",
         "source": "기업마당", "posted_date": "", "is_aggregator": False},
    ]
    monkeypatch.setattr(m, "fetch_all", lambda sites, **kw: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **kw: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{"id": "g", "name": "t", "active": True,
                                                    "or_keywords": ["수출바우처"], "recipients": []}])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": False, "raw_all_enabled": True,
        "raw_all_recipients": ["ekth3691@gmail.com"], "company_match_enabled": False,
    })
    sent = []
    monkeypatch.setattr(m, "send_to_list",
                        lambda subject, body, recipients: sent.append((subject, body)))

    res = m.execute_monitor(allow_send=True, include_raw_all=True, persist_seen=False)
    assert res["ok"]
    raw = [s for s in sent if s[0].startswith("[원본전체]")]
    assert raw, "원본전체 메일이 구성돼야 함"
    subject, body = raw[0]
    # 행정고지 제목은 본문에 없어야, 지원공고 제목은 있어야 한다
    assert "주민등록" not in body and "CCTV" not in body and "행정예고" not in body
    assert "수출바우처" in body
    assert "행정고지 2건 제외" in body

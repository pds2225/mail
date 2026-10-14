"""2026-10-14 03:45 KST 실발송(run #265, main 20cd926) 메일 원문 기반 회귀(MAIL-036)."""
import gzip
import json
from datetime import date, datetime

import monitor
from scripts import mask_raw_emails as mre

TODAY = date(2026, 10, 14)


def _item(title, deadline="", **kw):
    return {"id": kw.pop("id", title[:12]), "title": title, "deadline": deadline, "description": "",
            "link": kw.pop("link", "https://example.org/n"), **kw}


# 1) 📍 섹션
def test_region_unknown_hides_unknown_org_and_cleans_titles():
    items = [
        _item("사업화 김제 청년 아지트 E :DA(이다) 「오늘은 로그아웃」 1차-컬러 테라피",
              link="https://www.jbci.or.kr/sub/business_1_view.html?id=6855"),
        _item("사업화 2026년 2차 중소기업 정보보호 지원 사업 수요기업 모집 공고",
              link="https://www.jbci.or.kr/sub/business_1_view.html?id=6849"),
        _item("2026년 재난안전기업 사업화 역량강화 컨설팅 참여..", link="http://jef.or.kr/bbs/board.php?wr_id=255"),
        _item("2026년 중소기업 기술분쟁 소송보험 지원사업 공고", description="상시접수", author="중소벤처기업부"),
    ]
    items[3]["description"] = "상시접수"
    txt = monitor.render_region_unknown(items, limit=10, total_count=86)
    assert "기관: 미기재" not in txt
    assert "▸ 김제 청년 아지트" in txt and "▸ 2026년 2차 중소기업 정보보호" in txt
    assert "▸ 2026년 재난안전기업 사업화 역량강화 컨설팅 참여\n" in txt
    assert "  기관: 중소벤처기업부 | 마감: 상시" in txt
    assert "  마감: 확인필요" in txt


def test_category_prefix_only_for_listed_source():
    assert monitor.clean_item_title(_item("사업화 역량강화 컨설팅", link="https://other.example/x")) == "사업화 역량강화 컨설팅"


# 2) 제목 회차 = 실제 발송 시각
def test_send_time_label():
    kst = monitor.KST
    assert monitor._send_date_label(datetime(2026, 10, 14, 3, 46, tzinfo=kst)) == "10/14 오전"
    assert monitor._send_date_label(datetime(2026, 10, 13, 13, 38, tzinfo=kst)) == "10/13 오후"
    assert monitor._send_date_label(datetime(2026, 10, 13, 18, 40, tzinfo=kst)) == "10/13 저녁"


# 3) 제목 장식
def test_title_decorations_removed():
    t = "★ 「하반기 AI 앵커기업 현장방문 프로그램」 참가기업 모집(~10/16) – 첨단 AI 팩토리 견학 –"
    assert monitor.clean_mail_title(t) == "「하반기 AI 앵커기업 현장방문 프로그램」 참가기업 모집(~10/16)"
    for p in ("☆", "▶", "■", "※"):
        assert monitor.clean_mail_title(f"{p} 2026년 수출바우처 모집") == "2026년 수출바우처 모집"
    assert monitor.clean_mail_title("2026 AI-데이터 바우처 공급기업 모집") == "2026 AI-데이터 바우처 공급기업 모집"


# 4) 집중 모니터링
def test_watchlist_body_format():
    items = [
        _item("2026년 사회서비스제공기관 전문 경영 컨설팅 컨설턴트 모집(2차) 재공고 N새로운 게시글",
              link="https://jeju.pass.or.kr/notice-board/view/id/3003"),
        _item("2026년 수출바우처 모집", "2026-10-20"),
        _item("2025년 지난 공고", "2025-09-03"),
    ]
    body = monitor.render_watchlist_body(items, today=TODAY)
    assert "[1] 2026년 사회서비스제공기관 전문 경영 컨설팅 컨설턴트 모집(2차) 재공고\n  마감: 확인필요" in body
    assert "[2] 2026년 수출바우처 모집\n  마감: 10/20 (D-6)" in body
    assert "지난 공고" not in body and "미기재" not in body and "새로운 게시글" not in body


# 5) 아티팩트
def test_filter_trace_written(tmp_path, monkeypatch):
    from mail_core.operations import filter_trace
    monkeypatch.setattr(filter_trace, "LOGS_DIR", tmp_path)
    diag = {"included": [{"id": "a", "title": "t", "is_relevant": True, "region_status": "eligible"}],
            "review": [], "region_unknown": [], "excluded": [
                {"id": "b", "title": "u", "is_relevant": False, "exclude_reason_codes": ["KW_MISS"]}]}
    monitor._write_filter_traces(diag, group_id="grp_x", run_id="R1")
    files = list(tmp_path.glob("filter_trace_*.jsonl"))
    rows = [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines()]
    assert {r["bucket"] for r in rows} == {"included", "excluded"}
    assert "KW_MISS" in json.dumps(rows)


def test_mask_raw_emails(tmp_path):
    src = tmp_path / "raw" / "2026-10-14" / "notices" / "n1"
    src.mkdir(parents=True)
    (src / "meta.json").write_text('{"contact": "staff@example.test"}', encoding="utf-8")
    (src / "detail.html.gz").write_bytes(gzip.compress("문의: help@example.test, a%40example.test".encode()))
    dst = tmp_path / "out" / "raw"
    mre.mask_tree(tmp_path / "raw", dst)
    meta = (dst / "2026-10-14/notices/n1/meta.json").read_text(encoding="utf-8")
    html = gzip.decompress((dst / "2026-10-14/notices/n1/detail.html.gz").read_bytes()).decode()
    assert "@" not in meta and "example.test" not in html
    assert (src / "meta.json").read_text(encoding="utf-8").count("@") == 1  # 원본 불변


def test_workflow_artifact_path_is_relative_single_dir():
    import yaml
    wf = yaml.safe_load(open(".github/workflows/monitor.yml", encoding="utf-8"))
    steps = [s for j in wf["jobs"].values() for s in j.get("steps", [])]
    up = [s for s in steps if str(s.get("with", {}).get("name", "")).startswith("run-records")][0]
    assert up["with"]["path"].strip() == "var/logs/run_records/"
    assert up["with"]["retention-days"] == 30
    assert ".." not in up["with"]["path"] and not up["with"]["path"].startswith("/")


# 6) 전시회·박람회 → 기타
def test_exhibition_recruitment_is_gita():
    for t in ("MWC2027-4YFN 서울기업관 서울소재 참가기업 모집 공고",
              "CES 2027 통합한국관 참가기업 모집", "2026 K-뷰티 박람회 부스 참가기업 모집"):
        assert monitor._mail_support_cell(_item(t, _types=["바우처"], support_field="세계 3대 IT 전시회")) == "기타", t
    assert monitor._mail_support_cell(_item("2026년 2차 일반 물류바우처 사업 참여기업 모집 공고")) == "바우처"

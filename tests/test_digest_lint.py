"""MAIL-035 발송 전 digest lint · 기록 dump 회귀(run #263/#264 실메일 문자열)."""
import json
from datetime import datetime

import monitor
from mail_core.delivery import digest_lint as dl

NOW = datetime(2026, 10, 13, 12, 57, tzinfo=monitor.KST)

# run #263 실메일 본문 일부(구 렌더러 출력 그대로)
BODY_263 = """그룹: 예비창업 AI (전국·서울강조)
전체 2622건 → 그룹 매칭 7건

📋 지원사업 공고 목록

■ 바우처 (2건)
모집중(2026-207호) 2026년 강원 미래모빌리티 기업지원 프로그램 모집 통합공고
   💰 완료 제 목 :
   전국 · 10/13 (D-0)
2026년 서울테크노파크-KISTI(한국과학기술정보연구원) 기술협력 파트너링 데이 참여기업 모집(~9.30)
   💰 기업지원공고 전체
   서울 · 9/30 (D+13)

■ 판로·실증 (1건)
[교육안내] 2026년 광명상생플랫폼 운영지원사업 온라인 마케팅 2차 교육 참석자 모집
   💰 공지사항 공지사항 HOME 공고ㆍ안내 공지사항 공지사항 지역기술혁신의…
   서울 · 확인필요
────────────────────────────────
🙋 이 추천, 맞았나요? — 아래 링크를 누르면 메일 작성창이 자동으로 열립니다.
"""


def test_lint_flags_real_263_problems():
    r = dl.lint_digest("[예비창업 AI (전국·서울강조)] 7건 (10/13 저녁)", BODY_263, is_junk=monitor.is_support_junk)
    codes = set(r["codes"])
    assert {"EXPIRED", "JUNK_SUPPORT", "SUBJECT_COUNT", "HEADER_COUNT"} <= codes
    assert r["cards"] == 3 and not r["ok"]
    assert "FOOTER_AS_CARD" not in codes  # 현 파서는 꼬리말에서 멈춘다


def test_lint_section_count_and_footer_card_detection():
    body = "📋 지원사업 공고 목록\n\n■ 기타 (6건)\n제목A\n   서울 · 10/20 (D-7)\n"
    r = dl.lint_digest("[g] 1건 (x)", body, is_junk=monitor.is_support_junk)
    assert "SECTION_COUNT" in r["codes"] and "SUBJECT_COUNT" not in r["codes"]
    # 파서가 꼬리말을 카드로 잡는 회귀를 흉내(구 파서 출력 rows)
    orig = dl.parse_plain_table
    dl.parse_plain_table = lambda b: ("", [{"공고": "────────", "마감": "확인필요", "지원": "기타"}], "")
    try:
        assert "FOOTER_AS_CARD" in dl.lint_digest("[g] 1건", "📋 지원사업 공고 목록")["codes"]
    finally:
        dl.parse_plain_table = orig


def test_unknown_share_warning_only():
    body = "📋 지원사업 공고 목록\n\n■ 기타 (3건)\n" + "".join(f"제목{i}\n   확인필요\n" for i in range(3))
    r = dl.lint_digest("[g] 3건", body)
    assert r["codes"] == ["UNKNOWN_SHARE"] and r["ok"]  # 경고일 뿐 오류 아님


def test_strip_junk_support_lines_keeps_amount():
    body = "제목\n   💰 기업지원공고 전체\n제목2\n   💰 최대 100만원\n"
    out = dl.strip_junk_support_lines(body, monitor.is_support_junk)
    assert "기업지원공고 전체" not in out and "최대 100만원" in out


def test_redact_removes_tokens_and_emails():
    t = ("mailto:owner%40example.test?subject=%5BMAIL-FB%5D%20O%20ema_56db4de359808ba02cca%201791838601.04943702e2838d44"
         " 문의 member1@example.test [MAIL-FB] X abc.123")
    out = dl.redact(t)
    assert "@" not in out and "MAIL-FB" not in out and "04943702e2838d44" not in out


def _item(title, deadline, **kw):
    return {"id": kw.pop("id", title[:10]), "title": title, "deadline": deadline, "description": "",
            "link": "https://example.org/x", **kw}


def test_lint_group_mail_autofix_and_dump(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "DIGEST_DUMP_DIR", tmp_path)
    alerts = []
    monkeypatch.setattr(monitor, "alert_ntfy", lambda *a, **k: alerts.append(a))
    live = _item("2026년 강원 미래모빌리티 기업지원 프로그램 모집 통합공고", "2026-10-13", id="live")
    dead = _item("2026년 서울테크노파크-KISTI 기술협력 파트너링 데이 참여기업 모집(~9.30)", "", id="dead",
                 posted_date="2026-10-08")
    group = {"id": "grp_prestartup_ai", "name": "예비창업 AI (전국·서울강조)",
             "recipients": ["member1@example.test"]}

    def build(gi, ri):
        return monitor._build_group_mail_content(
            group=group, g_items=gi, ru_mail_items=ri, ru_items=ri, ru_limit=10, filtered_new=gi,
            window_label="w", days_back=3, date_str="10/13 오전", now=NOW)

    # 구 렌더처럼 만료 카드·틀린 건수가 섞인 본문을 강제로 넣는다
    bad = {"subject": "[예비창업 AI (전국·서울강조)] 2건 (10/13 오전)", "body": BODY_263, "voucher_items": []}
    content, blocked = monitor._lint_group_mail(group=group, content=bad, g_items=[live, dead], ru_mail_items=[],
                                                rebuild=build, now=NOW, run_id="RUN1")
    assert not blocked
    assert content["subject"] == "[예비창업 AI (전국·서울강조)] 1건 (10/13 오전)"
    assert "파트너링" not in content["body"].split("🙋")[0]
    assert alerts  # 경고 발송(ntfy)
    dump = json.loads((tmp_path / "RUN1" / "grp_prestartup_ai.json").read_text(encoding="utf-8"))
    raw = json.dumps(dump, ensure_ascii=False)
    assert "@" not in raw and "member1" not in raw and "MAIL-FB" not in raw
    assert dump["recipients_masked"] == ["me*****(example.test)"]
    assert dump["lint"]["ok"] and dump["auto_fixes"]
    assert [i["id"] for i in dump["items_shown"]] == ["live"]
    assert dump["items_shown"][0]["card_deadline"] == "10/13 (D-0)"
    assert "<html>" in dump["html"]


def test_blocking_flag_default_off_and_on(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "DIGEST_DUMP_DIR", tmp_path)
    monkeypatch.setattr(monitor, "alert_ntfy", lambda *a, **k: None)
    monkeypatch.delenv("MAIL_DIGEST_LINT_BLOCKING", raising=False)
    group = {"id": "g", "name": "g"}
    bad = {"subject": "[g] 1건", "body": "📋 지원사업 공고 목록\n\n■ 기타 (1건)\n제목\n   9/30 (D+13)\n",
           "voucher_items": []}
    same = lambda gi, ri: bad  # noqa: E731 — 재생성해도 못 고치는 경우
    _c, blocked = monitor._lint_group_mail(group=group, content=bad, g_items=[], ru_mail_items=[],
                                           rebuild=same, now=NOW, run_id="R")
    assert blocked is False
    monkeypatch.setenv("MAIL_DIGEST_LINT_BLOCKING", "1")
    _c, blocked = monitor._lint_group_mail(group=group, content=bad, g_items=[], ru_mail_items=[],
                                           rebuild=same, now=NOW, run_id="R")
    assert blocked is True


def test_lint_failure_is_fail_open(monkeypatch):
    monkeypatch.setattr(dl, "lint_digest", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    c = {"subject": "s", "body": "b", "voucher_items": []}
    assert monitor._lint_group_mail(group={}, content=c, g_items=[], ru_mail_items=[], rebuild=None,
                                    now=NOW, run_id="R") == (c, False)

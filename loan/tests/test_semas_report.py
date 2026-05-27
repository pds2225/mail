from pathlib import Path

from loan.semas.collector import mask_email, run_scan


SAMPLE_HTML = """
<html><body>
  <section>
    <a href="/ols/notice/1">2026년 소상공인 정책자금 직접대출 접수 안내</a>
    <span>2026.05.26</span>
  </section>
  <section>
    <a href="/ols/notice/2">재도전특별자금 재창업 신청 마감 안내</a>
    <span>2026.05.25</span>
  </section>
  <p>정책자금 온라인신청 접수 중이며 예산소진 시 마감될 수 있습니다.</p>
</body></html>
"""


def _fetcher(url: str, timeout: float):
    return {"ok": True, "status_code": 200, "html": SAMPLE_HTML, "error": ""}


def test_report_generation_and_send_email_false_blocks_mail(tmp_path, monkeypatch):
    report_path = tmp_path / "semas_loan_scan.md"
    seen_path = tmp_path / "semas_seen_notices.json"
    monkeypatch.setenv("SEMAS_LOAN_URL", "https://example.com/semas")
    monkeypatch.setenv("ALLOW_SEND_EMAIL", "true")
    calls = []

    result = run_scan(
        run_mode="dry-run",
        send_email_requested=False,
        fetcher=_fetcher,
        mail_sender=lambda subject, body, recipients: calls.append((subject, body, recipients)),
        report_path=report_path,
        seen_path=seen_path,
    )

    assert result["email_status"] == "미실행"
    assert calls == []
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "# 소진공 정책자금 공지 점검 리포트" in report
    assert "2026년 소상공인 정책자금 직접대출 접수 안내" in report


def test_allow_send_email_false_blocks_mail(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMAS_LOAN_URL", "https://example.com/semas")
    monkeypatch.setenv("ALLOW_SEND_EMAIL", "false")
    calls = []

    result = run_scan(
        run_mode="dry-run",
        send_email_requested=True,
        fetcher=_fetcher,
        mail_sender=lambda subject, body, recipients: calls.append((subject, body, recipients)),
        report_path=tmp_path / "report.md",
        seen_path=tmp_path / "seen.json",
    )

    assert result["email_status"] == "미실행"
    assert "ALLOW_SEND_EMAIL" in result["email_reason"]
    assert calls == []


def test_missing_smtp_does_not_abort_report(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMAS_LOAN_URL", "https://example.com/semas")
    monkeypatch.setenv("ALLOW_SEND_EMAIL", "true")
    monkeypatch.setenv("MAIL_TO", "loan-recipient@example.test")  # pragma: allowlist secret
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)  # pragma: allowlist secret
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)

    result = run_scan(
        run_mode="dry-run",
        send_email_requested=True,
        fetcher=_fetcher,
        report_path=tmp_path / "report.md",
        seen_path=tmp_path / "seen.json",
    )

    assert result["email_status"] == "실패"
    assert "GMAIL_ADDRESS" in result["email_reason"]
    assert Path(result["report_path"]).exists()


def test_external_site_failure_still_generates_report(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMAS_LOAN_URL", "https://example.com/semas")

    def failing_fetcher(url: str, timeout: float):
        return {"ok": False, "status_code": None, "html": "", "error": "timeout"}

    result = run_scan(
        run_mode="dry-run",
        send_email_requested=False,
        fetcher=failing_fetcher,
        report_path=tmp_path / "report.md",
        seen_path=tmp_path / "seen.json",
    )

    assert result["connection_result"] == "불가"
    assert result["http_status"] == "미확인"
    assert Path(result["report_path"]).read_text(encoding="utf-8").find("timeout") != -1


def test_mask_email_hides_local_part():
    assert mask_email("loan-recipient@example.test") == "lo************@example.test"


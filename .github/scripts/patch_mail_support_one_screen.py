from pathlib import Path

monitor = Path("monitor.py")
test = Path("tests/test_mail_digest_mobile.py")

text = monitor.read_text(encoding="utf-8")
old = "MAIL_SUPPORT_BLURB_LIMIT = 480"
new = "MAIL_SUPPORT_BLURB_LIMIT = 160"
if old not in text:
    raise RuntimeError("MAIL_SUPPORT_BLURB_LIMIT=480 anchor not found")
text = text.replace(old, new, 1)
text = text.replace(
    '"""구조화 지원내용을 우선하고, 없으면 상세본문을 모바일 길이로 정제한다."""',
    '"""구조화 지원내용을 우선하고, 모바일 한 화면 기준 160자로 제한한다."""',
    1,
)
monitor.write_text(text, encoding="utf-8")

test_text = test.read_text(encoding="utf-8")
if "assert len(text) <= 482" not in test_text:
    raise RuntimeError("existing support blurb length assertion not found")
test_text = test_text.replace("assert len(text) <= 482", "assert len(text) <= 162", 1)

extra_test = '''\n\ndef test_mail_support_blurb_long_text_stays_within_one_mobile_screen():\n    item = _item(\n        support_field=(\n            "사업화 자금, 시제품 제작, 전문가 컨설팅, 국내외 판로개척, "\n            "홍보물 제작, 인증 취득, 시험분석 및 후속 투자연계를 지원합니다. " * 12\n        )\n    )\n    text = m._mail_support_blurb(item)\n    assert len(text) <= 162\n    assert text.endswith(" …")\n    body = m.fallback_body([item])\n    support_line = next(line for line in body.splitlines() if line.startswith("• 지원내용:"))\n    assert len(support_line.removeprefix("• 지원내용: ")) <= 162\n'''
if "test_mail_support_blurb_long_text_stays_within_one_mobile_screen" not in test_text:
    test_text += extra_test

test.write_text(test_text, encoding="utf-8")
print("patched support blurb limit to 160 chars")

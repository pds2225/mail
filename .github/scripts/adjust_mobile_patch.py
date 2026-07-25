from pathlib import Path

path = Path('.github/scripts/patch_mail_digest_mobile.py')
text = path.read_text(encoding='utf-8')

text = text.replace(
    '''            title = _mail_clean_text(it.get("title") or "(제목없음)", limit=160)\n            author = _mail_clean_text(it.get("author") or "미기재", limit=80)\n            types = " · ".join(str(v) for v in (it.get("_types") or ["미분류"])[:2])\n            region = _region_label(it)\n            lines.extend([''',
    '''            title = strip_title_badges(_mail_clean_text(it.get("title") or "(제목없음)", limit=160))\n            author = _mail_clean_text(it.get("author") or "미기재", limit=80)\n            types = " · ".join(str(v) for v in (it.get("_types") or ["미분류"])[:2])\n            region = _region_label(it)\n            display_region = "제한 없음" if region.endswith("전체") else region\n            lines.extend([''',
)
text = text.replace(
    '''                f"• 마감: {resolve_item_deadline(it) or '미기재'} | 지역: {region}",''',
    '''                f"• 마감: {resolve_item_deadline(it) or '미기재'} | 지역: {display_region}",''',
)
text = text.replace('os.environ.setdefault("MONITOR_NO_FEEDBACK_LINKS", "1")\n', '')
text = text.replace(
    'assert "📌 2026년 AI 사업화 지원 & 참여기업 모집 새로운게시글" in body',
    'assert "📌 2026년 AI 사업화 지원 & 참여기업 모집" in body',
)
text = text.replace(
    'f"📍 지역 확인 필요 — 메일 표시 {len(shown)}건 / 전체 {total}건",',
    'f"📍 지역 미상 — 확인 필요 (메일 표시 {len(shown)}건 / 전체 {total}건)",',
)

required = [
    'display_region = "제한 없음" if region.endswith("전체") else region',
    'title = strip_title_badges(',
    '지역 미상 — 확인 필요',
]
missing = [marker for marker in required if marker not in text]
if missing:
    raise RuntimeError(f'adjust markers missing: {missing}')

path.write_text(text, encoding='utf-8')
print('adjusted mobile patch script')

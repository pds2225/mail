# 공고첨부 EXE (선택, Python 없이)

비개발자 기본 경로는 Python 원클릭입니다.

1. `처음설치_한번만.cmd` (처음 1회 — Python 없으면 winget으로 설치 시도)
2. `지원사업 공고첨부_받기.cmd` (평소)

`.exe` 는 저장소에 올리지 않습니다(용량·보안). 개발자가 Windows에서 만들 때만 씁니다.

```text
pyinstaller --noconfirm --clean --distpath dist --workpath build scripts/attach_downloader.spec
```

받는 사람:

1. `지원사업_공고첨부_받기.exe` 더블클릭
2. 공고 상세 페이지 주소 붙여넣기 → Enter
3. 첨부는 바탕화면 `지원사업_공고첨부` 폴더에 저장

Windows가 막으면: 추가 정보 → 실행. 메일은 보내지 않습니다.

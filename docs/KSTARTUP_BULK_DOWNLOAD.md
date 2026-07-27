# K-Startup 지정 공고 첨부파일 일괄 다운로드

## 목적

`config/targets/kstartup_20260623.txt`에 적힌 공고 제목만 K-Startup 모집중 목록에서 찾아 공고별 첨부파일을 내려받는다.

## 실행 전 준비

```powershell
cd D:\mail
python -m pip install -r requirements.txt
```

## 1단계: 다운로드 대상 확인만 하기

```powershell
cd D:\mail
python scripts\download_kstartup_targets.py --dry-run
```

결과:

```text
D:\mail\downloads\kstartup\20260623\download_manifest_dry_run.json
```

`DRY_RUN`이면 다운로드 예정 파일이다. `NOT_FOUND`는 K-Startup 현재 목록에서 제목 매칭 실패, `NO_ATTACHMENTS`는 상세페이지에서 첨부파일 후보를 찾지 못한 경우다.

## 2단계: 실제 다운로드

```powershell
cd D:\mail
python scripts\download_kstartup_targets.py
```

저장 위치:

```text
D:\mail\downloads\kstartup\20260623\공고명\첨부파일
```

전체 결과 로그:

```text
D:\mail\downloads\kstartup\20260623\download_manifest.json
```

## 입력 파일

```text
config/targets/kstartup_20260623.txt
```

한 줄에 공고 제목 1개씩 적는다. 제목이 완전히 같지 않아도 유사도 0.72 이상이면 매칭한다.

## 주의사항

- 이 스크립트는 메일을 보내지 않는다.
- `monitor.py`의 K-Startup 수집기를 재사용한다.
- 현재 수집기는 K-Startup 공공(PBC010)·민간(PBC020) 목록을 각각 `viewCount=100`으로 읽는다.
- K-Startup이 첨부파일 다운로드를 자바스크립트 세션 방식으로 숨기는 경우 일부 파일은 `NO_ATTACHMENTS` 또는 `DOWNLOAD_FAILED`가 될 수 있다.
- 실패 건은 `download_manifest.json`을 보고 수동 확인하거나 Playwright 클릭 방식 보강이 필요하다.

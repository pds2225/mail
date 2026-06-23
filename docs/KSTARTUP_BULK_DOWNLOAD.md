# K-Startup 지정 공고 첨부파일 일괄 다운로드

## 목적

`targets/kstartup_20260623.txt`에 적힌 공고 제목만 K-Startup 모집중 목록에서 찾아 공고별 첨부파일을 내려받는다.

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
targets/kstartup_20260623.txt
```

한 줄에 공고 제목 1개씩 적는다. 제목이 완전히 같지 않아도 유사도 0.72 이상이면 매칭한다.

## 매칭 방식

스크립트는 메일 발송과 분리된 다운로드 도구다. 실행 시 `monitor.py` 임포트에 필요한
환경변수는 더미값으로 채우지만, 실제 메일은 보내지 않는다.

제목 매칭 순서:

1. K-Startup 모집중 목록 공공(`PBC010`)·민간(`PBC020`)을 `--max-pages`만큼 수집한다.
2. 기업마당, SBA/MSS/KOSME 등 고가치 원출처, 전체 모니터링 사이트 풀을 보조 후보로 읽는다.
3. 그래도 못 찾으면 K-Startup 제목 검색을 수행한다.
4. 각 후보는 제목 유사도와 핵심 토큰 겹침으로 재랭킹하며, 기본 임계값은 `--min-score 0.72`다.

보조 후보 풀은 느릴 수 있다. 빠른 재시도나 원인분리에는 다음 옵션을 쓴다.

```powershell
python scripts\download_kstartup_targets.py --dry-run --no-bizinfo
python scripts\download_kstartup_targets.py --dry-run --no-extra-sources
python scripts\download_kstartup_targets.py --dry-run --no-full-monitor
```

`--no-full-monitor`는 가장 빠르지만 K-Startup 밖 원출처에만 남아 있는 공고가 `NOT_FOUND`로
늘어날 수 있다.

## manifest 읽는 법

`download_manifest_dry_run.json` 또는 `download_manifest.json`에는 다음 필드가 남는다.

| 필드 | 의미 |
|------|------|
| `collected_items` | K-Startup 다중 페이지에서 수집한 후보 수 |
| `bizinfo_items` | 기업마당 보조 후보 수 |
| `extra_source_items` | SBA/MSS/KOSME 등 지정 원출처 후보 수 |
| `monitor_items` | 전체 모니터링 사이트 후보 수 |
| `match_source` | 실제 매칭된 풀 (`kstartup`, `bizinfo`, `extra`, `monitor`, `kstartup_search`) |
| `match_score` | 최종 제목 매칭 점수 |

주요 상태값:

| 상태 | 의미 | 다음 조치 |
|------|------|-----------|
| `DRY_RUN` | 저장 예정 첨부파일을 찾음 | 실제 다운로드 실행 |
| `DOWNLOADED` | 첨부파일 저장 완료 | 파일 열람 확인 |
| `NOT_FOUND` | 임계값 이상 제목 후보 없음 | 제목 오타, `--max-pages`, 보조 풀 옵션 확인 |
| `DETAIL_FETCH_FAILED` | 상세페이지 요청 실패 | 네트워크/TLS 또는 상세 URL 확인 |
| `NO_ATTACHMENTS` | 상세/원출처 페이지에서 첨부 후보 없음 | 공고 원문 수동 확인 |
| `DOWNLOAD_FAILED` | 후보 URL 다운로드 실패 | manifest의 `file_url`을 브라우저에서 확인 |

## 주의사항

- 이 스크립트는 메일을 보내지 않는다.
- `monitor.py`의 K-Startup 수집기를 재사용한다.
- 기본값은 K-Startup 공공(PBC010)·민간(PBC020) 목록을 각각 `viewCount=100`, `--max-pages 30`으로 읽는다.
- K-Startup이 첨부파일 다운로드를 자바스크립트 세션 방식으로 숨기는 경우 일부 파일은 `NO_ATTACHMENTS` 또는 `DOWNLOAD_FAILED`가 될 수 있다.
- K-Startup 상세에 원출처/사업안내 링크가 있으면 최대 5개 원출처 페이지에서도 첨부 후보를 찾는다.
- 실패 건은 `download_manifest.json`을 보고 수동 확인하거나 Playwright 클릭 방식 보강이 필요하다.

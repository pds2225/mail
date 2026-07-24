# 원문 저장 (Raw Store) 설계

공고 **누락을 나중에 다시 보기** 위해, 수집 직후 메타와 (가능하면) 상세 HTML을 PC 로컬에 쌓습니다.

## 왜 먼저?

| 순위 | 층 | 역할 |
|------|-----|------|
| 1 | **원문 저장** | “그때 뭐가 왔는지” 증거 · 파서 고친 뒤 **재파싱** |
| 2 | 수집기 | 사이트에서 목록 가져오기 |
| 3 | 메타 파서 | 지역·마감·키워드 판정 |

원문이 없으면 수집기·파서를 고쳐도 **과거 공고는 복구 불가**입니다.

## 폴더 구조

```
D:\mail\data\raw\
  2026-06-24/                    ← 실행일(KST)
    run.json                     ← 이번 실행 요약(건수·시각). 같은 날 여러 번이면 배열로 누적
    notices/
      bizinfo_abc123/            ← 공고 ID (파일명 안전 문자만)
        meta.json                ← 목록 단계 메타 (제목·링크·source·마감 등)
        detail.meta.json         ← 상세 HTML 저장 시 URL·크기
        detail.html.gz           ← 상세 페이지 원문 (gzip, 선택)
```

- **Git에 안 올림** (`.gitignore`의 `data/raw/`)
- **Vercel 서버**에는 디스크가 없으므로 → PC·로컬 실행 전용 (`raw_store_enabled`)

## 무엇을 언제 저장하나

| 시점 | 저장 내용 |
|------|-----------|
| `seen_ids` 통과 **신규 공고**마다 | `meta.json` (가벼움, 전건) |
| K-Startup / NIPA / 수출바우처 **상세 보강** 시 | `detail.html.gz` + `meta.json` 갱신 |
| 목록 페이지 HTML | v1 미포함 (v2: 수집 0건·실패 사이트만) |

## 보관 기간

| 설정 | 기본값 | 의미 |
|------|--------|------|
| `raw_store_retention_days` | **30** | 30일 지난 `YYYY-MM-DD` 폴더 자동 삭제 |
| `raw_store_max_detail_bytes` | **800000** (~800KB) | 상세 HTML 1건 상한 (초과 시 잘림) |

30일 × 신규 ~2000건/일 × meta ~2KB ≈ **수백 MB** 수준 (상세 HTML은 `MAX_DETAIL_ENRICH` 건수만큼만).

## config/settings.json

```json
{
  "raw_store_enabled": true,
  "raw_store_retention_days": 30,
  "raw_store_max_detail_bytes": 800000,
  "raw_store_gzip_detail": true
}
```

선택: `"raw_store_dir": "D:\\mail\\data\\raw"` (기본값과 같으면 생략 가능)

## 용량·디스크

- **meta만**: 하루 수천 건 가능
- **detail**: `MAX_DETAIL_ENRICH`(기본 40) × gzip HTML → 하루 수 MB~수십 MB
- 디스크 부족 시 `retention_days`를 14로 줄이거나 `raw_store_enabled: false`

## 재파싱 (다음 단계)

저장된 원문으로 파서만 다시 돌리기:

```powershell
cd D:\mail
python -c "from raw_store import RawStore; print(RawStore.load_meta('공고_id'))"
python -c "from raw_store import RawStore; t=RawStore.load_detail_html('공고_id'); print(len(t or ''))"
```

전용 `scripts/reparse_from_raw.py`는 v2에서 추가 예정.

## 안전

- API 키·비밀번호는 저장하지 않음
- 메일 발송과 무관 (dry-run / send 모두 동일하게 저장 가능)
- `MONITOR_NO_PERSIST_SEEN`과 별개 — seen_ids와 원문 저장은 독립

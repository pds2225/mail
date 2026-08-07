# 제목 O/X 검수 (메일 없음)

대시보드에서 제목만 보고 맞음/아님을 빠르게 라벨링하는 UI.

## 위치

- 앱: Streamlit `streamlit_app.py`
- 탭: **검수·O/X**
- 섹션: **제목 O/X (메일 발송 없음)**

## 레이아웃

1. 안내 문구 — O=맞음, X=아님, 메일 미발송, `feedback_labels.jsonl` 저장
2. **제목 큐 다시 만들기** 버튼 (`scripts/build_ox_title_queue.py`)
3. 카운터: `대기 N / 전체 큐 M · 누적 라벨 K`
4. 목록: 왼쪽 제목 · 오른쪽 **O 맞음** / **X 아님**

## 데이터

| 파일 | 용도 |
|------|------|
| `data/golden/ox_title_queue.json` | 검수 대기 제목 큐 |
| `data/golden/feedback_labels.jsonl` | O/X 누적 라벨 |
| `mail_core/delivery/feedback.py` | `record_local_verdict` / `feedback_verdicts` |

## 스크린샷

로컬 캡처: `/opt/cursor/artifacts/ox_title_review_main.webp` (에이전트 실행 환경)

## 관련

- [[filter-pipeline]]

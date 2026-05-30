# Vercel 사이트 관리 감사 (AUDIT)

감사 일자: 2026-05-28  
대상 레포: `pds2225/mail` (GitHub 원본)

## Vercel / Next.js 앱 위치

| 항목 | 경로 |
|------|------|
| Next.js 앱 루트 | `web/` |
| 패키지 | `web/package.json` |
| App Router | `web/app/` |
| API Routes | `web/app/api/*` |
| 배포 설정 | 루트 `vercel.json` (`@vercel/next` → `web/package.json`) |
| Python API (기존) | `api/health.py`, `api/index.py` → `/api/health`, `/api/run` |

이전에는 정적 `auto_mail_web.html`만 `/`에 노출되었고, **저장 시 브라우저 메모리 + JSON 다운로드**만 가능해 GitHub 설정 파일과 동기화되지 않았습니다.

## 사이트 추가 기능 존재 여부

| 기능 | 상태 |
|------|------|
| 사이트 목록 (읽기) | ✅ `/sites` — `GET /api/config` → `sites.json` |
| 사이트 추가 폼 | ✅ `/sites/add` |
| 검증 버튼 | ✅ `POST /api/sites/validate` |
| PR 패킷 생성 | ✅ `POST /api/sites/packet` |
| 운영 `sites.json` 직접 쓰기 | ❌ 의도적 비활성 (승인 후 PR만) |

## 저장 지속성

| 환경 | 동작 |
|------|------|
| 로컬 `npm run dev` | 패킷 생성 시 `WORKS/SITE_ADD_PR_PACKET.md`, `docs/SITE_ADD_PR_PACKET.md` 기록 가능 |
| Vercel Serverless | FS 읽기 전용일 수 있음 → **API 응답 `packetMarkdown` 복사**가 1차 수단 |
| 운영 설정 | GitHub merge 후에만 반영 |

**결론:** Vercel UI만으로 운영 `sites.json`이 바뀌지 않음 — 지속성 문제(이전 HTML UI)는 해소됨.

## GitHub 설정 파일 반영 가능 여부

- **1차:** PR 패킷 마크다운 + JSON 스니펫 (수동/에이전트 PR)
- **2차 (NEEDS_USER):** `GITHUB_TOKEN` in Vercel env → 브랜치 생성 · 파일 수정 · Draft PR (자동 merge 금지)

원본 데이터: 레포 루트 `sites.json`, `groups.json`, `settings.json`.

## 현재 문제점 / 제한

1. Vercel 배포본에서 URL probe가 일부 정부 사이트 TLS에서 실패할 수 있음 (Cloud VM과 동일).
2. `html_table` / `html_card`는 `selectors` 수동 보완이 PR에 필요할 수 있음.
3. GitHub API 자동 PR은 토큰·권한 설정 전까지 수동 패킷 복사.
4. `streamlit_app.py`는 레포에 남아 있으나 **운영 UI로 사용하지 않음** (요구사항: Streamlit 전환 금지).

## 실사용성 점수

| 영역 | 점수 (5점 만점) | 비고 |
|------|-----------------|------|
| 사이트 추가 폼·검증 | 4.5 | 필수값·URL·중복·collector 점검 |
| PR 패킷 생성 | 4.5 | diff·초안·승인 체크리스트 |
| 수신자 관리 | 4.0 | 검증·마스킹·패킷 (그룹 선택 UI는 추후) |
| 운영 자동 반영 | 5.0 (안전) | 직접 반영 없음 = 의도된 설계 |
| GitHub 완전 자동화 | 2.0 | 토큰·Draft PR은 NEEDS_USER |

**종합: 4.0 / 5.0** — 승인 기반 PR 워크플로에 적합.

---

## PR #37 후속 보강 (2026-05-30)

| 항목 | 보강 내용 |
|------|-----------|
| Vercel FS | `web/scripts/copy-config.mjs` → `web/data/*.json` 빌드 번들 |
| 수신자 노출 | `/api/config` groups·settings 마스킹 (`config-mask.ts`) |
| 패킷 지속성 | `sessionStorage` + `.md`/JSON 다운로드 (`PacketPanel`) |
| sites patch | `siteJsonPatch` + 전체 미리보기(truncated) |
| 수신자 패킷 | 그룹 선택 UI, append-only patch, valid만 반영 |
| PR #37 상태 | **merged** — 동일 브랜치에 후속 커밋 push (새 PR 없음) |

# RECIPIENT_UPDATE_PACKET (템플릿)

수신자 변경은 **PR 승인 후**만 운영에 반영합니다.  
실제 패킷은 `/recipients` → 「PR 패킷 생성」 또는 `POST /api/recipients/packet` 으로 생성됩니다.

## 필요한 입력값

| 필드 | 설명 |
|------|------|
| emails | 줄바꿈·쉼표·세미콜론 구분 목록 |
| target | `group` (groups.json) 또는 `raw_all` (settings.json) |
| groupId | target=group 일 때 그룹 ID |

## 검증 결과 (예시 형식)

- valid: N건
- rejected: 형식 오류 / 중복
- masked: `ab***@example.com` 형태만 표시

## PR 반영 방식

1. `groups.json` 해당 그룹 `recipients` 배열에 추가 **또는**
2. `settings.json` `raw_all_recipients` 에 추가
3. dry-run으로 `recipient_audit` 확인
4. **실제 메일 발송 테스트 금지**

## 승인 필요

- 담당자 이메일 여부 확인
- PR merge 전 운영 발송 설정 변경 없음

---

**최신 패킷:** Vercel UI에서 생성하세요.

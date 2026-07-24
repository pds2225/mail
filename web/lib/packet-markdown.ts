import type { SiteRecord } from "./site-types";
import type { SiteValidationResult } from "./site-validation";
import { jsonPatchSnippet } from "./site-patch";
import { maskEmail } from "./recipient-validation";

export function buildSiteAddPacket(params: {
  branch: string;
  site: SiteRecord;
  validation: SiteValidationResult;
  existingCount: number;
  urlReachable: boolean | null;
}): string {
  const { branch, site, validation, existingCount, urlReachable } = params;
  const snippet = jsonPatchSnippet([], site);

  return `# SITE_ADD_PR_PACKET

생성 시각: ${new Date().toISOString()}
브랜치 제안: \`${branch}\`

## 수정 대상 파일

- \`config/sites.json\` (${existingCount}건 → ${existingCount + 1}건)

## 추가될 사이트 JSON

\`\`\`json
${snippet}
\`\`\`

## 검증 요약

| 항목 | 결과 |
|------|------|
| collector 등록 | ${validation.checks.collectorRegistered ? "OK" : "FAIL"} |
| URL 접근 테스트 | ${urlReachable === null ? "미실행" : urlReachable ? "OK" : "FAIL"} |
| date_unknown 위험 | ${validation.checks.dateUnknownRisk} |
| dry-run 가능 | ${validation.checks.dryRunReady ? "예" : "아니오"} |
| stable_id | ${validation.checks.stableIdNote} |

## 오류 / 경고

${validation.errors.length ? validation.errors.map((e) => `- [ERROR] ${e.field}: ${e.message}`).join("\n") : "- 없음"}

${validation.warnings.length ? validation.warnings.map((w) => `- [WARN] ${w.field}: ${w.message}`).join("\n") : ""}

## PR 제목 (초안)

\`feat(sites): add ${site.id} — ${site.name}\`

## PR 본문 (초안)

사이트 수집 소스 추가: **${site.name}**

- URL: ${site.url}
- type: \`${site.type}\`
- enabled: ${site.enabled}
- is_aggregator: ${site.is_aggregator}

### 검증

- [ ] \`python3 scripts/monitor_dry_run.py --skip-coverage-fetch\` 실행
- [ ] 해당 사이트 collector 수집 건수 확인
- [ ] 실제 메일 발송 없음 (dry-run)

## 사용자 승인 필요 지점

1. config/sites.json 변경 내용 검토
2. PR merge (자동 merge 금지)
3. 운영 cron/Actions는 별도 승인

## GitHub API 2차 연동 (NEEDS_USER)

\`GITHUB_TOKEN\` (Vercel env) + \`gh pr create --draft\` 로 자동화 가능. 토큰은 로그에 출력하지 않음.
`;
}

export function buildRecipientPacket(params: {
  target: "group" | "raw_all";
  groupId?: string;
  groupName?: string;
  added: string[];
  validation: ReturnType<typeof import("./recipient-validation").validateRecipients>;
}): string {
  const masked = params.validation.masked.join(", ") || "(없음)";
  return `# RECIPIENT_UPDATE_PACKET

생성 시각: ${new Date().toISOString()}
대상: ${params.target === "group" ? `config/groups.json → ${params.groupName || params.groupId}` : "config/settings.json → raw_all_recipients"}

## 추가 요청 이메일 (마스킹)

${params.added.map((e) => `- ${maskEmail(e)}`).join("\n")}

## 검증 결과

- valid: ${params.validation.valid.length}건
- rejected: ${params.validation.rejected.length}건

${params.validation.rejected.map((r) => `- rejected: ${maskEmail(r.value)} (${r.reason})`).join("\n") || ""}

## PR 반영 방식

1. \`config/groups.json\` 또는 \`config/settings.json\` 수동/PR 반영
2. 실제 메일 발송 테스트 금지 — dry-run만

## 승인 필요

- 이메일 주소가 운영 담당자 것인지 확인
- PR merge 후에만 운영 발송 설정 변경
`;
}

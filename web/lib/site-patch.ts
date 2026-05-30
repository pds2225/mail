import type { SiteRecord } from "./site-types";

export function buildSitesPatch(existing: SiteRecord[], addition: SiteRecord): SiteRecord[] {
  return [...existing, addition];
}

/** Single site object to append to sites.json array. */
export function jsonPatchSnippet(_existing: SiteRecord[], addition: SiteRecord): string {
  return JSON.stringify(addition, null, 2);
}

/** Full sites.json after append (for manual replace review). */
export function fullSitesJsonAfterAdd(existing: SiteRecord[], addition: SiteRecord): string {
  return JSON.stringify(buildSitesPatch(existing, addition), null, 2);
}

/** jq-style instruction for PR authors. */
export function sitesJsonApplyHint(siteId: string): string {
  return `sites.json 배열 끝에 아래 객체 1건 추가 (id: ${siteId})`;
}

export function unifiedDiffLines(existing: SiteRecord[], addition: SiteRecord): string[] {
  const lines = [
    "--- a/sites.json",
    "+++ b/sites.json",
    `@@ sites.json에 1건 추가 @@`,
    `+  ${JSON.stringify(addition, null, 2).split("\n").join("\n+  ")}`,
  ];
  return lines;
}

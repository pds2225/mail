import type { SiteRecord } from "./site-types";

export function buildSitesPatch(existing: SiteRecord[], addition: SiteRecord): SiteRecord[] {
  return [...existing, addition];
}

export function jsonPatchSnippet(existing: SiteRecord[], addition: SiteRecord): string {
  const next = buildSitesPatch(existing, addition);
  const last = next[next.length - 1];
  return JSON.stringify(last, null, 2);
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

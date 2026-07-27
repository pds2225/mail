import type { SiteRecord } from "./site-types";

export function buildSitesPatch(existing: SiteRecord[], addition: SiteRecord): SiteRecord[] {
  return [...existing, addition];
}

export function replaceSite(
  existing: SiteRecord[],
  originalId: string,
  replacement: SiteRecord,
): SiteRecord[] {
  const index = existing.findIndex((site) => site.id === originalId);
  if (index < 0) {
    throw new Error(`site not found: ${originalId}`);
  }
  return existing.map((site, current) => (current === index ? replacement : site));
}

export function changedSiteFields(
  before: SiteRecord,
  after: SiteRecord,
): string[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys]
    .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .sort();
}

export function jsonPatchSnippet(existing: SiteRecord[], addition: SiteRecord): string {
  const next = buildSitesPatch(existing, addition);
  const last = next[next.length - 1];
  return JSON.stringify(last, null, 2);
}

export function unifiedDiffLines(existing: SiteRecord[], addition: SiteRecord): string[] {
  const lines = [
    "--- a/config/sites.json",
    "+++ b/config/sites.json",
    `@@ config/sites.json에 1건 추가 @@`,
    `+  ${JSON.stringify(addition, null, 2).split("\n").join("\n+  ")}`,
  ];
  return lines;
}

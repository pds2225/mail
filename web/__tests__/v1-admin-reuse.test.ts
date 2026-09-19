import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import { pendingConfigManualCommitUrl } from "@/lib/github-commit-url";

function webSource(relative: string) {
  return fs.readFileSync(path.resolve(process.cwd(), relative), "utf-8");
}

describe("V1 admin reuse", () => {
  it("keeps the five V1 work areas under the government-support title", () => {
    const nav = webSource("app/components/NavBar.tsx");
    expect(nav).toContain("정부지원사업 메일링");
    for (const label of ["소스 관리", "그룹 관리", "설정", "실행", "공고 검수"]) {
      expect(nav).toContain(label);
    }
  });

  it("keeps common pages free of the old export-monitor title", () => {
    for (const file of ["app/page.tsx", "app/layout.tsx", "app/components/NavBar.tsx"]) {
      const source = webSource(file);
      expect(source).not.toContain("수출지원 모니터링");
      expect(source).not.toContain("수출·지원사업 모니터");
    }
  });

  it("never embeds config pending payload in GitHub URLs", () => {
    const existingUrl = pendingConfigManualCommitUrl({ existing: true });
    const newUrl = pendingConfigManualCommitUrl({ existing: false });

    expect(existingUrl).toBe(
      "https://github.com/pds2225/mail/edit/main/.apply/config-pending.json",
    );
    expect(newUrl).toBe(
      "https://github.com/pds2225/mail/new/main/.apply?filename=config-pending.json",
    );
    expect(existingUrl).not.toContain("value=");
    expect(newUrl).not.toContain("value=");
  });

  it("keeps group and settings pages on the shared manual pending panel", () => {
    for (const file of ["app/groups/page.tsx", "app/settings/page.tsx"]) {
      const source = webSource(file);
      expect(source).toContain("ManualPendingApply");
      expect(source).toContain("manualPasteRequired");
    }
  });

  it("never exposes recipient editing in group/settings pages", () => {
    const group = webSource("app/groups/page.tsx");
    const settings = webSource("app/settings/page.tsx");
    expect(group).not.toContain("raw_all_recipients:");
    expect(settings).not.toContain("raw_all_recipients:");
    expect(group).toContain("private store");
  });
});

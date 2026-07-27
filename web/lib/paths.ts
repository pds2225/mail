import path from "path";
import fs from "fs";

/** GitHub 레포 루트 (web/ 의 상위). Vercel 배포 시 레포 전체가 함께 올라감. */
export function repoRoot(): string {
  const candidates = [
    path.join(process.cwd(), ".."),
    process.cwd(),
    path.join(process.cwd(), "../.."),
  ];
  for (const root of candidates) {
    if (fs.existsSync(path.join(root, "config", "sites.json"))) {
      return path.resolve(root);
    }
  }
  return path.resolve(process.cwd(), "..");
}

export function configPath(name: "sites.json" | "groups.json" | "settings.json"): string {
  return path.join(repoRoot(), "config", name);
}

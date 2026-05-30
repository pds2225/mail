import path from "path";
import fs from "fs";

const CONFIG_NAMES = ["sites.json", "groups.json", "settings.json"] as const;
export type ConfigFileName = (typeof CONFIG_NAMES)[number];

/** Bundled config from `npm run build` (web/data). */
export function bundledConfigDir(): string {
  const fromCwd = path.join(process.cwd(), "data");
  if (fs.existsSync(path.join(fromCwd, "sites.json"))) return fromCwd;
  return path.join(process.cwd(), "web", "data");
}

/** GitHub 레포 루트 (web/ 의 상위). */
export function repoRoot(): string {
  const candidates = [
    path.join(process.cwd(), ".."),
    process.cwd(),
    path.join(process.cwd(), "../.."),
  ];
  for (const root of candidates) {
    if (fs.existsSync(path.join(root, "sites.json"))) {
      return path.resolve(root);
    }
  }
  return path.resolve(process.cwd(), "..");
}

export function configPath(name: ConfigFileName): string {
  const bundled = path.join(bundledConfigDir(), name);
  if (fs.existsSync(bundled)) return bundled;
  return path.join(repoRoot(), name);
}

export function configSourceLabel(): "bundled" | "repo" {
  const bundled = path.join(bundledConfigDir(), "sites.json");
  return fs.existsSync(bundled) ? "bundled" : "repo";
}

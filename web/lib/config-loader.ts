import fs from "fs";
import path from "path";
import { configPath } from "./paths";
import type { SiteRecord } from "./site-types";

export type GroupRecord = {
  id: string;
  name: string;
  active?: boolean;
  recipients?: string[];
  [key: string]: unknown;
};

function readBundledOrRepo(name: "sites.json" | "groups.json" | "settings.json"): string {
  const bundled = path.join(process.cwd(), "data", name);
  if (fs.existsSync(bundled)) {
    return fs.readFileSync(bundled, "utf-8");
  }
  return fs.readFileSync(configPath(name), "utf-8");
}

export function loadSites(): SiteRecord[] {
  return JSON.parse(readBundledOrRepo("sites.json")) as SiteRecord[];
}

export function loadGroups(): GroupRecord[] {
  return JSON.parse(readBundledOrRepo("groups.json")) as GroupRecord[];
}

export function loadSettings(): Record<string, unknown> {
  return JSON.parse(readBundledOrRepo("settings.json")) as Record<string, unknown>;
}

import fs from "fs";
import { configPath } from "./paths";
import type { SiteRecord } from "./site-types";

export function loadSites(): SiteRecord[] {
  const raw = fs.readFileSync(configPath("sites.json"), "utf-8");
  return JSON.parse(raw) as SiteRecord[];
}

export function loadGroups(): unknown[] {
  const raw = fs.readFileSync(configPath("groups.json"), "utf-8");
  return JSON.parse(raw) as unknown[];
}

export function loadSettings(): Record<string, unknown> {
  const raw = fs.readFileSync(configPath("settings.json"), "utf-8");
  return JSON.parse(raw) as Record<string, unknown>;
}

import fs from "fs";
import { configPath } from "./paths";
import type { SiteRecord } from "./site-types";

export type GroupRecord = {
  id: string;
  name: string;
  active?: boolean;
  recipients?: string[];
  [key: string]: unknown;
};

export function loadSites(): SiteRecord[] {
  const raw = fs.readFileSync(configPath("sites.json"), "utf-8");
  return JSON.parse(raw) as SiteRecord[];
}

export function loadGroups(): GroupRecord[] {
  const raw = fs.readFileSync(configPath("groups.json"), "utf-8");
  return JSON.parse(raw) as GroupRecord[];
}

export function loadSettings(): Record<string, unknown> {
  const raw = fs.readFileSync(configPath("settings.json"), "utf-8");
  return JSON.parse(raw) as Record<string, unknown>;
}

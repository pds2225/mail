import sitesData from "../data/sites.json";
import groupsData from "../data/groups.json";
import settingsData from "../data/settings.json";
import type { SiteRecord } from "./site-types";

export type GroupRecord = {
  id: string;
  name: string;
  active?: boolean;
  recipients?: string[];
  [key: string]: unknown;
};

/**
 * Build-time bundled config.
 *
 * `prebuild`/`pretest` copies repo `config/*.json` into `web/data/`.
 * Static imports make Next/Vercel include those files in the serverless bundle,
 * restoring the old PR #37 copy-config behaviour after the repository refactor.
 */
export function loadSites(): SiteRecord[] {
  return sitesData as SiteRecord[];
}

export function loadGroups(): GroupRecord[] {
  return groupsData as GroupRecord[];
}

export function loadSettings(): Record<string, unknown> {
  return settingsData as Record<string, unknown>;
}

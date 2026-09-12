import type { SiteRecord } from "./site-types";

export const PENDING_APPLY_PATH = ".apply/pending.json";

export type PendingApply = {
  v: 1;
  mode: "add" | "update";
  site: SiteRecord;
};

export function serializePendingApply(pending: PendingApply): string {
  return `${JSON.stringify(pending)}\n`;
}

export function githubNewFileUrl(opts: {
  repo?: string;
  branch?: string;
  directory: string;
  filename: string;
  value: string;
}): string {
  const repo = opts.repo || "pds2225/mail";
  const branch = opts.branch || "main";
  const params = new URLSearchParams({
    filename: opts.filename,
    value: opts.value,
  });
  return `https://github.com/${repo}/new/${branch}/${opts.directory}?${params.toString()}`;
}

export function pendingApplyCommitUrl(pending: PendingApply): string {
  return githubNewFileUrl({
    directory: ".apply",
    filename: "pending.json",
    value: serializePendingApply(pending),
  });
}

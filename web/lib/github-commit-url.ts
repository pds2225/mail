import type { SiteRecord } from "./site-types";

export const PENDING_APPLY_PATH = ".apply/pending.json";
export const CONFIG_PENDING_APPLY_PATH = ".apply/config-pending.json";

export type PendingApply = {
  v: 1;
  mode: "add" | "update";
  site: SiteRecord;
};

export type PendingConfigApply =
  | { v: 1; resource: "group"; id: string; patch: Record<string, unknown> }
  | { v: 1; resource: "settings"; patch: Record<string, unknown> }
  | {
      v: 1;
      resource: "review";
      items: { id: string; title: string; verdict: "O" | "X" }[];
    }
  | {
      v: 1;
      resource: "review";
      encoding: "gzip-base64";
      packed_items: string;
    };

export function serializePendingApply(pending: PendingApply | PendingConfigApply): string {
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


export function githubEditFileUrl(filePath: string, opts?: { repo?: string; branch?: string }): string {
  const repo = opts?.repo || "pds2225/mail";
  const branch = opts?.branch || "main";
  const safePath = filePath.split("/").map(encodeURIComponent).join("/");
  return `https://github.com/${repo}/edit/${branch}/${safePath}`;
}

import { githubApplyToken } from "./apply-auth";
import type { SiteRecord } from "./site-types";

const API = "https://api.github.com";

export function githubRepo(): { owner: string; repo: string } {
  const raw = process.env.GITHUB_APPLY_REPO || "pds2225/mail";
  const [owner, repo] = raw.split("/");
  return { owner: owner || "pds2225", repo: repo || "mail" };
}

export function githubBranch(): string {
  return process.env.GITHUB_APPLY_BRANCH || "main";
}

export function serializeSitesJson(sites: SiteRecord[]): string {
  return `${JSON.stringify(sites, null, 2)}\n`;
}

function authHeaders(): HeadersInit {
  const token = githubApplyToken();
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "mail-admin-web",
  };
}

export type RepoFile = {
  sha: string;
  text: string;
};

export async function getRepoTextFile(filePath: string): Promise<RepoFile> {
  const { owner, repo } = githubRepo();
  const branch = githubBranch();
  const url = `${API}/repos/${owner}/${repo}/contents/${filePath}?ref=${encodeURIComponent(branch)}`;
  const response = await fetch(url, { headers: authHeaders(), cache: "no-store" });
  const body = (await response.json()) as {
    message?: string;
    sha?: string;
    content?: string;
    encoding?: string;
  };
  if (!response.ok || !body.sha || !body.content) {
    throw new Error(body.message || `GitHub에서 ${filePath} 를 읽지 못했습니다.`);
  }
  const text = Buffer.from(body.content.replace(/\n/g, ""), "base64").toString("utf-8");
  return { sha: body.sha, text };
}

export async function putRepoTextFile(opts: {
  filePath: string;
  text: string;
  sha: string;
  message: string;
}): Promise<{ sha: string; htmlUrl: string; commitUrl: string }> {
  const { owner, repo } = githubRepo();
  const branch = githubBranch();
  const url = `${API}/repos/${owner}/${repo}/contents/${opts.filePath}`;
  const response = await fetch(url, {
    method: "PUT",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      message: opts.message,
      content: Buffer.from(opts.text, "utf-8").toString("base64"),
      sha: opts.sha,
      branch,
    }),
  });
  const body = (await response.json()) as {
    message?: string;
    content?: { sha?: string; html_url?: string };
    commit?: { html_url?: string; sha?: string };
  };
  if (!response.ok) {
    throw new Error(body.message || `GitHub에 ${opts.filePath} 를 쓰지 못했습니다.`);
  }
  return {
    sha: body.commit?.sha || body.content?.sha || "",
    htmlUrl: body.content?.html_url || "",
    commitUrl: body.commit?.html_url || "",
  };
}

export function parseSitesJson(text: string): SiteRecord[] {
  const parsed = JSON.parse(text) as unknown;
  if (!Array.isArray(parsed)) {
    throw new Error("config/sites.json 형식이 배열이 아닙니다.");
  }
  return parsed as SiteRecord[];
}

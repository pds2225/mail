import { timingSafeEqual } from "crypto";

export const APPLY_SECRET_HEADER = "x-config-apply-secret";
export const GITHUB_TOKEN_HEADER = "x-github-token";

function secretsEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export function configuredApplySecret(): string {
  return (process.env.CONFIG_APPLY_SECRET || "").trim();
}

export function serverGithubToken(): string {
  return (
    process.env.GITHUB_APPLY_TOKEN ||
    process.env.GITHUB_TOKEN ||
    process.env.AUTO_DEV_PAT ||
    ""
  ).trim();
}

export function requestGithubToken(req: Request): string {
  return (req.headers.get(GITHUB_TOKEN_HEADER) || "").trim();
}

/**
 * Server GitHub token is only used when CONFIG_APPLY_SECRET is also set.
 * Otherwise the public Vercel site would let anyone commit with the stored PAT.
 * With no shared secret, the visitor must supply their own repo-write token.
 */
export function githubApplyToken(req?: Request): string {
  const client = req ? requestGithubToken(req) : "";
  if (configuredApplySecret()) {
    return serverGithubToken() || client;
  }
  return client;
}

export function applyAuthError(req: Request): string | null {
  const expected = configuredApplySecret();
  if (expected) {
    const got = (req.headers.get(APPLY_SECRET_HEADER) || "").trim();
    if (!got || !secretsEqual(got, expected)) {
      return "반영 암호가 올바르지 않습니다.";
    }
  }
  if (!githubApplyToken(req)) {
    return "GitHub 토큰이 없습니다. 위쪽에 pds2225/mail 쓰기 권한 토큰을 입력하세요.";
  }
  return null;
}

export type ApplyMode = "server" | "client-token";

export function applyStatus() {
  const hasApplySecret = Boolean(configuredApplySecret());
  const hasGithubToken = Boolean(serverGithubToken());
  const applyReady = hasApplySecret && hasGithubToken;
  const mode: ApplyMode = applyReady ? "server" : "client-token";
  return {
    hasApplySecret,
    hasGithubToken,
    applyReady,
    mode,
    repo: process.env.GITHUB_APPLY_REPO || "pds2225/mail",
    branch: process.env.GITHUB_APPLY_BRANCH || "main",
    tokenUrl:
      "https://github.com/settings/tokens/new?description=mail-vercel-apply&scopes=public_repo",
  };
}

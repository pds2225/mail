import { timingSafeEqual } from "crypto";

export const APPLY_SECRET_HEADER = "x-config-apply-secret";

function secretsEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export function configuredApplySecret(): string {
  return (process.env.CONFIG_APPLY_SECRET || "").trim();
}

export function githubApplyToken(): string {
  return (
    process.env.GITHUB_APPLY_TOKEN ||
    process.env.GITHUB_TOKEN ||
    process.env.AUTO_DEV_PAT ||
    ""
  ).trim();
}

export function applyAuthError(req: Request): string | null {
  const expected = configuredApplySecret();
  if (!expected) {
    return "Vercel 환경변수 CONFIG_APPLY_SECRET 이 없습니다. 대시보드에서 설정한 뒤 반영하세요.";
  }
  const got = (req.headers.get(APPLY_SECRET_HEADER) || "").trim();
  if (!got || !secretsEqual(got, expected)) {
    return "반영 암호가 올바르지 않습니다.";
  }
  if (!githubApplyToken()) {
    return "Vercel 환경변수 GITHUB_APPLY_TOKEN (contents:write) 이 없습니다.";
  }
  return null;
}

export function applyStatus() {
  return {
    hasApplySecret: Boolean(configuredApplySecret()),
    hasGithubToken: Boolean(githubApplyToken()),
    repo: process.env.GITHUB_APPLY_REPO || "pds2225/mail",
    branch: process.env.GITHUB_APPLY_BRANCH || "main",
  };
}

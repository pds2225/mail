import { describe, expect, it } from "vitest";

/**
 * Vercel admin web must not import monitor.py or trigger SMTP.
 * This test guards against accidental coupling.
 */
describe("no real mail send from web layer", () => {
  it("web package has no nodemailer/smtp deps", async () => {
    const pkg = await import("../package.json");
    const deps = { ...pkg.default.dependencies, ...pkg.default.devDependencies };
    expect(deps).not.toHaveProperty("nodemailer");
    expect(Object.keys(deps).join(" ")).not.toMatch(/smtp|gmail/i);
  });
});

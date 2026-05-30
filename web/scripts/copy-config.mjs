#!/usr/bin/env node
/**
 * Build-time copy of repo config into web/data for Vercel serverless (read-only bundle).
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.join(__dirname, "..");
const repoRoot = path.join(webRoot, "..");
const outDir = path.join(webRoot, "data");

const files = ["sites.json", "groups.json", "settings.json"];

fs.mkdirSync(outDir, { recursive: true });
for (const name of files) {
  const src = path.join(repoRoot, name);
  if (!fs.existsSync(src)) {
    console.warn(`[copy-config] skip missing ${name}`);
    continue;
  }
  fs.copyFileSync(src, path.join(outDir, name));
  console.log(`[copy-config] ${name} → web/data/${name}`);
}

import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = process.cwd();
const repoConfig = resolve(webRoot, "..", "config");
const target = resolve(webRoot, "data");

if (!existsSync(repoConfig)) {
  throw new Error(`config directory not found: ${repoConfig}`);
}

mkdirSync(target, { recursive: true });
for (const name of ["sites.json", "groups.json", "settings.json"]) {
  cpSync(resolve(repoConfig, name), resolve(target, name));
}

console.log("copied config -> web/data");

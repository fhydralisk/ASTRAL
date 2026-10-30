import { readFile, writeFile } from "node:fs/promises";
const schema = JSON.parse(
  await readFile("../contracts/harness.openapi.json", "utf8"),
);
const project = await readFile("../pyproject.toml", "utf8");
const version = project.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (!version) throw new Error("Missing project version");
await writeFile(
  "src/lib/project-version.ts",
  `// Generated from pyproject.toml.\nexport const projectVersion = ${JSON.stringify(version)};\n`,
);
const prefix = "/v1/sessions/{session_id}";
const routes: { method: string; path: string }[] = [];
for (const [path, methods] of Object.entries(schema.paths) as [
  string,
  Record<string, unknown>,
][]) {
  if (!path.startsWith(prefix) || path.includes("/credentials/")) continue;
  for (const method of Object.keys(methods)) {
    if (
      !["get", "post", "put", "patch", "delete"].includes(method) ||
      (path === prefix && method !== "get")
    )
      continue;
    routes.push({
      method: method.toUpperCase(),
      path: path.slice(prefix.length) || "/",
    });
  }
}
await writeFile(
  "src/lib/scientific-routes.ts",
  `// Generated from contracts/harness.openapi.json.\nexport const scientificRoutes = ${JSON.stringify(routes, null, 2)} as const;\n`,
);

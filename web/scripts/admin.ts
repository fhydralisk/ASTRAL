import nextEnv from "@next/env";
nextEnv.loadEnvConfig(process.cwd());
const { createUser } = await import("../src/server/security");
const username = process.env.ADMIN_USERNAME,
  password = process.env.ADMIN_PASSWORD;
if (!username || !password)
  throw new Error("Set ADMIN_USERNAME and ADMIN_PASSWORD for this invocation");
await createUser(username, password, "admin");
console.log(
  "Administrator created. Clear ADMIN_PASSWORD from your environment.",
);
process.exit(0);

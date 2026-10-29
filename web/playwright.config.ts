import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  workers: 1,
  use: {
    baseURL: "http://localhost:3100",
    channel: "chromium",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "npx tsx tests/mock-harness.ts",
      port: 8123,
      reuseExistingServer: false,
    },
    {
      command: "npm run db:migrate && npm run dev -- --port 3100",
      url: "http://localhost:3100/api/health",
      reuseExistingServer: false,
      timeout: 120000,
      env: {
        APP_ORIGIN: "http://localhost:3100",
        HARNESS_URL: "http://localhost:8123",
        HARNESS_SERVICE_TOKEN: "playwright-internal-token-12345678",
        CREDENTIAL_MASTER_KEY: Buffer.alloc(32, 7).toString("base64"),
        DB_DIALECT: "sqlite",
        DATABASE_URL: "file:./test-e2e.db",
        COOKIE_SECURE: "false",
      },
    },
  ],
});

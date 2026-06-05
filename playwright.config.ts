import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 1,
  use: {
    baseURL: "http://localhost:3000",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.PW_SKIP_WEB_SERVER
    ? undefined
    : {
        command: "node e2e/next-dev-server.cjs",
        url: "http://localhost:3000",
        timeout: 30_000,
        reuseExistingServer: !process.env.CI,
      },
});

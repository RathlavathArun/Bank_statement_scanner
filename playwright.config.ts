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
  webServer: [
    {
      command:
        "cd apps/api && source venv/bin/activate && python main.py",
      url: "http://localhost:8000/docs",
      timeout: 20_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "cd apps/web && npm run dev",
      url: "http://localhost:3000",
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});

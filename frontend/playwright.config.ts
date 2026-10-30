import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,
  expect: { timeout: 10000 },
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile-webkit",
      use: { ...devices["iPhone 13"], browserName: "webkit" },
    },
  ],
  webServer: [
    {
      command:
        "python -m uvicorn app.main:create_app --factory --app-dir ../backend --host 127.0.0.1 --port 8000 --no-access-log",
      url: "http://127.0.0.1:8000/api/v1/health/ready",
      timeout: 60000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run preview -- --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      timeout: 30000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});

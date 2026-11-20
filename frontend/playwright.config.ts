import { defineConfig, devices } from "@playwright/test";

// E2E chạy trên bộ container chính đang chạy ở 127.0.0.1:18180 (không tạo môi trường riêng).
export default defineConfig({
  testDir: "e2e",
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:18180", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});

import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const rootDirectory = path.resolve(process.cwd(), "..");
const pythonExecutable = path.join(rootDirectory, ".venv", "Scripts", "python.exe");

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://127.0.0.1:8000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${pythonExecutable}" -m uvicorn api:app --host 127.0.0.1 --port 8000`,
    cwd: rootDirectory,
    url: "http://127.0.0.1:8000/api/health",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    {
      name: "edge",
      use: { ...devices["Desktop Chrome"], channel: "msedge" },
    },
  ],
});

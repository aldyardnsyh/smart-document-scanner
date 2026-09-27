import path from "node:path";
import { expect, test } from "@playwright/test";

test("complete scanner, result, history, theme, and mobile flows", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Turn an angled document photo into inspectable data." })).toBeVisible();
  await expect(page.getByText("How the five-stage pipeline works")).toBeVisible();

  const themeButton = page.getByRole("button", { name: /Switch to/ });
  const initialTheme = await page.locator("html").getAttribute("data-theme");
  await themeButton.click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", initialTheme ?? "light");

  await page.getByRole("link", { name: "Open scanner workbench" }).click();
  await expect(page).toHaveURL(/\/scanner$/);
  await page.locator('input[type="file"]').setInputFiles(
    path.resolve(process.cwd(), "../dataset/card_lowlight.jpg"),
  );
  await expect(page.getByText("card_lowlight.jpg")).toBeVisible();
  await page.getByRole("button", { name: "Business card", exact: true }).click();
  await page.getByRole("button", { name: "Process document" }).click();
  await expect(page).toHaveURL(/\/results\?jobId=[a-f0-9]{12}$/, { timeout: 90_000 });
  await expect(page.getByRole("heading", { name: /Processing results:/ })).toBeVisible();
  const jobId = new URL(page.url()).searchParams.get("jobId");
  expect(jobId).toBeTruthy();

  await page.getByRole("tab", { name: "Enhanced" }).click();
  await expect(page.getByRole("tab", { name: "Enhanced" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(page.getByText("125%")).toBeVisible();
  await page.getByRole("button", { name: "Fit" }).click();
  await expect(page.getByLabel("Image zoom controls").getByText("100%")).toBeVisible();
  await page.getByRole("button", { name: "Copy" }).click();
  await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();

  await page.getByRole("link", { name: "History", exact: true }).click();
  await expect(page).toHaveURL(/\/history$/);
  await expect(page.getByRole("heading", { name: "Processing history" })).toBeVisible();
  const historyFile = page.getByRole("heading", { name: "card_lowlight.jpg" }).first();
  await expect(historyFile).toBeVisible();
  await page.getByPlaceholder("Search file names").fill("lowlight");
  await expect(historyFile).toBeVisible();
  await page.getByPlaceholder("Search file names").fill("missing-file");
  await expect(page.getByRole("heading", { name: "No matching records" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(historyFile).toBeVisible();
  const historyCard = page.locator(`[data-job-id="${jobId}"]`);
  await historyCard.getByRole("button", { name: /Delete card_lowlight.jpg/ }).click();
  await expect(historyCard.getByRole("alertdialog")).toBeVisible();
  await historyCard.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(historyCard).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/scanner");
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toHaveClass(/is-open/);
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Overview" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: /Turn an angled document photo/ })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

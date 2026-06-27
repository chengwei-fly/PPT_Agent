import { test, expect } from "@playwright/test";

test.describe("US3 — 我的偏好", () => {
  test("should show preferences page at /preferences", async ({ page }) => {
    await page.goto("/preferences");
    await expect(page.getByText("我的偏好")).toBeVisible();
  });

  test("should show empty state or preference list", async ({ page }) => {
    await page.goto("/preferences");
    const hasEmpty = await page.getByText(/暂无偏好/).isVisible().catch(() => false);
    const hasTable = await page.getByRole("table").isVisible().catch(() => false);
    expect(hasEmpty || hasTable).toBeTruthy();
  });

  test("should show preference description", async ({ page }) => {
    await page.goto("/preferences");
    await expect(page.getByText(/Agent.*学习.*修改/)).toBeVisible();
  });

  test("should show scope labels if preferences exist", async ({ page }) => {
    await page.goto("/preferences");
    // If there are preferences, should show scope badges
    const content = await page.textContent("body");
    expect(content).toMatch(/封面|目录|正文|结尾|全局|暂无偏好/);
  });
});

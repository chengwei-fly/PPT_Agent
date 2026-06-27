import { test, expect } from "@playwright/test";

test.describe("US5 — 安全事件", () => {
  test("should show security page at /security", async ({ page }) => {
    await page.goto("/security");
    await expect(page.getByText("安全事件")).toBeVisible();
  });

  test("should show filter buttons", async ({ page }) => {
    await page.goto("/security");
    // Should have event type filters
    await expect(page.getByText("全部")).toBeVisible();
    const content = await page.textContent("body");
    expect(content).toMatch(/PII|命中|拦截|替换/);
  });

  test("should show data action buttons", async ({ page }) => {
    await page.goto("/security");
    await expect(page.getByText("导出数据")).toBeVisible();
    await expect(page.getByText("一键删除")).toBeVisible();
  });

  test("should show empty state or event table", async ({ page }) => {
    await page.goto("/security");
    const hasEmpty = await page.getByText(/暂无安全事件/).isVisible().catch(() => false);
    const hasTable = await page.getByRole("table").isVisible().catch(() => false);
    expect(hasEmpty || hasTable).toBeTruthy();
  });

  test("should show shield icon", async ({ page }) => {
    await page.goto("/security");
    // The Shield icon should be rendered
    const svg = page.locator("svg.lucide-shield");
    await expect(svg.first()).toBeVisible();
  });
});

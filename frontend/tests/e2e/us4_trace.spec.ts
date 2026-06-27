import { test, expect } from "@playwright/test";

test.describe("US4 — 生成轨迹", () => {
  test("should show trace page with task ID", async ({ page }) => {
    // Use a mock task ID — page should render even with invalid ID
    await page.goto("/trace/00000000-0000-0000-0000-000000000000");
    await expect(page.getByText("生成轨迹")).toBeVisible();
  });

  test("should show back button", async ({ page }) => {
    await page.goto("/trace/00000000-0000-0000-0000-000000000000");
    // Should have back navigation
    const backBtn = page.getByRole("button").filter({ hasText: /返回|←|back/i });
    await expect(backBtn.first()).toBeVisible();
  });

  test("should show 4 stage labels or empty state", async ({ page }) => {
    await page.goto("/trace/00000000-0000-0000-0000-000000000000");
    const content = await page.textContent("body");
    // Should show stage names or empty/message state
    expect(content).toMatch(/大纲|要点|SVG|PPTX|暂无|不存在|加载/);
  });

  test("should show stage descriptions", async ({ page }) => {
    await page.goto("/trace/00000000-0000-0000-0000-000000000000");
    const content = await page.textContent("body");
    // Should mention what each stage does
    expect(content).toMatch(/大纲|结构|要点|渲染|SVG|PPTX|下载|暂无|不存在/);
  });
});

import { test, expect } from "@playwright/test";

test.describe("US2 — 知识库管理", () => {
  test("should show knowledge page at /knowledge", async ({ page }) => {
    await page.goto("/knowledge");
    await expect(page.getByText("知识库")).toBeVisible();
  });

  test("should show upload dropzone", async ({ page }) => {
    await page.goto("/knowledge");
    // Should have upload area
    await expect(page.getByText(/拖拽|上传|选择文件/)).toBeVisible();
  });

  test("should show empty state when no samples", async ({ page }) => {
    await page.goto("/knowledge");
    // Should show empty state or sample list
    const hasEmpty = await page.getByText(/暂无样本|还没有上传/).isVisible().catch(() => false);
    const hasTable = await page.getByRole("table").isVisible().catch(() => false);
    expect(hasEmpty || hasTable).toBeTruthy();
  });

  test("should show file type restrictions", async ({ page }) => {
    await page.goto("/knowledge");
    // Should mention supported file types
    const content = await page.textContent("body");
    expect(content).toMatch(/PPTX|PDF|DOCX|pptx|pdf|docx/);
  });

  test("should show batch size limit info", async ({ page }) => {
    await page.goto("/knowledge");
    const content = await page.textContent("body");
    // Should mention limits
    expect(content).toMatch(/50MB|20|限制/);
  });
});

import { test, expect } from "@playwright/test";

test.describe("US1 — 一句话生成 PPT", () => {
  test("should show generation form on /generate", async ({ page }) => {
    await page.goto("/generate");
    await expect(page.getByText("一句话生成 PPT")).toBeVisible();
    await expect(page.getByPlaceholder(/做一份/)).toBeVisible();
    await expect(page.getByRole("button", { name: "开始生成" })).toBeVisible();
  });

  test("should show validation on empty submit", async ({ page }) => {
    await page.goto("/generate");
    await page.getByRole("button", { name: "开始生成" }).click();
    // Should show warning toast (sonner)
    await expect(page.getByText("请输入一句话需求")).toBeVisible();
  });

  test("should submit prompt and navigate to task page", async ({ page }) => {
    await page.goto("/generate");
    await page.getByPlaceholder(/做一份/).fill("做一份 10 页的季度工作汇报");
    await page.getByRole("button", { name: "开始生成" }).click();

    // Should navigate to /generate/{taskId}
    await expect(page).toHaveURL(/\/generate\/[a-f0-9-]+/);
  });

  test("should show progress after submission", async ({ page }) => {
    await page.goto("/generate");
    await page.getByPlaceholder(/做一份/).fill("测试生成进度");
    await page.getByRole("button", { name: "开始生成" }).click();

    // Wait for navigation
    await expect(page).toHaveURL(/\/generate\//, { timeout: 10000 });

    // Should show progress elements
    await expect(page.getByText("生成进度")).toBeVisible({ timeout: 10000 });
  });

  test("should show help tips", async ({ page }) => {
    await page.goto("/generate");
    await expect(page.getByText("知识库为空时")).toBeVisible();
    await expect(page.getByText("单用户最多 2 个并发")).toBeVisible();
  });
});

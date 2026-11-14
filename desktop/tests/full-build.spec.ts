import { test, expect } from "@playwright/test";

test("full build form exposes renderer isolation and never executes from browser preview", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "构建与日志", exact: true }).click();
  const panel = page.getByRole("region", { name: "完整本地 AOT 构建" });
  await expect(
    panel.getByRole("button", { name: "开始完整构建" }),
  ).toBeDisabled();
  await panel.getByLabel("完整构建渲染器").selectOption("gl41");
  await expect(panel.getByLabel("完整构建渲染器")).toHaveValue("gl41");
  await panel.getByLabel("完整构建渲染器").selectOption("metal");
  await expect(panel.getByLabel("完整构建渲染器")).toHaveValue("metal");
  await panel.getByLabel("完整构建运行模式").selectOption("fabric");
  await expect(
    panel.getByText("已审计本地 Mod，允许在隔离沙盒执行构建期转换"),
  ).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "开始完整构建" }),
  ).toBeDisabled();
  await expect(panel.getByRole("button", { name: "取消构建" })).toBeDisabled();
  await expect(panel.getByText(/浏览器用于工作流预览/)).toBeVisible();
  await page.screenshot({path:"test-results/full-build-browser-preview.png",fullPage:true});
});

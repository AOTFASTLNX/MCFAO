import { test, expect } from "@playwright/test";
test("guided studio exposes OpenGL compatibility in build review", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "选择要构建的游戏内容" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "5 确认构建", exact: true }).click();
  await expect(
    page.getByText("OpenGL 兼容 · GL41 / Zink / MoltenVK", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "构建 IPA", exact: true }).last(),
  ).toBeDisabled();
});

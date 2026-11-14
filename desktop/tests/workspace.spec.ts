import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

const report = JSON.parse(
  execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
    encoding: "utf8",
  }),
);
async function importReport(page: Page, value: unknown = report) {
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "preflight.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(value)),
    });
}

test("empty workspace, native affordances, dialog keyboard handling", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "你的世界，由你构建。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "导入整合包", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Modrinth 整合包/ }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "导入整合包", exact: true }),
  ).toBeFocused();
  expect(errors).toEqual([]);
});

test("real preflight report imports, filters, persists, exports and removes", async ({
  page,
}) => {
  await page.goto("/");
  await importReport(page);
  await expect(
    page.getByRole("heading", { name: "兼容性报告", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("fabricaot_ui_fixture", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("未测试", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "阻断 0", exact: true }).click();
  await expect(page.getByText("当前筛选下没有诊断事项。")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "兼容性报告", exact: true }).click();
  await expect(
    page.getByText("fabricaot_ui_fixture", { exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出报告", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("fabricaot-preflight.json");
  await importReport(page);
  await expect(page.getByLabel("当前实例").locator("option")).toHaveCount(1);
  await page.getByRole("button", { name: "移除实例记录" }).click();
  await page.getByRole("button", { name: "移除记录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "还没有兼容性报告" }),
  ).toBeVisible();
});

test("invalid JSON keeps existing instances and shows an error", async ({
  page,
}) => {
  await page.goto("/");
  await importReport(page);
  await importReport(page, { arbitrary: true });
  await expect(page.getByRole("alert")).toContainText("静态预检 JSON");
  await expect(page.getByLabel("当前实例").locator("option")).toHaveCount(1);
});

test("blocked reports cannot generate a preparation command", async ({
  page,
}) => {
  await page.goto("/");
  await importReport(page, {
    ...report,
    fatal: false,
    findings: [
      {
        code: "WRONG_MC_VERSION",
        severity: "error",
        message: "Expected 26.1.2",
      },
    ],
  });
  await expect(
    page.getByText("发现静态阻断项，请先处理后再构建。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "构建与日志", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "生成准备命令" }),
  ).toBeDisabled();
});

test("generates an honest prepare-only command from saved settings", async ({
  page,
}) => {
  await page.goto("/");
  await importReport(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("FabricAOT 项目目录").fill("/tmp/My Project");
  await page.getByRole("button", { name: "构建与日志", exact: true }).click();
  await page.getByLabel("本地 Mod 目录", { exact: true }).fill("/tmp/My Mods");
  await page.getByRole("button", { name: "生成准备命令" }).click();
  await expect(page.locator(".command-text")).toContainText("--prepare-only");
  await expect(page.locator(".command-text")).not.toContainText(
    "--audited-mods",
  );
  await page
    .getByLabel("本地 Mod 目录", { exact: true })
    .fill("/tmp/Other Mods");
  await expect(page.locator(".command-text")).toHaveCount(0);
});

test("corrupt local data is preserved until an explicit reset", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(() =>
    localStorage.setItem("fabricaot.desktop.v1", "{damaged"),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("暂停自动保存");
  expect(
    await page.evaluate(() => localStorage.getItem("fabricaot.desktop.v1")),
  ).toBe("{damaged");
});

for (const width of [375, 768, 1280, 1440]) {
  test("layout stays within viewport at " + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await importReport(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

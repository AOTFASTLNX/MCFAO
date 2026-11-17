import { test, expect } from "@playwright/test";

test("unsigned export hides signing requirements, persists choice and shows installation warning", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page
    .getByLabel("NCL 项目目录", { exact: true })
    .fill("/fixture/source");
  await page
    .getByLabel("构建配置", { exact: true })
    .fill("/fixture/config.json");
  await page
    .getByLabel("构建产物目录", { exact: true })
    .fill("/fixture/output");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByLabel("Apple Team ID").fill("BAD");
  await page.getByRole("checkbox", { name: /导出未签名 IPA/ }).check();
  await expect(page.getByText(/未签名 IPA 不能直接装机/)).toBeVisible();
  await expect(page.getByLabel("Apple Team ID")).toHaveCount(0);
  await expect(page.getByLabel("IPA 导出配置", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByText("Team ID 需要 10 位大写字母或数字。"),
  ).toHaveCount(0);
  await expect(page.getByText("请选择 IPA 开发导出配置。")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "3 开发签名", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: /导出未签名 IPA/ }),
  ).toBeChecked();
  await page.getByRole("checkbox", { name: /导出未签名 IPA/ }).uncheck();
  await expect(page.getByLabel("Apple Team ID")).toHaveValue("BAD");
});

test("storage settings are distinct and ownership starts unchecked in both themes", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  for (const label of [
    "编译缓存目录",
    "构建产物根目录",
    "任务记录目录",
    "Rust 缓存目录",
  ]) {
    await page.getByLabel(label, { exact: true }).fill("/fixture/" + label);
    await expect(page.getByLabel(label, { exact: true })).toHaveValue(
      "/fixture/" + label,
    );
  }
  await expect(
    page.getByRole("button", { name: "保存存储位置并检查空间", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: /我合法拥有 Minecraft Java Edition/ }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("button", { name: "从官方源下载游戏与资源", exact: true }),
  ).toBeDisabled();
  for (const theme of ["浅色", "深色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    for (const width of [375, 800, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
});

test("desktop setup and directory changes use bounded actions with explicit ownership", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const calls: unknown[] = [];
    Object.assign(window, {
      isTauri: true,
      __calls: calls,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "default_workspace") return "/fixture/bundled-source";
          if (command === "system_accent") return "#3478D4";
          if (command === "workbench_action") {
            calls.push(args);
            if (args.action === "bootstrap")
              return {
                workspace: "/fixture/bundled-source",
                config: "",
                configFields: {},
                exportOptions: "",
                output: "/fixture/builds",
                jobs: [],
                storage: {
                  cache: "/fixture/cache",
                  builds: "/fixture/builds",
                  jobs: "/fixture/jobs",
                  rust: "/fixture/rust",
                },
                setup: { state: "ready", message: "工具链已校验" },
              };
            if (args.action === "save-storage") return { ready: true };
            if (args.action === "setup-start")
              return { state: "ready", message: "下载请求已记录" };
          }
          return null;
        },
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(page.getByLabel("编译缓存目录", { exact: true })).toHaveValue(
    "/fixture/cache",
  );
  await page
    .getByLabel("Rust 缓存目录", { exact: true })
    .fill("/fixture/other-rust");
  await page
    .getByRole("button", { name: "保存存储位置并检查空间", exact: true })
    .click();
  await expect(page.getByText(/现有数据未迁移/)).toBeVisible();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const owned = page.getByRole("checkbox", {
    name: /我合法拥有 Minecraft Java Edition/,
  });
  await owned.check();
  await page
    .getByRole("button", { name: "从官方源下载游戏与资源", exact: true })
    .click();
  await expect(owned).not.toBeChecked();
  const calls = await page.evaluate(
    () =>
      (
        window as unknown as {
          __calls: {
            action: string;
            request: { fields?: Record<string, unknown> };
          }[];
        }
      ).__calls,
  );
  expect(
    calls.find((c) => c.action === "save-storage")?.request.fields?.rust,
  ).toBe("/fixture/other-rust");
  expect(
    calls.find((c) => c.action === "setup-start")?.request.fields?.owned,
  ).toBe(true);
});

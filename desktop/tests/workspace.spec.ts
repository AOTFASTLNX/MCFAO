import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
const report = JSON.parse(
  execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
    encoding: "utf8",
  }),
);
async function importReport(page: Page, value: unknown = report) {
  await page.locator("input[type=file]").setInputFiles({
    name: "preflight.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(value)),
  });
}
test("client grading filters combine with categories and keep selection independent", async ({
  page,
}) => {
  await page.goto("/");
  const extra = [
    {
      path: "mods/required.jar",
      origin: "manifest",
      category: "mods",
      optional: false,
      status: "available",
    },
    {
      path: "mods/optional.jar",
      origin: "manifest",
      category: "mods",
      optional: true,
      status: "available",
    },
    {
      path: "mods/server.jar",
      origin: "manifest",
      category: "mods",
      optional: false,
      status: "server_only",
    },
    {
      path: "mods/disabled.jar.disabled",
      origin: "overrides",
      category: "mods",
      optional: false,
      status: "disabled",
    },
    {
      path: "resourcepacks/optional.zip",
      origin: "manifest",
      category: "resourcepacks",
      optional: true,
      status: "available",
    },
  ].map((r) => ({
    ...r,
    id: r.origin + ":" + r.path,
    selectable: r.status === "available",
    default_selected: r.status === "available" && !r.optional,
    bytes: 10,
    file_count: 1,
  }));
  await importReport(page, {
    ...report,
    resources: [...report.resources, ...extra],
  });
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  const grades = page.locator(".resource-tiers");
  await grades.getByRole("button", { name: /^客户端可选/ }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(2);
  await page
    .locator(".resource-categories")
    .first()
    .getByRole("button", { name: /^Mod/ })
    .click();
  await expect(page.getByRole("checkbox")).toHaveCount(1);
  await page.getByRole("button", { name: "保留当前列表", exact: true }).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await grades.getByRole("button", { name: /^客户端必需/ }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(1);
  await page.getByRole("checkbox").uncheck();
  await expect(
    page.getByText("已排除 1 项客户端必需资源，可能导致依赖缺失或启动失败。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "恢复必需资源", exact: true }).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await grades.getByRole("button", { name: /^待确认/ }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(report.resources.length);
  await grades.getByRole("button", { name: /^仅服务端/ }).click();
  await expect(page.getByRole("checkbox")).toBeDisabled();
  await grades.getByRole("button", { name: /^不可导入/ }).click();
  await expect(page.getByRole("checkbox")).toBeDisabled();
  for (const theme of ["浅色", "深色"]) {
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page
      .getByRole("button", { name: "构建 IPA", exact: true })
      .first()
      .click();
    for (const width of [375, 800, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
});
test("resource management is a real fifth step with persisted per-file choices", async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1000 });
  await page.goto("/");
  const extra = [
    {
      id: "manifest:mods/optional.jar",
      path: "mods/optional.jar",
      origin: "manifest",
      category: "mods",
      optional: true,
    },
    {
      id: "overrides:resourcepacks/textures.zip",
      path: "resourcepacks/textures.zip",
      origin: "overrides",
      category: "resourcepacks",
      optional: false,
    },
    {
      id: "overrides:shaderpacks/lighting.zip",
      path: "shaderpacks/lighting.zip",
      origin: "overrides",
      category: "shaderpacks",
      optional: false,
    },
  ].map((r) => ({
    ...r,
    status: "available",
    selectable: true,
    default_selected: !r.optional,
    bytes: 1024,
    file_count: 1,
  }));
  await importReport(page, {
    ...report,
    resources: [...report.resources, ...extra],
  });
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "管理整合包资源" }),
  ).toBeVisible();
  const optional = page.getByRole("checkbox", {
    name: "保留 mods/optional.jar（清单下载）",
    exact: true,
  });
  await expect(optional).not.toBeChecked();
  await optional.check();
  await page.getByRole("button", { name: /^光影包/ }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(1);
  await expect(page.getByRole("checkbox")).toBeChecked();
  await page.getByRole("button", { name: "排除当前列表", exact: true }).click();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await page.getByRole("button", { name: /^材质包/ }).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await page
    .locator(".resource-categories")
    .first()
    .getByRole("button", { name: /^全部/ })
    .click();
  await page.getByLabel("搜索资源").fill("optional");
  await expect(optional).toBeChecked();
  const saved = await page.evaluate(
    () =>
      JSON.parse(localStorage.getItem("fabricaot.builder.v2")!)
        .resourceSelection,
  );
  expect(saved.included).toContain("manifest:mods/optional.jar");
  expect(saved.included).not.toContain("overrides:shaderpacks/lighting.zip");
  await page.getByRole("button", { name: "5 确认构建", exact: true }).click();
  await expect(
    page.getByText("保留 3 / 4 项资源", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel("最近导入").selectOption(report.source);
  await page.getByRole("button", { name: "2 资源管理", exact: true }).click();
  await expect(optional).toBeChecked();
  await page.setViewportSize({ width: 375, height: 1000 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("new workbench prioritizes a guided IPA build and exposes browser limits", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "选择要构建的游戏内容" }),
  ).toBeVisible();
  await expect(page.getByText("FROM YOUR MAC TO YOUR IPHONE")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "选择 .mrpack", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "准备你的构建环境" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("imports a real report, shows diagnostics and persists sources", async ({
  page,
}) => {
  await page.goto("/");
  await importReport(page);
  await expect(page.getByText("静态检查通过", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "查看兼容性与诊断详情" }).click();
  await page.getByRole("button", { name: /查看 Mod 列表/ }).click();
  await page.locator(".mod-item summary").click();
  await expect(
    page.getByText("fabricaot_ui_fixture · 1.0.0", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("未测试", { exact: true }).first()).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出报告", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("fabricaot-preflight.json");
  await page.reload();
  await expect(page.getByLabel("最近导入").locator("option")).toHaveCount(2);
  await page.getByLabel("最近导入").selectOption(report.source);
  await expect(page.getByText("静态检查通过", { exact: true })).toBeVisible();
});
test("Loader mismatch can be forced and records the choice in review", async ({
  page,
}) => {
  await page.goto("/");
  await importReport(page, { ...report, fabric_loader_version: "0.19.2" });
  const next = page.getByRole("button", { name: "下一步", exact: true });
  const force = page.getByRole("checkbox", { name: /强制编译/ });
  await expect(next).toBeEnabled();
  await force.check();
  await expect(next).toBeEnabled();
  await force.uncheck();
  await expect(next).toBeEnabled();
  await force.check();
  await next.click();
  await expect(
    page.getByRole("heading", { name: "管理整合包资源" }),
  ).toBeVisible();
  await next.click();
  await expect(
    page.getByRole("heading", { name: "准备你的构建环境" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "5 确认构建", exact: true }).click();
  await expect(
    page.getByText("强制编译 · Fabric Loader 0.19.3", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel("最近导入").selectOption(report.source);
  await expect(force).not.toBeChecked();
  await expect(next).toBeEnabled();
});
test("Mod list searches every file and filters statuses with per-file reasons", async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1000 });
  await page.goto("/");
  await importReport(page, {
    ...report,
    mod_inventory: [
      ...report.mod_inventory,
      {
        path: "mods/remote-search.jar",
        origin: "manifest",
        status: "pending_download",
        findings: [],
      },
      {
        path: "mods/optional.jar",
        origin: "manifest",
        status: "skipped_optional",
        findings: [],
      },
      {
        path: "mods/server.jar",
        origin: "manifest",
        status: "server_only",
        findings: [],
      },
      {
        path: "mods/broken.jar",
        origin: "embedded",
        status: "unreadable",
        findings: [
          {
            severity: "error",
            code: "INVALID_MOD_JAR",
            message: "broken.jar: invalid archive",
          },
        ],
      },
      {
        path: "mods/off.jar.disabled",
        origin: "local",
        status: "disabled",
        findings: [],
      },
    ],
  });
  const toggle = page.getByRole("button", { name: /查看 Mod 列表/ });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".mod-item")).toHaveCount(6);
  await page.getByLabel("搜索 Mod", { exact: true }).fill("remote-search");
  await expect(page.locator(".mod-item")).toHaveCount(1);
  await page.locator(".mod-item summary").click();
  await expect(
    page.getByText("ID / 版本待读取", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("未测试", { exact: true })).toBeVisible();
  await page.getByLabel("搜索 Mod", { exact: true }).fill("");
  await page.getByLabel("筛选 Mod 状态").selectOption("unreadable");
  await page.locator(".mod-item summary").click();
  await expect(
    page.getByText("broken.jar: invalid archive", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Mixin 需要构建期转换", { exact: false }),
  ).not.toBeVisible();
  await page.getByLabel("搜索 Mod", { exact: true }).fill("nothing-here");
  await expect(
    page.getByText("没有匹配的 Mod，请尝试其他关键词或选择全部状态。"),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("large Mod list loads more and remains usable on a narrow window", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 1000 });
  await page.goto("/");
  await importReport(page, {
    ...report,
    mods: [],
    mod_inventory: Array.from({ length: 65 }, (_, i) => ({
      path: "mods/long-file-name-" + i + ".jar",
      origin: "manifest",
      status: "pending_download",
      findings: [],
    })),
  });
  await page.getByRole("button", { name: /查看 Mod 列表/ }).click();
  await expect(page.locator(".mod-item")).toHaveCount(50);
  await page.getByRole("button", { name: /显示更多/ }).click();
  await expect(page.locator(".mod-item")).toHaveCount(65);
  await page.getByLabel("搜索 Mod", { exact: true }).fill("long-file-name-64");
  await expect(page.locator(".mod-item")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("blocked source never enables advancing or building", async ({ page }) => {
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
  await expect(page.getByText("需要处理", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: /强制编译/ }).check();
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "5 确认构建", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "构建 IPA", exact: true }).last(),
  ).toBeDisabled();
  await expect(page.getByText("来源存在阻断问题，请先处理。")).toBeVisible();
});
test("vanilla form reaches review, validates team and never generates shell commands", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page
    .getByLabel("FabricAOT 项目目录", { exact: true })
    .fill("/local/repo");
  await page.getByLabel("构建配置", { exact: true }).fill("/local/config.json");
  await page.getByLabel("构建产物目录", { exact: true }).fill("/local/builds");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByLabel("Apple Team ID").fill("BAD");
  await page
    .getByLabel("IPA 导出配置", { exact: true })
    .fill("/local/ExportOptions.plist");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByText("Team ID 需要 10 位大写字母或数字。"),
  ).toBeVisible();
  await expect(
    page.getByText("请在 FabricAOT 桌面应用中执行构建。"),
  ).toBeVisible();
  await expect(page.getByText("--prepare-only")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "2 构建环境", exact: true }).click();
  await expect(page.getByLabel("构建配置", { exact: true })).toHaveValue(
    "/local/config.json",
  );
});
test("corrupt storage remains intact until explicit keyboard-accessible reset", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("fabricaot.builder.v2", "bad-json"),
  );
  await page.goto("/");
  await expect(
    page.getByText(
      "本地记录无法读取，自动保存已暂停。请先在设置中导出原始记录。",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("fabricaot.builder.v2")),
  ).toBe("bad-json");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "重置界面记录", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "重置界面记录", exact: true }),
  ).toBeFocused();
});
for (const width of [375, 768, 1280, 1440])
  test("responsive layout " + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "选择要构建的游戏内容" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "构建记录", exact: true }).click();
    await expect(page.getByText("还没有构建任务", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });

test("theme toggle switches every surface and survives a reload", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  const root = page.locator("html");
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "切换为浅色模式" }).click();
  await expect(root).toHaveAttribute("data-theme", "light");
  await expect(
    page.getByRole("button", { name: "切换为深色模式" }),
  ).toHaveAttribute("aria-pressed", "true");
  const surfaces = await page.evaluate(() => {
    const background = (selector: string) =>
      getComputedStyle(document.querySelector(selector)!).backgroundColor;
    return {
      shell: background(".sidebar"),
      panel: background(".builder-panel"),
      colorScheme: getComputedStyle(document.documentElement).colorScheme,
    };
  });
  expect(surfaces.colorScheme).toBe("light");
  expect(surfaces.shell).toBe("rgb(236, 237, 239)");
  expect(surfaces.panel).toBe("rgb(255, 255, 255)");
  await page.getByRole("button", { name: "构建记录", exact: true }).click();
  await expect(page.locator(".job-list-panel")).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "浅色", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "深色", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "跟随系统", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("light theme keeps narrow layouts free of horizontal overflow", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("fabricaot.theme.v1", "light"),
  );
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await expect(page.getByRole("group", { name: "外观主题" })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("system accent setting reaches interactive tokens only", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("fabricaot.theme.v1", "light"),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("交互强调色").selectOption("#8B83CB");
  await expect(page.getByLabel("交互强调色")).toHaveValue("#8B83CB");
  const accent = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--accent"),
  );
  expect(accent.trim()).toBe("#716aa5");
  await page.reload();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByLabel("交互强调色")).toHaveValue("#8B83CB");
});

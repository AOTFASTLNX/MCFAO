import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
const report = JSON.parse(
  execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
    encoding: "utf8",
  }),
);
/** Instance name shown in the recent-source menu (see sourceName). */
const reportName: string = report.pack_name;
async function importReport(page: Page, value: unknown = report) {
  await page.locator("input[type=file]").setInputFiles({
    name: "preflight.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(value)),
  });
}
/** Open the page-drawn popup button and pick a row by its visible label. */
async function pick(page: Page, label: string, option: string) {
  const trigger = page.getByRole("button", { name: label, exact: true });
  await trigger.click();
  await page
    .getByRole("listbox", { name: label, exact: true })
    .getByRole("option", { name: option, exact: true })
    .click();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
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
      JSON.parse(localStorage.getItem("ncl.builder.v2")!)
        .resourceSelection,
  );
  expect(saved.included).toContain("manifest:mods/optional.jar");
  expect(saved.included).not.toContain("overrides:shaderpacks/lighting.zip");
  await page.getByRole("button", { name: "5 确认构建", exact: true }).click();
  await expect(
    page.getByText("保留 3 / 4 项资源", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await pick(page, "最近导入", reportName);
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
  expect((await download).suggestedFilename()).toBe("ncl-preflight.json");
  await page.reload();
  await page.getByRole("button", { name: "最近导入", exact: true }).click();
  await expect(
    page.getByRole("listbox", { name: "最近导入" }).getByRole("option"),
  ).toHaveCount(2);
  await page.keyboard.press("Escape");
  await pick(page, "最近导入", reportName);
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
  await expect(
    page.getByText("此来源中的 Mod 已完成构建期代码审计"),
  ).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: /代码审计/ })).toHaveCount(0);
  await page.reload();
  await pick(page, "最近导入", reportName);
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
  await pick(page, "筛选 Mod 状态", "读取失败（1）");
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
    .getByLabel("NCL 项目目录", { exact: true })
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
    page.getByText("请在 NCL Builder 桌面应用中执行构建。"),
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

test("theme setting switches every surface and survives a reload", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  const root = page.locator("html");
  await expect(root).toHaveAttribute("data-theme", "dark");
  // The top bar no longer carries a toggle; appearance lives in settings.
  await expect(page.locator(".theme-toggle")).toHaveCount(0);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "浅色", exact: true }).click();
  await expect(root).toHaveAttribute("data-theme", "light");
  await expect(
    page.getByRole("button", { name: "浅色", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const surfaces = await page.evaluate(() => {
    const background = (selector: string) =>
      getComputedStyle(document.querySelector(selector)!).backgroundColor;
    return {
      shell: background(".sidebar"),
      colorScheme: getComputedStyle(document.documentElement).colorScheme,
    };
  });
  expect(surfaces.colorScheme).toBe("light");
  expect(surfaces.shell).toBe("rgb(231, 232, 233)");
  await page.getByRole("button", { name: "构建记录", exact: true }).click();
  // History sits on the window surface and separates its two regions with a
  // divider instead of wrapping them in a card.
  await expect(page.locator(".job-list-panel")).toHaveCSS(
    "background-color",
    "rgba(0, 0, 0, 0)",
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
    localStorage.setItem("ncl.theme.v1", "light"),
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
    localStorage.setItem("ncl.theme.v1", "light"),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await pick(page, "交互强调色", "紫色");
  await expect(
    page.getByRole("button", { name: "交互强调色", exact: true }),
  ).toHaveText("紫色");
  const accent = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--accent"),
  );
  expect(accent.trim()).toBe("#716aa5");
  await page.reload();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "交互强调色", exact: true }),
  ).toHaveText("紫色");
});

const layerSurfaces = {
  sidebar: ".sidebar",
  window: "body",
  raised: ".stepper",
  card: ".segmented button.selected",
} as const;

async function measureLayers(page: import("@playwright/test").Page, theme: string) {
  await page.addInitScript(
    (value) => localStorage.setItem("ncl.theme.v1", value),
    theme,
  );
  await page.goto("/");
  await page.getByRole("button", { name: "构建 IPA", exact: true }).click();
  await page.locator(".builder-panel").waitFor();
  return page.evaluate((selectors) => {
    const lightness = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error("missing surface " + selector);
      const color = getComputedStyle(element).backgroundColor;
      const match = color.match(/rgba?\(([^)]+)\)/);
      if (!match) throw new Error("unresolved background " + color);
      const [r, g, b] = match[1]
        .split(",")
        .slice(0, 3)
        .map((value) => Number(value.trim()) / 255);
      return Math.round(((Math.max(r, g, b) + Math.min(r, g, b)) / 2) * 100);
    };
    return Object.fromEntries(
      Object.entries(selectors).map(([key, selector]) => [key, lightness(selector)]),
    );
  }, layerSurfaces);
}

test("neutral layers step by three percent without decorative borders", async ({
  page,
}) => {
  const light = await measureLayers(page, "light");
  expect(light.sidebar).toBe(91);
  expect(light.window - light.sidebar).toBe(3);
  expect(light.raised - light.window).toBe(3);
  expect(light.card - light.raised).toBe(3);

  const dark = await measureLayers(page, "dark");
  expect(dark.window - dark.sidebar).toBe(3);
  expect(dark.raised - dark.window).toBe(3);
  expect(dark.card - dark.raised).toBe(3);
  expect(dark.card).toBeLessThan(50);

  const borders = await page.evaluate(() => {
    const width = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error("missing surface " + selector);
      const style = getComputedStyle(element);
      return [
        style.borderTopWidth,
        style.borderRightWidth,
        style.borderBottomWidth,
        style.borderLeftWidth,
      ];
    };
    return {
      sidebar: width(".sidebar"),
      topbar: width(".topbar"),
      panel: width(".builder-panel"),
      stepper: width(".stepper"),
    };
  });
  for (const edges of Object.values(borders)) {
    expect(edges).toEqual(["0px", "0px", "0px", "0px"]);
  }
});

test("text keeps WCAG AA contrast on every neutral layer", async ({ page }) => {
  for (const theme of ["light", "dark"]) {
    await page.addInitScript(
      (value) => localStorage.setItem("ncl.theme.v1", value),
      theme,
    );
    await page.goto("/");
    await page.getByRole("button", { name: "构建 IPA", exact: true }).click();
    await page.locator(".builder-panel").waitFor();
    const ratios = await page.evaluate(() => {
      const channel = (value: number) => {
        const c = value / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      const luminance = (color: string) => {
        const match = color.match(/rgba?\(([^)]+)\)/);
        if (!match) throw new Error("unresolved color " + color);
        const [r, g, b] = match[1]
          .split(",")
          .slice(0, 3)
          .map((value) => Number(value.trim()));
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
      };
      const contrast = (a: string, b: string) => {
        const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
        return (hi + 0.05) / (lo + 0.05);
      };
      const style = getComputedStyle(document.documentElement);
      const text = style.getPropertyValue("--text").trim();
      const muted = style.getPropertyValue("--muted").trim();
      const dim = style.getPropertyValue("--dim").trim();
      const surfaces = [
        ".sidebar",
        "body",
        ".stepper",
        ".segmented button.selected",
      ].map(
        (selector) =>
          getComputedStyle(document.querySelector(selector)!).backgroundColor,
      );
      const probe = document.createElement("div");
      document.body.append(probe);
      const resolve = (token: string) => {
        probe.style.color = token;
        return getComputedStyle(probe).color;
      };
      const result = surfaces.map((surface) => ({
        surface,
        text: contrast(resolve(text), surface),
        muted: contrast(resolve(muted), surface),
        dim: contrast(resolve(dim), surface),
      }));
      probe.remove();
      return result;
    });
    for (const row of ratios) {
      expect(row.text).toBeGreaterThanOrEqual(4.5);
      expect(row.muted).toBeGreaterThanOrEqual(4.5);
      expect(row.dim).toBeGreaterThanOrEqual(4.5);
    }
  }
});

test("builder fills the window without an aside or a card outline", async ({
  page,
}) => {
  await page.goto("/");
  const layout = await page.evaluate(() => {
    const panel = document.querySelector(".builder-panel")!;
    const style = getComputedStyle(panel);
    const content = document.querySelector(".main-content")!;
    return {
      aside: document.querySelectorAll(".build-aside, .aside-checklist").length,
      targetCard: document.querySelectorAll(".target-card").length,
      background: style.backgroundColor,
      borders: [
        style.borderTopWidth,
        style.borderRightWidth,
        style.borderBottomWidth,
        style.borderLeftWidth,
      ],
      widthRatio:
        panel.getBoundingClientRect().width /
        content.getBoundingClientRect().width,
    };
  });
  expect(layout.aside).toBe(0);
  expect(layout.targetCard).toBe(0);
  expect(layout.background).toBe("rgba(0, 0, 0, 0)");
  expect(layout.borders).toEqual(["0px", "0px", "0px", "0px"]);
  expect(layout.widthRatio).toBeGreaterThan(0.9);
});

test("settings place labels left of controls without a wrapping card", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  // Pages cross-fade before mounting, so wait for the settings surface.
  await expect(page.locator(".settings-page")).toBeVisible();

  // The page sits on the window surface; only text inputs keep a card look.
  const shell = await page.evaluate(() => {
    const pageRoot = document.querySelector(".settings-page")!;
    const style = getComputedStyle(pageRoot);
    return {
      cards: pageRoot.querySelectorAll(".panel, .builder-panel").length,
      background: style.backgroundColor,
      border: style.borderTopWidth,
    };
  });
  expect(shell.cards).toBe(0);
  expect(shell.background).toBe("rgba(0, 0, 0, 0)");
  expect(shell.border).toBe("0px");

  const rows = await page.evaluate(() => {
    const rect = (element: Element) => element.getBoundingClientRect();
    return Array.from(document.querySelectorAll(".setting-row")).map(
      (row) => {
        const label = row.querySelector(".setting-label")!;
        const control = row.querySelector(
          ".setting-control, .theme-options",
        )!;
        const a = rect(label);
        const b = rect(control);
        return {
          labelRight: a.right,
          controlLeft: b.left,
          sameLine: Math.abs(a.top + a.height / 2 - (b.top + b.height / 2)) < 14,
        };
      },
    );
  });
  expect(rows.length).toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.controlLeft).toBeGreaterThan(row.labelRight);
    expect(row.sameLine).toBe(true);
  }
});

test("popup menus animate, close on outside click and work from the keyboard", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const trigger = page.getByRole("button", { name: "交互强调色", exact: true });
  // The closed list stays mounted so it can transition; it is aria-hidden then.
  const popup = page.locator(".accent-setting .select-popup");

  await expect(popup).toBeHidden();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  const motion = await popup.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      duration: style.transitionDuration,
      opacity: style.opacity,
    };
  });
  expect(motion.opacity).toBe("0");
  expect(motion.duration).toMatch(/0\.1[46]s/);

  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(popup).toBeVisible();
  await expect(trigger.locator("svg")).toHaveCSS("transform", /matrix/);

  await page.mouse.click(4, 4);
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(popup).toBeHidden();

  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  await expect(popup).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(popup).toBeHidden();
  await expect(trigger).toHaveText("蓝色");

  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Escape");
  await expect(popup).toBeHidden();
  await expect(trigger).toHaveText("蓝色");
});

test("no page repeats a marketing footer under the content", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  for (const name of ["构建 IPA", "构建记录", "环境与资源", "设置"]) {
    await page.getByRole("button", { name, exact: true }).first().click();
    await expect(page.locator(".page-footer")).toHaveCount(0);
    await expect(page.getByText("内容由你掌控", { exact: false })).toHaveCount(0);
    await expect(page.getByText("Fabric Only", { exact: false })).toHaveCount(0);
  }
});

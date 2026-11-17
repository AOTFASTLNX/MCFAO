import { test, expect, type Page } from "@playwright/test";

async function desktop(page: Page) {
  await page.addInitScript(() => {
    const GiB = 1024 ** 3;
    const state = {
      calls: [] as Record<string, unknown>[],
      blocked: false,
      fail: false,
      cleaned: false,
      directory: "/fixture/Unified Storage",
      saveFail: false,
    };
    const roots = {
      cache: "/Volumes/Build/cache",
      builds: "/fixture/builds",
      jobs: "/fixture/jobs",
      rust: "/Volumes/Build/rust",
    };
    const form = {
      workspace: "/fixture/source",
      config: "",
      output: roots.builds,
      python: "",
      exportOptions: "",
      source: "",
      loader: "vanilla",
      unsigned: true,
    };
    localStorage.setItem("ncl.builder.v2", JSON.stringify(form));
    const plan = () => ({
      status: "STORAGE_PLAN",
      dataRoot: "/fixture",
      freeBytes: 64 * GiB,
      reclaimBytes: state.cleaned || state.blocked ? 0 : 14 * GiB,
      managedBytes: (state.cleaned ? 36 : 50) * GiB,
      scannedAt: "2026-11-17T12:30:00Z",
      blocked: state.blocked,
      reason: state.blocked
        ? "自定义目录支持占用统计与 Finder 管理，暂不提供自动清理。"
        : "",
      warnings: [],
      volumes: [
        {
          id: "system",
          path: "/",
          totalBytes: 256 * GiB,
          freeBytes: 80 * GiB,
          managedBytes: 13 * GiB,
          otherBytes: 163 * GiB,
          roles: ["builds", "jobs"],
        },
        {
          id: "external",
          path: "/Volumes/Build",
          totalBytes: 128 * GiB,
          freeBytes: 64 * GiB,
          managedBytes: 37 * GiB,
          otherBytes: 27 * GiB,
          roles: ["cache", "rust"],
        },
      ],
      usage: Object.entries(roots).map(([role, path]) => ({
        role,
        path,
        bytes:
          ({
            cache: state.cleaned ? 22 : 32,
            builds: state.cleaned ? 8 : 12,
            jobs: 1,
            rust: 5,
          }[role] || 0) * GiB,
        volumeId: ["cache", "rust"].includes(role) ? "external" : "system",
        available: true,
        itemCount: role === "cache" ? 20 : 1,
        items: [
          {
            path: path + (role === "cache" ? "/toolchains" : "/example"),
            bytes: 1 * GiB,
          },
        ],
      })),
      groups:
        state.blocked || state.cleaned
          ? []
          : [
              {
                id: "cache",
                label: "编译缓存",
                detail: "重新下载后可恢复。",
                bytes: 10 * GiB,
                count: 1,
                items: [
                  {
                    path: roots.cache + "/upstream",
                    bytes: 10 * GiB,
                    reason: "工具链缓存",
                  },
                ],
              },
              {
                id: "intermediates",
                label: "构建中间产物",
                detail: "清理后需要重新编译。",
                bytes: 4 * GiB,
                count: 1,
                items: [
                  {
                    path: roots.builds + "/failed/aot",
                    bytes: 4 * GiB,
                    reason: "AOT 对象",
                  },
                ],
              },
            ],
    });
    Object.assign(window, {
      isTauri: true,
      __storageTest: state,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "default_workspace") return form.workspace;
          if (command === "system_accent") return "#3478D4";
          state.calls.push({ command, ...args });
          if (command === "reveal_path") return null;
          if (command === "plugin:dialog|open") return state.directory;
          if (command !== "workbench_action") return null;
          if (args.action === "bootstrap")
            return { ...form, configFields: {}, jobs: [], storage: roots };
          if (args.action === "storage-plan") {
            if (state.fail) throw new Error("磁盘已断开，请重新连接");
            return plan();
          }
          if (args.action === "storage-clean") {
            state.cleaned = true;
            return { freedBytes: 10 * GiB };
          }
          if (args.action === "storage-change-plan") {
            const paths = (args.request as any).fields.paths;
            return {
              token: "fixture-token",
              paths,
              rows: Object.entries(roots).map(([role, source]) => ({
                role,
                source,
                destination: paths[role],
                bytes: GiB,
                count: 2,
              })),
            };
          }
          if (args.action === "storage-change-apply") {
            if (state.saveFail) throw new Error("所选目录不可写");
            return { ready: true, pathMappings: {}, warnings: [] };
          }
          if (args.action === "history") return [];
          if (args.action === "reset-storage")
            return { ready: true, storage: roots };
          if (args.action === "save-storage") {
            if (state.saveFail) throw new Error("所选目录不可写");
            return { ready: true };
          }
          return null;
        },
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(
    page.getByText("Builder 文件占用", { exact: true }),
  ).toBeVisible();
}

test("sidebar page shows storage distribution, disk filters, largest directories and Finder action", async ({
  page,
}, info) => {
  await desktop(page);
  await expect(page.locator(".sm-stats")).toContainText("50.0 GiB");
  await expect(page.locator(".sm-categories > button")).toHaveCount(4);
  await page.getByRole("button", { name: /Build.*64.0 GiB 可用/ }).click();
  await expect(page.locator(".sm-categories > button")).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: "编译缓存", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "编译缓存目录明细" }),
  ).toContainText("最大的 12 项");
  await page
    .getByRole("button", { name: "在 Finder 中显示 toolchains" })
    .click();
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.find(
          (c: any) => c.command === "reveal_path",
        )?.path,
    ),
  ).toBe("/Volumes/Build/cache/toolchains");
  await page.getByRole("button", { name: "显示全部磁盘" }).click();
  await page.getByRole("button", { name: /构建产物.*12.0 GiB/ }).click();
  await expect(
    page.getByRole("region", { name: "构建产物目录明细" }),
  ).toContainText("/fixture/builds");
  for (const theme of ["浅色", "深色"]) {
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "存储位置", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "磁盘空间", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.getByRole("button", { name: "存储管理", exact: true }).click();
    for (const width of [1440, 800, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: info.outputPath(`storage-${theme}-${width}.png`),
        fullPage: width === 375,
      });
    }
  }
});

test("cleanup is opt-in, previews exact selection, traps focus, cancels and refreshes after confirmation", async ({
  page,
}) => {
  await desktop(page);
  await expect(
    page.getByRole("button", { name: "清理所选", exact: true }),
  ).toBeDisabled();
  await page.getByRole("checkbox", { name: /编译缓存.*10.0 GiB/ }).check();
  await page.getByText("查看 1 项清理明细", { exact: true }).first().click();
  await expect(
    page.getByText("/Volumes/Build/cache/upstream", { exact: false }).first(),
  ).toBeVisible();
  await expect(page.locator(".sm-cleanup-footer")).toContainText("10.0 GiB");
  await page.getByRole("button", { name: "清理所选", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "清理磁盘空间？" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "取消", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.filter(
          (c: any) => c.action === "storage-clean",
        ).length,
    ),
  ).toBe(0);
  await page.getByRole("button", { name: "清理所选", exact: true }).click();
  await dialog
    .getByRole("button", { name: "删除并释放空间", exact: true })
    .click();
  await expect(page.locator(".sm-stats")).toContainText("36.0 GiB");
  await expect(
    page.getByText("已释放 10.0 GiB", { exact: true }).first(),
  ).toBeVisible();
  const selected = await page.evaluate(
    () =>
      (window as any).__storageTest.calls.find(
        (c: any) => c.action === "storage-clean",
      )?.request.fields.groups,
  );
  expect(selected).toEqual(["cache"]);
});

test("read-only directories and failed rescans show specific reasons", async ({
  page,
}) => {
  await desktop(page);
  await page.evaluate(() => {
    (window as any).__storageTest.blocked = true;
  });
  await page.getByRole("button", { name: "重新扫描", exact: true }).click();
  await expect(
    page.getByText("自定义目录支持占用统计与 Finder 管理，暂不提供自动清理。", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "清理所选", exact: true }),
  ).toBeDisabled();
  await page.evaluate(() => {
    (window as any).__storageTest.fail = true;
  });
  await page.getByRole("button", { name: "重新扫描", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("磁盘已断开");
  await expect(
    page.getByRole("button", { name: "重新扫描", exact: true }),
  ).toBeEnabled();
});

test("quick directory confirms before picker, saves all roles and updates output", async ({
  page,
}) => {
  await desktop(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const quick = page.getByRole("button", {
    name: "快速选择储存目录",
    exact: true,
  });
  await quick.click();
  const dialog = page.getByRole("dialog", { name: "覆盖当前储存设置？" });
  await expect(dialog).toContainText(
    "此操作会覆盖当前已有的储存设置，是否继续？",
  );
  await expect(
    dialog.getByRole("button", { name: "取消", exact: true }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.filter(
          (c: any) => c.command === "plugin:dialog|open",
        ).length,
    ),
  ).toBe(0);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await quick.click();
  await dialog.getByRole("button", { name: "继续选择目录" }).click();
  const handling = page.getByRole("dialog", { name: "如何处理已有文件？" });
  await expect(handling).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.filter(
          (c: any) => c.action === "storage-change-apply",
        ).length,
    ),
  ).toBe(0);
  await handling.getByRole("radio", { name: /保留原位/ }).check();
  await handling.getByRole("button", { name: "应用所选方式" }).click();
  await expect(page.getByRole("status")).toContainText(
    "储存设置已更新。已有文件保留原位。",
  );
  const fields = await page.evaluate(
    () =>
      (window as any).__storageTest.calls.find(
        (c: any) => c.action === "storage-change-apply",
      )?.request.fields.paths,
  );
  expect(fields).toEqual({
    cache: "/fixture/Unified Storage/cache",
    builds: "/fixture/Unified Storage/builds",
    jobs: "/fixture/Unified Storage/jobs",
    rust: "/fixture/Unified Storage/rust",
  });
  expect(
    await page.evaluate(
      () => JSON.parse(localStorage.getItem("ncl.builder.v2")!).output,
    ),
  ).toBe("/fixture/Unified Storage/builds");
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(page.getByLabel("编译缓存目录", { exact: true })).toHaveValue(
    fields.cache,
  );
});

test("cancelled picker and rejected save preserve previous storage paths", async ({
  page,
}) => {
  await desktop(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.evaluate(() => {
    (window as any).__storageTest.directory = null;
  });
  await page
    .getByRole("button", { name: "快速选择储存目录", exact: true })
    .click();
  await page.getByRole("button", { name: "继续选择目录" }).click();
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.filter(
          (c: any) => c.action === "save-storage",
        ).length,
    ),
  ).toBe(0);
  await page.evaluate(() => {
    Object.assign((window as any).__storageTest, {
      directory: "/fixture/new",
      saveFail: true,
    });
  });
  await page
    .getByRole("button", { name: "快速选择储存目录", exact: true })
    .click();
  await page.getByRole("button", { name: "继续选择目录" }).click();
  const handling = page.getByRole("dialog", { name: "如何处理已有文件？" });
  await handling.getByRole("radio", { name: /保留原位/ }).check();
  await handling.getByRole("button", { name: "应用所选方式" }).click();
  await expect(handling.getByRole("alert")).toContainText("所选目录不可写");
  await handling.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(page.getByLabel("编译缓存目录", { exact: true })).toHaveValue(
    "/Volumes/Build/cache",
  );
});

for (const policy of ["migrate", "delete"] as const)
  test(`directory policy ${policy} requires explicit selection before apply`, async ({
    page,
  }) => {
    await desktop(page);
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page
      .getByRole("button", { name: "快速选择储存目录", exact: true })
      .click();
    await page.getByRole("button", { name: "继续选择目录" }).click();
    let dialog = page.getByRole("dialog", { name: "如何处理已有文件？" });
    await expect(
      dialog.getByRole("button", { name: "应用所选方式" }),
    ).toBeDisabled();
    await dialog
      .getByRole("radio", {
        name: policy === "migrate" ? /迁移已有文件/ : /删除已有文件/,
      })
      .check();
    await dialog.getByRole("button", { name: "应用所选方式" }).click();
    if (policy === "delete") {
      dialog = page.getByRole("dialog", { name: "删除已有文件？" });
      await expect(dialog).toContainText("包括构建产物、IPA、缓存和任务记录");
      expect(
        await page.evaluate(
          () =>
            (window as any).__storageTest.calls.filter(
              (c: any) => c.action === "storage-change-apply",
            ).length,
        ),
      ).toBe(0);
      await dialog
        .getByRole("button", { name: "删除原文件并切换目录" })
        .click();
    }
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(
      await page.evaluate(
        () =>
          (window as any).__storageTest.calls.find(
            (c: any) => c.action === "storage-change-apply",
          )?.request.fields.policy,
      ),
    ).toBe(policy);
  });

test("reset directory settings confirms and restores paths without deleting files", async ({
  page,
}) => {
  await desktop(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const reset = page.getByRole("button", { name: "重置目录设置", exact: true });
  await reset.click();
  const dialog = page.getByRole("dialog", { name: "重置目录设置？" });
  await expect(dialog).toContainText("已有文件保留原位");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.filter(
          (call: any) => call.action === "reset-storage",
        ).length,
    ),
  ).toBe(0);
  await reset.click();
  await dialog.getByRole("button", { name: "恢复默认目录" }).click();
  await expect(page.getByRole("status")).toContainText("已恢复默认目录设置");
  expect(
    await page.evaluate(
      () =>
        (window as any).__storageTest.calls.filter(
          (call: any) => call.action === "reset-storage",
        ).length,
    ),
  ).toBe(1);
  expect(
    await page.evaluate(
      () => JSON.parse(localStorage.getItem("ncl.builder.v2")!).output,
    ),
  ).toBe("/fixture/builds");
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(page.getByLabel("编译缓存目录", { exact: true })).toHaveValue(
    "/Volumes/Build/cache",
  );
});

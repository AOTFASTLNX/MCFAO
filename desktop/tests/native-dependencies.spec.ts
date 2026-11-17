import { test, expect, type Page } from "@playwright/test";

async function desktop(page: Page) {
  await page.addInitScript(() => {
    const names: Record<string, string> = {
      glfw: "GLFW-lite",
      lwjgl: "LWJGL-lite",
      gl41: "OSMesa / MoltenVK",
      lwjglOpengl: "LWJGL OpenGL shim",
      metal: "Metal 后端",
      openal: "OpenAL Soft",
      shaders: "着色器",
    };
    const deps: Record<string, string[]> = {
      lwjgl: ["glfw"],
      lwjglOpengl: ["gl41"],
      metal: ["glfw", "lwjgl"],
    };
    const form = {
      workspace: "/fixture/source",
      config: "/fixture/config.json",
      output: "/fixture/builds",
      python: "",
      exportOptions: "",
      loader: "vanilla",
      unsigned: true,
      source: "",
      forceCompile: false,
      team: "",
      resourceSelection: null,
    };
    localStorage.setItem("ncl.builder.v2", JSON.stringify(form));
    const state = {
      calls: [] as Record<string, unknown>[],
      state: "running",
      job: null as Record<string, unknown> | null,
    };
    const inventory = () => ({
      ready: false,
      checkedAt: "2026-11-17T00:00:00Z",
      libraries: Object.entries(names).map(([key, name]) => ({
        key,
        name,
        path:
          key === "metal"
            ? ""
            : state.state === "succeeded" && key === "glfw"
              ? "/Volumes/K/artifacts/graphics/dependencies-20261117/glfw"
              : "/fixture/old-" + key,
        builtAt: "2026-11-16T12:00:00Z",
        target: "arm64-apple-ios17.0",
        timeBasis: "build",
        state:
          key === "glfw"
            ? state.state === "succeeded"
              ? "current"
              : "stale"
            : key === "lwjgl"
              ? "stale"
              : key === "metal"
                ? "missing"
                : key === "shaders"
                  ? "invalid"
                  : "current",
        changedFiles:
          key === "glfw" && state.state !== "succeeded"
            ? ["ios/glfw-lite/glfw_lite.c"]
            : [],
        reasons: key === "lwjgl" ? ["GLFW-lite 哈希已变更，待重建"] : [],
        dependsOn: deps[key] ?? [],
        required: !["metal", "shaders"].includes(key),
        mode: key === "gl41" ? "fetch" : "build",
      })),
    });
    Object.assign(window, {
      isTauri: true,
      __dependencyTest: state,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "default_workspace") return form.workspace;
          if (command === "system_accent") return "#3478D4";
          if (command !== "workbench_action") return null;
          state.calls.push(args);
          if (args.action === "bootstrap")
            return { ...form, configFields: {}, jobs: [] };
          if (args.action === "dependencies") return inventory();
          if (args.action === "start") {
            state.state = "running";
            state.job = {
              id: (state.job ? "b" : "a").repeat(32),
              kind: "dependencies",
              name: "原生依赖库重建",
              state: "queued",
              stage: "dependency-glfw",
              startedAt: "2026-11-17T00:00:00Z",
              folder: "/fixture/job",
              build: "/Volumes/K/artifacts/graphics/dependencies-20261117",
              request: args.request,
              error: "",
            };
            return state.job;
          }
          if (args.action === "status" || args.action === "cancel") {
            if (args.action === "cancel") state.state = "cancelled";
            return {
              ...state.job,
              state: state.state,
              stage:
                state.state === "succeeded"
                  ? "dependencies-complete"
                  : "dependency-glfw",
              log: "first-party compiler output\nGLFW compiling",
              dependencyProgress: { completed: 0, total: 2 },
              error:
                state.state === "failed"
                  ? "clang fixture failure: preserved original configuration"
                  : "",
              ...(state.state === "succeeded"
                ? {
                    configFields: {
                      glfw: "/Volumes/K/artifacts/graphics/dependencies-20261117/glfw",
                    },
                  }
                : {}),
            };
          }
          return null;
        },
      },
    });
  });
  await page.goto("/");
}

test("inventory lists seven dependencies, changed files and four states in both themes", async ({
  page,
}, testInfo) => {
  await desktop(page);
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
  const manager = page.getByRole("region", { name: "原生依赖库管理" });
  await expect(manager.getByRole("heading", { level: 3 })).toHaveText([
    "GLFW-lite",
    "LWJGL-lite",
    "OSMesa / MoltenVK",
    "LWJGL OpenGL shim",
    "Metal 后端",
    "OpenAL Soft",
    "着色器",
  ]);
  await expect(page.getByTestId("dependency-glfw")).toContainText(
    "ios/glfw-lite/glfw_lite.c",
  );
  await expect(page.getByTestId("dependency-glfw")).toContainText("已过期");
  await expect(page.getByTestId("dependency-metal")).toContainText("缺失");
  await expect(page.getByTestId("dependency-shaders")).toContainText(
    "校验失败",
  );
  await expect(page.getByTestId("dependency-gl41")).toContainText("一致");
  await expect(page.getByTestId("dependency-gl41")).toContainText(
    "重新获取并校验哈希",
  );
  await page.screenshot({
    path: testInfo.outputPath("native-dependencies.png"),
  });
  for (const theme of ["浅色", "深色"]) {
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.getByRole("button", { name: "环境与资源", exact: true }).click();
    await page.setViewportSize({ width: 800, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("individual rebuild uses start/status/cancel and marks LWJGL stale after GLFW success", async ({
  page,
}) => {
  await desktop(page);
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
  await page
    .getByRole("button", { name: "重建 GLFW-lite", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "依赖库重建任务" }),
  ).toContainText("GLFW compiling");
  const keys = await page.evaluate(() => {
    const s = (
      window as unknown as {
        __dependencyTest: {
          calls: { action: string; request: { dependencyKeys: string[] } }[];
        };
      }
    ).__dependencyTest;
    return s.calls.find((c) => c.action === "start")?.request.dependencyKeys;
  });
  expect(keys).toEqual(["glfw"]);
  await page.evaluate(() => {
    (
      window as unknown as { __dependencyTest: { state: string } }
    ).__dependencyTest.state = "succeeded";
  });
  await expect(
    page.getByText("构建配置已切换到新目录。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("dependency-glfw")).toContainText(
    "dependencies-20261117/glfw",
  );
  await expect(page.getByTestId("dependency-lwjgl")).toContainText("待重建");
  await page
    .getByRole("button", { name: "重建 LWJGL-lite", exact: true })
    .click();
  await page.getByRole("button", { name: "取消重建", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "依赖库重建任务" }),
  ).toContainText("已取消");
});

test("whole rebuild follows dependency order and failed task keeps old paths with reason", async ({
  page,
}) => {
  await desktop(page);
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
  await page
    .getByRole("button", { name: "按顺序整体重建", exact: true })
    .click();
  const keys = await page.evaluate(() => {
    const s = (
      window as unknown as {
        __dependencyTest: {
          calls: { action: string; request: { dependencyKeys: string[] } }[];
        };
      }
    ).__dependencyTest;
    return s.calls.find((c) => c.action === "start")?.request.dependencyKeys;
  });
  expect(keys).toEqual([
    "glfw",
    "lwjgl",
    "gl41",
    "lwjglOpengl",
    "metal",
    "openal",
    "shaders",
  ]);
  await page.evaluate(() => {
    (
      window as unknown as { __dependencyTest: { state: string } }
    ).__dependencyTest.state = "failed";
  });
  await expect(
    page.getByRole("alert").filter({ hasText: "clang fixture failure" }),
  ).toBeVisible();
  await expect(page.getByTestId("dependency-glfw")).toContainText(
    "/fixture/old-glfw",
  );
  await expect(
    page.getByText("构建配置已切换到新目录。", { exact: true }),
  ).toHaveCount(0);
});

test("wizard rejects stale dependencies before IPA start and offers one-click rebuild", async ({
  page,
}) => {
  await desktop(page);
  await page.getByRole("button", { name: "4 确认构建", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "原生依赖预检" }),
  ).toContainText("ios/glfw-lite/glfw_lite.c");
  await page
    .getByRole("button", { name: "构建 IPA", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("region", { name: "原生依赖库管理" }),
  ).toBeVisible();
  const count = await page.evaluate(
    () =>
      (
        window as unknown as {
          __dependencyTest: { calls: { action: string }[] };
        }
      ).__dependencyTest.calls.filter((c) => c.action === "start").length,
  );
  expect(count).toBe(0);
  await page
    .getByRole("button", { name: "一键重建所需依赖", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "依赖库重建任务" }),
  ).toBeVisible();
});

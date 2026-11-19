import { test, expect, type Page } from "@playwright/test";

async function desktop(page: Page, config: string) {
  await page.addInitScript((configValue) => {
    const form = {
      workspace: "/fixture/source",
      config: configValue,
      output: "/fixture/builds",
      python: "",
      exportOptions: "/fixture/ExportOptions.plist",
      loader: "vanilla",
      unsigned: true,
      source: "",
      forceCompile: false,
      team: "",
      resourceSelection: null,
    };
    localStorage.setItem("ncl.builder.v2", JSON.stringify(form));
    // This suite starts after the separate first-launch flow.
    localStorage.setItem("ncl.onboarding.v1", JSON.stringify({ version: 1, accepted: true, storageRoot: "/fixture", completed: true }));
    Object.assign(window, {
      isTauri: true,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "account_action") return { configured: true, verified: true, profile: { id: "a".repeat(32), name: "FixturePlayer" }, verifiedAt: Date.now() / 1000, verifiedUntil: Date.now() / 1000 + 3600 };
          if (command === "default_workspace") return form.workspace;
          if (command === "system_accent") return "#3478D4";
          if (command !== "workbench_action") return null;
          if (args.action === "bootstrap")
            return {
              ...form,
              configFields: {},
              jobs: [],
              storage: {
                cache: "/fixture/cache",
                builds: "/fixture/builds",
                jobs: "/fixture/jobs",
                rust: "/fixture/rust",
              },
            };
          if (args.action === "dependencies")
            return { ready: true, checkedAt: "", libraries: [] };
          return null;
        },
      },
    });
  }, config);
  await page.goto("/");
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
}

test("missing build configuration greys the environment actions and names the cause", async ({
  page,
}, testInfo) => {
  await desktop(page, "");
  const detect = page.getByRole("button", { name: "检测环境", exact: true });
  const rebuild = page.getByRole("button", {
    name: "按顺序整体重建",
    exact: true,
  });
  await expect(detect).toBeDisabled();
  await expect(rebuild).toHaveCount(0);
  await page.locator(".environment-disclosure summary").filter({ hasText: "原生依赖库" }).click();
  await expect(rebuild).toBeDisabled();
  await expect(page.getByText("自动准备完成后即可检测环境。")).toBeVisible();
  await expect(detect).toHaveAttribute("title", /构建环境尚未准备/);
  await expect(
    page.getByRole("button", { name: "选择配置文件", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "一键下载并准备" })).toBeEnabled();

  const disabled = await detect.evaluate((element) => {
    const style = getComputedStyle(element);
    const root = getComputedStyle(document.documentElement);
    const probe = document.createElement("div");
    probe.style.background = "var(--accent)";
    document.body.append(probe);
    const accent = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return {
      background: style.backgroundColor,
      accent,
      accentToken: root.getPropertyValue("--accent").trim(),
      cursor: style.cursor,
    };
  });
  expect(disabled.cursor).toBe("not-allowed");
  // The accent surface must be gone; a filled accent pill still reads as a
  // live action even when the DOM rejects the click.
  expect(disabled.background).not.toBe(disabled.accent);
  expect(disabled.accentToken).toBeTruthy();

  for (const theme of ["浅色", "深色"]) {
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.getByRole("button", { name: "环境与资源", exact: true }).click();
    const colour = await detect.evaluate((element) => {
      const probe = document.createElement("div");
      probe.style.background = "var(--accent)";
      document.body.append(probe);
      const accent = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return {
        background: getComputedStyle(element).backgroundColor,
        accent,
      };
    });
    expect(colour.background).not.toBe(colour.accent);
    await page.screenshot({
      path: testInfo.outputPath(`disabled-${theme}.png`),
      fullPage: false,
    });
  }
});

test("a configured workspace keeps the environment actions enabled", async ({
  page,
}) => {
  await desktop(page, "/fixture/config.json");
  const detect = page.getByRole("button", { name: "检测环境", exact: true });
  await expect(detect).toBeEnabled();
  await expect(page.getByText("自动准备完成后即可检测环境。")).toHaveCount(0);
  const accent = await detect.evaluate((element) => {
    const probe = document.createElement("div");
    probe.style.background = "var(--accent)";
    document.body.append(probe);
    const token = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return {
      background: getComputedStyle(element).backgroundColor,
      token,
    };
  });
  expect(accent.background).toBe(accent.token);
});

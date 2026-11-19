import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

async function install(
  page: Page,
  options: {
    configured?: boolean;
    complete?: boolean;
    files?: boolean;
    account?: boolean;
    resume?: boolean;
    refreshFails?: boolean;
    verificationDeferred?: boolean;
    localTesting?: boolean;
  } = {},
) {
  await page.addInitScript((options) => {
    const profile = { id: "a".repeat(32), name: "FirstPlayer" };
    const snapshot = (name = "FirstPlayer") => ({
      configured: options.configured !== false,
      verified: true,
      profile: { ...profile, name },
      verifiedAt: Date.now() / 1000,
      verifiedUntil: Date.now() / 1000 + 3600,
    });
    const state = {
      verified:
        !!options.account ||
        sessionStorage.getItem("onboarding-fixture-account") === "verified",
      name: "FirstPlayer",
      directory: "/fixture/NCL Data",
      files: !!options.files,
      failure: "",
      pending: false,
      ready: false,
      saved: 0,
      opened: 0,
      calls: [] as string[],
      setupState: "",
    };
    if (!sessionStorage.getItem("onboarding-fixture-seeded")) {
      if (options.complete || options.resume)
        localStorage.setItem(
          "ncl.onboarding.v1",
          JSON.stringify({
            version: 1,
            accepted: true,
            storageRoot: options.complete ? "/fixture/NCL Data" : "",
            completed: !!options.complete,
            verificationDeferred: !!options.verificationDeferred,
          }),
        );
      sessionStorage.setItem("onboarding-fixture-seeded", "true");
    }
    Object.assign(window, {
      isTauri: true,
      __onboardingTest: state,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: any) => {
          if (command === "default_workspace") return "/fixture/source";
          if (command === "system_accent") return "#2f6fbe";
          if (command === "open_account_login") {
            state.opened++;
            return null;
          }
          if (command === "account_action") {
            state.calls.push("account:" + args.action);
            if (options.localTesting) {
              if (args.action !== "status") throw new Error("本地测试版无需登录");
              return { configured: false, verified: false, profile: null, loginRequired: false };
            }
            if (["status", "refresh", "cancel"].includes(args.action)) {
              if (args.action === "refresh" && options.refreshFails)
                throw new Error("暂时无法连接账号验证服务");
              if (args.action === "cancel") state.pending = false;
              return state.verified
                ? snapshot(state.name)
                : {
                    configured: options.configured !== false,
                    verified: false,
                    profile: null,
                  };
            }
            if (args.action === "begin") {
              state.pending = true;
              return {
                userCode: "ABCD1234",
                verificationUrl: "https://www.microsoft.com/link",
                interval: 0.1,
                expiresAt: Date.now() / 1000 + 900,
              };
            }
            if (args.action === "poll") {
              if (state.failure) throw new Error(state.failure);
              return state.ready
                ? { ready: true }
                : { pending: true, interval: 0.1 };
            }
            if (args.action === "commit") {
              state.verified = true;
              sessionStorage.setItem("onboarding-fixture-account", "verified");
              state.name =
                state.verified && options.account
                  ? "SecondPlayer"
                  : "FirstPlayer";
              return snapshot(state.name);
            }
          }
          if (command === "plugin:dialog|open") return state.directory;
          if (command === "workbench_action") {
            state.calls.push(args.action);
            if (args.action === "setup-start") {
              if ((!state.verified && !options.localTesting) || args.request.fields?.owned !== true)
                throw new Error("正版资格未验证");
              state.setupState = "running";
              return { state: "running", message: "正在下载并校验工具链" };
            }
            if (args.action === "setup-status")
              return state.setupState === "ready"
                ? { state: "ready", config: "/fixture/NCL Data/jobs/setup/config.json" }
                : { state: state.setupState || "idle", message: "正在下载并校验工具链" };
            if (args.action === "storage-change-plan")
              return {
                token: "plan",
                paths: args.request.fields.paths,
                rows: ["cache", "builds", "jobs", "rust"].map((role) => ({
                  role,
                  source: "/old/" + role,
                  destination: args.request.fields.paths[role],
                  bytes: state.files ? 1024 : 0,
                  count: state.files ? 1 : 0,
                })),
              };
            if (args.action === "storage-change-apply") {
              state.saved++;
              return { ready: true };
            }
            if (args.action === "bootstrap")
              return {
                workspace: "/fixture/source",
                config: state.setupState === "ready" ? "/fixture/NCL Data/jobs/setup/config.json" : "",
                setup: state.setupState === "running" ? { state: "running" } : undefined,
                exportOptions: "",
                output: "/fixture/builds",
                configFields: {},
                jobs: [],
              };
            if (args.action === "history") return [];
          }
          return null;
        },
      },
    });
  }, options);
}
async function patch(page: Page, value: Record<string, unknown>) {
  await page.evaluate(
    (value) => Object.assign((window as any).__onboardingTest, value),
    value,
  );
}
async function accept(page: Page) {
  await page.getByRole("button", { name: "了解并继续" }).click();
  await expect(
    page.getByRole("heading", { name: "登录你的正版账号" }),
  ).toBeVisible();
}
async function signIn(page: Page) {
  await page
    .getByRole("button", { name: "使用 Microsoft 账号登录", exact: true })
    .click();
  await expect(page.getByLabel("登录验证码")).toHaveText("ABCD1234");
  await patch(page, { ready: true });
  await expect(
    page.getByText("Minecraft Java Edition · 正版资格已验证", { exact: true }),
  ).toBeVisible();
}
const evidence = (name: string) =>
  path.resolve("../artifacts/desktop/onboarding", name);
async function capture(page: Page, name: string) {
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (animation) =>
            animation.effect?.getComputedTiming().iterations !== Infinity,
        )
        .map((animation) => animation.finished.catch(() => undefined)),
    );
  });
  await page.screenshot({ path: evidence(name), fullPage: true });
}

test("first launch completes four gated steps once, persists paths and places accounts first", async ({
  page,
}) => {
  await install(page);
  await page.goto("/");
  await expect(page.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "1",
  );
  await expect(
    page.getByText(/不以任何形式直接分发修改后的游戏文件/),
  ).toBeVisible();
  await capture(page, "01-disclosure-light.png");
  await accept(page);
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await signIn(page);
  await capture(page, "02-account-light.png");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "为构建留出空间" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  await expect(page.getByText("已选择储存目录", { exact: true })).toBeVisible();
  await capture(page, "03-storage-light.png");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "初步配置已完成" }),
  ).toBeVisible();
  await capture(page, "04-complete-light.png");
  expect(
    await page.evaluate(
      () => JSON.parse(localStorage.getItem("ncl.onboarding.v1")!).completed,
    ),
  ).toBe(false);
  await page.getByRole("button", { name: "上一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "为构建留出空间" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "稍后下载", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  expect(
    await page.evaluate(() => (window as any).__onboardingTest.saved),
  ).toBe(1);
  expect(
    await page.evaluate(
      () => JSON.parse(localStorage.getItem("ncl.builder.v2")!).output,
    ),
  ).toBe("/fixture/NCL Data/builds");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(
    page.locator(".settings-group").first().getByRole("heading"),
  ).toHaveText("账号管理");
  await expect(
    page.getByRole("button", { name: "切换账号", exact: true }),
  ).toBeVisible();
  await capture(page, "05-settings-light.png");
  await page.reload();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
});

test("missing publisher configuration permits explicit temporary skip and remembers it", async ({
  page,
}) => {
  await install(page, { configured: false });
  await page.goto("/");
  await accept(page);
  await expect(page.getByText(/登录服务待配置/)).toBeVisible();
  await capture(page, "02-login-unconfigured-light.png");
  await expect(
    page.getByRole("button", { name: "使用 Microsoft 账号登录" }),
  ).toBeDisabled();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "登录你的正版账号" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("navigation", { name: "主导航" })).toHaveCount(0);
  await page.getByRole("button", { name: "暂时跳过正版验证" }).click();
  await expect(
    page.getByRole("heading", { name: "为构建留出空间" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByText("正版验证已暂时跳过", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Minecraft Java Edition · 正版资格已验证", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "开始使用" }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
});

test("failed qualification and cancellation cannot advance or save initial configuration", async ({
  page,
}) => {
  await install(page, { resume: true });
  await page.goto("/");
  await patch(page, { failure: "未验证到 Minecraft Java Edition 正版资格" });
  await page.getByRole("button", { name: "使用 Microsoft 账号登录" }).click();
  await expect(page.getByRole("alert")).toContainText("未验证到");
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await patch(page, { failure: "" });
  await page.getByRole("button", { name: "使用 Microsoft 账号登录" }).click();
  await page.getByRole("button", { name: "取消登录" }).click();
  await expect(page.getByLabel("登录验证码")).toHaveCount(0);
  expect(
    await page.evaluate(() => (window as any).__onboardingTest.saved),
  ).toBe(0);
});

test("a configured account that fails verification can still defer explicitly", async ({
  page,
}) => {
  await install(page, { configured: true });
  await page.goto("/");
  await accept(page);
  await patch(page, { failure: "Minecraft 服务拒绝了本应用的登录请求（HTTP 403）" });
  await page.getByRole("button", { name: "使用 Microsoft 账号登录" }).click();
  await expect(page.getByRole("alert")).toContainText("403");
  await expect(
    page.getByRole("button", { name: "下一步", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "暂时跳过正版验证" }).click();
  await expect(
    page.getByRole("heading", { name: "为构建留出空间" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByText("正版验证已暂时跳过", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Minecraft Java Edition · 正版资格已验证", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "开始使用" }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
});

test("existing files reuse the storage policy dialog and cancelling the picker never saves", async ({
  page,
}) => {
  await install(page, { resume: true, account: true, files: true });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "为构建留出空间" }),
  ).toBeVisible();
  await patch(page, { directory: null });
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  expect(
    await page.evaluate(() => (window as any).__onboardingTest.saved),
  ).toBe(0);
  await patch(page, { directory: "/fixture/NCL Data" });
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading")).toHaveText("如何处理已有文件？");
  await dialog.getByRole("radio", { name: /保留原位/ }).check();
  await dialog.getByRole("button", { name: "应用所选方式" }).click();
  await expect(dialog).toHaveCount(0);
  expect(
    await page.evaluate(() => (window as any).__onboardingTest.saved),
  ).toBe(1);
});

test("account switching preserves the old identity on failure and replaces it only after verification", async ({
  page,
}) => {
  await install(page, { complete: true, account: true });
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await patch(page, { failure: "未验证到正版资格" });
  await page.getByRole("button", { name: "切换账号", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("未验证到");
  await expect(page.getByText("FirstPlayer", { exact: true })).toBeVisible();
  await patch(page, { failure: "", ready: true });
  await page.getByRole("button", { name: "切换账号", exact: true }).click();
  await expect(page.getByText("SecondPlayer", { exact: true })).toBeVisible();
});

test("a completed guide requires native verification even with a forged completion flag", async ({
  page,
}) => {
  await install(page, { complete: true });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "验证账号后继续" }),
  ).toBeVisible();
  await expect(page.getByRole("navigation", { name: "主导航" })).toHaveCount(0);
});

test("failed session refresh retains identity and permits a new login", async ({
  page,
}) => {
  await install(page, { complete: true, account: true, refreshFails: true });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "验证账号后继续" }),
  ).toBeVisible();
  await expect(page.getByText("FirstPlayer", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("暂时无法连接");
  await expect(
    page.getByRole("button", { name: "使用 Microsoft 账号登录", exact: true }),
  ).toBeEnabled();
});

test("corrupt saved build settings cannot crash the guide or be overwritten by directory selection", async ({
  page,
}) => {
  await install(page, { resume: true, account: true });
  await page.addInitScript(() =>
    localStorage.setItem("ncl.builder.v2", "{broken"),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "为构建留出空间" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("现有构建设置无法读取");
  expect(
    await page.evaluate(() => localStorage.getItem("ncl.builder.v2")),
  ).toBe("{broken");
  expect(
    await page.evaluate(() => (window as any).__onboardingTest.saved),
  ).toBe(0);
});

for (const theme of ["light", "dark"] as const)
  test(`${theme} guide fits minimum window and small preview with reduced motion`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
    await install(page, { account: true });
    await page.goto("/");
    for (const width of [375, 800, 1100]) {
      await page.setViewportSize({ width, height: 760 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await expect(
        page.getByRole("button", { name: "了解并继续" }),
      ).toBeVisible();
    }
    await capture(page, `01-disclosure-${theme}-minimum.png`);
    await accept(page);
    await page.getByRole("button", { name: "下一步", exact: true }).click();
    await page.getByRole("button", { name: "选择目录", exact: true }).click();
    await page.getByRole("button", { name: "下一步", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "初步配置已完成" }),
    ).toBeFocused();
    await capture(page, `04-complete-${theme}-minimum.png`);
    expect(
      await page
        .locator(".onboarding-progress > span")
        .evaluate((element) => getComputedStyle(element).transitionDuration),
    ).toBe("0s");
  });

test("the step after storage can start preparation and the workbench resumes it", async ({ page }) => {
  await install(page, { resume: true, account: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "为构建留出空间" })).toBeVisible();
  await expect(page.getByRole("button", { name: "一键下载并准备" })).toHaveCount(0);
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  await expect(page.getByText("已选择储存目录", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "一键下载并准备" }).click();
  await expect(page.getByText("正在下载并校验工具链")).toBeVisible();
  await page.getByRole("button", { name: "开始使用", exact: true }).click();
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
  await patch(page, { setupState: "ready" });
  await expect(page.getByRole("button", { name: "重新检查并准备" })).toBeVisible();
  await expect.poll(() => page.evaluate(
    () => JSON.parse(localStorage.getItem("ncl.builder.v2")!).config,
  )).toBe("/fixture/NCL Data/jobs/setup/config.json");
});

test("environment preparation offers login and adopts the generated configuration", async ({ page }) => {
  await install(page, { complete: true, verificationDeferred: true });
  await page.goto("/");
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
  const setup = page.getByRole("region", { name: "自动准备构建环境" });
  await expect(page.getByRole("button", { name: "选择配置文件" })).toHaveCount(0);
  await expect(setup.getByRole("button", { name: "一键下载并准备" })).toHaveCount(0);
  await setup.getByRole("button", { name: "使用 Microsoft 账号登录" }).click();
  await expect(setup.getByLabel("登录验证码")).toHaveText("ABCD1234");
  await patch(page, { ready: true });
  await setup.getByRole("button", { name: "一键下载并准备" }).click();
  await expect(setup.getByText("正在下载并校验工具链")).toBeVisible();
  const detect = page.getByRole("button", { name: "检测环境", exact: true });
  await expect(detect).toBeDisabled();
  await patch(page, { setupState: "ready" });
  await expect(detect).toBeEnabled();
  await expect(setup.getByText("构建配置已自动生成并保存，可以开始构建。")).toBeVisible();
  await expect.poll(() => page.evaluate(
    () => JSON.parse(localStorage.getItem("ncl.builder.v2")!).config,
  )).toBe("/fixture/NCL Data/jobs/setup/config.json");
});

test("the local test package skips account verification and prepares a configuration", async ({ page }) => {
  await install(page, { localTesting: true });
  await page.goto("/");
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "3");
  await expect(page.getByText("正版登录", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "了解并继续" }).click();
  await expect(page.getByRole("heading", { name: "为构建留出空间" })).toBeVisible();
  await page.getByRole("button", { name: "选择目录", exact: true }).click();
  await expect(page.getByText("已选择储存目录", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "一键下载并准备" }).click();
  await expect(page.getByText("正在下载并校验工具链")).toBeVisible();
  await page.getByRole("button", { name: "开始使用", exact: true }).click();
  await page.getByRole("button", { name: "环境与资源", exact: true }).click();
  await patch(page, { setupState: "ready" });
  await expect(page.getByRole("button", { name: "检测环境", exact: true })).toBeEnabled();
  const calls: string[] = await page.evaluate(() => (window as any).__onboardingTest.calls);
  expect(calls.filter((action) => action.startsWith("account:"))).toEqual(["account:status"]);
  expect(calls).toContain("setup-start");
});

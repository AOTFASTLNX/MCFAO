import { test, expect, type Page } from "@playwright/test";
import type { AotCompatibility } from "../src/workflow";

async function openBuilder(page: Page) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "选择要构建的游戏内容" }),
  ).toBeVisible();
}

test("step selection is one moving layer and settles on the chosen step", async ({
  page,
}) => {
  await openBuilder(page);
  const stepper = page.locator(".stepper");
  await expect(stepper.locator(".motion-indicator")).toHaveCount(1);

  const origin = await stepper.locator(".motion-indicator").boundingBox();
  await page.getByRole("button", { name: "5 确认构建", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "准备好，开始构建。" }),
  ).toBeVisible();
  // Only the active row keeps its selected colour once the transition ends.
  await expect(stepper).toHaveAttribute("data-motion-moving", "false");
  await expect(stepper.locator(".motion-indicator")).toHaveAttribute(
    "data-moving",
    "false",
  );
  const target = await page.locator('.step[data-step-index="4"]').boundingBox();
  const indicator = await stepper.locator(".motion-indicator").boundingBox();
  expect(Math.abs(indicator!.x - target!.x)).toBeLessThan(1.5);
  expect(Math.abs(indicator!.width - target!.width)).toBeLessThan(1.5);
  expect(origin!.x).toBeLessThan(target!.x);

  // The moving block is the selected surface; rows stay transparent so the
  // block can travel between them without a second fading background.
  const backgrounds = await page
    .locator(".step")
    .evaluateAll((rows) =>
      rows.map((row) => getComputedStyle(row).backgroundColor),
    );
  expect(new Set(backgrounds)).toEqual(new Set(["rgba(0, 0, 0, 0)"]));
});

test("rapid step switching keeps one coherent selection and direction", async ({
  page,
}) => {
  await openBuilder(page);
  const steps = page.locator(".step");
  await steps.nth(4).click();
  await steps.nth(1).click();
  await steps.nth(3).click();
  await steps.nth(0).click();
  await expect(
    page.getByRole("heading", { name: "选择要构建的游戏内容" }),
  ).toBeVisible();
  await expect(page.locator(".stepper")).toHaveAttribute(
    "data-motion-moving",
    "false",
  );
  await expect(page.locator(".step.current")).toHaveCount(1);
  await expect(page.locator(".step.current")).toContainText("游戏内容");
  await expect(page.locator(".stepper .motion-indicator")).toHaveCount(1);
});

test("forward and back step content use opposite sides", async ({ page }) => {
  await openBuilder(page);
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  const body = page.locator(".step-body");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(body).toHaveAttribute("data-phase", /out|in/);
  await expect(
    page.getByRole("heading", { name: "准备你的构建环境" }),
  ).toBeVisible();
  await expect(body).toHaveAttribute("data-phase", "idle");
  await page.getByRole("button", { name: "上一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "选择要构建的游戏内容" }),
  ).toBeVisible();
  await expect(body).toHaveAttribute("data-direction", "none");
});

test("step counter and sidebar selection stay in one place", async ({
  page,
}) => {
  await openBuilder(page);
  const counter = page.locator(".wizard-count");
  const before = await counter.boundingBox();
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(counter).toHaveAttribute("aria-label", "第 2 步，共 4 步");
  const after = await counter.boundingBox();
  expect(Math.abs(after!.x - before!.x)).toBeLessThan(1.5);
  expect(Math.abs(after!.width - before!.width)).toBeLessThan(1.5);

  const nav = page.locator(".sidebar nav");
  await expect(nav.locator(".motion-indicator")).toHaveCount(1);
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(nav).toHaveAttribute("data-motion-moving", "false");
  const active = await page
    .locator(".sidebar nav .nav-item.selected")
    .boundingBox();
  const layer = await nav.locator(".motion-indicator").boundingBox();
  expect(Math.abs(layer!.y - active!.y)).toBeLessThan(1.5);
  // The block remains the visible selected surface after the move settles.
  expect(
    await nav
      .locator(".motion-indicator")
      .evaluate((el) => getComputedStyle(el).opacity),
  ).toBe("1");
});

test("reduced motion removes travel while keeping state visible", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openBuilder(page);
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "准备你的构建环境" }),
  ).toBeVisible();
  const body = page.locator(".step-body");
  await expect(body).toHaveAttribute("data-phase", "idle");
  expect(await body.evaluate((el) => getComputedStyle(el).transform)).toBe(
    "none",
  );
  await expect(page.locator(".step.current")).toHaveCount(1);
  await expect(page.locator(".wizard-count")).toHaveAttribute(
    "aria-label",
    "第 2 步，共 4 步",
  );
});

test("keyboard shortcut changes steps with the same transition", async ({
  page,
}) => {
  await openBuilder(page);
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await page.locator(".builder-panel").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Alt+ArrowRight");
  await expect(
    page.getByRole("heading", { name: "准备你的构建环境" }),
  ).toBeVisible();
  await page.keyboard.press("Alt+ArrowLeft");
  await expect(
    page.getByRole("heading", { name: "选择要构建的游戏内容" }),
  ).toBeVisible();
});

test("page changes cross-fade without horizontal travel", async ({ page }) => {
  await openBuilder(page);
  const column = page.locator(".page-column");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  // The destination is reached with a fade; the surface never travels.
  await expect(page.getByText("外观主题", { exact: true })).toBeVisible();
  await expect(column).toHaveAttribute("data-phase", "idle");
  expect(await column.evaluate((el) => getComputedStyle(el).transform)).toBe(
    "none",
  );
  expect(await column.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
});

test("page cross-fade dims out and eases back in over time", async ({
  page,
}) => {
  await openBuilder(page);
  await page.evaluate(() => {
    const column = document.querySelector<HTMLElement>(".page-column")!;
    const start = performance.now();
    const samples: { t: number; opacity: number; phase: string }[] = [];
    (window as unknown as { __fade: typeof samples }).__fade = samples;
    const timer = window.setInterval(() => {
      samples.push({
        t: performance.now() - start,
        opacity: Number(getComputedStyle(column).opacity),
        phase: column.dataset.phase ?? "",
      });
      if (performance.now() - start > 1000) window.clearInterval(timer);
    }, 16);
  });
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByText("外观主题", { exact: true })).toBeVisible();
  await page.waitForTimeout(900);
  const samples = await page.evaluate(
    () =>
      (
        window as unknown as {
          __fade: { t: number; opacity: number; phase: string }[];
        }
      ).__fade,
  );
  const lowest = Math.min(...samples.map((s) => s.opacity));
  const dipped = samples.find((s) => s.opacity < 0.5);
  expect(lowest).toBeLessThan(0.05);
  expect(dipped).toBeTruthy();
  // The fade occupies a visible interval instead of a single frame.
  const dimming = samples.filter(
    (s) => s.opacity > 0.05 && s.opacity < 0.95,
  ).length;
  expect(dimming).toBeGreaterThan(3);
  expect(samples.at(-1)!.opacity).toBe(1);
});

test("sidebar selection block travels through intermediate positions", async ({
  page,
}) => {
  await openBuilder(page);
  const nav = page.locator(".sidebar nav");
  await page.evaluate(() => {
    const block = document.querySelector<HTMLElement>(
      ".sidebar nav .motion-indicator",
    )!;
    const start = performance.now();
    const samples: number[] = [];
    (window as unknown as { __positions: number[] }).__positions = samples;
    const timer = window.setInterval(() => {
      samples.push(block.getBoundingClientRect().top);
      if (performance.now() - start > 800) window.clearInterval(timer);
    }, 16);
  });
  await page.getByRole("button", { name: "存储管理", exact: true }).click();
  await expect(page.locator(".storage-page")).toBeVisible();
  await page.waitForTimeout(700);
  const positions = await page.evaluate(
    () => (window as unknown as { __positions: number[] }).__positions,
  );
  const first = positions[0];
  const last = positions.at(-1)!;
  const intermediate = positions.filter(
    (p) => Math.abs(p - first) > 1 && Math.abs(p - last) > 1,
  );
  expect(last).toBeGreaterThan(first);
  expect(intermediate.length).toBeGreaterThan(3);
  expect(
    await nav
      .locator(".motion-indicator")
      .evaluate((el) => getComputedStyle(el).opacity),
  ).toBe("1");
});

test("hovering a nav row or step never shifts its contents sideways", async ({
  page,
}) => {
  await openBuilder(page);
  const navRow = page.locator(".sidebar nav .nav-item").nth(1);
  const navLabel = await navRow.locator("svg").boundingBox();
  await navRow.hover();
  const hovered = await navRow.locator("svg").boundingBox();
  expect(hovered!.x).toBe(navLabel!.x);
  const next = page.locator('.wizard-footer .primary[data-action="next"]');
  const arrow = await next.locator("svg").boundingBox();
  await next.hover();
  const arrowHovered = await next.locator("svg").boundingBox();
  expect(arrowHovered!.x).toBe(arrow!.x);
});

test("game type switch moves a single plate without overlapping content", async ({
  page,
}) => {
  await openBuilder(page);
  const segmented = page.locator(".segmented");
  const fabric = await segmented.locator(".segment-plate").boundingBox();
  const fabricLabel = await page
    .getByRole("button", { name: "Fabric 整合包", exact: true })
    .boundingBox();
  // The plate is the selected label's own box: same position, same width, so
  // its caps stay parallel to the pill-shaped labels underneath.
  expect(fabric!.x).toBe(fabricLabel!.x);
  expect(fabric!.width).toBe(fabricLabel!.width);
  await page.getByRole("button", { name: "原版 26.1.2", exact: true }).click();
  await expect(segmented).toHaveAttribute("data-selection", "vanilla");
  // React can publish the new selection before the pulse effect starts.
  // Wait for actual movement so the initial idle flag cannot satisfy the check.
  await expect
    .poll(
      async () => (await segmented.locator(".segment-plate").boundingBox())!.x,
    )
    .toBeGreaterThan(fabric!.x);
  await expect(segmented).toHaveAttribute("data-motion-moving", "false");
  const vanilla = await segmented.locator(".segment-plate").boundingBox();
  expect(vanilla!.x).toBeGreaterThan(fabric!.x);
  expect(vanilla!.width).toBe(fabric!.width);
  const vanillaLabel = await page
    .getByRole("button", { name: "原版 26.1.2", exact: true })
    .boundingBox();
  expect(vanilla!.x).toBe(vanillaLabel!.x);
  const radii = await segmented.evaluate((element) => {
    const radius = (node: Element) =>
      Number.parseFloat(getComputedStyle(node).borderTopLeftRadius);
    return [
      radius(element),
      radius(element.querySelector(".segment-plate")!),
      ...[...element.querySelectorAll("button")].map(radius),
    ];
  });
  for (const radius of radii) expect(radius).toBeGreaterThanOrEqual(999);
  await expect(page.locator(".vanilla-card")).toBeVisible();
  await expect(page.locator(".source-drop")).toHaveCount(0);
});

test("drag target reports accepted and rejected payloads", async ({ page }) => {
  await openBuilder(page);
  const drop = page.locator(".source-drop");
  const overlay = drop.locator(".drop-overlay");
  await expect(drop).toHaveAttribute("data-drag", "none");
  // The native event is not available in a browser, so drive the same state
  // the event handler sets and assert the visible feedback contract.
  await drop.evaluate((element) =>
    element.setAttribute("data-drag", "accepted"),
  );
  await expect(overlay).toBeVisible();
  await expect(overlay).toContainText("松开以导入");
  await drop.evaluate((element) =>
    element.setAttribute("data-drag", "rejected"),
  );
  await expect(overlay).toContainText("Prism");
});

async function openRunningBuild(
  page: Page,
  compatibility: AotCompatibility | null = null,
) {
  await page.addInitScript((report) => {
    const job = {
      id: "a".repeat(32),
      name: "NCL fixture",
      state: "running",
      stage: "source",
      startedAt: new Date(Date.now() - 65_000).toISOString(),
      folder: "/fixture/job",
      build: "/fixture/build",
      request: { workspace: "/fixture", loader: "fabric" },
      error: "",
      compatibility: report,
      log: Array.from({ length: 200 }, (_, i) => `INFO step ${i}`).join("\n"),
    };
    // This suite starts after the separate first-launch flow.
    localStorage.setItem(
      "ncl.onboarding.v1",
      JSON.stringify({
        version: 1,
        accepted: true,
        storageRoot: "/fixture",
        completed: true,
      }),
    );
    Object.assign(window, {
      isTauri: true,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "account_action")
            return {
              configured: true,
              verified: true,
              profile: { id: "a".repeat(32), name: "FixturePlayer" },
              verifiedAt: Date.now() / 1000,
              verifiedUntil: Date.now() / 1000 + 3600,
            };
          if (command === "default_workspace") return "/fixture";
          if (command === "system_accent") return null;
          if (command !== "workbench_action") return null;
          if (args.action === "bootstrap")
            return {
              workspace: "/fixture",
              config: "/fixture/config.json",
              exportOptions: "/fixture/Export.plist",
              output: "/fixture/builds",
              configFields: {},
              jobs: [job],
            };
          if (args.action === "status") return job;
          if (args.action === "dependencies")
            return { ready: true, checkedAt: "", libraries: [] };
          return null;
        },
      },
    });
  }, compatibility);
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^构建记录/ })).toBeVisible({
    timeout: 15000,
  });
  await page.getByRole("button", { name: /^构建记录/ }).click();
  await expect(
    page.getByRole("heading", { name: "取得并校验内容", exact: true }),
  ).toBeVisible();
}

test("build history shows AOT findings and leaves launch and device unverified", async ({
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 760 });
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await openRunningBuild(page, {
    modCount: 4,
    fixes: 1,
    warnings: 1,
    blockers: 0,
    findingGroups: 2,
    stages: {
      static: "PASS",
      transform: "PASS",
      aot: "PASS",
      startup: "UNVERIFIED",
      device: "UNVERIFIED",
    },
    findings: [
      {
        code: "TYPED_GSON_CONFIG",
        severity: "fix",
        target: "fixture.ConfigDTO",
        count: 1,
      },
      {
        code: "MIXIN_TARGET_UNAVAILABLE",
        severity: "warning",
        target: "fixture.OptionalMixin",
        count: 1,
      },
    ],
  });
  const report = page.getByRole("region", { name: "AOT 兼容性" });
  await expect(report.getByRole("status")).toContainText(
    "4 个 Mod · 1 项自动修复 · 1 条警告",
  );
  await expect(report).toContainText(
    "AOT 产物 通过 · 启动 待验证 · 真机 待验证",
  );
  const summary = report.locator("summary");
  await summary.focus();
  await summary.press("Enter");
  await expect(
    report.getByText(/Mixin 目标不可用.*fixture.OptionalMixin/),
  ).toBeVisible();
});

test("running Fabric build stages fit their rows above the log", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 760 });
  await openRunningBuild(page);

  const labels = page.locator(".pipeline-label");
  const strip = page.locator(".job-stage-strip");
  await expect(labels).toHaveCount(14);
  for (const width of [1100, 800, 1440, 375]) {
    await page.setViewportSize({ width, height: 760 });
    expect(
      await strip.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
      `${width}px: stage summary fits`,
    ).toBe(true);
    const layout = await labels.evaluateAll((elements) => {
      const logTop = document
        .querySelector(".log-panel")!
        .getBoundingClientRect().top;
      return elements.map((label) => {
        const range = document.createRange();
        range.selectNodeContents(label);
        const text = range.getBoundingClientRect();
        const row = label.parentElement!.getBoundingClientRect();
        return {
          label: label.textContent,
          lines: range.getClientRects().length,
          fitsRow:
            text.top >= row.top - 1 &&
            text.right <= row.right + 1 &&
            text.bottom <= row.bottom + 1,
          aboveLog: text.bottom < logTop,
        };
      });
    });
    for (const { label, ...geometry } of layout) {
      expect(geometry, `${width}px: ${label}`).toEqual({
        lines: 1,
        fitsRow: true,
        aboveLog: true,
      });
    }
  }
});

test("a long log keeps the reader in place until they return to the end", async ({
  page,
}) => {
  await openRunningBuild(page);
  const scroll = page.locator(".log-scroll");
  await expect(page.locator(".log-line")).toHaveCount(200);
  await scroll.evaluate((element) => element.scrollTo(0, 0));
  await page.waitForTimeout(400);
  expect(await scroll.evaluate((element) => element.scrollTop)).toBe(0);
});

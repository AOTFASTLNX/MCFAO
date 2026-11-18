import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const windowConfig = JSON.parse(
  readFileSync(
    new URL("../src-tauri/tauri.conf.json", import.meta.url),
    "utf8",
  ),
).app.windows[0];

for (const theme of ["light", "dark"] as const) {
  for (const size of [
    { width: windowConfig.width, height: windowConfig.height },
    { width: windowConfig.minWidth, height: windowConfig.minHeight },
  ]) {
    test(`macOS titlebar and compact layout ${theme} ${size.width}`, async ({
      page,
    }) => {
      await page.setViewportSize(size);
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/");
      // Browser previews exercise the same overlay spacing as the macOS host.
      await page.locator(".app-shell").evaluate((shell) => {
        shell.setAttribute("data-window-chrome", "overlay");
      });
      const titlebar = page.locator(".sidebar-titlebar");
      await expect(titlebar).toBeVisible();
      await expect(page.locator(".brand img")).toHaveCount(0);
      const clearance = (await titlebar.boundingBox())!;
      const brand = (await page.locator(".brand").boundingBox())!;
      expect(brand.y).toBeGreaterThanOrEqual(clearance.y + clearance.height);
      expect(
        await page.locator(".topbar").evaluate((header) => {
          const bounds = header.getBoundingClientRect();
          return document
            .elementFromPoint(bounds.x + bounds.width / 2, bounds.y + 4)
            ?.hasAttribute("data-tauri-drag-region");
        }),
      ).toBe(true);

      // The top bar holds no theme toggle; appearance is set in settings.
      await expect(page.locator(".topbar .theme-toggle")).toHaveCount(0);

      for (const name of ["构建 IPA", "构建记录", "环境与资源", "设置"]) {
        await page.getByRole("button", { name, exact: true }).first().click();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await page
          .locator(
            ".step-scroll, .main-content[data-docked] > .page-column:not([data-builder]), .main-content:not([data-docked])",
          )
          .evaluate((pane) => pane.scrollTo(0, pane.scrollHeight));
        await expect(page.locator(".topbar")).toBeInViewport();
        expect((await page.locator(".topbar").boundingBox())!.y).toBe(0);
      }
      await page
        .getByRole("button", { name: "构建 IPA", exact: true })
        .first()
        .click();
      // The page cross-fades between routes; capture once it has settled so
      // the baseline records a full-opacity page instead of a random frame of
      // the fade.
      await expect(page.locator(".page-column")).toHaveAttribute(
        "data-phase",
        "idle",
      );
      // The sidebar selection block and the step indicator spring into place;
      // wait for both to settle so the baseline is not a random mid-flight
      // frame of the same layout.
      for (const capsule of [".sidebar nav", ".stepper"]) {
        await expect(page.locator(capsule)).toHaveAttribute(
          "data-motion-moving",
          "false",
        );
      }
      await page
        .locator(".step-scroll")
        .evaluate((pane) => pane.scrollTo(0, 0));
      await page.screenshot({
        path: `../artifacts/desktop/titlebar-compact/${theme}-${size.width}.png`,
      });
    });
  }
}

test("traffic lights use equal top and leading inset", () => {
  expect(windowConfig.trafficLightPosition.x).toBe(
    windowConfig.trafficLightPosition.y,
  );
});

test("sidebar navigation keeps a comfortable row rhythm", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  const rows = await page
    .locator(".sidebar nav .nav-item")
    .evaluateAll((items) =>
      items.map((item) => {
        const bounds = item.getBoundingClientRect();
        return {
          top: bounds.top,
          bottom: bounds.bottom,
          height: bounds.height,
        };
      }),
    );
  expect(rows).toHaveLength(5);
  for (const row of rows) expect(row.height).toBeGreaterThanOrEqual(34);
  for (let i = 1; i < rows.length; i += 1)
    expect(rows[i].top - rows[i - 1].bottom).toBeGreaterThanOrEqual(4);
});

test("sidebar selection is one moving block without a side marker", async ({
  page,
}) => {
  await page.goto("/");
  const nav = page.locator(".sidebar nav");
  const selected = nav.locator(".nav-item.selected");
  await expect(selected).toHaveCount(1);
  expect(
    await selected.evaluate((item) => ({
      content: getComputedStyle(item, "::before").content,
      rowBackground: getComputedStyle(item).backgroundColor,
    })),
  ).toEqual({ content: "none", rowBackground: "rgba(0, 0, 0, 0)" });
  const block = nav.locator(".motion-indicator");
  await expect(block).toHaveCount(1);
  expect(await block.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  const row = (await selected.boundingBox())!;
  const layer = (await block.boundingBox())!;
  expect(Math.abs(layer.y - row.y)).toBeLessThan(1.5);
  expect(Math.abs(layer.height - row.height)).toBeLessThan(1.5);
});

test("the page scroll bar belongs to the pane below the title bar", async ({
  page,
}) => {
  // Wider than the 1460px content cap so the centred column is narrower than
  // the scroll pane and the bar's position is unambiguous.
  await page.setViewportSize({ width: 1900, height: 760 });
  await page.goto("/");
  await page.locator(".app-shell").evaluate((shell) => {
    shell.setAttribute("data-window-chrome", "overlay");
  });
  // Use a real long report; an empty source page can fit without scrolling.
  const report = JSON.parse(
    execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
      encoding: "utf8",
    }),
  );
  await page.locator("input[type=file]").setInputFiles({
    name: "preflight.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(report)),
  });
  await expect(page.getByText("导入检查报告", { exact: true })).toBeVisible();
  const scroll = await page.evaluate(() => {
    const pane = document.querySelector<HTMLElement>(".step-scroll")!;
    const topbar = document.querySelector<HTMLElement>(".topbar")!;
    pane.scrollTop = pane.scrollHeight;
    return {
      // The window frame itself must not scroll; only the pane does.
      documentScroll: document.documentElement.scrollHeight > innerHeight,
      paneScrollable: pane.scrollHeight > pane.clientHeight,
      paneScrolled: pane.scrollTop > 0,
      paneTop: pane.getBoundingClientRect().top,
      topbarBottom: topbar.getBoundingClientRect().bottom,
      // The scroll bar hugs the window edge, not the centred content column.
      paneRight: pane.getBoundingClientRect().right,
      viewport: innerWidth,
      contentRight: document.querySelector(".stepper")!.getBoundingClientRect()
        .right,
      overflowY: getComputedStyle(pane).overflowY,
    };
  });
  expect(scroll.documentScroll).toBe(false);
  expect(scroll.overflowY).toBe("auto");
  expect(scroll.paneScrollable).toBe(true);
  expect(scroll.paneScrolled).toBe(true);
  expect(scroll.paneTop).toBeGreaterThanOrEqual(scroll.topbarBottom);
  expect(scroll.paneRight).toBe(scroll.viewport);
  expect(scroll.paneRight).toBeGreaterThan(scroll.contentRight);
});

test("a loaded report keeps the document inside the window", async ({
  page,
}) => {
  const report = JSON.parse(
    execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
      encoding: "utf8",
    }),
  );
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  await page.locator(".app-shell").evaluate((shell) => {
    shell.setAttribute("data-window-chrome", "overlay");
  });
  // The report pane is the tallest state of the builder; its hidden file input
  // used to overflow the scroll pane and add a second window-level scroll bar.
  await page.locator("input[type=file]").setInputFiles({
    name: "preflight.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(report)),
  });
  await expect(page.getByText("导入检查报告", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(() => ({
      documentFits: document.documentElement.scrollHeight <= innerHeight,
      paneScrolls:
        document.querySelector<HTMLElement>(".step-scroll")!.scrollHeight >
        document.querySelector<HTMLElement>(".step-scroll")!.clientHeight,
    })),
  ).toEqual({ documentFits: true, paneScrolls: true });
});

test("every page scrolls in the pane without a second window scroll bar", async ({
  page,
}) => {
  const report = JSON.parse(
    execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
      encoding: "utf8",
    }),
  );
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  await page.locator(".app-shell").evaluate((shell) => {
    shell.setAttribute("data-window-chrome", "overlay");
  });
  await page.locator("input[type=file]").setInputFiles({
    name: "preflight.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(report)),
  });
  for (const name of ["构建 IPA", "构建记录", "环境与资源", "设置"]) {
    await page.getByRole("button", { name, exact: true }).first().click();
    expect(
      await page.evaluate(
        (label) => ({
          page: label,
          documentFits: document.documentElement.scrollHeight <= innerHeight,
        }),
        name,
      ),
    ).toEqual({ page: name, documentFits: true });
  }
});

test("builder content scrolls behind fixed bars and clears them at the ends", async ({
  page,
}) => {
  const report = JSON.parse(
    execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
      encoding: "utf8",
    }),
  );
  await page.setViewportSize({ width: 1100, height: 1200 });
  await page.goto("/");
  const pane = page.locator(".step-scroll");
  const measure = (fraction: number) =>
    pane.evaluate((body, fraction) => {
      const workspace = body.closest(".main-content")!.getBoundingClientRect();
      const maxScroll = body.scrollHeight - body.clientHeight;
      body.scrollTop = maxScroll * fraction;
      const top = document.querySelector(".stepper")!.getBoundingClientRect();
      const bottom = document
        .querySelector(".wizard-footer")!
        .getBoundingClientRect();
      const scroller = body.getBoundingClientRect();
      const content = body.querySelector<HTMLElement>(".step-body")!;
      const first = body.querySelector<HTMLElement>(
        ".step-scroll-column",
      )!.firstElementChild!;
      return {
        maxScroll,
        scrollTop: body.scrollTop,
        topInset: top.top - workspace.top,
        bottomInset: workspace.bottom - bottom.bottom,
        scrollsBehindBothBars:
          scroller.top < top.top && scroller.bottom > bottom.bottom,
        startClear: first.getBoundingClientRect().top >= top.bottom,
        endClear: content.getBoundingClientRect().bottom <= bottom.top,
      };
    }, fraction);

  const short = await measure(0);
  expect(short).toMatchObject({
    maxScroll: 0,
    topInset: 8,
    bottomInset: 8,
    scrollsBehindBothBars: true,
    startClear: true,
    endClear: true,
  });

  await page.setViewportSize({ width: 800, height: 640 });
  await page.locator("input[type=file]").setInputFiles({
    name: "preflight.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(report)),
  });
  await expect(page.getByRole("button", { name: "导出报告" })).toBeVisible();
  for (const fraction of [0, 0.5, 1]) {
    const long = await measure(fraction);
    expect(long.maxScroll).toBeGreaterThan(0);
    expect(
      Math.abs(long.scrollTop - long.maxScroll * fraction),
    ).toBeLessThanOrEqual(1);
    expect(long).toMatchObject({
      topInset: short.topInset,
      bottomInset: short.bottomInset,
      scrollsBehindBothBars: true,
    });
    if (fraction === 0) {
      expect(long.startClear).toBe(true);
      expect(long.endClear).toBe(false);
    }
    if (fraction === 1) {
      expect(long.startClear).toBe(false);
      expect(long.endClear).toBe(true);
    }
  }

  await page.getByRole("button", { name: "3 构建环境", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "准备你的构建环境" }),
  ).toBeInViewport();
  await expect(page.locator(".step-body")).toHaveAttribute(
    "data-phase",
    "idle",
  );
  expect(await pane.evaluate((body) => body.scrollTop)).toBe(0);
  expect(await measure(0)).toMatchObject({
    topInset: short.topInset,
    bottomInset: short.bottomInset,
  });
});

test("history and environment actions stay above their scrolling pages", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  for (const [route, action] of [
    ["构建记录", "新建构建"],
    ["环境与资源", "检测环境"],
  ] as const) {
    await page.getByRole("button", { name: route, exact: true }).click();
    const toolbar = page.locator(".page-toolbar");
    await expect(toolbar.getByRole("button", { name: action })).toBeVisible();
    const position = await toolbar.boundingBox();
    // An empty history can fit in the window, so force a tall list for this check.
    const result = await page.locator(".page-column").evaluate((body) => {
      const spacer = document.createElement("div");
      spacer.style.height = `${body.clientHeight}px`;
      body.append(spacer);
      body.scrollTop = body.scrollHeight;
      const result = {
        scrollTop: body.scrollTop,
        toolbarTop: document
          .querySelector(".page-toolbar")!
          .getBoundingClientRect().top,
      };
      spacer.remove();
      return result;
    });
    expect(result.scrollTop).toBeGreaterThan(0);
    expect(result.toolbarTop).toBe(position!.y);
  }
});

test("environment and history drop the outer card for dividers", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  const look = async (region: string) =>
    page.evaluate((selector) => {
      const first = document.querySelectorAll<HTMLElement>(selector)[0];
      const second = document.querySelectorAll<HTMLElement>(selector)[1];
      const style = getComputedStyle(second);
      return {
        first: getComputedStyle(first).backgroundColor,
        second: getComputedStyle(second).backgroundColor,
        divider: style.borderTopWidth,
        dividerColor: style.borderTopColor,
      };
    }, region);
  for (const page_ of ["环境与资源", "构建记录"]) {
    await page.getByRole("button", { name: page_, exact: true }).click();
    const region = page_ === "环境与资源" ? ".panel.flat" : ".flat";
    // Pages cross-fade before mounting, so wait for the destination regions.
    await expect(page.locator(region).nth(1)).toBeVisible();
    const look_ = await look(region);
    expect(look_.first).toBe("rgba(0, 0, 0, 0)");
    expect(look_.second).toBe("rgba(0, 0, 0, 0)");
    // Environment stacks its regions, history separates them by column.
    const edge = await page.evaluate((selector) => {
      const style = getComputedStyle(
        document.querySelectorAll<HTMLElement>(selector)[1],
      );
      return {
        top: style.borderTopWidth,
        left: style.borderLeftWidth,
      };
    }, region);
    expect(edge.top === "1px" || edge.left === "1px").toBe(true);
  }
});

test("controls inside a capsule are pills concentric with it", async ({
  page,
}) => {
  for (const theme of ["light", "dark"]) {
    for (const width of [800, 1100, 1900]) {
      await page.setViewportSize({ width, height: 760 });
      await page.addInitScript(
        (value) => localStorage.setItem("ncl.theme.v1", value),
        theme,
      );
      await page.goto("/");
      const capsules = await page.evaluate(() => {
        const box = (element: Element) => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          const pad = (side: string) =>
            Number.parseFloat(style.getPropertyValue(side));
          return {
            radius: Number.parseFloat(style.borderTopLeftRadius),
            height: rect.height,
            padTop: pad("padding-top"),
            padLeft: pad("padding-left"),
            padRight: pad("padding-right"),
            padBottom: pad("padding-bottom"),
          };
        };
        return {
          stepper: box(document.querySelector(".stepper")!),
          step: box(document.querySelector(".step")!),
          wizard: box(document.querySelector(".wizard-footer")!),
          next: box(document.querySelector(".wizard-footer .primary")!),
          back: box(document.querySelector(".wizard-footer .text-button")!),
        };
      });
      for (const [name, capsule] of Object.entries(capsules)) {
        // A pill's cap radius is half its height; anything larger is clamped.
        expect(capsule.radius, name).toBeGreaterThanOrEqual(999);
      }
      // Concentric caps: outer radius = inner radius + the gap between them.
      // Both boxes are pills, so the check reduces to the inset being equal on
      // every side, which is what keeps the curves parallel.
      for (const [outer, inner] of [
        [capsules.stepper, capsules.step],
        [capsules.wizard, capsules.next],
        [capsules.wizard, capsules.back],
      ] as const) {
        expect(outer.padTop).toBe(outer.padBottom);
        expect(outer.padTop).toBe(outer.padLeft);
        expect(outer.padTop).toBe(outer.padRight);
        expect(inner.height / 2 + outer.padTop).toBeCloseTo(
          outer.height / 2,
          0,
        );
      }
    }
  }
});

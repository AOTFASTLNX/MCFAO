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
          .locator(".main-content")
          .evaluate((pane) => pane.scrollTo(0, pane.scrollHeight));
        await expect(page.locator(".topbar")).toBeInViewport();
        expect((await page.locator(".topbar").boundingBox())!.y).toBe(0);
      }
      await page
        .getByRole("button", { name: "构建 IPA", exact: true })
        .first()
        .click();
      await page.evaluate(() => window.scrollTo(0, 0));
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
        return { top: bounds.top, bottom: bounds.bottom, height: bounds.height };
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
  const scroll = await page.evaluate(() => {
    const pane = document.querySelector<HTMLElement>(".main-content")!;
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
      contentRight: document
        .querySelector(".builder-panel")!
        .getBoundingClientRect().right,
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
        document.querySelector<HTMLElement>(".main-content")!.scrollHeight >
        document.querySelector<HTMLElement>(".main-content")!.clientHeight,
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

test("page actions float over the content instead of scrolling away", async ({
  page,
}) => {
  const report = JSON.parse(
    execFileSync("python3", [path.resolve("tests/make_fixture.py")], {
      encoding: "utf8",
    }),
  );
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "构建 IPA", exact: true }).click();
  const builder = await page.evaluate(() => {
    const probe = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector)!;
      const style = getComputedStyle(element);
      return {
        position: style.position,
        radius: style.borderTopLeftRadius,
      };
    };
    return {
      stepper: probe(".stepper"),
      wizard: probe(".wizard-footer"),
    };
  });
  await page.getByRole("button", { name: "构建记录", exact: true }).click();
  const toolbar = await page.locator(".page-toolbar").evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      position: style.position,
      radius: style.borderTopLeftRadius,
    };
  });
  for (const capsule of [...Object.values(builder), toolbar]) {
    expect(capsule.position).toBe("sticky");
    expect(Number.parseFloat(capsule.radius)).toBeGreaterThanOrEqual(999);
  }

  await page.getByRole("button", { name: "构建 IPA", exact: true }).click();
  // A long step makes the pane scroll, which is when the capsules pin.
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "preflight.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(report)),
    });
  await expect(page.getByText("导入检查报告", { exact: true })).toBeVisible();
  const pane = await page.locator(".main-content").evaluate((element) => {
    element.scrollTo(0, 300);
    const stepper = document.querySelector(".stepper")!.getBoundingClientRect();
    const footer = document
      .querySelector(".wizard-footer")!
      .getBoundingClientRect();
    const box = element.getBoundingClientRect();
    return {
      scrolled: element.scrollTop,
      stepperPinned: Math.round(stepper.top - box.top),
      footerPinned: Math.round(box.bottom - footer.bottom),
    };
  });
  expect(pane.scrolled).toBeGreaterThan(0);
  // Both capsules stop an 8 px inset from the pane edges, clear of the top
  // bar and the window bottom.
  expect(pane.stepperPinned).toBe(8);
  expect(pane.footerPinned).toBe(8);
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
    const edge = await page.evaluate(
      (selector) => {
        const style = getComputedStyle(
          document.querySelectorAll<HTMLElement>(selector)[1],
        );
        return {
          top: style.borderTopWidth,
          left: style.borderLeftWidth,
        };
      },
      region,
    );
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
          const pad = (side: string) => Number.parseFloat(style.getPropertyValue(side));
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
        expect(inner.height / 2 + outer.padTop).toBeCloseTo(outer.height / 2, 0);
      }
    }
  }
});

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

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
        await page.evaluate(() =>
          window.scrollTo(0, document.body.scrollHeight),
        );
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
  expect(rows).toHaveLength(4);
  for (const row of rows) expect(row.height).toBeGreaterThanOrEqual(34);
  for (let i = 1; i < rows.length; i += 1)
    expect(rows[i].top - rows[i - 1].bottom).toBeGreaterThanOrEqual(4);
});

test("sidebar selection uses its row background without a side marker", async ({
  page,
}) => {
  await page.goto("/");
  const selected = page.locator(".sidebar nav .nav-item.selected");
  await expect(selected).toHaveCount(1);
  expect(
    await selected.evaluate((item) => {
      const marker = getComputedStyle(item, "::before");
      return {
        content: marker.content,
        rowBackground: getComputedStyle(item).backgroundColor,
      };
    }),
  ).toEqual({
    content: "none",
    rowBackground: "color(srgb 0.184314 0.435294 0.745098 / 0.14)",
  });
});

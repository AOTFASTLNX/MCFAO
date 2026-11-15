import { describe, expect, it } from "vitest";
import {
  accentOptions,
  applyAccent,
  DARK_ACCENT,
  DEFAULT_ACCENT,
  parseAccentPreference,
  readAccentPreference,
  readableAccent,
  parseThemePreference,
  readThemePreference,
  resolveTheme,
  syncWindowTheme,
  systemPrefersDark,
  THEME_KEY,
  toggleTheme,
} from "./theme";

describe("system accent", () => {
  it("keeps a chosen accent that supports white label text", () => {
    expect(readableAccent("#2b5f9e")).toBe("#2b5f9e");
  });

  it("falls back when an accent would fail normal text contrast", () => {
    expect(readableAccent("#3478D4")).toBe("#2f6cbf");
    expect(readableAccent("#E5AB55")).toBe("#876632");
    expect(readableAccent("invalid")).toBe(DEFAULT_ACCENT);
  });

  it("uses a lighter accent in dark appearance", () => {
    expect(readableAccent("#3478D4", true)).toBe(DARK_ACCENT);
    expect(readableAccent("#6FA8EC", true)).toBe("#6FA8EC");
    expect(readableAccent("invalid", true)).toBe(DARK_ACCENT);
  });

  it("accepts only system or a six-digit hex value", () => {
    expect(parseAccentPreference("system")).toBe("system");
    expect(parseAccentPreference("#8B83CB")).toBe("#8B83CB");
    expect(parseAccentPreference("#12345")).toBe("system");
    expect(parseAccentPreference("red")).toBe("system");
    expect(accentOptions[0].value).toBe("system");
  });

  it("reads the stored accent and survives blocked storage", () => {
    expect(
      readAccentPreference({ getItem: () => "#34A77D" } as unknown as Storage),
    ).toBe("#34A77D");
    expect(
      readAccentPreference({
        getItem: () => {
          throw new Error("blocked");
        },
      } as unknown as Storage),
    ).toBe("system");
    expect(readAccentPreference(null)).toBe("system");
  });

  it("maps the chosen accent to a theme-aware CSS token", () => {
    const values: Record<string, string> = {};
    const previous = globalThis.document;
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: {
        documentElement: {
          style: {
            setProperty: (key: string, value: string) => {
              values[key] = value;
            },
          },
        },
      },
    });
    applyAccent("system", "#3478D4", "light");
    expect(values["--accent"]).toBe("#2f6cbf");
    applyAccent("system", "#6FA8EC", "dark");
    expect(values["--accent"]).toBe("#6FA8EC");
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: previous,
    });
  });
});

describe("theme preference", () => {
  it("only accepts the three supported values", () => {
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("dark")).toBe("dark");
    expect(parseThemePreference("system")).toBe("system");
    expect(parseThemePreference("Light")).toBe("system");
    expect(parseThemePreference("sepia")).toBe("system");
    expect(parseThemePreference(null)).toBe("system");
  });

  it("follows the system preference until the user picks a theme", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("toggles from the theme that is actually showing", () => {
    expect(toggleTheme("system", false)).toBe("dark");
    expect(toggleTheme("system", true)).toBe("light");
    expect(toggleTheme("light", true)).toBe("dark");
    expect(toggleTheme("dark", false)).toBe("light");
  });

  it("survives missing or unreadable storage", () => {
    expect(
      readThemePreference({ getItem: () => "dark" } as unknown as Storage),
    ).toBe("dark");
    expect(
      readThemePreference({
        getItem: () => {
          throw new Error("blocked");
        },
      } as unknown as Storage),
    ).toBe("system");
    expect(readThemePreference(null)).toBe("system");
    expect(THEME_KEY).toBe("ncl.theme.v1");
  });

  it("treats a missing media query as light", () => {
    expect(systemPrefersDark({ matches: true } as MediaQueryList)).toBe(true);
    expect(systemPrefersDark({ matches: false } as MediaQueryList)).toBe(false);
    expect(systemPrefersDark(null)).toBe(false);
  });

  it("leaves browser previews alone when syncing the native window", async () => {
    await expect(syncWindowTheme("light")).resolves.toBeUndefined();
  });
});

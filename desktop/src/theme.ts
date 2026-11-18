export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

import {
  ACCENT_KEY,
  LEGACY_ACCENT_KEY,
  LEGACY_THEME_KEY,
  THEME_KEY,
  readWithLegacy,
} from "./storage";

export { ACCENT_KEY, THEME_KEY };

export const DEFAULT_ACCENT = "#2f6fbe";
export const DARK_ACCENT = "#4a8fe0";

export const accentOptions = [
  { value: "system", label: "跟随系统" },
  { value: "#3478D4", label: "蓝色" },
  { value: "#8B83CB", label: "紫色" },
  { value: "#D96A6A", label: "红色" },
  { value: "#E5AB55", label: "橙色" },
  { value: "#34A77D", label: "绿色" },
  // macOS systemGray. The readableAccent() step keeps the filled control
  // legible in light appearance and the native gray in dark appearance.
  { value: "#8E8E93", label: "灰色" },
] as const;

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((index) => {
    const value = parseInt(hex.slice(index, index + 2), 16) / 255;
    return value <= 0.03928
      ? value / 12.92
      : Math.pow((value + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(a: string, b: string): number {
  const lighter = Math.max(luminance(a), luminance(b));
  const darker = Math.min(luminance(a), luminance(b));
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * macOS accent colors are bright. In light appearance the accent is used as a
 * filled control with a white label, so darken the same hue until that label
 * meets normal-text contrast. Dark appearance keeps the native color when it
 * is legible against the raised surface.
 */
export function readableAccent(value: string, dark = false): string {
  if (!/^#[0-9a-f]{6}$/i.test(value)) return dark ? DARK_ACCENT : DEFAULT_ACCENT;
  if (dark) {
    return contrast(value, "#27282b") >= 4.5 ? value : DARK_ACCENT;
  }
  let channels = [1, 3, 5].map((index) =>
    parseInt(value.slice(index, index + 2), 16),
  );
  for (let step = 0; step < 12; step += 1) {
    const candidate =
      "#" +
      channels
        .map((channel) => channel.toString(16).padStart(2, "0"))
        .join("");
    if (contrast("#ffffff", candidate) >= 4.5) return candidate;
    channels = channels.map((channel) => Math.max(0, Math.round(channel * 0.9)));
  }
  return DEFAULT_ACCENT;
}

export function parseAccentPreference(raw: string | null): string {
  if (raw === "system") return raw;
  return raw && /^#[0-9a-f]{6}$/i.test(raw) ? raw : "system";
}

export function readAccentPreference(
  storage: Pick<Storage, "getItem"> | null = typeof window === "undefined"
    ? null
    : window.localStorage,
): string {
  return parseAccentPreference(
    readWithLegacy(storage, ACCENT_KEY, LEGACY_ACCENT_KEY),
  );
}

export function applyAccent(
  preference: string,
  systemAccent: string | null,
  resolved: ResolvedTheme,
): void {
  if (typeof document === "undefined") return;
  const requested = preference === "system" ? systemAccent ?? DEFAULT_ACCENT : preference;
  document.documentElement.style.setProperty(
    "--accent",
    readableAccent(requested, resolved === "dark"),
  );
}

export const themeLabels: Record<ThemePreference, string> = {
  system: "跟随系统",
  light: "浅色",
  dark: "深色",
};

export function parseThemePreference(raw: string | null): ThemePreference {
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

export function resolveTheme(
  preference: ThemePreference,
  systemDark: boolean,
): ResolvedTheme {
  if (preference === "system") return systemDark ? "dark" : "light";
  return preference;
}

export function toggleTheme(
  preference: ThemePreference,
  systemDark: boolean,
): ThemePreference {
  return resolveTheme(preference, systemDark) === "dark" ? "light" : "dark";
}

export function readThemePreference(
  storage: Pick<Storage, "getItem"> | null = typeof window === "undefined"
    ? null
    : window.localStorage,
): ThemePreference {
  return parseThemePreference(
    readWithLegacy(storage, THEME_KEY, LEGACY_THEME_KEY),
  );
}

export function systemPrefersDark(
  query: Pick<MediaQueryList, "matches"> | null = typeof window === "undefined"
    ? null
    : window.matchMedia("(prefers-color-scheme: dark)"),
): boolean {
  return query?.matches === true;
}

export function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta)
    meta.setAttribute("content", resolved === "light" ? "#F5F5F7" : "#18191B");
}

// The macOS title bar, traffic lights and overlay scroll bars are native
// AppKit views; the webview theme alone leaves them dark. Ask the Rust host to
// switch the app appearance, then fall back to the window API so an older
// binary still follows the CSS theme.
export async function syncWindowTheme(resolved: ResolvedTheme): Promise<void> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window))
    return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("set_window_theme", { theme: resolved });
    return;
  } catch {
    // Pre-0.2.6 builds only expose the window theme command.
  }
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTheme(resolved);
  } catch {
    // Older builds without the window theme permission keep the CSS theme.
  }
}

export async function getSystemAccent(): Promise<string | null> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window))
    return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string>("system_accent");
  } catch {
    return null;
  }
}

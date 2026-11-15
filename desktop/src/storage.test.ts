import { describe, expect, it } from "vitest";
import {
  ACCENT_KEY,
  FORM_KEY,
  LEGACY_ACCENT_KEY,
  LEGACY_FORM_KEY,
  LEGACY_STORAGE_KEY,
  LEGACY_THEME_KEY,
  STORAGE_KEY,
  THEME_KEY,
  migrateLegacyKeys,
  readWithLegacy,
} from "./storage";

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

describe("pre-rename local storage compatibility", () => {
  it("reads a legacy value when the current key is absent", () => {
    const storage = new MemoryStorage();
    storage.setItem(LEGACY_THEME_KEY, "dark");
    storage.setItem(LEGACY_ACCENT_KEY, "#3478D4");
    expect(readWithLegacy(storage, THEME_KEY, LEGACY_THEME_KEY)).toBe("dark");
    expect(readWithLegacy(storage, ACCENT_KEY, LEGACY_ACCENT_KEY)).toBe("#3478D4");
  });

  it("migrates every old key and preserves the old records", () => {
    const storage = new MemoryStorage();
    storage.setItem(LEGACY_FORM_KEY, '{"workspace":"/old"}');
    storage.setItem(LEGACY_STORAGE_KEY, '{"instances":[]}');
    storage.setItem(LEGACY_THEME_KEY, "light");
    storage.setItem(LEGACY_ACCENT_KEY, "#8B83CB");
    migrateLegacyKeys(storage);
    expect(storage.getItem(FORM_KEY)).toBe('{"workspace":"/old"}');
    expect(storage.getItem(STORAGE_KEY)).toBe('{"instances":[]}');
    expect(storage.getItem(THEME_KEY)).toBe("light");
    expect(storage.getItem(ACCENT_KEY)).toBe("#8B83CB");
    expect(storage.getItem(LEGACY_FORM_KEY)).toBe('{"workspace":"/old"}');
  });

  it("does not overwrite a current value with an old one", () => {
    const storage = new MemoryStorage();
    storage.setItem(LEGACY_THEME_KEY, "dark");
    storage.setItem(THEME_KEY, "light");
    migrateLegacyKeys(storage);
    expect(storage.getItem(THEME_KEY)).toBe("light");
  });
});

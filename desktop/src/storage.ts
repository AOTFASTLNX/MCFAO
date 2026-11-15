/** Current and pre-rename local-storage keys.
 *
 * The old keys are part of the user's saved workspace, theme and form data.
 * Keep reading them so an update does not silently reset the GUI.
 */
export const FORM_KEY = "ncl.builder.v2";
export const STORAGE_KEY = "ncl.desktop.v1";
export const THEME_KEY = "ncl.theme.v1";
export const ACCENT_KEY = "ncl.accent.v1";

export const LEGACY_FORM_KEY = "fabricaot.builder.v2";
export const LEGACY_STORAGE_KEY = "fabricaot.desktop.v1";
export const LEGACY_THEME_KEY = "fabricaot.theme.v1";
export const LEGACY_ACCENT_KEY = "fabricaot.accent.v1";

const KEY_PAIRS: readonly (readonly [string, string])[] = [
  [FORM_KEY, LEGACY_FORM_KEY],
  [STORAGE_KEY, LEGACY_STORAGE_KEY],
  [THEME_KEY, LEGACY_THEME_KEY],
  [ACCENT_KEY, LEGACY_ACCENT_KEY],
];

export function readWithLegacy(
  storage: Pick<Storage, "getItem"> | null,
  current: string,
  legacy: string,
): string | null {
  try {
    return storage?.getItem(current) ?? storage?.getItem(legacy) ?? null;
  } catch {
    return null;
  }
}

/** Copy old values to the current keys once. Old keys are retained as a
 * fallback for rolling back to an earlier build. */
export function migrateLegacyKeys(storage: Pick<Storage, "getItem" | "setItem"> | null): void {
  for (const [current, legacy] of KEY_PAIRS) {
    try {
      if (!storage || storage.getItem(current) !== null) continue;
      const value = storage.getItem(legacy);
      if (value !== null) storage.setItem(current, value);
    } catch {
      // A blocked storage must not prevent the current session from starting.
    }
  }
}

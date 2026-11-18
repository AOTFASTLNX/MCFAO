import type { BuildForm } from "./workflow";

export const ONBOARDING_KEY = "ncl.onboarding.v1";
export interface OnboardingState {
  version: 1;
  accepted: boolean;
  storageRoot: string;
  completed: boolean;
  verificationDeferred?: boolean;
}
export const emptyOnboarding: OnboardingState = {
  version: 1,
  accepted: false,
  storageRoot: "",
  completed: false,
};
export function readOnboarding(raw: string | null): OnboardingState {
  try {
    const value = JSON.parse(raw || "null");
    if (value?.version !== 1) return { ...emptyOnboarding };
    const accepted = value.accepted === true;
    const storageRoot =
      typeof value.storageRoot === "string" && value.storageRoot.startsWith("/")
        ? value.storageRoot
        : "";
    return {
      ...(value.verificationDeferred === true
        ? { verificationDeferred: true }
        : {}),
      version: 1,
      accepted,
      storageRoot,
      completed: accepted && !!storageRoot && value.completed === true,
    };
  } catch {
    return { ...emptyOnboarding };
  }
}
export function onboardingStep(
  state: OnboardingState,
  verified: boolean,
): number {
  if (!state.accepted) return 0;
  if (!verified) return 1;
  return state.storageRoot ? 3 : 2;
}
export function storageFormPatch(
  form: BuildForm,
  builds: string,
  mappings: Record<string, string> = {},
): Partial<BuildForm> {
  const patch: Partial<BuildForm> = { output: builds };
  const sorted = Object.entries(mappings).sort(
    (a, b) => b[0].length - a[0].length,
  );
  for (const key of ["config", "exportOptions", "source"] as const) {
    const value = form[key];
    for (const [source, destination] of sorted) {
      if (value === source || value.startsWith(source + "/")) {
        patch[key] = destination + value.slice(source.length);
        break;
      }
    }
  }
  return patch;
}

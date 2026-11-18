import { describe, expect, it } from "vitest";
import { accountIsVerified } from "./Account";
import {
  emptyOnboarding,
  onboardingStep,
  readOnboarding,
  storageFormPatch,
} from "./onboarding";
import { defaultForm } from "./workflow";

describe("first launch state", () => {
  it("starts with the disclosure and rejects malformed or premature completion", () => {
    for (const value of [
      null,
      "bad",
      "{}",
      '{"version":2,"completed":true}',
      '{"version":1,"completed":true}',
    ]) {
      expect(readOnboarding(value)).toEqual(emptyOnboarding);
    }
  });
  it("resumes from the first unmet requirement and never trusts stored ownership", () => {
    const draft = { ...emptyOnboarding, accepted: true };
    expect(onboardingStep(emptyOnboarding, false)).toBe(0);
    expect(onboardingStep(draft, false)).toBe(1);
    expect(onboardingStep(draft, true)).toBe(2);
    expect(onboardingStep({ ...draft, storageRoot: "/disk/NCL" }, true)).toBe(
      3,
    );
    expect(
      onboardingStep(
        { ...draft, storageRoot: "/disk/NCL", completed: true },
        false,
      ),
    ).toBe(1);
  });
  it("requires acceptance and an absolute directory to persist completion", () => {
    expect(
      readOnboarding(
        JSON.stringify({
          ...emptyOnboarding,
          completed: true,
          storageRoot: "/disk",
        }),
      ).completed,
    ).toBe(false);
    expect(
      readOnboarding(
        JSON.stringify({
          ...emptyOnboarding,
          accepted: true,
          completed: true,
          storageRoot: "relative",
        }),
      ).completed,
    ).toBe(false);
    const complete = {
      ...emptyOnboarding,
      accepted: true,
      completed: true,
      storageRoot: "/disk/NCL",
    };
    expect(readOnboarding(JSON.stringify(complete))).toEqual(complete);
  });
  it("preserves configuration while mapping migrated paths at directory boundaries", () => {
    const form = {
      ...defaultForm,
      config: "/old/config.json",
      source: "/older/pack",
      exportOptions: "/old/specific/export.plist",
    };
    expect(
      storageFormPatch(form, "/new/builds", {
        "/old": "/new",
        "/old/specific": "/special",
      }),
    ).toEqual({
      output: "/new/builds",
      config: "/new/config.json",
      exportOptions: "/special/export.plist",
    });
    expect(form.source).toBe("/older/pack");
  });
  it("uses native verification with a bounded lifetime", () => {
    const snapshot = {
      configured: true,
      verified: true,
      profile: { id: "a".repeat(32), name: "Player" },
      verifiedUntil: 2000,
    };
    expect(accountIsVerified(snapshot, 1999)).toBe(true);
    expect(accountIsVerified(snapshot, 2000)).toBe(false);
    expect(accountIsVerified({ ...snapshot, profile: null }, 1000)).toBe(false);
    expect(accountIsVerified({ ...snapshot, verified: false }, 1000)).toBe(
      false,
    );
  });
});

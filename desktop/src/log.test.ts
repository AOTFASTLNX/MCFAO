import { describe, expect, it } from "vitest";
import { logLevel, logTone } from "./log";

describe("build log semantics", () => {
  it("distinguishes errors, warnings and ordinary info", () => {
    expect(logTone("[ERROR] build failed")).toBe("error");
    expect(logTone("WARN loader mismatch")).toBe("warning");
    expect(logTone("INFO started")).toBe("info");
    expect(logTone("compiling sources")).toBe("plain");
  });

  it("extracts a stable level label for the gutter", () => {
    expect(logLevel("[ERROR] build failed")).toBe("ERROR");
    expect(logLevel("warning: missing signature")).toBe("WARNING");
    expect(logLevel("ordinary line")).toBeNull();
  });

  it("treats progress markers as secondary text", () => {
    expect(logTone("正在校验输入")).toBe("muted");
    expect(logTone("-- output")).toBe("muted");
  });
});

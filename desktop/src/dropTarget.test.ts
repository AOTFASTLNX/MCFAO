import { describe, expect, it } from "vitest";
import { dragVerdict, dropMessage } from "./dropTarget";

describe("drag target", () => {
  it("accepts modpacks and extensionless instance folders", () => {
    expect(dragVerdict(["/tmp/Example.mrpack"])).toBe("accepted");
    expect(dragVerdict(["/tmp/Example.MRPACK"])).toBe("accepted");
    expect(dragVerdict(["/Users/me/instances/1.21.1 Fabric"])).toBe("accepted");
  });

  it("rejects files that cannot be a pack or an instance", () => {
    expect(dragVerdict(["/tmp/notes.txt"])).toBe("rejected");
    expect(dragVerdict(["/tmp/archive.zip"])).toBe("rejected");
    expect(dragVerdict(["/tmp/mod.jar", "/tmp/config.json"])).toBe("rejected");
  });

  it("does not reject an empty native drag payload", () => {
    expect(dragVerdict([])).toBe("accepted");
  });

  it("keeps accepted and rejected copy distinct", () => {
    expect(dropMessage("accepted")).not.toBe(dropMessage("rejected"));
    expect(dropMessage("rejected")).toContain("Prism");
  });
});

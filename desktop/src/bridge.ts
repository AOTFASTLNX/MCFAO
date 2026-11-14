import { invoke, isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { Environment, Settings } from "./model";

export const native = isTauri();
export async function pickSource(directory: boolean): Promise<string | null> {
  if (!native)
    throw new Error("请在桌面应用中选择整合包；浏览器中可导入预检 JSON 报告。");
  // Validate the suffix after selection: macOS UTI associations can disable
  // valid mrpack archives when an extension-only NSOpenPanel filter is used.
  const source = await open({
    directory,
    multiple: false,
    title: directory ? "选择 Prism 实例目录" : "选择 .mrpack 整合包",
  });
  if (source && !directory && !source.toLowerCase().endsWith(".mrpack"))
    throw new Error("请选择 .mrpack 整合包文件。已有报告请使用“预检报告”入口。");
  return source;
}
export async function inspectSource(
  source: string,
  python: string,
): Promise<{ report: unknown; elapsedMs: number }> {
  return invoke("inspect_pack", { source, python });
}
export async function getEnvironment(python: string): Promise<Environment> {
  return invoke("check_environment", { python });
}
export async function defaultWorkspace(): Promise<string | null> {
  return invoke("default_workspace");
}
export async function pickWorkspace(): Promise<string | null> {
  return open({
    directory: true,
    multiple: false,
    title: "选择 FabricAOT 项目目录",
  });
}
export async function saveDocument(
  name: string,
  content: string,
): Promise<boolean> {
  if (native) return invoke("save_document", { name, content });
  const url = URL.createObjectURL(
    new Blob([content], { type: "text/plain;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}
export function detectPlatform(environment: Environment | null): string {
  if (environment) return environment.os + " · " + environment.arch;
  return native ? "桌面模式" : "浏览器预览";
}
export function buildInstructions(settings: Settings, command: string): string {
  return (
    "FabricAOT 构建准备\nMinecraft 26.1.2 / Java 25 / Fabric / iOS ARM64\n\n在 macOS Apple Silicon 的终端中，先进入项目目录：\n" +
    settings.workspace +
    "\n\n执行以下命令进行元数据准备：\n" +
    command +
    "\n\n此命令使用 --prepare-only，不执行未审计的第三方 Mod。\n完整 AOT 编译、签名和 IPA 导出请按 docs/BUILDING.md 操作。\n静态预检不构成 Mod 真机兼容性证明。\n"
  );
}

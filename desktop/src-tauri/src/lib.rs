use serde::Serialize;
use serde_json::Value;
use std::{
    io::Read,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::OnceLock,
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

const MAX_OUTPUT: usize = 8 * 1024 * 1024;
#[derive(Debug)]
struct Captured {
    code: Option<i32>,
    stdout: String,
    stderr: String,
}

// Fixed tool invocations, literal arguments, bounded output, and a deadline; no shell.
fn capture(program: &str, args: &[&str], deadline: Duration) -> Result<Captured, String> {
    capture_with_script_dir(program, args, deadline, None)
}

// The tools import sibling modules (`preflight` -> `mod_file_policy`), so the
// interpreter needs the script directory on its module path. Passing it
// explicitly keeps the lookup deterministic without relying on the current
// working directory or on Python's implicit script-directory behaviour.
fn script_module_path(script: &Path) -> Option<String> {
    let dir = script.parent()?;
    let existing = std::env::var_os("PYTHONPATH").unwrap_or_default();
    let mut value = dir.as_os_str().to_owned();
    if !existing.is_empty() {
        value.push(":");
        value.push(existing);
    }
    Some(value.to_string_lossy().into_owned())
}

fn capture_with_script_dir(
    program: &str,
    args: &[&str],
    deadline: Duration,
    script: Option<&Path>,
) -> Result<Captured, String> {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(script) = script {
        if let Some(path) = script_module_path(script) {
            command.env("PYTHONPATH", path);
        }
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command
        .spawn()
        .map_err(|e| format!("无法启动 {program}：{e}"))?;
    let stdout = child.stdout.take().ok_or("无法读取标准输出")?;
    let stderr = child.stderr.take().ok_or("无法读取错误输出")?;
    fn read_pipe(pipe: impl Read, limit: usize) -> Result<Vec<u8>, String> {
        let mut bytes = Vec::new();
        pipe.take((limit + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|e| e.to_string())?;
        if bytes.len() > limit {
            return Err("工具输出超过允许大小".into());
        }
        Ok(bytes)
    }
    let out = thread::spawn(move || read_pipe(stdout, MAX_OUTPUT));
    let err = thread::spawn(move || read_pipe(stderr, 64 * 1024));
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if started.elapsed() < deadline => thread::sleep(Duration::from_millis(30)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err("工具运行超时，已终止进程".to_string());
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(error.to_string());
            }
        }
    };
    let stdout = out.join().map_err(|_| "输出读取线程异常")?;
    let stderr = err.join().map_err(|_| "错误读取线程异常")?;
    let code = status?.code();
    Ok(Captured {
        code,
        stdout: String::from_utf8(stdout?).map_err(|_| "工具输出不是 UTF-8")?,
        stderr: String::from_utf8_lossy(&stderr?).trim().into(),
    })
}
const MIN_PYTHON: (u32, u32) = (3, 11);

// GUI launches inherit launchd's PATH (/usr/bin:/bin:/usr/sbin:/sbin), where "python3" is the
// Xcode 3.9 stub. Run a candidate through "arch -arm64" so Rosetta-only interpreters fail here
// instead of inside the AOT host gate.
fn native_capture(program: &str, args: &[&str], deadline: Duration) -> Result<Captured, String> {
    if cfg!(target_os = "macos") {
        let mut native = vec!["-arm64", program];
        native.extend(args);
        capture("/usr/bin/arch", &native, deadline)
    } else {
        capture(program, args, deadline)
    }
}

// Same as `native_capture`, with the script directory on the module path.
fn native_capture_with_script(
    program: &str,
    args: &[&str],
    deadline: Duration,
    script: &Path,
) -> Result<Captured, String> {
    if cfg!(target_os = "macos") {
        let mut native = vec!["-arm64", program];
        native.extend(args);
        capture_with_script_dir("/usr/bin/arch", &native, deadline, Some(script))
    } else {
        capture_with_script_dir(program, args, deadline, Some(script))
    }
}

fn python_probe(program: &str) -> Option<(u32, u32)> {
    let output = native_capture(
        program,
        &[
            "-c",
            "import sys; print('%d.%d' % sys.version_info[:2])",
        ],
        Duration::from_secs(10),
    )
    .ok()?;
    if output.code != Some(0) {
        return None;
    }
    let mut parts = output.stdout.trim().split('.');
    Some((parts.next()?.parse().ok()?, parts.next()?.parse().ok()?))
}

fn discover_python() -> String {
    if cfg!(target_os = "windows") {
        return "python".into();
    }
    let mut candidates: Vec<String> = Vec::new();
    if let Some(path) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&path) {
            for name in ["python3.14", "python3.13", "python3.12", "python3.11", "python3"] {
                let candidate = dir.join(name);
                if candidate.is_file() {
                    candidates.push(candidate.to_string_lossy().into_owned());
                }
            }
        }
    }
    for known in [
        "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
    ] {
        candidates.push(known.into());
    }
    candidates
        .into_iter()
        .find(|program| python_probe(program).is_some_and(|version| version >= MIN_PYTHON))
        .unwrap_or_else(|| "python3".into())
}

fn python_program(custom: &str) -> String {
    if !custom.trim().is_empty() {
        return custom.trim().into();
    }
    static DISCOVERED: OnceLock<String> = OnceLock::new();
    DISCOVERED.get_or_init(discover_python).clone()
}
fn development_workspace() -> Option<PathBuf> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()?
        .parent()?
        .to_path_buf();
    root.join("tools/preflight.py").is_file().then_some(root)
}
#[tauri::command]
fn default_workspace() -> Option<String> {
    development_workspace().map(|p| p.to_string_lossy().into_owned())
}

// The macOS title bar, traffic lights and overlay scroll bars are drawn by the
// native window, not the webview. Applying the appearance app-wide keeps the
// window chrome on the same theme as the workbench.
#[tauri::command]
fn set_window_theme(app: tauri::AppHandle, theme: String) -> Result<(), String> {
    let theme = match theme.as_str() {
        "light" => tauri::Theme::Light,
        "dark" => tauri::Theme::Dark,
        other => return Err(format!("未知外观：{other}")),
    };
    app.set_theme(Some(theme));
    if let Some(window) = app.get_webview_window("main") {
        let background = if matches!(theme, tauri::Theme::Light) {
            (245, 245, 247, 255)
        } else {
            (24, 25, 27, 255)
        };
        window
            .set_background_color(Some(tauri::window::Color(
                background.0,
                background.1,
                background.2,
                background.3,
            )))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

// The webview does not expose the macOS accent color. Read AppKit's
// controlAccentColor once per launch and map it to the same interaction tokens
// used by the stylesheet; status colors stay independent.
#[tauri::command]
fn system_accent() -> String {
    #[cfg(target_os = "macos")]
    {
        use objc2_app_kit::{NSColor, NSColorSpace};
        objc2::rc::autoreleasepool(|_| {
            let color = NSColor::controlAccentColor();
            let space = NSColorSpace::sRGBColorSpace();
            color
                .colorUsingColorSpace(&space)
                .map(|value| {
                    format!(
                        "#{:02X}{:02X}{:02X}",
                        (value.redComponent() * 255.0).round() as u8,
                        (value.greenComponent() * 255.0).round() as u8,
                        (value.blueComponent() * 255.0).round() as u8
                    )
                })
                .unwrap_or_else(|| "#3478D4".into())
        })
    }
    #[cfg(not(target_os = "macos"))]
    {
        "#3478D4".into()
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Inspection {
    report: Value,
    elapsed_ms: u128,
}
fn inspect(script: PathBuf, source: &str, python: &str) -> Result<Inspection, String> {
    if source.is_empty() || source.len() > 4096 || source.contains(['\0', '\n', '\r']) {
        return Err("请选择有效的整合包文件或 Prism 实例目录".into());
    }
    let script_path = script.clone();
    let script = script_path.to_str().ok_or("预检脚本路径无法编码")?;
    let started = Instant::now();
    let python = python_program(python);
    let result = capture_with_script_dir(
        &python,
        &["-X", "utf8", script, source],
        Duration::from_secs(120),
        Some(&script_path),
    )?;
    if !matches!(result.code, Some(0 | 2)) {
        return Err(format!("预检工具异常退出：{}", result.stderr));
    }
    let report: Value = serde_json::from_str(&result.stdout)
        .map_err(|e| format!("预检工具未返回有效 JSON：{e} {}", result.stderr))?;
    if report.get("status").and_then(Value::as_str) != Some("STATIC_PREFLIGHT_ONLY") {
        return Err("预检报告类型不正确".into());
    }
    Ok(Inspection {
        report,
        elapsed_ms: started.elapsed().as_millis(),
    })
}
#[tauri::command]
async fn inspect_pack(
    app: tauri::AppHandle,
    source: String,
    python: String,
) -> Result<Inspection, String> {
    let bundled = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("tools/preflight.py");
    let script = if bundled.is_file() {
        bundled
    } else {
        development_workspace()
            .ok_or("找不到附带的静态预检脚本，请重新构建桌面应用")?
            .join("tools/preflight.py")
    };
    tauri::async_runtime::spawn_blocking(move || inspect(script, &source, &python))
        .await
        .map_err(|e| e.to_string())?
}

#[derive(Serialize)]
struct Check {
    name: String,
    status: &'static str,
    detail: String,
}
#[derive(Serialize)]
struct Environment {
    os: &'static str,
    arch: &'static str,
    checks: Vec<Check>,
}
fn tool_check(name: &str, program: &str, args: &[&str], expected: Option<&str>) -> Check {
    let (status, detail) = match capture(program, args, Duration::from_secs(15)) {
        Ok(output) if output.code == Some(0) => {
            let version = if output.stdout.trim().is_empty() {
                &output.stderr
            } else {
                &output.stdout
            };
            let first = version.lines().next().unwrap_or("没有版本输出");
            let correct = expected
                .map(|major| {
                    first
                        .split_whitespace()
                        .nth(1)
                        .unwrap_or("")
                        .split('.')
                        .next()
                        == Some(major)
                })
                .unwrap_or(true);
            (
                if correct { "ready" } else { "missing" },
                first.chars().take(240).collect(),
            )
        }
        Ok(output) => ("missing", output.stderr.chars().take(240).collect()),
        Err(error) => ("missing", error),
    };
    Check {
        name: name.into(),
        status,
        detail,
    }
}
fn python_check(custom: &str) -> Check {
    let program = python_program(custom);
    let (status, detail) = match python_probe(&program) {
        Some(version) if version >= MIN_PYTHON => (
            "ready",
            format!("{program} · Python {}.{}", version.0, version.1),
        ),
        Some((major, minor)) => (
            "missing",
            format!("{program} 是 Python {major}.{minor}，需要 3.11 或更高版本"),
        ),
        None => ("missing", format!("无法运行 {program}")),
    };
    Check {
        name: "Python 3".into(),
        status,
        detail,
    }
}
#[tauri::command]
async fn check_environment(python: String) -> Result<Environment, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python_thread = thread::spawn(move || python_check(&python));
        let java_thread =
            thread::spawn(|| tool_check("Java 25", "java", &["--version"], Some("25")));
        let xcode = if cfg!(target_os = "macos") {
            tool_check("Xcode", "/usr/bin/xcodebuild", &["-version"], None)
        } else {
            Check {
                name: "Xcode".into(),
                status: "unavailable",
                detail: "iOS 编译与签名需要 macOS Apple Silicon".into(),
            }
        };
        let python = python_thread.join().map_err(|_| "Python 检测异常")?;
        let java = java_thread.join().map_err(|_| "Java 检测异常")?;
        Ok(Environment {
            os: std::env::consts::OS,
            arch: std::env::consts::ARCH,
            checks: vec![python, java, xcode],
        })
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn save_document(
    app: tauri::AppHandle,
    name: String,
    content: String,
) -> Result<bool, String> {
    if content.len() > MAX_OUTPUT
        || (!name.ends_with(".json") && !name.ends_with(".txt"))
        || name.contains(['/', '\\'])
    {
        return Err("导出文件名或大小无效".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        match app.dialog().file().set_file_name(name).blocking_save_file() {
            Some(file) => {
                let path = file.into_path().map_err(|e| e.to_string())?;
                std::fs::write(path, content).map_err(|e| e.to_string())?;
                Ok(true)
            }
            None => Ok(false),
        }
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn workbench_action(
    workspace: String,
    python: String,
    action: String,
    request: Value,
    id: Option<String>,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        if ![
            "bootstrap",
            "check",
            "start",
            "status",
            "cancel",
            "history",
            "retry",
            "resolve-exclusions",
            "save-config",
            "reveal",
            "reveal-folder",
        ]
        .contains(&action.as_str())
        {
            return Err("不支持的工作台操作".into());
        }
        let root = PathBuf::from(&workspace)
            .canonicalize()
            .map_err(|e| e.to_string())?;
        if !root.join("tools/mcfao.py").is_file()
            || !root.join("tools/desktop_workbench.py").is_file()
        {
            return Err("请选择完整的 FabricAOT 项目目录".into());
        }
        let script = root.join("tools/desktop_workbench.py");
        let serialized = serde_json::to_string(&request).map_err(|e| e.to_string())?;
        if serialized.len() > 65536 {
            return Err("任务配置过大".into());
        }
        let actual_action = if action == "reveal" || action == "reveal-folder" {
            "status"
        } else {
            &action
        };
        let mut args = vec![
            "-B",
            script.to_str().ok_or("路径无法编码")?,
            actual_action,
            "--workspace",
            &workspace,
            "--request",
            &serialized,
        ];
        if let Some(ref ident) = id {
            args.extend(["--id", ident]);
        }
        // The desktop host may be Intel while running on Apple Silicon. Universal
        // Python otherwise inherits Rosetta and cannot satisfy the AOT host gate.
        let python = python_program(&python);
        let output = native_capture_with_script(
            &python,
            &args,
            Duration::from_secs(110),
            &script,
        )?;
        let value: Value = serde_json::from_str(&output.stdout)
            .map_err(|_| format!("构建服务未返回有效结果：{}", output.stderr))?;
        if output.code != Some(0) {
            return Err(value["error"].as_str().unwrap_or("构建操作失败").into());
        }
        if action == "reveal" || action == "reveal-folder" {
            let path = if action == "reveal-folder" {
                value["folder"].as_str()
            } else {
                value["ipa"].as_str().or_else(|| value["folder"].as_str())
            }
            .ok_or("没有可打开的产物")?;
            if cfg!(target_os = "macos") {
                Command::new("/usr/bin/open")
                    .args(["-R", path])
                    .spawn()
                    .map_err(|e| e.to_string())?;
            } else {
                return Err("此操作需要 macOS".into());
            }
        }
        Ok(value)
    })
    .await
    .map_err(|e| e.to_string())?
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            default_workspace,
            set_window_theme,
            system_accent,
            workbench_action,
            inspect_pack,
            check_environment,
            save_document
        ])
        .run(tauri::generate_context!())
        .expect("无法启动 FabricAOT 桌面工作台");
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn arguments_are_literal_and_unicode_is_preserved() {
        let value = "中文 path ' $(echo BAD) ; echo BAD";
        let python = python_program("");
        let result = capture(
            &python,
            &[
                "-X",
                "utf8",
                "-c",
                "import sys; print(sys.argv[1])",
                value,
            ],
            Duration::from_secs(5),
        )
        .unwrap();
        assert_eq!(result.stdout.trim(), value);
    }
    #[test]
    fn deadline_kills_process() {
        let python = python_program("");
        let result = capture(
            &python,
            &["-c", "import time; time.sleep(10)"],
            Duration::from_millis(100),
        );
        assert!(result.unwrap_err().contains("超时"));
    }
    #[test]
    fn output_is_bounded() {
        let python = python_program("");
        let result = capture(
            &python,
            &["-c", "import sys; sys.stdout.write('a' * (9 * 1024 * 1024))"],
            Duration::from_secs(5),
        );
        assert!(result.unwrap_err().contains("超过"));
    }
    #[test]
    fn default_interpreter_meets_the_build_requirement() {
        let python = python_program("");
        let version = python_probe(&python)
            .unwrap_or_else(|| panic!("默认解释器 {python} 无法运行"));
        assert!(
            version >= MIN_PYTHON,
            "默认解释器 {python} 是 {version:?}，低于 3.11"
        );
        assert_eq!(python_check("").status, "ready");
    }
    #[test]
    fn explicit_interpreter_choice_is_respected() {
        assert_eq!(python_program("  /opt/custom/python3.12  "), "/opt/custom/python3.12");
        let old = python_check("/usr/bin/python3");
        assert_eq!(old.status, "missing");
        assert!(old.detail.contains("3.9"), "{}", old.detail);
    }
    #[test]
    fn fatal_preflight_is_a_report_not_an_ipc_failure() {
        let result = inspect(
            development_workspace().unwrap().join("tools/preflight.py"),
            "/nonexistent/fabricaot-pack.mrpack",
            "",
        )
        .unwrap();
        assert_eq!(result.report["fatal"], true);
        assert_eq!(result.report["findings"][0]["code"], "NOT_FOUND");
        assert_eq!(result.report["aot_ios_verified"], false);
    }
    #[test]
    fn invalid_source_fails_before_process_launch() {
        assert!(inspect(PathBuf::from("invalid.py"), "a\nb", "")
            .unwrap_err()
            .contains("有效"));
    }

    #[test]
    fn tools_import_their_sibling_modules() {
        // `preflight` imports `mod_file_policy`; the interpreter only finds it
        // when the script directory is on the module path.
        let script = development_workspace().unwrap().join("tools/preflight.py");
        let dir = script.parent().unwrap().to_path_buf();
        assert_eq!(script_module_path(&script).unwrap(), dir.to_string_lossy());
        let python = python_program("");
        let output = capture_with_script_dir(
            &python,
            &["-X", "utf8", "-c", "import preflight"],
            Duration::from_secs(30),
            Some(&script),
        )
        .unwrap();
        assert_eq!(output.code, Some(0), "{}", output.stderr);
    }
}

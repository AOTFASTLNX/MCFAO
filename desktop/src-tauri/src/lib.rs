use serde::Serialize;
use serde_json::Value;
use std::{
    io::Read,
    path::PathBuf,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;
mod build_job;
#[tauri::command]
async fn stage_instance(
    workspace: String,
    source: String,
    python: String,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        if workspace
            .chars()
            .chain(source.chars())
            .any(|c| c.is_control())
        {
            return Err("路径包含控制字符".into());
        }
        let root = PathBuf::from(workspace)
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let source = PathBuf::from(source)
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let script = root.join("tools/import_instance.py");
        if !root.join(".git").exists() || !script.is_file() {
            return Err("请选择包含导入工具的 MCFAO 工作区".into());
        }
        let id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_nanos();
        let output = root.join("artifacts/desktop-imports").join(id.to_string());
        let args = vec![
            "-u".to_string(),
            "-B".into(),
            script.to_string_lossy().into_owned(),
            "--source".into(),
            source.to_string_lossy().into_owned(),
            "--output".into(),
            output.to_string_lossy().into_owned(),
        ];
        let result = capture(
            python_program(&python),
            &args.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
            Duration::from_secs(900),
        )?;
        if result.code != Some(0) {
            return Err(format!("实例文件导入失败：{}", result.stderr));
        }
        serde_json::from_str(&result.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

const MAX_OUTPUT: usize = 8 * 1024 * 1024;
#[derive(Debug)]
struct Captured {
    code: Option<i32>,
    stdout: String,
    stderr: String,
}

// Fixed tool invocations, literal arguments, bounded output, and a deadline; no shell.
fn capture(program: &str, args: &[&str], deadline: Duration) -> Result<Captured, String> {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
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
fn python_program(custom: &str) -> &str {
    if custom.trim().is_empty() {
        if std::path::Path::new("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3")
            .is_file()
        {
            return "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3";
        }
        if cfg!(target_os = "windows") {
            "python"
        } else {
            "python3"
        }
    } else {
        custom
    }
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
    let script = script.to_str().ok_or("预检脚本路径无法编码")?;
    let started = Instant::now();
    let result = capture(
        python_program(python),
        &["-I", "-X", "utf8", script, source],
        Duration::from_secs(120),
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
#[tauri::command]
async fn check_environment(python: String) -> Result<Environment, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let python_thread = thread::spawn(move || {
            tool_check(
                "Python 3",
                python_program(&python),
                &["--version"],
                Some("3"),
            )
        });
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
pub fn run() {
    tauri::Builder::default()
        .manage(build_job::Jobs::default())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            default_workspace,
            inspect_pack,
            check_environment,
            save_document,
            build_job::start_build,
            build_job::build_status,
            build_job::cancel_build,
            build_job::open_build_output,
            build_job::export_build_log,
            stage_instance,
            build_job::build_adaptation_report
        ])
        .build(tauri::generate_context!())
        .expect("无法启动 FabricAOT 桌面工作台")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                app.state::<build_job::Jobs>().shutdown();
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn arguments_are_literal_and_unicode_is_preserved() {
        let value = "中文 path ' $(echo BAD) ; echo BAD";
        let result = capture(
            python_program(""),
            &[
                "-I",
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
        let result = capture(
            python_program(""),
            &["-I", "-c", "import time; time.sleep(10)"],
            Duration::from_millis(100),
        );
        assert!(result.unwrap_err().contains("超时"));
    }
    #[test]
    fn output_is_bounded() {
        let result = capture(
            python_program(""),
            &[
                "-I",
                "-c",
                "import sys; sys.stdout.write('a' * (9 * 1024 * 1024))",
            ],
            Duration::from_secs(5),
        );
        assert!(result.unwrap_err().contains("超过"));
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
}

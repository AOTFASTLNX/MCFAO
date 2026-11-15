use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::VecDeque,
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri_plugin_dialog::DialogExt;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BuildRequest {
    workspace: String,
    config: String,
    output: String,
    python: String,
    renderer: String,
    loader: String,
    mods: String,
    audited_mods: bool,
    unsigned: bool,
    bundle_id: String,
    heap_gib: u8,
    parallelism: u8,
    #[serde(default)]
    instance_data: String,
}
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    id: String,
    state: String,
    stage: String,
    output: String,
    log_path: String,
    lines: VecDeque<String>,
    artifact: Option<Value>,
    error: Option<String>,
}
struct Job {
    snapshot: Snapshot,
    pid: Option<u32>,
}
#[derive(Clone, Default)]
pub struct Jobs(Arc<Mutex<Option<Job>>>);

fn text_path(value: &str) -> Result<PathBuf, String> {
    if value.trim().is_empty() || value.len() > 4096 || value.chars().any(|c| c.is_control()) {
        return Err("路径不能为空或包含控制字符".into());
    }
    let path = PathBuf::from(value);
    if path
        .components()
        .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err("路径不允许 ..".into());
    }
    Ok(path)
}
fn under(root: &Path, value: &str) -> Result<PathBuf, String> {
    let path = text_path(value)?;
    Ok(if path.is_absolute() {
        path
    } else {
        root.join(path)
    })
}
fn checked(request: &BuildRequest) -> Result<(PathBuf, PathBuf, Vec<String>, String), String> {
    if !cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        return Err("完整构建需要 Apple Silicon macOS".into());
    }
    if !["gl41", "metal"].contains(&request.renderer.as_str())
        || !["vanilla", "fabric"].contains(&request.loader.as_str())
    {
        return Err("未知渲染器或加载器".into());
    }
    if !(6..=9).contains(&request.heap_gib) || !(1..=8).contains(&request.parallelism) {
        return Err("AOT 参数超出范围".into());
    }
    if request.bundle_id.len() > 180
        || !request.bundle_id.contains('.')
        || !request
            .bundle_id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'-')
    {
        return Err("Bundle ID 无效".into());
    }
    let root = text_path(&request.workspace)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if !root.join(".git").exists() || !root.join("tools/mcfao.py").is_file() {
        return Err("请选择完整 MCFAO Git 工作区".into());
    }
    let config = under(&root, &request.config)?
        .canonicalize()
        .map_err(|e| format!("配置文件：{e}"))?;
    if config.extension().and_then(|s| s.to_str()) != Some("json")
        || fs::metadata(&config).map_err(|e| e.to_string())?.len() > 1024 * 1024
    {
        return Err("配置必须是小于 1 MiB 的 JSON".into());
    }
    let output = under(&root, &request.output)?;
    for ancestor in output.ancestors() {
        if let Ok(meta) = fs::symlink_metadata(ancestor) {
            if meta.file_type().is_symlink() {
                return Err("输出路径不能经过符号链接".into());
            }
        }
    }
    if root.starts_with(&output)
        || (output.starts_with(&root) && !output.starts_with(root.join("artifacts")))
    {
        return Err("项目内输出必须位于 artifacts 子目录，且不能覆盖源码".into());
    }
    if output.is_dir()
        && fs::read_dir(&output)
            .map_err(|e| e.to_string())?
            .next()
            .is_some()
        && !output.join("inputs.json").is_file()
    {
        return Err("输出目录非空且不是可重试构建".into());
    }
    if output.join("result.json").exists() {
        return Err("已完成的构建不可覆盖，请选择新目录".into());
    }
    let mut args = vec![
        "-u".into(),
        "-B".into(),
        root.join("tools/mcfao.py").to_string_lossy().into_owned(),
        "build".into(),
        "--version".into(),
        "26.1.2".into(),
        "--loader".into(),
        request.loader.clone(),
        "--renderer".into(),
        request.renderer.clone(),
        "--target".into(),
        "ios-arm64".into(),
        "--config".into(),
        config.to_string_lossy().into_owned(),
        "--output".into(),
        output.to_string_lossy().into_owned(),
        "--bundle-id".into(),
        request.bundle_id.clone(),
        "--heap-gib".into(),
        request.heap_gib.to_string(),
        "--parallelism".into(),
        request.parallelism.to_string(),
    ];
    if request.unsigned {
        args.push("--unsigned".into());
    }
    if request.loader == "fabric" {
        if !request.audited_mods {
            return Err("Fabric 完整转换需要确认 Mod 已审计；构建仍使用默认拒绝沙盒".into());
        }
        let mods = under(&root, &request.mods)?
            .canonicalize()
            .map_err(|e| e.to_string())?;
        if !mods.is_dir() {
            return Err("Mod 路径必须是目录".into());
        }
        args.extend([
            "--mods".into(),
            mods.to_string_lossy().into_owned(),
            "--audited-mods".into(),
        ]);
        if !request.instance_data.is_empty() {
            let instance = under(&root, &request.instance_data)?
                .canonicalize()
                .map_err(|e| e.to_string())?;
            if !instance.join("import.json").is_file() {
                return Err("实例导入清单缺失".into());
            }
            args.extend([
                "--instance-data".into(),
                instance.to_string_lossy().into_owned(),
            ]);
        }
    }
    let python = if request.python.trim().is_empty() {
        let installed = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3";
        if Path::new(installed).is_file() {
            installed.to_string()
        } else {
            "python3".to_string()
        }
    } else {
        let path = text_path(&request.python)?;
        if !path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .starts_with("python3")
        {
            return Err("请选择 Python 3 解释器".into());
        }
        request.python.clone()
    };
    Ok((root, output, args, python))
}
fn append(jobs: &Jobs, text: &str) {
    if let Ok(mut guard) = jobs.0.lock() {
        if let Some(job) = guard.as_mut() {
            for line in text.lines() {
                for (prefix, stage) in [
                    ("split:", "方法拆分"),
                    ("fabric:", "Fabric / MDAF 适配"),
                    ("gl41-patch:", "GL41 客户端适配"),
                    ("metal-injection:", "Metal 客户端适配"),
                    ("aot:", "AOT 分析与编译"),
                    ("runtime:", "iOS 运行时"),
                    ("link:", "iOS 链接"),
                    ("stage:", "动态库与资源打包"),
                    ("package:", "Xcode / IPA 导出与完整性校验"),
                ] {
                    if line.starts_with(prefix) {
                        job.snapshot.stage = stage.into();
                    }
                }
                job.snapshot.lines.push_back(line.to_string());
                while job.snapshot.lines.len() > 2000 {
                    job.snapshot.lines.pop_front();
                }
            }
        }
    }
}
fn stream(
    mut pipe: impl Read + Send + 'static,
    jobs: Jobs,
    log: Arc<Mutex<File>>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let mut bytes = [0u8; 4096];
        loop {
            match pipe.read(&mut bytes) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    if let Ok(mut file) = log.lock() {
                        let _ = file.write_all(&bytes[..count]);
                    }
                    append(&jobs, &String::from_utf8_lossy(&bytes[..count]));
                }
            }
        }
    })
}
impl Jobs {
    pub fn shutdown(&self) {
        if let Ok(guard) = self.0.lock() {
            if let Some(pid) = guard.as_ref().and_then(|job| job.pid) {
                #[cfg(unix)]
                let _ = stop_tree(pid);
            }
        }
    }
    fn start(&self, request: BuildRequest) -> Result<Snapshot, String> {
        let (root, output, args, python) = checked(&request)?;
        let mut guard = self.0.lock().map_err(|e| e.to_string())?;
        if guard.as_ref().is_some_and(|j| j.pid.is_some()) {
            return Err("已有构建在运行".into());
        }
        let id = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_nanos()
            .to_string();
        let parent = output.parent().ok_or("输出目录无父目录")?;
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        let log_path = parent.join(format!("gui-build-{id}.log"));
        let log = Arc::new(Mutex::new(
            File::create(&log_path).map_err(|e| e.to_string())?,
        ));
        let mut command = Command::new(&python);
        command
            .args(args)
            .current_dir(&root)
            .env("MCFAO_STREAM_LOGS", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        for name in [
            "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "_JAVA_OPTIONS",
            "CLASSPATH",
        ] {
            command.env_remove(name);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        let mut child = command
            .spawn()
            .map_err(|e| format!("无法启动 Python 3：{e}"))?;
        let snapshot = Snapshot {
            id,
            state: "running".into(),
            stage: "依赖 / 工具链与游戏资源校验".into(),
            output: output.to_string_lossy().into_owned(),
            log_path: log_path.to_string_lossy().into_owned(),
            lines: VecDeque::new(),
            artifact: None,
            error: None,
        };
        *guard = Some(Job {
            snapshot: snapshot.clone(),
            pid: Some(child.id()),
        });
        let jobs = self.clone();
        thread::spawn(move || {
            let out = stream(child.stdout.take().unwrap(), jobs.clone(), log.clone());
            let err = stream(child.stderr.take().unwrap(), jobs.clone(), log);
            let status = child.wait();
            let _ = out.join();
            let _ = err.join();
            if let Ok(mut guard) = jobs.0.lock() {
                if let Some(job) = guard.as_mut() {
                    job.pid = None;
                    if job.snapshot.state == "cancelled" {
                        return;
                    }
                    match status {
                        Ok(status) if status.success() => {
                            let verified = (|| -> Result<Value, String> {
                                let value: Value = serde_json::from_slice(
                                    &fs::read(output.join("result.json"))
                                        .map_err(|e| e.to_string())?,
                                )
                                .map_err(|e| e.to_string())?;
                                let ipa = Path::new(value["ipa"].as_str().ok_or("构建未返回 IPA")?)
                                    .canonicalize()
                                    .map_err(|e| e.to_string())?;
                                if !ipa
                                    .starts_with(output.canonicalize().map_err(|e| e.to_string())?)
                                    || value["renderer"] != request.renderer
                                {
                                    return Err("产物路径或渲染器不匹配".into());
                                }
                                let hash = Command::new("/usr/bin/shasum")
                                    .args(["-a", "256"])
                                    .arg(&ipa)
                                    .output()
                                    .map_err(|e| e.to_string())?;
                                let digest = String::from_utf8_lossy(&hash.stdout)
                                    .split_whitespace()
                                    .next()
                                    .unwrap_or("")
                                    .to_string();
                                if !hash.status.success()
                                    || value["sha256"] != digest
                                    || value["bytes"].as_u64()
                                        != Some(
                                            fs::metadata(&ipa).map_err(|e| e.to_string())?.len(),
                                        )
                                {
                                    return Err("IPA 大小或 SHA-256 校验失败".into());
                                }
                                Ok(value)
                            })();
                            match verified {
                                Ok(value) => {
                                    job.snapshot.state = "done".into();
                                    job.snapshot.stage =
                                        "IPA 完整性校验通过；真机验收单独记录".into();
                                    job.snapshot.artifact = Some(value);
                                }
                                Err(error) => {
                                    job.snapshot.state = "failed".into();
                                    job.snapshot.error = Some(error);
                                }
                            }
                        }
                        other => {
                            job.snapshot.state = "failed".into();
                            job.snapshot.error =
                                Some(format!("构建进程失败：{other:?}。请查看完整日志。"));
                        }
                    }
                }
            }
        });
        Ok(snapshot)
    }
}

// Stop the root before enumerating descendants, then freeze descendants before killing them.
// Nested sandbox / capture processes create their own sessions, so killpg alone is insufficient.
#[cfg(unix)]
fn stop_tree(pid: u32) -> Result<(), String> {
    unsafe {
        libc::kill(pid as i32, libc::SIGSTOP);
    }
    let mut known = vec![pid];
    for _ in 0..3 {
        let listing = Command::new("/bin/ps")
            .args(["-axo", "pid=,ppid="])
            .output()
            .map_err(|e| e.to_string())?;
        let pairs: Vec<(u32, u32)> = String::from_utf8_lossy(&listing.stdout)
            .lines()
            .filter_map(|line| {
                let mut p = line.split_whitespace();
                Some((p.next()?.parse().ok()?, p.next()?.parse().ok()?))
            })
            .collect();
        loop {
            let mut added = false;
            for (child, parent) in &pairs {
                if known.contains(parent) && !known.contains(child) {
                    known.push(*child);
                    unsafe {
                        libc::kill(*child as i32, libc::SIGSTOP);
                    }
                    added = true;
                }
            }
            if !added {
                break;
            }
        }
    }
    for child in known.iter().rev() {
        unsafe {
            libc::kill(*child as i32, libc::SIGKILL);
        }
    }
    Ok(())
}
#[tauri::command]
pub fn start_build(
    jobs: tauri::State<'_, Jobs>,
    request: BuildRequest,
) -> Result<Snapshot, String> {
    jobs.start(request)
}
#[tauri::command]
pub fn build_status(jobs: tauri::State<'_, Jobs>) -> Result<Option<Snapshot>, String> {
    Ok(jobs
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .as_ref()
        .map(|j| j.snapshot.clone()))
}
#[tauri::command]
pub fn cancel_build(jobs: tauri::State<'_, Jobs>) -> Result<(), String> {
    let mut guard = jobs.0.lock().map_err(|e| e.to_string())?;
    if let Some(job) = guard.as_mut() {
        if let Some(pid) = job.pid {
            #[cfg(unix)]
            stop_tree(pid)?;
            job.snapshot.state = "cancelled".into();
            job.snapshot.stage = "已取消；保留日志与已验证缓存".into();
        }
    }
    Ok(())
}
#[tauri::command]
pub fn open_build_output(jobs: tauri::State<'_, Jobs>) -> Result<(), String> {
    let guard = jobs.0.lock().map_err(|e| e.to_string())?;
    let job = guard.as_ref().ok_or("没有构建任务")?;
    let path = Path::new(&job.snapshot.output);
    let path = if path.exists() {
        path
    } else {
        path.parent().ok_or("目录不存在")?
    };
    Command::new("/usr/bin/open")
        .arg(path)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}
#[tauri::command]
pub async fn export_build_log(
    app: tauri::AppHandle,
    jobs: tauri::State<'_, Jobs>,
) -> Result<bool, String> {
    let source = {
        let guard = jobs.0.lock().map_err(|e| e.to_string())?;
        PathBuf::from(&guard.as_ref().ok_or("没有构建任务")?.snapshot.log_path)
    };
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .set_file_name("fabricaot-build.txt")
            .blocking_save_file()
        else {
            return Ok(false);
        };
        let destination = file.into_path().map_err(|e| e.to_string())?;
        if destination == source {
            return Err("请选择不同的日志导出路径".into());
        }
        fs::copy(source, destination).map_err(|e| e.to_string())?;
        Ok(true)
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
pub fn build_adaptation_report(jobs: tauri::State<'_, Jobs>) -> Result<Option<Value>, String> {
    let guard = jobs.0.lock().map_err(|e| e.to_string())?;
    let Some(job) = guard.as_ref() else {
        return Ok(None);
    };
    let root = Path::new(&job.snapshot.output);
    let fabric = root.join("fabric");
    if !fabric.is_dir() {
        return Ok(None);
    }
    let canonical = root.canonicalize().map_err(|e| e.to_string())?;
    let mut candidates = Vec::new();
    for entry in fs::read_dir(&fabric).map_err(|e| e.to_string())? {
        let attempt = entry.map_err(|e| e.to_string())?.path();
        let path = attempt.join("product/result.json");
        if let Ok(metadata) = fs::metadata(&path) {
            if metadata.len() > 16 * 1024 * 1024 {
                continue;
            }
            if let Ok(path) = path.canonicalize() {
                if path.starts_with(&canonical) {
                    candidates.push((metadata.modified().ok(), path));
                }
            }
        }
    }
    candidates.sort_by(|a, b| a.0.cmp(&b.0));
    let Some((_, path)) = candidates.pop() else {
        return Ok(None);
    };
    let report: Value = serde_json::from_slice(&fs::read(&path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let mut selected = serde_json::Map::new();
    for key in [
        "status",
        "mods",
        "mdaf",
        "semanticCompatibility",
        "excludedMods",
        "retiredJars",
        "tracingAgent",
        "error",
        "sandbox",
    ] {
        if let Some(value) = report.get(key) {
            selected.insert(key.into(), value.clone());
        }
    }
    selected.insert(
        "reportPath".into(),
        Value::String(path.to_string_lossy().into_owned()),
    );
    selected.insert(
        "runtimeValidation".into(),
        Value::String("NOT RUN - no FUNCTION_PASS from static/AOT analysis".into()),
    );
    Ok(Some(Value::Object(selected)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "Runs genuine local Minecraft AOT; requires licensed local assets and explicit output"]
    fn actual_local_aot_through_tauri_ipc() {
        let jobs = Jobs::default();
        let app = tauri::test::mock_builder()
            .manage(jobs.clone())
            .invoke_handler(tauri::generate_handler![
                start_build,
                build_status,
                cancel_build
            ])
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .unwrap();
        let webview = tauri::WebviewWindowBuilder::new(&app, "main", Default::default())
            .build()
            .unwrap();
        let mut r = request();
        r.config = std::env::var("MCFAO_TEST_CONFIG").expect("explicit local config required");
        r.output = std::env::var("MCFAO_TEST_OUTPUT").expect("explicit fresh output required");
        let response = tauri::test::get_ipc_response(
            &webview,
            tauri::webview::InvokeRequest {
                cmd: "start_build".into(),
                callback: tauri::ipc::CallbackFn(0),
                error: tauri::ipc::CallbackFn(1),
                url: "tauri://localhost".parse().unwrap(),
                body: tauri::ipc::InvokeBody::Json(serde_json::json!({"request":r})),
                headers: Default::default(),
                invoke_key: tauri::test::INVOKE_KEY.into(),
            },
        );
        assert!(response.is_ok(), "start IPC failed: {response:?}");
        let started = std::time::Instant::now();
        loop {
            let snapshot = jobs.0.lock().unwrap().as_ref().unwrap().snapshot.clone();
            if snapshot.state != "running" {
                let path = Path::new(&snapshot.output)
                    .parent()
                    .unwrap()
                    .join(format!("tauri-workflow-{}.json", snapshot.id));
                fs::write(path, serde_json::to_vec_pretty(&snapshot).unwrap()).unwrap();
                assert_eq!(snapshot.state, "done", "{:?}", snapshot.error);
                assert!(snapshot.artifact.is_some());
                break;
            }
            if started.elapsed() > std::time::Duration::from_secs(1800) {
                jobs.shutdown();
                panic!("full AOT workflow timed out");
            }
            std::thread::sleep(std::time::Duration::from_millis(500));
        }
    }
    fn request() -> BuildRequest {
        BuildRequest {
            workspace: Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .to_string_lossy()
                .into_owned(),
            config: "artifacts/integration-20261115/config-gl41.json".into(),
            output: "artifacts/gui-test".into(),
            python: "".into(),
            renderer: "gl41".into(),
            loader: "vanilla".into(),
            mods: "".into(),
            instance_data: "".into(),
            audited_mods: false,
            unsigned: true,
            bundle_id: "org.fabricaot.integration.test".into(),
            heap_gib: 7,
            parallelism: 3,
        }
    }
    #[test]
    fn rejects_unsafe_paths_and_unknown_modes() {
        for path in ["", "x\ny", "a/../b"] {
            assert!(text_path(path).is_err());
        }
        let mut r = request();
        r.renderer = "x; touch /tmp/no".into();
        assert!(checked(&r).is_err());
    }
    fn fixture() -> (PathBuf, BuildRequest) {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "mcfao-中文 $ literal-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(root.join("tools")).unwrap();
        fs::write(root.join(".git"), "fixture").unwrap();
        fs::write(
            root.join("tools/mcfao.py"),
            "# validation-only first-party test fixture",
        )
        .unwrap();
        fs::write(root.join("config.json"), "{}").unwrap();
        let mut r = request();
        r.workspace = root.to_string_lossy().into_owned();
        r.config = "config.json".into();
        (root, r)
    }
    #[test]
    fn fabric_requires_audited_inputs_before_execution() {
        let (root, mut r) = fixture();
        r.loader = "fabric".into();
        r.audited_mods = false;
        let err = checked(&r).unwrap_err();
        fs::remove_dir_all(root).unwrap();
        assert!(err.contains("审计"), "{err}");
    }
    #[test]
    fn full_build_argv_preserves_paths_and_has_no_prepare_only() {
        let (root, r) = fixture();
        let (_, _, argv, _) = checked(&r).unwrap();
        assert!(!argv.iter().any(|s| s == "--prepare-only"));
        assert!(argv.contains(&"--unsigned".into()));
        assert_eq!(argv[2], root.join("tools/mcfao.py").to_string_lossy());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn tauri_commands_are_invocable_and_reject_unknown_renderer() {
        let app = tauri::test::mock_builder()
            .manage(Jobs::default())
            .invoke_handler(tauri::generate_handler![
                start_build,
                build_status,
                cancel_build
            ])
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .unwrap();
        let webview = tauri::WebviewWindowBuilder::new(&app, "main", Default::default())
            .build()
            .unwrap();
        let call = |cmd: &str, body: Value| {
            tauri::test::get_ipc_response(
                &webview,
                tauri::webview::InvokeRequest {
                    cmd: cmd.into(),
                    callback: tauri::ipc::CallbackFn(0),
                    error: tauri::ipc::CallbackFn(1),
                    url: "tauri://localhost".parse().unwrap(),
                    body: tauri::ipc::InvokeBody::Json(body),
                    headers: Default::default(),
                    invoke_key: tauri::test::INVOKE_KEY.into(),
                },
            )
        };
        assert!(call("build_status", serde_json::json!({}))
            .unwrap()
            .deserialize::<Option<Value>>()
            .unwrap()
            .is_none());
        let mut r = request();
        r.renderer = "invalid".into();
        assert!(call("start_build", serde_json::json!({"request":r})).is_err());
        assert!(call("cancel_build", serde_json::json!({})).is_ok());
    }
    #[test]
    fn stage_and_log_buffer_are_bounded() {
        let jobs = Jobs::default();
        *jobs.0.lock().unwrap() = Some(Job {
            pid: None,
            snapshot: Snapshot {
                id: "test".into(),
                state: "running".into(),
                stage: "".into(),
                output: "".into(),
                log_path: "".into(),
                lines: VecDeque::new(),
                artifact: None,
                error: None,
            },
        });
        for _ in 0..3000 {
            append(&jobs, "aot: analysis");
        }
        let state = jobs.0.lock().unwrap();
        let s = &state.as_ref().unwrap().snapshot;
        assert_eq!(s.lines.len(), 2000);
        assert_eq!(s.stage, "AOT 分析与编译");
    }
    #[test]
    fn cancellation_kills_nested_sessions_and_preserves_unrelated_process() {
        use std::io::{BufRead, BufReader};
        let mut sentinel = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let mut root=Command::new("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3")
            .args(["-u","-c","import subprocess,time; p=subprocess.Popen(['/bin/sleep','30'],start_new_session=True); print(p.pid,flush=True); time.sleep(30)"])
            .stdout(Stdio::piped()).spawn().unwrap();
        let mut line = String::new();
        BufReader::new(root.stdout.take().unwrap())
            .read_line(&mut line)
            .unwrap();
        let nested: u32 = line.trim().parse().unwrap();
        let result = stop_tree(root.id());
        let exited = root.wait().unwrap();
        let sentinel_alive = sentinel.try_wait().unwrap().is_none();
        let _ = sentinel.kill();
        let _ = sentinel.wait();
        assert!(result.is_ok());
        assert!(!exited.success());
        assert!(sentinel_alive);
        let status = Command::new("/bin/ps")
            .args(["-p", &nested.to_string(), "-o", "stat="])
            .output()
            .unwrap();
        let stat = String::from_utf8_lossy(&status.stdout);
        assert!(
            stat.trim().is_empty() || stat.trim().starts_with('Z'),
            "nested session survived: {stat}"
        );
    }
}

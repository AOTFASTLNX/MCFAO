//! Remembers the workbench window size between launches.
//!
//! The size is stored in logical points, so a window restored on a Retina or
//! an external display keeps the same apparent size. Only the normal window
//! size is recorded; maximised, fullscreen and minimised frames are skipped.

use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        mpsc::{self, RecvTimeoutError},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::Duration,
};
use tauri::{LogicalSize, WebviewWindow, WindowEvent};

pub const MIN_WIDTH: f64 = 800.0;
pub const MIN_HEIGHT: f64 = 640.0;
const DEFAULT_WIDTH: f64 = 1100.0;
const DEFAULT_HEIGHT: f64 = 760.0;
const MAX_WIDTH: f64 = 10_000.0;
const MAX_HEIGHT: f64 = 10_000.0;
// The work area excludes the menu bar and Dock, but the window frame (and a
// little breathing room) still has to fit inside it.
const EDGE_ALLOWANCE_X: f64 = 32.0;
const EDGE_ALLOWANCE_Y: f64 = 64.0;
const DEBOUNCE: Duration = Duration::from_millis(500);
const STATE_VERSION: u32 = 1;

const DEFAULT_SIZE: WindowSize = WindowSize {
    width: DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct WindowSize {
    pub width: f64,
    pub height: f64,
}

#[derive(Serialize, Deserialize)]
struct StoredFile {
    #[serde(default = "state_version")]
    version: u32,
    #[serde(default)]
    width: f64,
    #[serde(default)]
    height: f64,
}

fn state_version() -> u32 {
    STATE_VERSION
}

/// Restores the last normal size, clamped to the current work area, before the
/// window is shown. A missing or damaged file keeps the design default.
fn restore_target(window: &WebviewWindow, path: Option<&Path>) -> Option<WindowSize> {
    let saved = path.and_then(read_state).unwrap_or(DEFAULT_SIZE);
    let size = clamp_to_work_area(saved, work_area(window));
    if window
        .set_size(LogicalSize::new(size.width, size.height))
        .is_ok()
    {
        let _ = window.center();
    }
    Some(size)
}

/// Tracks normal resize events and writes them after the drag settles.
pub struct WindowMemory {
    sender: Mutex<Option<mpsc::Sender<WriterCommand>>>,
    worker: Mutex<Option<JoinHandle<()>>>,
    last_normal: Arc<Mutex<Option<WindowSize>>>,
}

impl WindowMemory {
    pub fn install(window: &WebviewWindow, path: Option<PathBuf>) -> Self {
        let restored = restore_target(window, path.as_deref());
        let (sender, receiver) = mpsc::channel();
        let worker = thread::spawn(move || writer_loop(receiver, path));
        let last_normal = Arc::new(Mutex::new(None));
        let restored = Arc::new(Mutex::new(restored));
        let memory = Self {
            sender: Mutex::new(Some(sender.clone())),
            worker: Mutex::new(Some(worker)),
            last_normal: last_normal.clone(),
        };
        let window = window.clone();
        let observer = window.clone();
        observer.on_window_event(move |event| match event {
            WindowEvent::Resized(size) => {
                if size.width == 0 || size.height == 0 {
                    return;
                }
                // Resizes while the window is still hidden belong to the
                // restore step, not to a user drag.
                if !window.is_visible().unwrap_or(true) {
                    return;
                }
                if window.is_minimized().unwrap_or(false)
                    || window.is_maximized().unwrap_or(false)
                    || window.is_fullscreen().unwrap_or(false)
                {
                    return;
                }
                let scale = window.scale_factor().unwrap_or(1.0);
                if !scale.is_finite() || scale <= 0.0 {
                    return;
                }
                let Some(size) = sanitize(size.width as f64 / scale, size.height as f64 / scale)
                else {
                    return;
                };
                // The restore may have clamped the saved size to a smaller
                // work area (for example after unplugging an external
                // display). Do not replace the user's larger saved choice
                // with that temporary frame.
                if let Ok(mut restored) = restored.lock() {
                    if matches_restore(*restored, size) {
                        return;
                    }
                    *restored = None;
                }
                if let Ok(mut last) = last_normal.lock() {
                    *last = Some(size);
                }
                let _ = sender.send(WriterCommand::Size(size));
            }
            WindowEvent::CloseRequested { .. } => {
                // A window closed from a zoomed or fullscreen frame must not
                // replace the normal size the user chose earlier.
                if window.is_maximized().unwrap_or(false)
                    || window.is_fullscreen().unwrap_or(false)
                {
                    return;
                }
                if let Some(size) = last_normal.lock().ok().and_then(|last| *last) {
                    let _ = sender.send(WriterCommand::Flush(size));
                }
            }
            _ => {}
        });
        memory
    }

    /// Writes a pending size and stops the writer thread at application exit.
    pub fn shutdown(&self) {
        let last = self.last_normal.lock().ok().and_then(|last| *last);
        if let Ok(sender) = self.sender.lock() {
            if let Some(sender) = sender.as_ref() {
                // Cmd-Q does not necessarily emit a close request; flush the
                // latest normal size here as well as in the close handler.
                if let Some(size) = last {
                    let _ = sender.send(WriterCommand::Flush(size));
                }
                let _ = sender.send(WriterCommand::Stop);
            }
        }
        if let Ok(mut worker) = self.worker.lock() {
            if let Some(worker) = worker.take() {
                let _ = worker.join();
            }
        }
    }
}

enum WriterCommand {
    Size(WindowSize),
    Flush(WindowSize),
    Stop,
}

fn writer_loop(receiver: mpsc::Receiver<WriterCommand>, path: Option<PathBuf>) {
    let mut pending: Option<WindowSize> = None;
    loop {
        let command = if pending.is_some() {
            match receiver.recv_timeout(DEBOUNCE) {
                Ok(command) => command,
                Err(RecvTimeoutError::Timeout) => {
                    if let Some(size) = pending.take() {
                        write_state(path.as_deref(), size);
                    }
                    continue;
                }
                Err(RecvTimeoutError::Disconnected) => {
                    if let Some(size) = pending.take() {
                        write_state(path.as_deref(), size);
                    }
                    return;
                }
            }
        } else {
            match receiver.recv() {
                Ok(command) => command,
                Err(_) => return,
            }
        };
        match command {
            WriterCommand::Size(size) => pending = Some(size),
            WriterCommand::Flush(size) => {
                pending = None;
                write_state(path.as_deref(), size);
            }
            WriterCommand::Stop => {
                if let Some(size) = pending.take() {
                    write_state(path.as_deref(), size);
                }
                return;
            }
        }
    }
}

fn work_area(window: &WebviewWindow) -> Option<(f64, f64)> {
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten())?;
    let scale = monitor.scale_factor();
    if !scale.is_finite() || scale <= 0.0 {
        return None;
    }
    let area = monitor.work_area().size;
    Some((area.width as f64 / scale, area.height as f64 / scale))
}

fn read_state(path: &Path) -> Option<WindowSize> {
    parse_state(&fs::read_to_string(path).ok()?)
}

fn parse_state(raw: &str) -> Option<WindowSize> {
    let stored: StoredFile = serde_json::from_str(raw).ok()?;
    sanitize(stored.width, stored.height)
}

fn sanitize(width: f64, height: f64) -> Option<WindowSize> {
    if !width.is_finite() || !height.is_finite() {
        return None;
    }
    if width < 1.0 || height < 1.0 || width > MAX_WIDTH || height > MAX_HEIGHT {
        return None;
    }
    Some(WindowSize {
        width: width.round(),
        height: height.round(),
    })
}

// A resize event can arrive a frame or two after the requested size has been
// applied, and it can be rounded by the display's backing scale. Treat the
// reported size as the restore frame when it is within one point of the target.
fn matches_restore(restored: Option<WindowSize>, reported: WindowSize) -> bool {
    restored.is_some_and(|target| {
        (target.width - reported.width).abs() <= 1.0
            && (target.height - reported.height).abs() <= 1.0
    })
}

fn clamp_to_work_area(size: WindowSize, area: Option<(f64, f64)>) -> WindowSize {
    let mut width = size.width.max(MIN_WIDTH);
    let mut height = size.height.max(MIN_HEIGHT);
    if let Some((area_width, area_height)) = area {
        if area_width.is_finite() && area_height.is_finite() {
            width = width.min((area_width - EDGE_ALLOWANCE_X).max(MIN_WIDTH));
            height = height.min((area_height - EDGE_ALLOWANCE_Y).max(MIN_HEIGHT));
        }
    }
    WindowSize {
        width: width.round(),
        height: height.round(),
    }
}

fn write_state(path: Option<&Path>, size: WindowSize) {
    let Some(path) = path else {
        return;
    };
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }
    let Ok(bytes) = serde_json::to_vec_pretty(&StoredFile {
        version: STATE_VERSION,
        width: size.width,
        height: size.height,
    }) else {
        return;
    };
    let temporary = path.with_extension("json.tmp");
    if fs::write(&temporary, bytes).is_err() {
        return;
    }
    if fs::rename(&temporary, path).is_err() {
        // Windows cannot rename over an existing file; replace it explicitly.
        let _ = fs::remove_file(path);
        let _ = fs::rename(&temporary, path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_path(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ncl-window-memory-{}-{name}.json",
            std::process::id()
        ))
    }

    #[test]
    fn window_size_round_trips_through_disk() {
        let path = temporary_path("roundtrip");
        let _ = fs::remove_file(&path);
        write_state(
            Some(&path),
            WindowSize {
                width: 1280.0,
                height: 820.0,
            },
        );
        assert_eq!(
            read_state(&path),
            Some(WindowSize {
                width: 1280.0,
                height: 820.0,
            })
        );
        assert!(!path.with_extension("json.tmp").exists());
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn malformed_or_absurd_state_falls_back() {
        assert_eq!(parse_state("not json"), None);
        assert_eq!(parse_state(r#"{"width": 0, "height": 760}"#), None);
        assert_eq!(parse_state(r#"{"width": 1100}"#), None);
        assert_eq!(parse_state(r#"{"width": 1e9, "height": 760}"#), None);
        assert_eq!(
            parse_state(r#"{"version": 2, "width": 1100.5, "height": 760.4, "x": 10}"#),
            Some(WindowSize {
                width: 1101.0,
                height: 760.0,
            })
        );
    }

    #[test]
    fn restored_size_stays_inside_the_work_area() {
        assert_eq!(
            clamp_to_work_area(
                WindowSize {
                    width: 2400.0,
                    height: 1400.0,
                },
                Some((1280.0, 720.0)),
            ),
            WindowSize {
                width: 1248.0,
                height: 656.0,
            }
        );
        assert_eq!(
            clamp_to_work_area(
                WindowSize {
                    width: 500.0,
                    height: 400.0,
                },
                Some((1920.0, 1080.0)),
            ),
            WindowSize {
                width: MIN_WIDTH,
                height: MIN_HEIGHT,
            }
        );
        assert_eq!(clamp_to_work_area(DEFAULT_SIZE, Some((1440.0, 875.0))), DEFAULT_SIZE);
        assert_eq!(
            clamp_to_work_area(
                WindowSize {
                    width: 500.0,
                    height: 400.0,
                },
                Some((700.0, 500.0)),
            ),
            WindowSize {
                width: MIN_WIDTH,
                height: MIN_HEIGHT,
            }
        );
        assert_eq!(
            clamp_to_work_area(
                WindowSize {
                    width: 2400.0,
                    height: 1400.0,
                },
                None,
            ),
            WindowSize {
                width: 2400.0,
                height: 1400.0,
            }
        );
    }

    #[test]
    fn only_the_exact_restore_frame_is_ignored() {
        let restored = WindowSize {
            width: 1306.0,
            height: 822.0,
        };
        assert!(matches_restore(Some(restored), restored));
        assert!(matches_restore(
            Some(restored),
            WindowSize {
                width: 1306.0,
                height: 821.0,
            }
        ));
        assert!(!matches_restore(
            Some(restored),
            WindowSize {
                width: 1200.0,
                height: 822.0,
            }
        ));
        assert!(!matches_restore(None, restored));
    }
}

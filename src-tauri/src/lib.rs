use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{RunEvent, Manager};

#[cfg(target_os = "windows")]
use winapi::um::winuser::{
    GetForegroundWindow, GetWindowRect, GetSystemMetrics,
    SM_CXSCREEN, SM_CYSCREEN,
    GetShellWindow, GetClassNameW,
    SetWindowDisplayAffinity
};
#[cfg(target_os = "windows")]
const WDA_EXCLUDEFROMCAPTURE: u32 = 0x00000011;

// Global handle to the Python child process
static PYTHON_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

fn get_backend_dir() -> PathBuf {
    let mut current = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for _ in 0..3 {
        let p = current.join("python-backend");
        if p.exists() && p.is_dir() {
            return p;
        }
        if let Some(parent) = current.parent() {
            current = parent.to_path_buf();
        } else {
            break;
        }
    }
    PathBuf::from("python-backend")
}

#[tauri::command]
fn open_file(path: String) {
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("cmd")
            .arg("/c")
            .arg("start")
            .arg("")
            .arg(&path)
            .spawn();
    }
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open")
            .arg(path)
            .spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("xdg-open")
            .arg(path)
            .spawn();
    }
}

#[tauri::command]
fn open_folder(path: String) {
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("explorer")
            .arg("/select,")
            .arg(path)
            .spawn();
    }
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open")
            .arg("-R")
            .arg(path)
            .spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("xdg-open")
            .arg(path)
            .spawn();
    }
}

fn spawn_python_backend(app_handle: &tauri::AppHandle) {
    let is_dev = cfg!(debug_assertions);

    if is_dev {
        println!("[tauri] Dev mode detected, starting manual python spawn...");
        let backend_dir = get_backend_dir();
        let python_exe = backend_dir.join("venv").join("Scripts").join("python.exe");
        let main_py = backend_dir.join("main.py");

        if backend_dir.exists() {
            println!("[tauri] Spawning: {:?} {:?}", python_exe, main_py);
            match Command::new(&python_exe)
                .arg(&main_py)
                .current_dir(&backend_dir)
                .spawn()
            {
                Ok(child) => {
                    println!("[tauri] Python Dev Backend started (PID {})", child.id());
                    *PYTHON_PROCESS.lock().unwrap() = Some(child);
                }
                Err(e) => {
                    eprintln!("[tauri] Dev backend failed to spawn: {}", e);
                }
            }
        } else {
            eprintln!("[tauri] Backend directory not found: {:?}", backend_dir);
        }
    } else {
        use tauri_plugin_shell::ShellExt;
        let sidecar_result = app_handle.shell().sidecar("file-intelligence-backend");
        if let Ok(sidecar) = sidecar_result {
            match sidecar.spawn() {
                Ok((_events, _child)) => {
                    println!("[tauri] Python Sidecar started");
                }
                Err(e) => {
                    eprintln!("[tauri] Sidecar spawn failed: {}", e);
                }
            }
        }
    }
}

#[tauri::command]
async fn set_expanded(window: tauri::Window, expanded: bool) -> Result<(), String> {
    if let Ok(Some(monitor)) = window.primary_monitor() {
        let scale = monitor.scale_factor();
        let size = monitor.size();
        let pos = monitor.position();

        let w = if expanded { 400.0 } else { 44.0 };
        let h = if expanded { 700.0 } else { 140.0 };

        let win_w_phys = (w * scale) as i32;
        let win_h_phys = (h * scale) as i32;

        let _ = window.set_size(tauri::PhysicalSize::new(win_w_phys, win_h_phys));
        let _ = window.set_position(tauri::PhysicalPosition::new(
            pos.x + size.width as i32 - win_w_phys,
            pos.y + (size.height as i32 - win_h_phys) / 2
        ));
    }
    Ok(())
}

fn kill_python_backend() {
    if let Ok(mut guard) = PYTHON_PROCESS.lock() {
        if let Some(ref mut child) = *guard {
            let pid = child.id();
            match child.kill() {
                Ok(_) => println!("[tauri] Python backend (PID {}) killed.", pid),
                Err(e) => eprintln!("[tauri] Failed to kill Python backend: {}", e),
            }
        }
        *guard = None;
    }
}

fn start_fullscreen_monitor(app_handle: tauri::AppHandle) {
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(std::time::Duration::from_millis(1000));

            #[cfg(target_os = "windows")]
            unsafe {
                let hwnd = GetForegroundWindow();
                if hwnd.is_null() { continue; }

                // Skip desktop/shell window
                let shell_hwnd = GetShellWindow();
                if hwnd == shell_hwnd { continue; }

                // Skip desktop background windows
                let mut class_name: Vec<u16> = vec![0u16; 256];
                GetClassNameW(hwnd, class_name.as_mut_ptr(), 256);
                let class_str = String::from_utf16_lossy(&class_name);
                let class_str = class_str.trim_matches('\0');
                if class_str == "WorkerW"
                    || class_str == "Progman"
                    || class_str == "Shell_TrayWnd" {
                    continue;
                }

                let mut rect = std::mem::zeroed();
                if GetWindowRect(hwnd, &mut rect) != 0 {
                    let screen_w = GetSystemMetrics(SM_CXSCREEN);
                    let screen_h = GetSystemMetrics(SM_CYSCREEN);

                    let width = rect.right - rect.left;
                    let height = rect.bottom - rect.top;

                    let is_fs = width >= screen_w && height >= screen_h;

                    let main_win = app_handle.get_webview_window("main");
                    if let Some(win) = main_win {
                        if is_fs {
                            let _ = win.hide();
                        } else {
                            let _ = win.show();
                        }
                    }
                }
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            spawn_python_backend(app.handle());
            start_fullscreen_monitor(app.handle().clone());

            let main_win = app.get_webview_window("main").unwrap();
            let _ = main_win.set_shadow(false);

            // Exclude window from screenshots and screen capture
            // Exclude window from screenshots and screen capture
#[cfg(target_os = "windows")]
{
    use raw_window_handle::HasWindowHandle;
    use raw_window_handle::RawWindowHandle;
    if let Ok(handle) = main_win.window_handle() {
        if let RawWindowHandle::Win32(win32_handle) = handle.as_raw() {
            unsafe {
                SetWindowDisplayAffinity(
                    win32_handle.hwnd.get() as _,
                    WDA_EXCLUDEFROMCAPTURE
                );
            }
        }
    }
}

            if let Ok(Some(monitor)) = main_win.primary_monitor() {
                let scale = monitor.scale_factor();
                let size = monitor.size();
                let pos = monitor.position();

                let win_w_phys = (44.0 * scale) as i32;
                let win_h_phys = (140.0 * scale) as i32;

                let _ = main_win.set_size(tauri::PhysicalSize::new(win_w_phys, win_h_phys));
                let _ = main_win.set_position(tauri::PhysicalPosition::new(
                    pos.x + size.width as i32 - win_w_phys,
                    pos.y + (size.height as i32 - win_h_phys) / 2
                ));
            }

            // Show only after correct position is set
            let _ = main_win.show();

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![open_folder, open_file, set_expanded])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                kill_python_backend();
            }
        });
}
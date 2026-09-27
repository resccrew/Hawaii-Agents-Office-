use std::sync::{Arc, Mutex};

use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the running backend sidecar so it can be killed on app exit.
///
/// Shared via `Arc` (not just Tauri-managed state) because it has to be
/// reachable from two independent exit paths: Tauri's own
/// `RunEvent::ExitRequested` (the normal Cmd+Q / window-close flow) *and*
/// a raw OS signal handler for SIGTERM/SIGINT. The two are not the same
/// thing — a signal (force-quit, `killall`, session logout, a process
/// supervisor stopping the app) bypasses Tauri's event loop entirely, so
/// relying on `ExitRequested` alone leaves the sidecar running and the
/// port held. Verified during Phase 0 packaging checks: `kill -TERM` on
/// the app's main process orphaned the sidecar, which is exactly the
/// "next launch can't bind :8010" failure the README already warns about.
type BackendProcess = Arc<Mutex<Option<CommandChild>>>;

fn kill_backend(state: &BackendProcess) {
  if let Some(child) = state.lock().unwrap().take() {
    // The PyInstaller `--onefile` sidecar bootloader forks a second,
    // untracked grandchild process on macOS that does the actual work
    // (extracts itself, then execs the real interpreter) — `child.kill()`
    // only reaches the bootloader's own PID, not that grandchild, so it
    // alone leaves the real server running and :8010 still bound
    // (verified during Phase 0 packaging checks). Kill the whole process
    // group instead of just the tracked child: `open`/LaunchServices makes
    // this app process its own group leader, and neither the bootloader
    // nor its fork()'d grandchild ever call setpgid, so both inherit our
    // group — confirmed via `ps -o pid,pgid`, all three share one PGID
    // equal to *our own* PID, not the child's. `kill(0, sig)` sends to
    // "every process in the caller's own group", which is what's needed
    // here (a negative *child* PID would be wrong — the child isn't a
    // group leader itself).
    #[cfg(unix)]
    unsafe {
      libc::kill(0, libc::SIGTERM);
    }
    let _ = child.kill();
  }
}

/// Reads the shared token the backend generates on first start
/// (~/.studio-ops/api-token — see backend/app/core/auth.py), so the webview
/// can attach it to every REST/WS call without that file ever needing to be
/// readable from renderer-side JS directly.
#[tauri::command]
fn get_api_token() -> Result<String, String> {
  let home = std::env::var("HOME").map_err(|_| "HOME is not set".to_string())?;
  let path = std::path::Path::new(&home).join(".studio-ops").join("api-token");
  std::fs::read_to_string(&path)
    .map(|s| s.trim().to_string())
    .map_err(|e| format!("failed to read {}: {e}", path.display()))
}

/// Best-effort probe: true if something is already listening on
/// 127.0.0.1:{port}. Binding is the only portable way to check this from
/// Rust's std alone (no extra crate) — a successful bind means the port was
/// free (and is immediately released again by dropping the listener).
fn port_in_use(port: u16) -> bool {
  std::net::TcpListener::bind(("127.0.0.1", port)).is_err()
}

/// Surfaces the "backend can't start, port already taken" failure mode
/// docs/review/backend.md flagged (D2) — previously the app just launched
/// with a permanently unreachable backend and no indication why. macOS-only
/// (`osascript`) since that's this app's only shipped target today; every
/// platform still gets the `log::error!` line either way.
fn warn_port_in_use(port: u16) {
  let msg = format!(
    "Studio Ops backend port {port} is already in use by another process \
     (perhaps another copy of this app, or a leftover process from a crash). \
     Close whatever is using port {port}, then relaunch Hawaii Agents Office."
  );
  log::error!("{msg}");
  #[cfg(target_os = "macos")]
  {
    let _ = std::process::Command::new("osascript")
      .args(["-e", &format!("display alert \"Hawaii Agents Office\" message \"{msg}\" as critical")])
      .status();
  }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .invoke_handler(tauri::generate_handler![get_api_token])
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      if port_in_use(8010) {
        warn_port_in_use(8010);
      }

      let sidecar_command = app.handle().shell().sidecar("studio-ops-backend").unwrap();
      let (mut rx, child) = sidecar_command.spawn().expect("Failed to spawn sidecar");

      let backend: BackendProcess = Arc::new(Mutex::new(Some(child)));
      app.manage(backend.clone());

      let signal_backend = backend.clone();
      ctrlc::set_handler(move || {
        kill_backend(&signal_backend);
        std::process::exit(0);
      })
      .expect("Failed to register SIGTERM/SIGINT handler");

      tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
          if let CommandEvent::Stdout(line) = event {
            println!("backend stdout: {}", String::from_utf8_lossy(&line));
          } else if let CommandEvent::Stderr(line) = event {
            println!("backend stderr: {}", String::from_utf8_lossy(&line));
          }
        }
      });

      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application")
    .run(|app_handle, event| {
      // Tauri doesn't take one single path out of the event loop: a menu
      // "Quit" (Cmd+Q) was observed going straight to `RunEvent::Exit`
      // (the non-cancellable "the loop is ending now" event) WITHOUT ever
      // emitting `ExitRequested` first — the sidecar kill wired only to
      // ExitRequested therefore never ran and the backend (and :8010)
      // outlived the app. Covering all three plausible exit signals —
      // Exit, ExitRequested (the cancellable variant, e.g. triggered
      // programmatically or by some window managers), and the last
      // window's CloseRequested (the titlebar/red-dot close, which on a
      // single-window app is effectively "quit" too) — means whichever
      // path macOS actually took still runs kill_backend. kill_backend
      // itself is idempotent (state.lock().unwrap().take() is a no-op
      // once the child is already gone), so covering more paths than
      // strictly necessary here is free, not a double-kill hazard.
      let should_kill = matches!(
        event,
        RunEvent::Exit
          | RunEvent::ExitRequested { .. }
          | RunEvent::WindowEvent { event: WindowEvent::CloseRequested { .. }, .. }
      );
      if should_kill {
        if let Some(state) = app_handle.try_state::<BackendProcess>() {
          kill_backend(&state);
        }
      }
    });
}

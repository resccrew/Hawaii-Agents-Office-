use std::sync::{Arc, Mutex};

use tauri::{Manager, RunEvent};
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
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
      if let RunEvent::ExitRequested { .. } = event {
        if let Some(state) = app_handle.try_state::<BackendProcess>() {
          kill_backend(&state);
        }
      }
    });
}

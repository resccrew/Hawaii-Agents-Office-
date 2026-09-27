use std::sync::{Arc, Mutex};

use serde::Deserialize;
use tauri::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, RunEvent, WindowEvent};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;
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

/// Tray menu item ids that aren't a per-agent entry (those use the agent's
/// own id, prefixed, so they never collide with a fixed id below).
const TRAY_OPEN_ID: &str = "tray-open";
const TRAY_QUIT_ID: &str = "tray-quit";
const TRAY_AGENT_PREFIX: &str = "tray-agent:";

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

/// Focuses (and un-minimizes) the main window — shared by the tray "Open"
/// item, clicking a waiting agent in the tray menu, and the global hotkey.
fn show_main_window(app: &AppHandle) {
  if let Some(window) = app.get_webview_window("main") {
    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
  }
}

/// One waiting agent as surfaced in the tray menu — kept minimal since the
/// frontend (which already tracks full agent state via roomStore) is the
/// source of truth; the tray is a read-only reflection of it, rebuilt
/// whenever the frontend calls `update_tray_status`.
#[derive(Deserialize)]
struct TrayAgentEntry {
  id: String,
  label: String,
}

/// Rebuilds the tray icon's tooltip and dynamic menu (waiting-agent list)
/// to match the counts/roster the frontend already computed from its own
/// `roomStore` state. Called from the frontend on every state change that
/// affects these numbers, not polled — the backend has no separate concept
/// of "which agents are waiting", the frontend's derived view is authoritative.
#[tauri::command]
fn update_tray_status(
  app: AppHandle,
  working: u32,
  waiting: u32,
  agents: Vec<TrayAgentEntry>,
) -> Result<(), String> {
  let tooltip = if waiting > 0 {
    format!("Hawaii Agents Office — {working} working, {waiting} waiting for you")
  } else {
    format!("Hawaii Agents Office — {working} working")
  };

  let open_item = MenuItem::with_id(&app, TRAY_OPEN_ID, "Open", true, None::<&str>)
    .map_err(|e| e.to_string())?;
  let mut items: Vec<Box<dyn tauri::menu::IsMenuItem<tauri::Wry>>> = vec![Box::new(open_item)];
  items.push(Box::new(PredefinedMenuItem::separator(&app).map_err(|e| e.to_string())?));

  if agents.is_empty() {
    let none_item = MenuItem::with_id(&app, "tray-none", "No agents waiting", false, None::<&str>)
      .map_err(|e| e.to_string())?;
    items.push(Box::new(none_item));
  } else {
    for agent in &agents {
      let id = format!("{TRAY_AGENT_PREFIX}{}", agent.id);
      let item = MenuItem::with_id(&app, id, &agent.label, true, None::<&str>)
        .map_err(|e| e.to_string())?;
      items.push(Box::new(item));
    }
  }

  items.push(Box::new(PredefinedMenuItem::separator(&app).map_err(|e| e.to_string())?));
  let quit_item = MenuItem::with_id(&app, TRAY_QUIT_ID, "Quit", true, None::<&str>)
    .map_err(|e| e.to_string())?;
  items.push(Box::new(quit_item));

  let refs: Vec<&dyn tauri::menu::IsMenuItem<tauri::Wry>> = items.iter().map(|i| i.as_ref()).collect();
  let menu = Menu::with_items(&app, &refs).map_err(|e| e.to_string())?;

  if let Some(tray) = app.tray_by_id("main-tray") {
    tray.set_menu(Some(menu)).map_err(|e| e.to_string())?;
    tray.set_tooltip(Some(&tooltip)).map_err(|e| e.to_string())?;
  }
  Ok(())
}

/// Sets (or clears, on 0) the macOS dock badge to the number of agents
/// waiting on a permission/response — the frontend recomputes this from
/// its own roomStore on every state_update and calls this whenever it changes.
#[tauri::command]
fn set_waiting_badge_count(app: AppHandle, count: i64) -> Result<(), String> {
  if let Some(window) = app.get_webview_window("main") {
    window
      .set_badge_count(if count > 0 { Some(count) } else { None })
      .map_err(|e| e.to_string())?;
  }
  Ok(())
}

/// Shows a native OS notification. Deliberately does not decide throttling
/// or "is this worth notifying about" — the frontend (desktopBridge.ts)
/// already owns that policy (it has the full agent history to reason about),
/// this command just renders whatever it was told to render. Focus check
/// still lives here since only the Rust side can reliably ask the OS
/// whether the window currently has focus.
#[tauri::command]
fn show_agent_notification(app: AppHandle, title: String, body: String) -> Result<(), String> {
  let focused = app
    .get_webview_window("main")
    .map(|w| w.is_focused().unwrap_or(false))
    .unwrap_or(false);
  if focused {
    return Ok(());
  }
  app
    .notification()
    .builder()
    .title(title)
    .body(body)
    .show()
    .map_err(|e| e.to_string())
}

/// Re-registers the global "bring the most-overdue waiting agent to the
/// front" shortcut. Unregisters whatever was registered before (a no-op the
/// first time) so Settings can change it live without a restart. Never
/// fails the app if the requested combo is already claimed by something
/// else on the OS — logs and leaves the previous shortcut (if any) in
/// place instead, per the "don't crash on a hotkey conflict" requirement.
#[tauri::command]
fn set_global_shortcut(app: AppHandle, shortcut: String, previous: Option<String>) -> Result<(), String> {
  let gs = app.global_shortcut();

  if let Some(prev) = previous.as_deref() {
    if let Ok(prev_shortcut) = prev.parse::<Shortcut>() {
      let _ = gs.unregister(prev_shortcut);
    }
  }

  let parsed: Shortcut = shortcut
    .parse()
    .map_err(|e| format!("'{shortcut}' is not a valid shortcut: {e}"))?;

  match gs.register(parsed) {
    Ok(()) => Ok(()),
    Err(e) => {
      log::warn!("could not register global shortcut '{shortcut}' (likely already in use by another app): {e}");
      Err(format!("could not register '{shortcut}' — it may already be in use by another app"))
    }
  }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_notification::init())
    .plugin(
      tauri_plugin_global_shortcut::Builder::new()
        .with_handler(|app, _shortcut, event| {
          // Any registered shortcut currently means exactly one thing (the
          // "show me who's waiting" hotkey) — no per-shortcut dispatch
          // needed yet. Only react to the press, not the release, so a
          // held key doesn't fire repeatedly.
          if event.state() == ShortcutState::Pressed {
            show_main_window(app);
            let _ = app.emit("hotkey-open-waiting", ());
          }
        })
        .build(),
    )
    .invoke_handler(tauri::generate_handler![
      get_api_token,
      update_tray_status,
      set_waiting_badge_count,
      show_agent_notification,
      set_global_shortcut,
    ])
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // Default hotkey, mirroring the frontend's uiSettingsStore default —
      // registered once at startup; Settings changes it later via
      // `set_global_shortcut`. A conflict here must not abort startup
      // (the rest of the app is fully usable without the hotkey).
      if let Ok(default_shortcut) = "CmdOrCtrl+Shift+H".parse::<Shortcut>() {
        if let Err(e) = app.global_shortcut().register(default_shortcut) {
          log::warn!("default global shortcut CmdOrCtrl+Shift+H unavailable (already in use?): {e}");
        }
      }

      let open_item = MenuItem::with_id(app, TRAY_OPEN_ID, "Open", true, None::<&str>)?;
      let none_item = MenuItem::with_id(app, "tray-none", "No agents waiting", false, None::<&str>)?;
      let quit_item = MenuItem::with_id(app, TRAY_QUIT_ID, "Quit", true, None::<&str>)?;
      let initial_menu = Menu::with_items(
        app,
        &[
          &open_item,
          &PredefinedMenuItem::separator(app)?,
          &none_item,
          &PredefinedMenuItem::separator(app)?,
          &quit_item,
        ],
      )?;

      let backend_for_tray: BackendProcess = Arc::new(Mutex::new(None));
      let tray_backend_ref = backend_for_tray.clone();
      TrayIconBuilder::with_id("main-tray")
        .menu(&initial_menu)
        .tooltip("Hawaii Agents Office")
        .icon(app.default_window_icon().unwrap().clone())
        .on_menu_event(move |app, event: MenuEvent| {
          let id = event.id().as_ref();
          if id == TRAY_OPEN_ID {
            show_main_window(app);
          } else if id == TRAY_QUIT_ID {
            kill_backend(&tray_backend_ref);
            app.exit(0);
          } else if let Some(agent_id) = id.strip_prefix(TRAY_AGENT_PREFIX) {
            show_main_window(app);
            let _ = app.emit("tray-open-agent", agent_id.to_string());
          }
        })
        .build(app)?;

      if port_in_use(8010) {
        warn_port_in_use(8010);
      }

      let sidecar_command = app.handle().shell().sidecar("studio-ops-backend").unwrap();
      let (mut rx, child) = sidecar_command.spawn().expect("Failed to spawn sidecar");

      *backend_for_tray.lock().unwrap() = Some(child);
      app.manage(backend_for_tray.clone());

      let signal_backend = backend_for_tray.clone();
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
      // strictly necessary here is free, not a double-kill hazard. The
      // tray's own "Quit" item bypasses this closure entirely (it calls
      // `app.exit(0)` directly), which is why it kills the backend itself
      // too, inline, right before exiting.
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

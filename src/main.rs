mod device;
mod errors;
mod event;
mod keymap;
mod state;

use device::DeviceManager;
use errors::VilandError;
use state::State;
use std::sync::atomic::{AtomicBool, Ordering};
use tracing::{error, info, warn};
use tracing_appender::rolling::{RollingFileAppender, Rotation};
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

static SHOULD_EXIT: AtomicBool = AtomicBool::new(false);

fn setup_logging() {
    let log_dir = std::env::var("XDG_DATA_HOME")
        .map(|p| std::path::PathBuf::from(p).join("viland").join("logs"))
        .unwrap_or_else(|_| {
            std::env::var("HOME")
                .map(|p| std::path::PathBuf::from(p).join(".local").join("share").join("viland").join("logs"))
                .unwrap_or_else(|_| std::path::PathBuf::from("/tmp/viland/logs"))
        });

    std::fs::create_dir_all(&log_dir).ok();

    let file_appender = RollingFileAppender::new(Rotation::DAILY, &log_dir, "viland.log");
    let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);

    tracing_subscriber::registry()
        .with(EnvFilter::new("info"))
        .with(fmt::layer().with_writer(non_blocking).with_ansi(false))
        .with(fmt::layer().with_writer(std::io::stdout))
        .init();

    Box::leak(Box::new(_guard));
}

unsafe fn setup_signal_handlers() {
    use std::mem::zeroed;

    let mut sigint_action: libc::sigaction = zeroed();
    sigint_action.sa_sigaction = signal_handler as *const () as usize;
    libc::sigaction(libc::SIGINT, &sigint_action, std::ptr::null_mut());

    let mut sigterm_action: libc::sigaction = zeroed();
    sigterm_action.sa_sigaction = signal_handler as *const () as usize;
    libc::sigaction(libc::SIGTERM, &sigterm_action, std::ptr::null_mut());
}

extern "C" fn signal_handler(_signum: i32) {
    SHOULD_EXIT.store(true, Ordering::SeqCst);
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    setup_logging();

    info!("Viland starting...");

    unsafe {
        setup_signal_handlers();
    }

    let mut state = State::new();
    let mut device_manager = DeviceManager::new()?;

    if let Err(e) = device_manager.init() {
        error!("Failed to initialize devices: {}", e);
        return Err(e.into());
    }

    info!("Viland initialized, entering main loop");

    loop {
        if SHOULD_EXIT.load(Ordering::SeqCst) {
            info!("Received signal, shutting down gracefully");
            let _ = std::process::Command::new("notify-send")
                .args(["-t", "1500", "Viland", "Shutting down..."])
                .spawn();
            state.release_all_virtual(&mut device_manager);
            device_manager.ungrab_all();
            return Ok(());
        }

        match device_manager.poll_events() {
            Ok(events) => {
                for ev in events {
                    if let Err(e) = state.process_event(ev, &mut device_manager) {
                        warn!("Error processing event: {}", e);
                    }

                    if state.should_exit() {
                        info!("Emergency exit triggered");
                        let _ = std::process::Command::new("notify-send")
                            .args(["-t", "1500", "Viland", "Emergency Exit"])
                            .spawn();
                        state.release_all_virtual(&mut device_manager);
                        device_manager.ungrab_all();
                        return Ok(());
                    }
                }
            }
            Err(e) => {
                error!("Poll error: {}", e);
            }
        }
    }
}
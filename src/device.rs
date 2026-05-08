use std::collections::HashMap;
use std::fs;
use std::os::unix::io::{AsRawFd, RawFd};
use std::path::PathBuf;

use evdev::*;
use evdev::uinput::{VirtualDevice};

use crate::event::{Event, KeyState};
use crate::errors::VilandError;
use tracing::{info, warn};

const OUR_VENDOR: u16 = 0x1234;
const OUR_PRODUCT: u16 = 0x5678;

pub struct DeviceManager {
    fd_to_id: HashMap<RawFd, u32>,
    devices: HashMap<RawFd, Device>,
    uinput: Option<VirtualDevice>,
    epoll_fd: RawFd,
    inotify_fd: RawFd,
    grabbed_fds: Vec<RawFd>,
}

impl DeviceManager {
    pub fn new() -> Result<Self, VilandError> {
        unsafe {
            let epoll_fd = libc::epoll_create1(0);
            if epoll_fd < 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }

            let inotify_fd = libc::inotify_init1(libc::O_NONBLOCK);
            if inotify_fd < 0 {
                let _ = libc::close(epoll_fd);
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }

            Ok(Self {
                fd_to_id: HashMap::new(),
                devices: HashMap::new(),
                uinput: None,
                epoll_fd,
                inotify_fd,
                grabbed_fds: Vec::new(),
            })
        }
    }

    pub fn init(&mut self) -> Result<(), VilandError> {
        let input_dir = PathBuf::from("/dev/input");
        let entries = fs::read_dir(&input_dir)?;

        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(name) = path.file_name() {
                let name_str = name.to_string_lossy();
                if name_str.starts_with("event") {
                    self.try_add_device(&path);
                }
            }
        }

        if self.devices.is_empty() {
            return Err(VilandError::DeviceNotFound);
        }

        self.setup_uinput()?;
        self.setup_inotify()?;

        Ok(())
    }

    fn try_add_device(&mut self, path: &PathBuf) {
        match Device::open(path) {
            Ok(mut device) => {
                if self.is_keyboard(&device) {
                    if let Err(e) = device.set_nonblocking(true) {
                        warn!("Failed to set non-blocking on {}: {}", path.display(), e);
                        return;
                    }
                    if let Err(e) = device.grab() {
                        warn!("Failed to grab device {}: {}", path.display(), e);
                        return;
                    }

                    let fd = device.as_raw_fd();
                    let id = self.get_device_id(&device);

                    if let Err(e) = self.add_to_epoll(fd) {
                        warn!("Failed to add device {} to epoll: {}", path.display(), e);
                        let _ = device.ungrab();
                        return;
                    }

                    info!("Grabbed keyboard: {} (fd={}, id={})", 
                        device.name().unwrap_or("unknown"), fd, id);
                    
                    self.fd_to_id.insert(fd, id);
                    self.devices.insert(fd, device);
                    self.grabbed_fds.push(fd);
                }
            }
            Err(e) => {
                if e.kind() != std::io::ErrorKind::PermissionDenied {
                    warn!("Failed to open device {}: {}", path.display(), e);
                }
            }
        }
    }

    fn setup_uinput(&mut self) -> Result<(), VilandError> {
        let mut keys = AttributeSet::<KeyCode>::new();
        // Add all standard keys
        for i in 0..=575 {
            keys.insert(KeyCode(i));
        }

        let uinput = VirtualDevice::builder()?
            .name("Viland Virtual Keyboard")
            .with_keys(&keys)?
            .input_id(InputId::new(BusType::BUS_USB, OUR_VENDOR, OUR_PRODUCT, 1))
            .build()?;

        self.uinput = Some(uinput);
        info!("uinput device created");
        Ok(())
    }

    fn setup_inotify(&self) -> Result<(), VilandError> {
        let c_path = std::ffi::CString::new("/dev/input").unwrap();
        unsafe {
            let mask = libc::IN_CREATE | libc::IN_DELETE;
            let wd = libc::inotify_add_watch(self.inotify_fd, c_path.as_ptr(), mask);
            if wd < 0 {
                warn!("Failed to add inotify watch: {}", std::io::Error::last_os_error());
            }

            let mut event = libc::epoll_event {
                u64: self.inotify_fd as u64,
                events: (libc::EPOLLIN | libc::EPOLLHUP | libc::EPOLLERR) as u32,
            };
            if libc::epoll_ctl(self.epoll_fd, libc::EPOLL_CTL_ADD, self.inotify_fd, &mut event) != 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

    fn is_keyboard(&self, device: &Device) -> bool {
        // Skip our own virtual device
        if device.input_id().vendor() == OUR_VENDOR && device.input_id().product() == OUR_PRODUCT {
            return false;
        }

        if let Some(keys) = device.supported_keys() {
            let mut has_a = false;
            let mut has_z = false;
            let mut has_enter = false;
            let mut has_space = false;
            let mut alpha_count = 0;

            for key in keys.iter() {
                let code = key.0;
                if code == 30 { has_a = true; }
                if code == 44 { has_z = true; }
                if code == 28 { has_enter = true; }
                if code == 57 { has_space = true; }
                if (30..=55).contains(&code) {
                    alpha_count += 1;
                }
            }

            has_a && has_z && has_enter && has_space && alpha_count >= 10
        } else {
            false
        }
    }

    fn get_device_id(&self, device: &Device) -> u32 {
        let id = device.input_id();
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        // BusType doesn't implement Hash, so we hash its raw value
        std::hash::Hash::hash(&id.bus_type().0, &mut hasher);
        std::hash::Hash::hash(&id.vendor(), &mut hasher);
        std::hash::Hash::hash(&id.product(), &mut hasher);
        std::hash::Hash::hash(&id.version(), &mut hasher);
        (std::hash::Hasher::finish(&hasher) & 0xFFFFFFFF) as u32
    }

    fn add_to_epoll(&self, fd: RawFd) -> Result<(), VilandError> {
        let mut event = libc::epoll_event {
            u64: fd as u64,
            events: (libc::EPOLLIN | libc::EPOLLHUP | libc::EPOLLERR) as u32,
        };
        unsafe {
            if libc::epoll_ctl(self.epoll_fd, libc::EPOLL_CTL_ADD, fd, &mut event) != 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

    fn remove_from_epoll(&self, fd: RawFd) -> Result<(), VilandError> {
        unsafe {
            if libc::epoll_ctl(self.epoll_fd, libc::EPOLL_CTL_DEL, fd, std::ptr::null_mut()) != 0 {
                return Err(VilandError::Io(std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

    pub fn poll_events(&mut self) -> Result<Vec<Event>, VilandError> {
        let mut events = Vec::new();
        let mut ready_list = [libc::epoll_event { u64: 0, events: 0 }; 64];

        let n = unsafe {
            libc::epoll_wait(
                self.epoll_fd,
                ready_list.as_mut_ptr(),
                64,
                100, // timeout 100ms
            )
        };

        if n < 0 {
            let err = std::io::Error::last_os_error();
            if err.kind() == std::io::ErrorKind::Interrupted {
                return Ok(events);
            }
            return Err(VilandError::Io(err));
        }

        let mut fds_to_remove = Vec::new();

        for item in ready_list.iter().take(n as usize) {
            let fd = item.u64 as RawFd;
            let revents = item.events as i32;

            if fd == self.inotify_fd {
                self.handle_inotify();
                continue;
            }

            if revents & (libc::EPOLLHUP | libc::EPOLLERR) != 0 {
                info!("Device fd {} disconnected", fd);
                fds_to_remove.push(fd);
                continue;
            }

            if let Some(device) = self.devices.get_mut(&fd) {
                match device.fetch_events() {
                    Ok(batch) => {
                        let device_id = self.fd_to_id.get(&fd).copied().unwrap_or(0);
                        for ev in batch {
                            if let EventSummary::Key(_, key, value) = ev.destructure() {
                                if let Some(state) = KeyState::from(value as u32) {
                                    let timestamp = ev.timestamp()
                                        .duration_since(std::time::UNIX_EPOCH)
                                        .unwrap_or_default()
                                        .as_millis() as u64;
                                    events.push(Event::new(
                                        device_id,
                                        key.0,
                                        state,
                                        timestamp,
                                    ));
                                }
                            }
                        }
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                    Err(e) => {
                        warn!("Error fetching events from device {}: {}", fd, e);
                        fds_to_remove.push(fd);
                    }
                }
            }
        }

        for fd in fds_to_remove {
            self.remove_device(fd);
        }

        Ok(events)
    }

    fn remove_device(&mut self, fd: RawFd) {
        if let Some(mut device) = self.devices.remove(&fd) {
            let _ = device.ungrab();
            let _ = self.remove_from_epoll(fd);
            self.fd_to_id.remove(&fd);
            if let Some(pos) = self.grabbed_fds.iter().position(|&x| x == fd) {
                self.grabbed_fds.remove(pos);
            }
        }
    }

    fn handle_inotify(&mut self) {
        let mut buffer = [0u8; 1024];
        let size = unsafe { libc::read(self.inotify_fd, buffer.as_mut_ptr() as *mut _, 1024) };
        if size <= 0 {
            return;
        }

        let mut offset = 0;
        while offset < size as usize {
            let event = unsafe { &*(buffer.as_ptr().add(offset) as *const libc::inotify_event) };
            if event.len > 0 {
                let name_ptr = unsafe { buffer.as_ptr().add(offset + std::mem::size_of::<libc::inotify_event>()) };
                let name_cstr = unsafe { std::ffi::CStr::from_ptr(name_ptr as *const libc::c_char) };
                if let Ok(name_str) = name_cstr.to_str() {
                    if name_str.starts_with("event") {
                        let path = PathBuf::from("/dev/input").join(name_str);
                        if event.mask & libc::IN_CREATE != 0 {
                            info!("Inotify: New device detected: {}", path.display());
                            self.try_add_device(&path);
                        } else if event.mask & libc::IN_DELETE != 0 {
                            info!("Inotify: Device removed: {}", name_str);
                        }
                    }
                }
            }
            offset += (std::mem::size_of::<libc::inotify_event>() + event.len as usize) as usize;
        }
    }

    pub fn emit_key(&mut self, key_code: u16, state: KeyState) -> Result<(), VilandError> {
        if let Some(ref mut uinput) = self.uinput {
            let val = match state {
                KeyState::Press => 1,
                KeyState::Release => 0,
                KeyState::Repeat => 2,
            };
            let ev = InputEvent::new(EventType::KEY.0, key_code, val);
            uinput.emit(&[ev])?;
        }
        Ok(())
    }

    pub fn emit_key_press(&mut self, key: u16) -> Result<(), VilandError> {
        self.emit_key(key, KeyState::Press)
    }

    pub fn emit_key_release(&mut self, key: u16) -> Result<(), VilandError> {
        self.emit_key(key, KeyState::Release)
    }

    pub fn release_all_keys(&mut self, virtual_pressed: &std::collections::HashSet<u16>) {
        if let Some(ref mut uinput) = self.uinput {
            let mut events = Vec::new();
            for &key_code in virtual_pressed {
                events.push(InputEvent::new(EventType::KEY.0, key_code, 0));
            }
            if !events.is_empty() {
                let _ = uinput.emit(&events);
            }
        }
    }

    pub fn ungrab_all(&mut self) {
        let fds: Vec<RawFd> = self.grabbed_fds.drain(..).collect();
        for fd in fds {
            if let Some(mut device) = self.devices.remove(&fd) {
                let _ = device.ungrab();
                let _ = self.remove_from_epoll(fd);
            }
        }
        self.fd_to_id.clear();
    }
}

impl Drop for DeviceManager {
    fn drop(&mut self) {
        self.ungrab_all();
        unsafe {
            if self.inotify_fd >= 0 { libc::close(self.inotify_fd); }
            if self.epoll_fd >= 0 { libc::close(self.epoll_fd); }
        }
    }
}
